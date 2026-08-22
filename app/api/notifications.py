"""
In-App Notifications API endpoints.
NOTE: This is ONLY for in-app notifications, NO email/SMS/push external.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import Optional
from datetime import datetime, timezone

from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse, NotificationListResponse, UnreadCountResponse
from app.core.security import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("/", response_model=NotificationListResponse)
async def get_notifications(
    unread_only: bool = False,
    type: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's notifications with filters.
    
    **Filters:**
    - unread_only: Show only unread notifications
    - type: Filter by notification type
    """
    query = select(Notification).where(Notification.user_id == current_user.id)
    
    if unread_only:
        query = query.where(Notification.is_read == False)
    
    if type:
        query = query.where(Notification.type == type)
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(Notification.created_at.desc()).offset(offset).limit(per_page)
    
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get count of unread notifications (for badge)."""
    result = await db.execute(
        select(func.count(Notification.id))
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
    )
    count = result.scalar() or 0
    
    return UnreadCountResponse(unread_count=count)


@router.get("/types")
async def get_notification_types(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of notification types user has received."""
    result = await db.execute(
        select(Notification.type)
        .where(Notification.user_id == current_user.id)
        .distinct()
        .order_by(Notification.type)
    )
    types = [row[0] for row in result.fetchall()]
    
    return {"types": types}


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get single notification details."""
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(404, "Notifikasi tidak ditemukan")
    
    if notification.user_id != current_user.id:
        raise HTTPException(403, "Bukan notifikasi Anda")
    
    return notification


@router.patch("/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark notification as read."""
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(404, "Notifikasi tidak ditemukan")
    
    if notification.user_id != current_user.id:
        raise HTTPException(403, "Bukan notifikasi Anda")
    
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
    
    return {"message": "Notifikasi ditandai sudah dibaca"}


@router.patch("/mark-all-read")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read."""
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    await db.commit()
    
    return {"message": "Semua notifikasi ditandai sudah dibaca"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete notification."""
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(404, "Notifikasi tidak ditemukan")
    
    if notification.user_id != current_user.id:
        raise HTTPException(403, "Bukan notifikasi Anda")
    
    await db.delete(notification)
    await db.commit()
    
    return {"message": "Notifikasi dihapus"}


@router.delete("/clear-all")
async def clear_all_notifications(
    read_only: bool = Query(True, description="Only clear read notifications"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Clear notifications."""
    query = select(Notification).where(Notification.user_id == current_user.id)
    
    if read_only:
        query = query.where(Notification.is_read == True)
    
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    for notification in notifications:
        await db.delete(notification)
    
    await db.commit()
    
    return {"message": f"{len(notifications)} notifikasi dihapus"}
