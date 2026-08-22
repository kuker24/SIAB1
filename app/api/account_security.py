"""
Account Security API - Admin endpoints for managing locked accounts.

Endpoints:
- GET  /api/admin/security/locked-accounts  - List all locked accounts
- POST /api/admin/security/unlock/{username} - Unlock specific account
- POST /api/admin/security/unlock-all       - Unlock all accounts
- GET  /api/admin/security/login-stats      - Login statistics
- POST /api/admin/security/captcha/generate - Generate CAPTCHA challenge
- POST /api/admin/security/captcha/verify   - Verify CAPTCHA answer
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
import logging

from app.database import get_db
from app.models.user import User
from app.core.security import get_current_admin, get_current_admin_or_pengawas
from app.core.account_lockout import get_lockout
from app.core.captcha import get_captcha
from app.core.audit_logger import AuditLogger, AuditEventType

router = APIRouter(prefix="/api/admin/security", tags=["Account Security"])
logger = logging.getLogger(__name__)


# ============== SCHEMAS ==============

class LockedAccountResponse(BaseModel):
    username: str
    locked_at: Optional[str]
    remaining_minutes: int
    remaining_seconds: int


class UnlockResponse(BaseModel):
    success: bool
    message: str
    username: Optional[str] = None


class BulkUnlockResponse(BaseModel):
    success: bool
    message: str
    count: int


class CaptchaGenerateResponse(BaseModel):
    challenge_id: str
    question: str


class CaptchaVerifyRequest(BaseModel):
    challenge_id: str
    answer: str


class CaptchaVerifyResponse(BaseModel):
    success: bool
    message: str


class LoginStatsResponse(BaseModel):
    locked_accounts_count: int
    locked_accounts: List[LockedAccountResponse]


# ============== ENDPOINTS ==============

@router.get("/locked-accounts", response_model=List[LockedAccountResponse])
async def get_locked_accounts(
    current_user: User = Depends(get_current_admin_or_pengawas)
):
    """Get all currently locked accounts."""
    lockout = get_lockout()
    accounts = await lockout.get_all_locked()

    return [
        LockedAccountResponse(
            username=acc["username"],
            locked_at=acc["locked_at"],
            remaining_minutes=acc["remaining_minutes"],
            remaining_seconds=acc["remaining_seconds"]
        )
        for acc in accounts
    ]


@router.post("/unlock/{username}", response_model=UnlockResponse)
async def unlock_account(
    username: str,
    request: Request,
    current_user: User = Depends(get_current_admin_or_pengawas),
    db: AsyncSession = Depends(get_db)
):
    """Unlock a specific account."""
    lockout = get_lockout()

    was_locked = await lockout.admin_unlock(username, current_user.username)

    if was_locked:
        # Audit log
        await AuditLogger.log(
            db=db,
            user_id=current_user.id,
            event_type=AuditEventType.SESSION_TERMINATED,
            event_data={
                "action": "account_unlock",
                "target_username": username
            },
            ip_address=request.client.host if request.client else None
        )

        return UnlockResponse(
            success=True,
            message=f"Akun {username} berhasil di-unlock",
            username=username
        )

    return UnlockResponse(
        success=False,
        message=f"Akun {username} tidak dalam status terkunci",
        username=username
    )


@router.post("/unlock-all", response_model=BulkUnlockResponse)
async def unlock_all_accounts(
    request: Request,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Unlock all locked accounts."""
    try:
        lockout = get_lockout()

        count = await lockout.unlock_all(current_user.username)

        if count > 0:
            # Audit log
            await AuditLogger.log(
                db=db,
                user_id=current_user.id,
                event_type=AuditEventType.ALL_SESSIONS_REVOKED,
                event_data={
                    "action": "bulk_account_unlock",
                    "count": count
                },
                ip_address=request.client.host if request.client else None
            )

        return BulkUnlockResponse(
            success=True,
            message=f"Berhasil unlock {count} akun",
            count=count
        )
    except Exception:
        logger.exception("Failed to unlock all accounts")
        raise HTTPException(status_code=500, detail="Gagal melakukan unlock massal")


@router.get("/stats", response_model=LoginStatsResponse)
async def get_login_stats(
    current_user: User = Depends(get_current_admin_or_pengawas)
):
    """Get login security statistics."""
    lockout = get_lockout()
    accounts = await lockout.get_all_locked()

    return LoginStatsResponse(
        locked_accounts_count=len(accounts),
        locked_accounts=[
            LockedAccountResponse(
                username=acc["username"],
                locked_at=acc["locked_at"],
                remaining_minutes=acc["remaining_minutes"],
                remaining_seconds=acc["remaining_seconds"]
            )
            for acc in accounts
        ]
    )


# ============== CAPTCHA ENDPOINTS ==============

@router.post("/captcha/generate", response_model=CaptchaGenerateResponse)
async def generate_captcha(
    request: Request
):
    """Generate a CAPTCHA challenge (public endpoint)."""
    captcha = get_captcha()

    # Use client IP as session ID
    session_id = request.client.host if request.client else "unknown"
    challenge_id, question, _ = await captcha.generate(session_id)

    return CaptchaGenerateResponse(
        challenge_id=challenge_id,
        question=question
    )


@router.post("/captcha/verify", response_model=CaptchaVerifyResponse)
async def verify_captcha(
    data: CaptchaVerifyRequest
):
    """Verify a CAPTCHA answer (public endpoint)."""
    captcha = get_captcha()

    is_valid = await captcha.verify(data.challenge_id, data.answer)

    if is_valid:
        return CaptchaVerifyResponse(
            success=True,
            message="CAPTCHA valid"
        )

    return CaptchaVerifyResponse(
        success=False,
        message="Jawaban CAPTCHA salah"
    )
