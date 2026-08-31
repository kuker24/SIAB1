"""
User management API endpoints.
"""
from typing import List, Optional
from datetime import datetime, timezone
import csv
import io
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, or_
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.core.feature_flags import require_feature_enabled
from app.database import get_db, get_db_read
from app.models.user import User
from app.models.activity_log import UserActivityLog
from app.schemas.user import (
    UserResponse, UserCreate, UserUpdate, UserSearchFilters, UserBatchUpdate
)
from app.core.security import (
    get_current_user,
    get_current_active_admin,
    get_current_teacher,
    get_password_hash,
)
from app.core.roles import (
    ROLE_ADMIN,
    ROLE_DEVELOPER,
    ROLE_GURUPLUS,
    ROLE_GURUPENGAWAS,
    ROLE_STUDENT,
    ROLE_TEACHER,
    can_assign_role,
    can_manage_user_account,
    is_admin_scope_role,
    is_developer_role,
)
from app.core.users_cache import (
    _get_cached_student_classes,
    _get_cached_student_classes_redis,
    _get_cached_users_list,
    _get_cached_users_list_redis,
    _invalidate_user_caches,
    _invalidate_user_caches_redis,
    _set_cached_student_classes,
    _set_cached_student_classes_redis,
    _set_cached_users_list,
    _set_cached_users_list_redis,
)

router = APIRouter(prefix="/api/users", tags=["Users"])
logger = logging.getLogger(__name__)
GURUPLUS_ROLE = "guruplus"
GURUPLUS_CLASS_NAME = "GuruPlus"
DEVELOPER_ROLE = ROLE_DEVELOPER


def _normalize_role(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _apply_role_student_class_defaults(
    role: Optional[str],
    student_class: Optional[str],
) -> Optional[str]:
    normalized_role = _normalize_role(role)
    normalized_class = (student_class or "").strip() or None

    if normalized_role == GURUPLUS_ROLE:
        return GURUPLUS_CLASS_NAME

    if normalized_role in {ROLE_TEACHER, ROLE_ADMIN, ROLE_DEVELOPER, ROLE_GURUPENGAWAS} and normalized_class == GURUPLUS_CLASS_NAME:
        return None

    return normalized_class


def _assert_role_assignment_allowed(actor_role: Optional[str], target_role: Optional[str]) -> None:
    normalized_target_role = _normalize_role(target_role)
    if not normalized_target_role:
        return
    if can_assign_role(actor_role, normalized_target_role):
        return

    if normalized_target_role == GURUPLUS_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role GuruPlus hanya dapat dikelola oleh developer.",
        )
    if normalized_target_role == DEVELOPER_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role developer hanya dapat dikelola oleh developer.",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tidak memiliki izin untuk menetapkan role ini.",
    )


def _assert_target_user_manageable(actor_role: Optional[str], target_role: Optional[str]) -> None:
    if can_manage_user_account(actor_role, target_role):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Akun developer hanya dapat dikelola oleh developer.",
    )

def _normalize_profile_picture_url(value: Optional[str]) -> Optional[str]:
    raw_value = (value or "").strip()
    if not raw_value:
        return None
    if any(char in raw_value for char in ('"', "'", "<", ">", " ", "\n", "\r", "\t")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "URL foto profil tidak valid")
    if raw_value.startswith("/"):
        return raw_value

    parsed = urlparse(raw_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "URL foto profil harus http(s) atau path lokal")
    return raw_value

# Admin Audit Logging Helper for User Management
async def log_admin_user_action(
    db,
    admin_user: User,
    action: str,
    target_user_id: int,
    target_username: str,
    details: dict = None
):
    """Log admin actions on user management for audit trail."""
    if is_admin_scope_role(admin_user.role):
        log_entry = UserActivityLog(
            user_id=admin_user.id,
            event_type=f"admin_user_{action}",
            event_data={
                "admin_username": admin_user.username,
                "action": action,
                "target_user_id": target_user_id,
                "target_username": target_username,
                "details": details or {}
            }
        )
        db.add(log_entry)
        await db.commit()

# === ADVANCED SEARCH ===

@router.get("/advanced-search")
async def advanced_user_search(
    role: Optional[str] = None,
    student_class: Optional[str] = None,
    is_active: Optional[bool] = None,
    search_query: Optional[str] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Advanced user search with multiple filters and pagination.
    """
    # Build dynamic query
    query = select(User)

    # Apply filters
    if role:
        query = query.where(User.role == role)
    if student_class:
        query = query.where(User.student_class == student_class)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if search_query:
        search = f"%{search_query}%"
        query = query.where(
            or_(
                User.username.ilike(search),
                User.full_name.ilike(search),
            )
        )
    if created_after:
        query = query.where(User.created_at >= created_after)
    if created_before:
        query = query.where(User.created_at <= created_before)

    # Apply sorting with a small whitelist to keep queries predictable.
    sort_columns = {
        "id": User.id,
        "username": User.username,
        "full_name": User.full_name,
        "created_at": User.created_at,
    }
    sort_column = sort_columns.get(sort_by, User.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc(), User.id.desc())
    else:
        query = query.order_by(sort_column.asc(), User.id.asc())

    # Count total (this is a simplified count, suboptimal for huge datasets but fine for this scale)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "users": [UserResponse.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if per_page > 0 else 1
    }


# === BASIC ENDPOINTS ===

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new user (Admin only).
    """
    # Check duplicate username
    existing = await db.execute(select(User).where(User.username == user_data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username sudah digunakan")

    # Create user
    normalized_role = _normalize_role(user_data.role or "student")
    _assert_role_assignment_allowed(current_user.role, normalized_role)
    user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=normalized_role,
        student_class=_apply_role_student_class_defaults(
            normalized_role,
            user_data.student_class,
        ),
        job_title=user_data.job_title,  # FIX: Add job_title mapping
        # Default fields
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)
    _invalidate_user_caches()
    await _invalidate_user_caches_redis()

    return user


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 1000,
    role: Optional[str] = None,
    student_class: Optional[str] = None,
    is_active: Optional[bool] = None,
    search_query: Optional[str] = None,
    sort_by: str = Query("created_at", pattern="^(id|username|full_name|created_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read)
):
    """List users (admin only) with lightweight projection."""
    safe_skip = max(0, skip)
    safe_limit = min(max(1, limit), 2000)

    cache_key = (
        safe_skip,
        safe_limit,
        role or "",
        student_class or "",
        is_active,
        (search_query or "").strip().lower(),
        sort_by,
        sort_order,
    )
    cached_users = _get_cached_users_list(cache_key)
    if cached_users is not None:
        return cached_users
    redis_cached_users = await _get_cached_users_list_redis(cache_key)
    if redis_cached_users is not None:
        _set_cached_users_list(cache_key, redis_cached_users)
        return redis_cached_users

    query = select(
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
    )
    if role:
        query = query.where(User.role == role)
    if student_class:
        query = query.where(User.student_class == student_class)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if search_query and search_query.strip():
        search = f"%{search_query.strip()}%"
        query = query.where(
            or_(
                User.username.ilike(search),
                User.full_name.ilike(search),
            )
        )

    sort_columns = {
        "id": User.id,
        "username": User.username,
        "full_name": User.full_name,
        "created_at": User.created_at,
    }
    sort_column = sort_columns.get(sort_by, User.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_column.asc(), User.id.asc())
    else:
        query = query.order_by(sort_column.desc(), User.id.desc())

    query = query.offset(safe_skip).limit(safe_limit)
    result = await db.execute(query)
    users = [dict(row) for row in result.mappings().all()]
    _set_cached_users_list(cache_key, users)
    await _set_cached_users_list_redis(cache_key, users)
    return users


@router.get("/student-classes")
async def get_student_classes(
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    """Get unique list of student classes."""
    _ = current_user
    cached_classes = _get_cached_student_classes()
    if cached_classes is not None:
        if is_developer_role(current_user.role):
            classes = sorted(set(cached_classes + [GURUPLUS_CLASS_NAME]))
            return {"classes": classes}
        return {"classes": cached_classes}
    redis_cached_classes = await _get_cached_student_classes_redis()
    if redis_cached_classes is not None:
        _set_cached_student_classes(redis_cached_classes)
        if is_developer_role(current_user.role):
            classes = sorted(set(redis_cached_classes + [GURUPLUS_CLASS_NAME]))
            return {"classes": classes}
        return {"classes": redis_cached_classes}

    result = await db.execute(
        select(User.student_class)
        .where(
            User.role == "student",
            User.student_class.isnot(None),
            func.trim(User.student_class) != ""
        )
        .distinct()
        .order_by(User.student_class)
    )
    classes = [row[0].strip() for row in result.fetchall() if row[0] and row[0].strip()]
    _set_cached_student_classes(classes)
    await _set_cached_student_classes_redis(classes)
    if is_developer_role(current_user.role):
        classes = sorted(set(classes + [GURUPLUS_CLASS_NAME]))
    return {"classes": classes}


@router.get("/students-by-class", response_model=List[UserResponse])
async def get_students_by_class(
    student_class: Optional[str] = None,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read),
):
    """Get students optionally filtered by class."""
    _ = current_user
    normalized_class = (student_class or "").strip()
    if normalized_class.lower() == GURUPLUS_CLASS_NAME.lower() and not is_developer_role(current_user.role):
        raise HTTPException(status_code=403, detail="Kelas GuruPlus hanya dapat diakses developer")

    cache_key = ("students_by_class", current_user.role.lower(), normalized_class.lower())
    cached_users = _get_cached_users_list(cache_key)
    if cached_users is not None:
        return cached_users

    redis_cached_users = await _get_cached_users_list_redis(cache_key)
    if redis_cached_users is not None:
        _set_cached_users_list(cache_key, redis_cached_users)
        return redis_cached_users

    target_role = GURUPLUS_ROLE if normalized_class.lower() == GURUPLUS_CLASS_NAME.lower() else "student"

    query = select(
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
    ).where(User.role == target_role)
    if student_class:
        query = query.where(User.student_class == normalized_class)
    query = query.order_by(User.full_name.asc(), User.username.asc())
    result = await db.execute(query)
    students = [dict(row) for row in result.mappings().all()]
    _set_cached_users_list(cache_key, students)
    await _set_cached_users_list_redis(cache_key, students)
    return students


@router.get("/{user_id:int}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read)
):
    """Get user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User tidak ditemukan")
    return user


@router.put("/{user_id:int}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),  # Changed from admin to any authenticated user
    db: AsyncSession = Depends(get_db)
):
    """Update user information. Users can update their own profile, admins can update anyone."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User tidak ditemukan")

    # Authorization check: users can only update themselves, admins can update anyone
    is_self_update = current_user.id == user_id
    is_admin = is_admin_scope_role(current_user.role)

    if not is_self_update and not is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tidak memiliki izin untuk mengubah user ini")

    # Guard privileged target accounts before any mutable field assignment.
    # This blocks admin from editing developer accounts while allowing developer-to-developer management.
    if not is_self_update:
        _assert_target_user_manageable(current_user.role, user.role)

    # Check duplicates if changing sensitive fields
    if user_data.username and user_data.username != user.username:
        existing = await db.execute(select(User).where(User.username == user_data.username))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username sudah digunakan")
        user.username = user_data.username

# if user_data.email and user_data.email != user.email: # REMOVED: Email not supported
# existing = await db.execute(select(User).where(User.email == user_data.email)) # REMOVED
#         if existing.scalar_one_or_none():
# raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email sudah digunakan") # REMOVED
# user.email = user_data.email # REMOVED

    # Update other fields
    if user_data.full_name: user.full_name = user_data.full_name
    if user_data.password and user_data.password.strip():
        if len(user_data.password) < 6:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password minimal 6 karakter")
        user.password_hash = get_password_hash(user_data.password)

    # Admin-only fields (role, is_active, student_class, student_id can only be changed by admin)
    if is_admin:
        if user_data.role:
            normalized_role = _normalize_role(user_data.role)
            _assert_role_assignment_allowed(current_user.role, normalized_role)
            user.role = normalized_role
        if user_data.student_class is not None: user.student_class = user_data.student_class
        if user_data.job_title is not None: user.job_title = user_data.job_title  # FIX: Add job_title update
        if user_data.is_active is not None: user.is_active = user_data.is_active
        user.student_class = _apply_role_student_class_defaults(user.role, user.student_class)

    # Profile picture can be updated by user themselves
    if user_data.profile_picture is not None:
        user.profile_picture = _normalize_profile_picture_url(user_data.profile_picture)

    await db.commit()
    await db.refresh(user)
    _invalidate_user_caches()
    await _invalidate_user_caches_redis()

    # Log admin action if admin updating other user
    if is_admin and not is_self_update:
        await log_admin_user_action(
            db, current_user, "update", user_id, user.username,
            {"changed_fields": [k for k, v in user_data.dict().items() if v is not None]}
        )

    return user


@router.delete("/{user_id:int}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User tidak ditemukan")

    if user.id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak dapat menghapus diri sendiri")

    _assert_target_user_manageable(current_user.role, user.role)

    # Soft Delete (Deactivate) instead of Hard Delete
    # This preserves exam history and logs
    user.is_active = False

    # Optional: Rename username to allow re-registration with same username later
    # user.username = f"{user.username}_deleted_{int(datetime.now().timestamp())}"

    await db.commit()
    _invalidate_user_caches()
    await _invalidate_user_caches_redis()

    # Log admin action
    await log_admin_user_action(
        db, current_user, "delete", user_id, user.username,
        {"soft_delete": True, "previous_is_active": True}
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# === BATCH OPERATIONS ===

@router.post("/batch-create")
async def batch_create_users(
    users: List[UserCreate],
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create multiple users at once.
    """
    if len(users) > 500:
        raise HTTPException(400, "Maximum 500 users per batch")

    created = []
    errors = []
    seen_usernames = set()

    for idx, user_data in enumerate(users):
        normalized_username = (user_data.username or "").strip().lower()
        if normalized_username in seen_usernames:
            errors.append(f"Row {idx+1}: Duplicate username in payload ({user_data.username})")
            continue
        seen_usernames.add(normalized_username)

        try:
            normalized_role = _normalize_role(user_data.role or ROLE_STUDENT)
            _assert_role_assignment_allowed(current_user.role, normalized_role)
            # Isolate each row with SAVEPOINT so one bad row does not break the full batch.
            async with db.begin_nested():
                existing = await db.execute(
                    select(User).where(User.username == user_data.username)
                )
                if existing.scalar_one_or_none():
                    errors.append(f"Row {idx+1}: Username exists ({user_data.username})")
                    continue

                user = User(
                    username=user_data.username,
                    password_hash=get_password_hash(user_data.password),
                    full_name=user_data.full_name,
                    role=normalized_role,
                    student_class=_apply_role_student_class_defaults(
                        normalized_role,
                        user_data.student_class,
                    ),
                    job_title=user_data.job_title,  # FIX: Add job_title mapping
                    created_at=datetime.now(timezone.utc)
                )
                db.add(user)
                await db.flush()
                created.append(user_data.username)
        except IntegrityError:
            errors.append(f"Row {idx+1}: Username conflict ({user_data.username})")
        except Exception as e:
            errors.append(f"Row {idx+1}: {str(e)}")

    await db.commit()
    _invalidate_user_caches()
    await _invalidate_user_caches_redis()

    return {
        "success": len(created),
        "failed": len(errors),
        "created_usernames": created,
        "errors": errors
    }


@router.patch("/batch-update")
async def batch_update_users(
    batch_data: UserBatchUpdate,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update multiple users with logic.
    """
    allowed_fields = {"is_active", "role", "student_class"}
    update_fields = {k: v for k, v in batch_data.update_data.items() if k in allowed_fields}

    if not update_fields:
        raise HTTPException(400, "No valid fields to update")

    # Prevent updating self inactive
    if "is_active" in update_fields and not update_fields["is_active"]:
        if current_user.id in batch_data.user_ids:
             raise HTTPException(400, "Cannot deactivate yourself in batch update")

    protected_target_count_result = await db.execute(
        select(func.count(User.id)).where(
            User.id.in_(batch_data.user_ids),
            User.role == DEVELOPER_ROLE,
        )
    )
    protected_target_count = int(protected_target_count_result.scalar() or 0)
    if protected_target_count > 0 and not is_developer_role(current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun developer hanya dapat dikelola oleh developer.",
        )

    if "role" in update_fields:
        normalized_role = _normalize_role(str(update_fields["role"]))
        _assert_role_assignment_allowed(current_user.role, normalized_role)
        update_fields["role"] = normalized_role
        if normalized_role == GURUPLUS_ROLE:
            update_fields["student_class"] = GURUPLUS_CLASS_NAME
        elif normalized_role in {ROLE_TEACHER, ROLE_ADMIN, ROLE_DEVELOPER, ROLE_GURUPENGAWAS}:
            update_fields["student_class"] = None

    stmt = (
        update(User)
        .where(User.id.in_(batch_data.user_ids))
        .values(**update_fields)
    )
    result = await db.execute(stmt)
    await db.commit()
    _invalidate_user_caches()
    await _invalidate_user_caches_redis()

    return {
        "updated": result.rowcount,
        "fields": list(update_fields.keys())
    }


@router.delete("/batch-delete")
async def batch_delete_users(
    user_ids: List[int] = Query(..., description="List of user IDs to delete"),
    permanent: bool = Query(False, description="Permanently delete or just deactivate"),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete multiple users.
    """
    if current_user.id in user_ids:
        raise HTTPException(400, "Cannot delete yourself")

    protected_target_count_result = await db.execute(
        select(func.count(User.id)).where(
            User.id.in_(user_ids),
            User.role == DEVELOPER_ROLE,
        )
    )
    protected_target_count = int(protected_target_count_result.scalar() or 0)
    if protected_target_count > 0 and not is_developer_role(current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun developer hanya dapat dihapus oleh developer.",
        )

    if permanent:
        stmt = delete(User).where(User.id.in_(user_ids))
    else:
        # Soft delete logic (if supported) or just inactive
        # Here we assume soft delete = is_active False for now based on existing patterns,
        # or actually strictly delete if permanent not implemented.
        # But previous analysis said 'Soft delete set is_active = False'
        stmt = update(User).where(User.id.in_(user_ids)).values(is_active=False)

    result = await db.execute(stmt)
    await db.commit()
    _invalidate_user_caches()
    await _invalidate_user_caches_redis()

    return {
        "deleted": result.rowcount,
        "mode": "permanent" if permanent else "soft"
    }


# === EXPORT ===

@router.post("/export")
async def export_users(
    filters: Optional[UserSearchFilters] = None,
    format: str = "csv",
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Export users to CSV based on filters (EXCLUDING ADMIN/DEVELOPER).
    """
    require_feature_enabled(
        settings.heavy_exports_active,
        "heavy_export",
        status_code=503,
        message="Export pengguna sedang dinonaktifkan selama mode ujian/puncak.",
    )
    # Reuse filter logic but explicitly exclude privileged control-plane accounts.
    query = select(User).where(User.role.notin_([ROLE_ADMIN, ROLE_DEVELOPER]))

    if filters:
        if filters.role and _normalize_role(filters.role) not in {ROLE_ADMIN, ROLE_DEVELOPER}:
            query = query.where(User.role == filters.role)
        if filters.student_class:
            query = query.where(User.student_class == filters.student_class)
        if filters.is_active is not None:
            query = query.where(User.is_active == filters.is_active)
        if filters.search_query and filters.search_query.strip():
            search = f"%{filters.search_query.strip()}%"
            query = query.where(
                or_(
                    User.username.ilike(search),
                    User.full_name.ilike(search),
                )
            )
        if filters.created_after:
            query = query.where(User.created_at >= filters.created_after)
        if filters.created_before:
            query = query.where(User.created_at <= filters.created_before)

    result = await db.execute(query.order_by(User.created_at.desc(), User.id.desc()))
    users = result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Username", "Full Name", "Role", "Class", "Status", "Created At"])

        for u in users:
            writer.writerow([
                u.id, u.username, u.full_name, u.role,
                u.student_class or "",
                "Active" if u.is_active else "Inactive",
                u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=users_export_{datetime.now().strftime('%Y%m%d')}.csv"}
        )
    else:
        raise HTTPException(400, "Only CSV format currently supported")


# === LEGACY BULK UPLOAD (KEEPING FOR COMPATIBILITY) ===

@router.get("/template/csv")
async def download_user_template(current_user: User = Depends(get_current_active_admin)):
    """Download CSV template for bulk user upload with examples for non-privileged user types."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(['username', 'password', 'full_name', 'role', 'student_class'])

    # Example rows for different roles (Admin Removed)
    writer.writerow(['siswa001', 'password123', 'Ahmad Fauzi', 'student', 'XII-IPA-1'])
    writer.writerow(['siswa002', 'password123', 'Budi Santoso', 'student', 'XII-IPA-1'])
    writer.writerow(['guru001', 'password123', 'Drs. Eko Prasetyo', 'teacher', ''])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_users.csv"}
    )

@router.post("/bulk-upload")
async def bulk_upload_users(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """Legacy Endpoint: Bulk upload users from CSV file."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(400, "File harus berformat CSV")

    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))

    results = {"success": 0, "failed": 0, "errors": []}
    seen_usernames = set()

    for row_num, row in enumerate(reader, start=2):
        try:
            username = row.get('username', '').strip()
            password = row.get('password', '').strip()
            full_name = row.get('full_name', '').strip()
            role = _normalize_role(row.get('role', 'student'))

            normalized_username = username.lower()
            if normalized_username in seen_usernames:
                results["failed"] += 1
                results["errors"].append(f"Line {row_num}: Duplicate username in payload ({username})")
                continue
            seen_usernames.add(normalized_username)

            # BLOCK IMPORT PRIVILEGED ROLES
            if role in {ROLE_ADMIN, ROLE_DEVELOPER}:
                results["failed"] += 1
                results["errors"].append(
                    f"Line {row_num}: Import role '{role}' tidak diizinkan demi keamanan"
                )
                continue

            if role == GURUPLUS_ROLE and not is_developer_role(current_user.role):
                results["failed"] += 1
                results["errors"].append(
                    f"Line {row_num}: Role GuruPlus hanya dapat diimpor oleh developer"
                )
                continue

            if role not in {ROLE_STUDENT, ROLE_TEACHER, GURUPLUS_ROLE, ROLE_GURUPENGAWAS}:
                results["failed"] += 1
                results["errors"].append(f"Line {row_num}: Role tidak valid ({role})")
                continue

            if not all([username, password, full_name]):
                results["failed"] += 1; results["errors"].append(f"Line {row_num}: Incomplete data"); continue

            async with db.begin_nested():
                existing = await db.execute(select(User).where((User.username == username)))
                if existing.scalar_one_or_none():
                    results["failed"] += 1; results["errors"].append(f"Line {row_num}: Username taken"); continue

                user = User(
                    username=username, password_hash=get_password_hash(password),
                    full_name=full_name,
                    role=role,
                    student_class=_apply_role_student_class_defaults(
                        role,
                        row.get('student_class'),
                    ),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(user)
                await db.flush()
                results["success"] += 1
        except IntegrityError:
            results["failed"] += 1
            results["errors"].append(f"Line {row_num}: Username conflict ({username})")
        except Exception as e:
            results["failed"] += 1; results["errors"].append(f"Line {row_num}: {str(e)}")

    await db.commit()
    _invalidate_user_caches()
    await _invalidate_user_caches_redis()
    return results
