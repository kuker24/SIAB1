"""
Security utilities for authentication and authorization.
"""
import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from passlib.context import CryptContext
import jwt
from jwt import PyJWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db_read
from app.models.user import User
from app.schemas.user import TokenData
from app.core.roles import (
    is_admin_scope_role,
    is_participant_role,
    is_teacher_scope_role,
)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token scheme
security = HTTPBearer()

AUTH_USER_CACHE_TTL_SECONDS = 20.0
AUTH_USER_CACHE_MAX_ITEMS = 20000


def _normalize_job_title(value: Optional[str]) -> str:
    return " ".join(str(value or "").strip().lower().split())


def is_pengawas_identity(role: Optional[str], job_title: Optional[str]) -> bool:
    normalized_role = str(role or "").strip().lower()
    if normalized_role != "teacher":
        return False
    normalized_title = _normalize_job_title(job_title)
    if not normalized_title:
        return False
    return (
        "pengawas" in normalized_title
        or normalized_title in {"proktor", "invigilator"}
    )


def is_pengawas_user(user: Any) -> bool:
    return is_pengawas_identity(
        getattr(user, "role", None),
        getattr(user, "job_title", None),
    )


def is_teacher_scope_restricted(user: Any) -> bool:
    normalized_role = str(getattr(user, "role", "") or "").strip().lower()
    return normalized_role == "teacher" and not is_pengawas_user(user)


def _load_freeze_exempt_usernames() -> set[str]:
    raw_value = str(os.getenv("FREEZE_EXEMPT_USERNAMES", "developer") or "")
    return {
        item.strip().lower()
        for item in raw_value.split(",")
        if item and item.strip()
    }


def _load_freeze_exempt_title_keywords() -> tuple[str, ...]:
    raw_value = str(os.getenv("FREEZE_EXEMPT_TITLE_KEYWORDS", "developer,devops") or "")
    keywords = tuple(
        item.strip().lower()
        for item in raw_value.split(",")
        if item and item.strip()
    )
    return keywords


FREEZE_EXEMPT_USERNAMES = _load_freeze_exempt_usernames()
FREEZE_EXEMPT_TITLE_KEYWORDS = _load_freeze_exempt_title_keywords()


def is_freeze_exempt_identity(
    role: Optional[str],
    username: Optional[str],
    job_title: Optional[str],
) -> bool:
    """
    Freeze exemption policy.
    Only admin-level identities can bypass freeze mode.
    """
    if not is_admin_scope_role(role):
        return False

    normalized_username = str(username or "").strip().lower()
    if normalized_username and normalized_username in FREEZE_EXEMPT_USERNAMES:
        return True

    normalized_title = _normalize_job_title(job_title)
    return bool(
        normalized_title
        and any(keyword in normalized_title for keyword in FREEZE_EXEMPT_TITLE_KEYWORDS)
    )


def is_freeze_exempt_user(user: Any) -> bool:
    return is_freeze_exempt_identity(
        getattr(user, "role", None),
        getattr(user, "username", None),
        getattr(user, "job_title", None),
    )


def _get_refresh_grace_minutes() -> int:
    raw_value = (os.getenv("JWT_REFRESH_GRACE_MINUTES", "15") or "15").strip()
    try:
        return max(0, min(int(raw_value), 1440))
    except ValueError:
        return 15


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    username: str
    full_name: str
    role: str
    student_class: Optional[str]
    job_title: Optional[str]
    is_active: bool
    profile_picture: Optional[str]
    last_login: Optional[datetime]

    @property
    def is_admin(self) -> bool:
        return is_admin_scope_role(self.role)

    @property
    def is_teacher(self) -> bool:
        return is_teacher_scope_role(self.role)

    @property
    def is_pengawas(self) -> bool:
        return is_pengawas_identity(self.role, self.job_title)

    @property
    def is_student(self) -> bool:
        return is_participant_role(self.role)


_auth_user_cache: Dict[str, tuple[float, AuthenticatedUser]] = {}


def _cache_token_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _get_cached_authenticated_user(token: str) -> Optional[AuthenticatedUser]:
    cache_key = _cache_token_key(token)
    cached = _auth_user_cache.get(cache_key)
    if not cached:
        return None
    expires_at, user = cached
    if time.monotonic() >= expires_at:
        _auth_user_cache.pop(cache_key, None)
        return None
    return user


def _store_cached_authenticated_user(token: str, user: AuthenticatedUser) -> None:
    now = time.monotonic()
    _auth_user_cache[_cache_token_key(token)] = (now + AUTH_USER_CACHE_TTL_SECONDS, user)
    if len(_auth_user_cache) > AUTH_USER_CACHE_MAX_ITEMS:
        stale_keys = [key for key, (expires_at, _user) in _auth_user_cache.items() if expires_at <= now]
        for key in stale_keys[: AUTH_USER_CACHE_MAX_ITEMS // 2]:
            _auth_user_cache.pop(key, None)


def _build_authenticated_user(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=int(user.id),
        username=str(user.username),
        full_name=str(user.full_name),
        role=str(user.role),
        student_class=user.student_class,
        job_title=user.job_title,
        is_active=bool(user.is_active),
        profile_picture=user.profile_picture,
        last_login=user.last_login,
    )


def warm_authenticated_user_cache(
    token: str,
    user: Union[User, AuthenticatedUser],
) -> AuthenticatedUser:
    """
    Prime the token cache right after token issuance.

    This removes the first authenticated DB lookup on burst flows such as
    student login -> immediate exam start.
    """
    authenticated_user = user if isinstance(user, AuthenticatedUser) else _build_authenticated_user(user)
    _store_cached_authenticated_user(token, authenticated_user)
    return authenticated_user


async def _resolve_authenticated_user(token: str, db: AsyncSession) -> Optional[AuthenticatedUser]:
    token_data = decode_token(token, verify_exp=True)
    if token_data is None:
        return None

    cached_user = _get_cached_authenticated_user(token)
    if cached_user is not None:
        if (
            cached_user.id == token_data.user_id
            and cached_user.username == token_data.username
            and cached_user.role == token_data.role
        ):
            return cached_user

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    authenticated_user = _build_authenticated_user(user)
    _store_cached_authenticated_user(token, authenticated_user)
    return authenticated_user


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    return encoded_jwt


def decode_token(token: str, verify_exp: bool = True) -> Optional[TokenData]:
    """Decode and validate a JWT token."""
    try:
        # Allow expired tokens if verify_exp is False (for refresh endpoint)
        options = {"verify_exp": verify_exp}

        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options=options
        )
        user_id_str = payload.get("sub")
        username: str = payload.get("username")
        role: str = payload.get("role")
        full_name = payload.get("full_name")
        student_class = payload.get("student_class")
        job_title = payload.get("job_title")
        is_active = payload.get("is_active")

        if user_id_str is None or username is None or role is None:
            return None

        # Convert user_id from string back to int
        user_id = int(user_id_str)

        return TokenData(
            user_id=user_id,
            username=username,
            role=role,
            full_name=full_name,
            student_class=student_class,
            job_title=job_title,
            is_active=bool(is_active) if is_active is not None else None,
        )
    except PyJWTError:
        return None


def create_session_poll_token(session_id: int, user_id: int, expires_minutes: int = 15) -> str:
    """Create short-lived signed token for session polling endpoint."""
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(expires_minutes)))
    payload = {
        "sub": str(user_id),
        "sid": int(session_id),
        "typ": "session_poll",
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_session_poll_token(token: str, session_id: int) -> Optional[int]:
    """Return user_id when token is valid for the given session, else None."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("typ") != "session_poll":
            return None
        token_sid = int(payload.get("sid", -1))
        token_uid = int(payload.get("sub", -1))
        if token_sid != int(session_id) or token_uid <= 0:
            return None
        return token_uid
    except (PyJWTError, ValueError, TypeError):
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db_read)
) -> AuthenticatedUser:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kadaluarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    user = await _resolve_authenticated_user(token, db)
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun tidak aktif"
        )

    return user


async def get_current_user_hot_path(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthenticatedUser:
    """
    Lightweight auth dependency for ultra-hot paths.

    Uses signed JWT payload as primary identity source and skips per-request
    DB user lookup to reduce connection pressure during submit bursts.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kadaluarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    cached_user = _get_cached_authenticated_user(token)
    if cached_user is not None:
        if not cached_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akun tidak aktif",
            )
        return cached_user

    token_data = decode_token(token, verify_exp=True)
    if token_data is None:
        raise credentials_exception

    hot_path_user = AuthenticatedUser(
        id=token_data.user_id,
        username=token_data.username,
        full_name=token_data.full_name or token_data.username,
        role=token_data.role,
        student_class=token_data.student_class,
        job_title=token_data.job_title,
        is_active=bool(token_data.is_active) if token_data.is_active is not None else True,
        profile_picture=None,
        last_login=None,
    )
    if not hot_path_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun tidak aktif",
        )
    _store_cached_authenticated_user(token, hot_path_user)
    return hot_path_user


async def get_current_user_for_refresh(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db_read)
) -> AuthenticatedUser:
    """
    Get user from token even if expired (for refresh endpoint).
    Only allows tokens expired within a short grace period.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    # Decode WITHOUT verifying expiry first
    token_data = decode_token(token, verify_exp=False)

    if token_data is None:
        raise credentials_exception

    # Manual expiry check with short grace period.
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        exp = payload.get("exp")
        if exp is None:
            raise credentials_exception

        expire_time = datetime.fromtimestamp(exp, tz=timezone.utc)
        refresh_grace = timedelta(minutes=_get_refresh_grace_minutes())
        if datetime.now(timezone.utc) > expire_time + refresh_grace:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sesi telah berakhir. Silakan login ulang.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception:
        raise credentials_exception

    cached_user = _get_cached_authenticated_user(token)
    if cached_user is not None and cached_user.id == token_data.user_id:
        user = cached_user
    else:
        result = await db.execute(select(User).where(User.id == token_data.user_id))
        db_user = result.scalar_one_or_none()
        user = _build_authenticated_user(db_user) if db_user is not None else None
        if user is not None:
            _store_cached_authenticated_user(token, user)

    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def get_current_active_admin(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Require admin role."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak. Hanya admin yang dapat mengakses."
        )
    return current_user


async def get_current_teacher(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Require teacher or admin role."""
    if not current_user.is_teacher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak. Hanya guru atau admin yang dapat mengakses."
        )
    return current_user


async def get_current_admin(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Require admin role only."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak. Hanya admin yang dapat mengakses."
        )
    return current_user


async def get_current_admin_or_pengawas(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Require admin or pengawas identity."""
    if current_user.is_admin or is_pengawas_user(current_user):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Akses ditolak. Hanya admin atau pengawas yang dapat mengakses.",
    )


# New: Flexible authentication for admin panel (supports session cookies)
async def get_current_user_flexible(
    request: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db_read)
) -> Optional[AuthenticatedUser]:
    """
    Get current user with flexible authentication.
    Supports both Bearer token (for API) and session cookies (for admin panel).
    Returns None if not authenticated (for optional auth).
    """
    user = None

    # Try Bearer token first
    if request and request.credentials:
        user = await _resolve_authenticated_user(request.credentials, db)

    # If no Bearer token, try session cookie (for backwards compatibility)
    # This allows admin panel to work without API token
    # Note: In production, you should use a proper session management system

    if user and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun tidak aktif"
        )

    return user


async def get_current_user_flexible_required(
    user: Optional[AuthenticatedUser] = Depends(get_current_user_flexible)
) -> AuthenticatedUser:
    """Require authentication (flexible method)."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user


async def get_current_admin_flexible(
    current_user: AuthenticatedUser = Depends(get_current_user_flexible_required)
) -> AuthenticatedUser:
    """Require admin role (flexible authentication)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak. Hanya admin yang dapat mengakses."
        )
    return current_user
