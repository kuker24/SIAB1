"""
Token Service - Handles access and refresh token operations.

Security features:
- Refresh token rotation: New refresh token on each use
- Token family tracking: Detect token reuse attacks
- Automatic cleanup: Remove expired tokens
"""
import secrets
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from fastapi import HTTPException, status

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.core.security import create_access_token
from app.config import settings


# Token expiry settings
REFRESH_TOKEN_EXPIRE_DAYS = 7
ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, 'jwt_access_token_expire_minutes', 60)


def generate_refresh_token() -> str:
    """Generate a cryptographically secure refresh token."""
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    """Hash token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


async def create_token_pair(
    db: AsyncSession,
    user: User,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Tuple[str, str]:
    """
    Create a new access/refresh token pair.
    
    Returns:
        Tuple of (access_token, refresh_token)
    """
    # Create access token
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "full_name": user.full_name,
            "student_class": user.student_class,
            "job_title": user.job_title,
            "is_active": bool(user.is_active),
        }
    )
    
    # Create refresh token
    refresh_token = generate_refresh_token()
    token_hash = hash_token(refresh_token)
    family_id = str(uuid.uuid4())
    
    # Store refresh token
    db_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=user_agent[:500] if user_agent else None,
        ip_address=ip_address[:45] if ip_address else None
    )
    db.add(db_token)
    await db.commit()
    
    return access_token, refresh_token


async def rotate_refresh_token(
    db: AsyncSession,
    old_refresh_token: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Tuple[str, str, User]:
    """
    Rotate refresh token - invalidate old, issue new.
    
    Implements token rotation for security:
    - Old token is revoked
    - New token is issued in same family
    - If old token is already revoked, entire family is revoked (reuse attack detected)
    
    Returns:
        Tuple of (new_access_token, new_refresh_token, user)
    
    Raises:
        HTTPException if token is invalid or reuse attack detected
    """
    token_hash = hash_token(old_refresh_token)
    
    # Find token
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    old_token = result.scalar_one_or_none()
    
    if not old_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token tidak valid"
        )
    
    # Check if token was already used (reuse attack detection)
    if old_token.is_revoked:
        # SECURITY: Token reuse detected! Revoke entire family
        await revoke_token_family(db, old_token.family_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sudah digunakan. Semua sesi telah dikeluarkan untuk keamanan."
        )
    
    # Check if token is expired
    if old_token.is_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token sudah kadaluarsa. Silakan login ulang."
        )
    
    # Get user
    result = await db.execute(
        select(User).where(User.id == old_token.user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Pengguna tidak ditemukan atau tidak aktif"
        )
    
    # Revoke old token
    old_token.is_revoked = True
    old_token.revoked_at = datetime.now(timezone.utc)
    
    # Create new token pair (same family for tracking)
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "full_name": user.full_name,
            "student_class": user.student_class,
            "job_title": user.job_title,
            "is_active": bool(user.is_active),
        }
    )
    
    new_refresh_token = generate_refresh_token()
    new_token_hash = hash_token(new_refresh_token)
    
    db_token = RefreshToken(
        user_id=user.id,
        token_hash=new_token_hash,
        family_id=old_token.family_id,  # Same family
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=user_agent[:500] if user_agent else None,
        ip_address=ip_address[:45] if ip_address else None
    )
    db.add(db_token)
    await db.commit()
    
    return access_token, new_refresh_token, user


async def revoke_token_family(db: AsyncSession, family_id: str) -> int:
    """
    Revoke all tokens in a family (for security incidents).
    
    Returns:
        Number of tokens revoked
    """
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.is_revoked == False
        )
    )
    tokens = result.scalars().all()
    
    now = datetime.now(timezone.utc)
    for token in tokens:
        token.is_revoked = True
        token.revoked_at = now
    
    await db.commit()
    return len(tokens)


async def revoke_user_tokens(db: AsyncSession, user_id: int) -> int:
    """
    Revoke all refresh tokens for a user (logout from all devices).
    
    Returns:
        Number of tokens revoked
    """
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False
        )
    )
    tokens = result.scalars().all()
    
    now = datetime.now(timezone.utc)
    for token in tokens:
        token.is_revoked = True
        token.revoked_at = now
    
    await db.commit()
    return len(tokens)


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """
    Remove expired tokens from database.
    Should be run periodically via a background task.
    
    Returns:
        Number of tokens deleted
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)  # Keep 30 days for audit
    
    result = await db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
    )
    await db.commit()
    
    return result.rowcount
