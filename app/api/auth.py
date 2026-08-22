"""
Authentication API endpoints.
"""
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
import asyncio
import time
import logging

from app.database import get_db, get_db_read
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.core.security import (
    AuthenticatedUser,
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_user_for_refresh,
    is_freeze_exempt_identity,
    is_pengawas_identity,
    warm_authenticated_user_cache,
)
from app.config import settings
from app.core.cache import is_freeze_mode_enabled
from app.core.client_ip import get_client_ip
from app.core.rate_limiter import RateLimiters, check_rate_limit
from app.core.account_lockout import MAX_ATTEMPTS
from app.core.roles import is_admin_scope_role, is_teacher_scope_role

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

_MAINTENANCE_MODE_CACHE = {
    "value": False,
    "expires_at_monotonic": 0.0,
}
_LOCAL_LOGIN_RATE_LIMIT = 120
_LOCAL_LOGIN_RATE_WINDOW_SECONDS = 60.0
_LOCAL_LOGIN_LOCKOUT_WINDOW_SECONDS = 15 * 60.0
_local_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_local_login_failures: dict[str, deque[float]] = defaultdict(deque)
_local_login_lockouts: dict[str, float] = {}


def _redact_token(token: str | None) -> str:
    value = str(token or "").strip()
    if not value:
        return "not-set"
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def _prune_timestamps(buffer: deque[float], window_seconds: float, now_ts: float) -> None:
    cutoff = now_ts - window_seconds
    while buffer and buffer[0] <= cutoff:
        buffer.popleft()


def _check_local_login_rate_limit(identifier: str) -> tuple[bool, int]:
    now_ts = time.monotonic()
    attempts = _local_login_attempts[identifier]
    _prune_timestamps(attempts, _LOCAL_LOGIN_RATE_WINDOW_SECONDS, now_ts)
    if len(attempts) >= _LOCAL_LOGIN_RATE_LIMIT:
        return False, 0
    attempts.append(now_ts)
    return True, max(0, _LOCAL_LOGIN_RATE_LIMIT - len(attempts))


def _local_lockout_key(username: str, client_ip: str) -> str:
    return f"{username.strip().lower()}:{client_ip}"


def _get_local_lockout_remaining_minutes(lockout_key: str) -> int:
    expires_at = _local_login_lockouts.get(lockout_key)
    if not expires_at:
        return 0
    remaining_seconds = expires_at - time.monotonic()
    if remaining_seconds <= 0:
        _local_login_lockouts.pop(lockout_key, None)
        _local_login_failures.pop(lockout_key, None)
        return 0
    return max(1, int((remaining_seconds + 59) // 60))


def _record_local_login_failure(lockout_key: str) -> tuple[int, str | None]:
    now_ts = time.monotonic()
    failures = _local_login_failures[lockout_key]
    _prune_timestamps(failures, _LOCAL_LOGIN_LOCKOUT_WINDOW_SECONDS, now_ts)
    failures.append(now_ts)
    attempts = len(failures)

    warning = None
    if attempts >= MAX_ATTEMPTS:
        _local_login_lockouts[lockout_key] = now_ts + _LOCAL_LOGIN_LOCKOUT_WINDOW_SECONDS
        warning = "Terlalu banyak percobaan gagal. Akun dikunci sementara."
    elif attempts >= max(1, MAX_ATTEMPTS - 1):
        warning = f"Sisa {max(MAX_ATTEMPTS - attempts, 0)} percobaan sebelum akun dikunci sementara."

    return attempts, warning


def _clear_local_login_failure_state(lockout_key: str) -> None:
    _local_login_failures.pop(lockout_key, None)
    _local_login_lockouts.pop(lockout_key, None)


@dataclass(frozen=True)
class LoginUserSnapshot:
    id: int
    username: str
    full_name: str
    role: str
    student_class: str | None
    is_active: bool
    created_at: datetime
    last_login: datetime | None
    profile_picture: str | None
    job_title: str | None
    password_hash: str

    @property
    def is_admin(self) -> bool:
        return is_admin_scope_role(self.role)

    def to_authenticated_user(self) -> "AuthenticatedUser":
        from app.core.security import AuthenticatedUser

        return AuthenticatedUser(
            id=self.id,
            username=self.username,
            full_name=self.full_name,
            role=self.role,
            student_class=self.student_class,
            job_title=self.job_title,
            is_active=self.is_active,
            profile_picture=self.profile_picture,
            last_login=self.last_login,
        )

    def to_user_response(self) -> UserResponse:
        return UserResponse(
            id=self.id,
            username=self.username,
            full_name=self.full_name,
            role=self.role,
            student_class=self.student_class,
            is_active=self.is_active,
            created_at=self.created_at,
            last_login=self.last_login,
            profile_picture=self.profile_picture,
            job_title=self.job_title,
        )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user.

    - **username**: Unique username (3-100 characters)
    - **password**: Password (min 6 characters)
    - **full_name**: Full name
    - **role**: User role (student, teacher, admin)
    """
    # Check if username already exists
    existing_user_query = select(User).where(
        func.lower(User.username) == (user_data.username or "").strip().lower()
    )
    existing_user = (await db.execute(existing_user_query)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username sudah terdaftar")

    # Security: public self-registration is restricted to student accounts only.
    requested_role = (user_data.role or "student").strip().lower()
    if requested_role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pendaftaran mandiri hanya untuk akun siswa."
        )

    # ✅ SECURITY FIX #3: Strong password validation
    from app.core.sanitization import validate_password_strength, sanitize_html

    try:
        validate_password_strength(user_data.password)
    except HTTPException as e:
        raise e

    # ✅ SECURITY FIX #1: Sanitize user inputs to prevent XSS
    safe_full_name = sanitize_html(user_data.full_name)
    safe_username = sanitize_html(user_data.username)

    # Create new user
    user = User(
        username=safe_username,
        # email=user_data.email,  # REMOVED: Email no longer used
        password_hash=get_password_hash(user_data.password),
        full_name=safe_full_name,
        role="student",
        created_at=datetime.now(timezone.utc)
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


async def _load_user_response(db: AsyncSession, user_id: int) -> UserResponse:
    """Load a full user profile for response contracts that require DB fields."""
    user_result = await db.execute(select(User).where(User.id == user_id))
    db_user = user_result.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Pengguna tidak ditemukan",
        )
    return UserResponse.model_validate(db_user)


async def _enforce_student_mobile_signature(request: Request) -> None:
    """
    Enforce app signature headers for student mobile login.
    Preserves admin bypass controls:
    - token_validation_bypass
    - allow_browser_testing (developer mode)
    """
    from app.utils.apk_validation import APKTokenValidator
    from app.core.cache import is_developer_mode_enabled, get_allowed_signatures

    # Keep existing admin-controlled bypass behavior
    if await APKTokenValidator.is_bypass_enabled():
        return
    if await is_developer_mode_enabled():
        return

    allowed_signatures = await get_allowed_signatures()
    if not allowed_signatures or all(not s.strip() for s in allowed_signatures):
        raise HTTPException(
            status_code=403,
            detail="Sistem APK belum dikonfigurasi. Hubungi admin untuk mengatur App Signatures."
        )

    app_signature = request.headers.get("X-App-Signature", "")
    app_timestamp = request.headers.get("X-App-Timestamp", "")

    if not app_signature or not app_timestamp:
        raise HTTPException(
            status_code=403,
            detail="Security Headers Missing. Update aplikasi ujian Anda."
        )

    normalized_sig = app_signature.replace(":", "").lower().strip()
    is_valid_sig = any(
        s and s.strip().lower() == normalized_sig for s in allowed_signatures
    )
    if not is_valid_sig:
        raise HTTPException(
            status_code=403,
            detail="Invalid App Signature. Unofficial app detected."
        )

    try:
        server_ts = int(time.time())
        client_ts = int(app_timestamp)
        if abs(server_ts - client_ts) > 3600:
            raise HTTPException(
                status_code=403,
                detail="Request Expired (Check Device Time)"
            )
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Invalid security timestamp"
        )


async def _is_maintenance_mode() -> bool:
    """Read maintenance mode with a short local cache to cut login DB hot-path reads."""
    now_mono = time.monotonic()
    if now_mono < float(_MAINTENANCE_MODE_CACHE["expires_at_monotonic"]):
        return bool(_MAINTENANCE_MODE_CACHE["value"])

    from app.database import async_session_read
    from app.models.system_settings import SystemSettings
    try:
        async with async_session_read() as db:
            result = await db.execute(select(SystemSettings.maintenance_mode))
            value = bool(result.scalar_one_or_none() or False)
    except Exception as exc:
        # Keep login path resilient when settings DB read is temporarily degraded.
        logger.warning("Failed reading maintenance mode setting: %s", exc)
        value = bool(_MAINTENANCE_MODE_CACHE["value"])

    _MAINTENANCE_MODE_CACHE["value"] = value
    _MAINTENANCE_MODE_CACHE["expires_at_monotonic"] = now_mono + 5.0
    return value


async def _persist_login_side_effects(user_id: int, username: str, role: str) -> None:
    """
    Persist non-critical login side-effects out-of-band.
    Keeps signin response path focused on auth latency under burst load.
    """
    try:
        from app.database import async_session_write
        from app.models.activity_log import UserActivityLog

        async with async_session_write() as db_bg:
            await db_bg.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_login=datetime.now(timezone.utc))
            )

            db_bg.add(
                UserActivityLog(
                    user_id=user_id,
                    event_type="login",
                    event_data={"username": username, "role": role},
                )
            )
            await db_bg.commit()
    except Exception as exc:
        logger.warning("Deferred login side-effects failed for user_id=%s: %s", user_id, exc)

@router.post("/login", response_model=Token)
@router.post("/signin", response_model=Token)
async def login(login_data: UserLogin, request: Request, db: AsyncSession = Depends(get_db_read)):
    """
    Login and get access token.

    - **username**: Username
    - **password**: Password
    """
    # Resolve real client IP behind reverse proxies (Nginx/Cloudflare)
    client_ip = get_client_ip(request)
    username_key = (login_data.username or "").strip().lower()
    login_rate_identifier = f"{username_key}:{client_ip}"
    local_lockout_key = _local_lockout_key(login_data.username, client_ip)

    is_allowed_local, remaining_local = _check_local_login_rate_limit(login_rate_identifier)
    if not is_allowed_local:
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak percobaan login untuk akun ini. Tunggu 1 menit.",
            headers={"Retry-After": "60", "X-RateLimit-Remaining": str(remaining_local)}
        )

    local_lockout_remaining = _get_local_lockout_remaining_minutes(local_lockout_key)
    if local_lockout_remaining > 0:
        raise HTTPException(
            status_code=423,
            detail=f"🔒 Akun terkunci. Coba lagi dalam {local_lockout_remaining} menit.",
            headers={"X-Lockout-Remaining": str(local_lockout_remaining)}
        )

    # Redis-backed limiter remains primary; local limiter above prevents fail-open.
    try:
        is_allowed, remaining = await check_rate_limit(
            RateLimiters.LOGIN_ATTEMPT,
            login_rate_identifier
        )
        if not is_allowed:
            raise HTTPException(
                status_code=429,
                detail="Terlalu banyak percobaan login untuk akun ini. Tunggu 1 menit.",
                headers={"Retry-After": "60", "X-RateLimit-Remaining": str(remaining)}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Primary rate limiter failed, local fallback remains active: %s", e)

    # ✅ Account Lockout Check
    from app.core.account_lockout import get_lockout
    lockout = get_lockout()

    try:
        is_locked, remaining_minutes = await lockout.is_locked(login_data.username)
        if is_locked:
            # Send Telegram lockout notification (fire and forget)
            if settings.telegram_alerting_active:
                try:
                    from app.utils.telegram_alerts import send_lockout_alert
                    # Use ensure_future to properly schedule the coroutine
                    asyncio.ensure_future(send_lockout_alert(login_data.username, client_ip))
                    logger.info("Scheduled Telegram lockout notification for %s", login_data.username)
                except Exception as e:
                    # Don't fail login check if notification fails
                    logger.error("Failed to schedule lockout Telegram alert: %s", e, exc_info=True)

            raise HTTPException(
                status_code=423,  # Locked
                detail=f"🔒 Akun terkunci. Coba lagi dalam {remaining_minutes} menit.",
                headers={"X-Lockout-Remaining": str(remaining_minutes)}
            )

        # ✅ Check if CAPTCHA required
        needs_captcha = await lockout.needs_captcha(login_data.username)
        captcha_answer = login_data.captcha_answer

        if needs_captcha and not captcha_answer:
            # Generate CAPTCHA challenge
            from app.core.captcha import get_captcha
            captcha = get_captcha()
            challenge_id, question, _ = await captcha.generate(login_data.username)
            raise HTTPException(
                status_code=428,  # Precondition Required
                detail={
                    "type": "captcha_required",
                    "message": "CAPTCHA diperlukan setelah beberapa percobaan gagal",
                    "challenge_id": challenge_id,
                    "question": question
                }
            )

        # Verify CAPTCHA if provided
        if needs_captcha and captcha_answer:
            from app.core.captcha import get_captcha
            captcha = get_captcha()
            challenge_id = login_data.captcha_id or ''
            is_valid = await captcha.verify(challenge_id, captcha_answer, delete_after_verify=False)

            if not is_valid:
                # ✅ Record failed attempt (CAPTCHA wrong counts as failure)
                attempts, _, _ = await lockout.record_failure(login_data.username, client_ip)

                # ✅ Generate NEW CAPTCHA for next attempt
                new_challenge_id, new_question, _ = await captcha.generate(login_data.username)
                # Delete old challenge
                if challenge_id:
                    from app.core.redis_pubsub import get_redis
                    redis = await get_redis()
                    await redis.delete(f"captcha:{challenge_id}")

                raise HTTPException(
                    status_code=428,  # Return 428 with new CAPTCHA
                    detail={
                        "type": "captcha_wrong",
                        "message": f"Jawaban CAPTCHA salah. Percobaan ke-{attempts}/{MAX_ATTEMPTS}",
                        "challenge_id": new_challenge_id,
                        "question": new_question,
                        "attempts": attempts
                    }
                )
            else:
                # ✅ CAPTCHA correct - delete it
                if challenge_id:
                    from app.core.redis_pubsub import get_redis
                    redis = await get_redis()
                    await redis.delete(f"captcha:{challenge_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Primary lockout/captcha backend failed, local fallback remains active: %s", e)
        needs_captcha = False


    # Load only the columns needed for authentication, then close the read
    # transaction before bcrypt/Redis work so burst logins do not sit idle in
    # transaction while CPU-bound password verification runs.
    result = await db.execute(
        select(
            User.id,
            User.username,
            User.full_name,
            User.role,
            User.student_class,
            User.is_active,
            User.created_at,
            User.last_login,
            User.profile_picture,
            User.job_title,
            User.password_hash,
        ).where(func.lower(User.username) == (login_data.username or "").strip().lower())
    )
    row = result.mappings().one_or_none()
    await db.commit()
    user = LoginUserSnapshot(**row) if row else None

    # ✅ SECURITY LOGGING
    from app.core.security_logging import log_login_failed, log_login_success

    password_ok = False
    if user:
        # bcrypt verification is CPU-bound; run in threadpool to avoid blocking event loop
        password_ok = await run_in_threadpool(verify_password, login_data.password, user.password_hash)

    if not user or not password_ok:
        # Record failed attempt
        local_attempts, local_warning = _record_local_login_failure(local_lockout_key)
        attempts = local_attempts
        captcha_needed = False
        warning = local_warning
        try:
            attempts_remote, captcha_needed, warning_remote = await lockout.record_failure(
                login_data.username,
                client_ip,
            )
            attempts = max(local_attempts, attempts_remote)
            warning = warning_remote or warning
        except Exception as exc:
            logger.warning("Failed to record remote lockout failure for %s: %s", login_data.username, exc)

        # Log failed login attempt
        log_login_failed(login_data.username, client_ip, "invalid_credentials")

        # Include warning if near lockout
        detail = "Username atau password salah"
        if warning:
            detail = f"{detail}. {warning}"

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={
                "WWW-Authenticate": "Bearer",
                "X-Login-Attempts": str(attempts),
                "X-Captcha-Required": str(captcha_needed).lower()
            },
        )

    if not user.is_active:
        # Log inactive account attempt
        log_login_failed(login_data.username, client_ip, "account_inactive")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun tidak aktif"
        )

    _clear_local_login_failure_state(local_lockout_key)

    # Enforce participant APK signature check (admin/teacher tetap normal via web).
    if user.role in ("student", "guruplus"):
        await _enforce_student_mobile_signature(request)

    # ✅ Freeze Mode Check (allow only freeze-exempt developer/admin identity)
    if await is_freeze_mode_enabled():
        if not is_freeze_exempt_identity(user.role, user.username, user.job_title):
            # Keep freeze state opaque for participant clients (web/mobile).
            if user.role in ("student", "guruplus"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Username atau password salah",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail={
                    "type": "freeze_mode",
                    "message": "🧊 Sistem sedang freeze. Hanya akun developer yang diizinkan sementara.",
                    "icon": "🧊",
                }
            )

    # ✅ Maintenance Mode Check (block non-admin access)
    if await _is_maintenance_mode():
        # Allow only admin to login during maintenance
        if not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "type": "maintenance",
                    "message": "🛠️ Sistem sedang dalam pemeliharaan. Hanya admin yang dapat mengakses saat ini.",
                    "icon": "🛠️"
                }
            )

    # ✅ APK Token Validation (Students Only)
    from app.utils.apk_validation import validate_student_apk_token

    # Get token from request body OR header (for WebView apps)
    client_token = login_data.build_token or request.headers.get('X-Build-Token')
    user_agent = request.headers.get('User-Agent', '')

    token_validation = await validate_student_apk_token(
        client_token=client_token,
        user_role=user.role,
        username=user.username,
        user_agent=user_agent
    )

    if not token_validation['valid']:
        # Log token rejection
        log_login_failed(user.username, client_ip, token_validation['reason'])

        # Log to security events table for audit
        from app.database import async_session_write
        from app.models.security_event import SecurityEvent
        security_event = SecurityEvent(
            event_type="APK_TOKEN_REJECTED",
            user_id=user.id,
            ip_address=client_ip,
            user_agent=request.headers.get('User-Agent', 'Unknown'),
            endpoint=request.url.path,
            method="POST",
            extra_data=str({
                "username": user.username,
                "reason": token_validation['reason'],
                "client_token": _redact_token(client_token),
                "accepted_tokens": [
                    _redact_token(token)
                    for token in (token_validation.get('accepted_tokens') or [])
                ],
                "accepted_label": token_validation.get('accepted_label'),
            }),
            severity="high" if token_validation['reason'] in {"APK_VERSION_OUTDATED", "APK_VERSION_MISMATCH"} else "medium"
        )
        async with async_session_write() as db_write:
            db_write.add(security_event)
            await db_write.commit()

        # Return professional error message
        error_detail = {
            "type": "apk_validation_failed",
            "error": token_validation['reason'],
            "message": token_validation.get('message', 'Validasi APK gagal'),
            "action_required": token_validation.get('action_required', 'Silakan hubungi administrator')
        }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail
        )

    # ✅ Log successful login
    log_login_success(user.username, user.id, client_ip)
    # Avoid burst write amplification: defer heavy side-effects for non-student roles only.
    if is_teacher_scope_role(user.role):
        asyncio.create_task(_persist_login_side_effects(user.id, user.username, user.role))

    # Create access token
    access_token = create_access_token(
        data={
            "sub": str(user.id),  # Must be string for python-jose
            "username": user.username,
            "role": user.role,
            "full_name": user.full_name,
            "student_class": user.student_class,
            "job_title": user.job_title,
            "is_active": bool(user.is_active),
        }
    )
    authenticated_user = user.to_authenticated_user()
    warm_authenticated_user_cache(access_token, authenticated_user)

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=user.to_user_response()
    )


def _enforce_login_scope(token: Token, allowed_roles: set[str], scope_label: str) -> Token:
    """Ensure login result role matches the requested auth lane."""
    role = (token.user.role or "").strip().lower()
    if role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Akses ditolak untuk jalur login {scope_label}. Role akun: {role or 'unknown'}",
        )
    return token


@router.post("/control/login", response_model=Token)
@router.post("/control/signin", response_model=Token)
async def login_control(login_data: UserLogin, request: Request, db: AsyncSession = Depends(get_db_read)):
    """Control-plane login (admin + teacher) for dashboard pages."""
    token = await login(login_data=login_data, request=request, db=db)
    return _enforce_login_scope(token, {"developer", "admin", "teacher"}, "control")


@router.post("/admin/login", response_model=Token)
@router.post("/admin/signin", response_model=Token)
async def login_admin(login_data: UserLogin, request: Request, db: AsyncSession = Depends(get_db_read)):
    """Admin-only login lane."""
    token = await login(login_data=login_data, request=request, db=db)
    return _enforce_login_scope(token, {"developer", "admin"}, "admin")


@router.post("/teacher/login", response_model=Token)
@router.post("/teacher/signin", response_model=Token)
async def login_teacher(login_data: UserLogin, request: Request, db: AsyncSession = Depends(get_db_read)):
    """Teacher-only login lane."""
    token = await login(login_data=login_data, request=request, db=db)
    return _enforce_login_scope(token, {"teacher"}, "teacher")


@router.post("/pengawas/login", response_model=Token)
@router.post("/pengawas/signin", response_model=Token)
async def login_pengawas(login_data: UserLogin, request: Request, db: AsyncSession = Depends(get_db_read)):
    """Pengawas-only login lane (teacher role with job_title pengawas)."""
    token = await login(login_data=login_data, request=request, db=db)
    enforced = _enforce_login_scope(token, {"teacher"}, "pengawas")
    if not is_pengawas_identity(enforced.user.role, enforced.user.job_title):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak untuk jalur login pengawas.",
        )
    return enforced


@router.post("/student/login", response_model=Token)
@router.post("/student/signin", response_model=Token)
async def login_student(login_data: UserLogin, request: Request, db: AsyncSession = Depends(get_db_read)):
    """Participant login lane for student and GuruPlus (mobile exam client)."""
    token = await login(login_data=login_data, request=request, db=db)
    return _enforce_login_scope(token, {"student", "guruplus"}, "student")


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_read),
):
    """Get current authenticated user profile."""
    return await _load_user_response(db, current_user.id)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    current_user: AuthenticatedUser = Depends(get_current_user_for_refresh),
    db: AsyncSession = Depends(get_db_read),
):
    """
    Refresh access token.
    Allows expired tokens (within grace period) to be exchanged for a new one.
    """
    access_token = create_access_token(
        data={
            "sub": str(current_user.id),
            "username": current_user.username,
            "role": current_user.role,
            "full_name": current_user.full_name,
            "student_class": current_user.student_class,
            "job_title": current_user.job_title,
            "is_active": bool(current_user.is_active),
        }
    )
    warm_authenticated_user_cache(access_token, current_user)

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=await _load_user_response(db, current_user.id),
    )
