"""
Media Library API endpoints.
Centralized media file management.
"""
import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models.user import User
from app.models.media import MediaFile
from app.schemas.media import MediaFileResponse, MediaFileUpdate, MediaListResponse, MediaStatsResponse
from app.core.sanitization import sanitize_filename, sanitize_html
from app.core.security import get_current_teacher
from app.core.roles import is_admin_scope_role

router = APIRouter(prefix="/api/media", tags=["Media Library"])

# Configuration
UPLOAD_DIR = Path("static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.tiff', '.tif', '.ico'],
    'video': ['.mp4', '.webm', '.mov'],
    'audio': ['.mp3', '.wav', '.ogg'],
    'document': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def get_file_type(filename: str) -> str:
    """Determine file type based on extension."""
    ext = Path(filename).suffix.lower()
    for file_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return 'unknown'


def get_all_allowed_extensions() -> List[str]:
    """Get all allowed extensions as a flat list."""
    all_exts = []
    for exts in ALLOWED_EXTENSIONS.values():
        all_exts.extend(exts)
    return all_exts


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return sanitize_html(stripped)


def _clean_tags(tags: Optional[List[str]]) -> List[str]:
    cleaned_tags: List[str] = []
    for raw_tag in tags or []:
        cleaned_tag = _clean_text(raw_tag)
        if cleaned_tag:
            cleaned_tags.append(cleaned_tag)
    return cleaned_tags


def _to_media_response(media: MediaFile, uploader_name: Optional[str]) -> MediaFileResponse:
    return MediaFileResponse(
        id=media.id,
        filename=media.filename,
        original_filename=_clean_text(media.original_filename) or media.filename,
        file_url=media.file_url,
        file_type=media.file_type,
        mime_type=media.mime_type,
        file_size=media.file_size,
        width=media.width,
        height=media.height,
        uploaded_by=media.uploaded_by,
        uploader_name=_clean_text(uploader_name) or "Unknown",
        created_at=media.created_at,
        tags=_clean_tags(media.tags),
        description=_clean_text(media.description),
        usage_count=media.usage_count or 0,
        last_used_at=media.last_used_at,
    )


def _measure_upload_size(upload_file: UploadFile) -> int:
    current_position = upload_file.file.tell()
    upload_file.file.seek(0, 2)
    size = int(upload_file.file.tell() or 0)
    upload_file.file.seek(current_position)
    return size


def _save_upload_stream(upload_file: UploadFile, file_path: Path) -> None:
    upload_file.file.seek(0)
    with open(file_path, "wb") as output_file:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            output_file.write(chunk)


@router.post("/upload", response_model=MediaFileResponse, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    tags: Optional[str] = None,
    description: Optional[str] = None,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload media file to library.

    **Supported file types:**
    - Images: jpg, jpeg, png, gif, webp, svg, bmp, tiff, tif, ico
    - Videos: mp4, webm, mov
    - Audio: mp3, wav, ogg
    - Documents: pdf, doc, docx, xls, xlsx, ppt, pptx

    **Max file size:** 10MB
    """
    # Validate file type
    safe_original_filename = sanitize_filename(file.filename or "")
    file_type = get_file_type(safe_original_filename)
    if file_type == 'unknown':
        allowed = ', '.join(get_all_allowed_extensions())
        raise HTTPException(400, f"Tipe file tidak didukung. Tipe yang diizinkan: {allowed}")

    file_size = await asyncio.to_thread(_measure_upload_size, file)

    # Validate file size
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(400, f"File terlalu besar. Maksimal: {MAX_FILE_SIZE / 1024 / 1024}MB")

    # Generate unique filename
    ext = Path(safe_original_filename).suffix
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = UPLOAD_DIR / unique_filename

    # Save file
    try:
        await asyncio.to_thread(_save_upload_stream, file, file_path)
    except Exception:
        logger.exception("Failed to save uploaded media file")
        raise HTTPException(500, "Gagal menyimpan file")

    # Extract metadata for images (including bmp, tiff, etc.)
    width, height = None, None
    if file_type == 'image' and ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif']:
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                width, height = img.size
        except Exception as e:
            logger.warning(f"Failed to extract image dimensions: {e}")

    # Parse tags
    tag_list = _clean_tags(tags.split(',') if tags else [])
    safe_description = _clean_text(description)

    # Create media record
    media = MediaFile(
        filename=unique_filename,
        original_filename=safe_original_filename,
        file_path=str(file_path),
        file_url=f"/static/uploads/{unique_filename}",
        file_type=file_type,
        mime_type=file.content_type,
        file_size=file_size,
        width=width,
        height=height,
        uploaded_by=current_user.id,
        tags=tag_list if tag_list else None,
        description=safe_description
    )

    db.add(media)
    await db.commit()
    await db.refresh(media)

    # Build response
    return _to_media_response(media, current_user.full_name)


@router.get("/", response_model=MediaListResponse)
async def list_media(
    file_type: Optional[str] = None,
    tags: Optional[str] = None,
    search_query: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    List media files with filters and pagination.

    **Filters:**
    - file_type: image, video, audio, document
    - tags: Comma-separated tags
    - search_query: Search in filename or description
    """
    from sqlalchemy.orm import selectinload

    query = select(MediaFile).options(selectinload(MediaFile.uploader))

    # Teachers can only see their own uploaded media
    if current_user.role == "teacher":
        query = query.where(MediaFile.uploaded_by == current_user.id)

    # Apply filters
    if file_type:
        query = query.where(MediaFile.file_type == file_type)

    if tags:
        tag_list = [t.strip() for t in tags.split(',')]
        query = query.where(MediaFile.tags.overlap(tag_list))

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.where(
            or_(
                MediaFile.original_filename.ilike(search_pattern),
                MediaFile.description.ilike(search_pattern)
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(MediaFile.created_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    media_files = result.scalars().all()

    # Format response
    files = []
    for media in media_files:
        files.append(_to_media_response(media, media.uploader.full_name if media.uploader else "Unknown"))

    return MediaListResponse(
        files=files,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0
    )


@router.get("/stats/summary", response_model=MediaStatsResponse)
async def get_media_stats(
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Get media library statistics."""
    teacher_scope = MediaFile.uploaded_by == current_user.id if current_user.role == "teacher" else None

    # Total files by type
    by_type_query = (
        select(
            MediaFile.file_type,
            func.count(MediaFile.id).label('count'),
            func.sum(MediaFile.file_size).label('total_size')
        )
        .group_by(MediaFile.file_type)
    )
    if teacher_scope is not None:
        by_type_query = by_type_query.where(teacher_scope)
    by_type_result = await db.execute(by_type_query)
    by_type_data = by_type_result.fetchall()

    # Total storage used
    total_size_query = select(func.sum(MediaFile.file_size))
    if teacher_scope is not None:
        total_size_query = total_size_query.where(teacher_scope)
    total_size_result = await db.execute(total_size_query)
    total_size = total_size_result.scalar() or 0

    # Total files
    total_files = sum(row[1] for row in by_type_data)

    # Most used tags
    tags_query = select(func.unnest(MediaFile.tags).label('tag')).where(MediaFile.tags.isnot(None))
    if teacher_scope is not None:
        tags_query = tags_query.where(teacher_scope)
    tags_result = await db.execute(tags_query)
    all_tags = [row[0] for row in tags_result.fetchall()]
    from collections import Counter
    tag_counts = Counter(all_tags)

    return MediaStatsResponse(
        by_type=[
            {
                "file_type": row[0],
                "count": row[1],
                "total_size": row[2] or 0
            }
            for row in by_type_data
        ],
        total_files=total_files,
        total_size_bytes=total_size,
        total_size_mb=round(total_size / 1024 / 1024, 2),
        top_tags=[
            {"tag": tag, "count": count}
            for tag, count in tag_counts.most_common(10)
        ]
    )


@router.get("/{media_id}", response_model=MediaFileResponse)
async def get_media(
    media_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Get media file details."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(MediaFile)
        .options(selectinload(MediaFile.uploader))
        .where(MediaFile.id == media_id)
    )
    media = result.scalar_one_or_none()

    if not media:
        raise HTTPException(404, "File tidak ditemukan")

    if current_user.role == "teacher" and media.uploaded_by != current_user.id:
        raise HTTPException(403, "Tidak memiliki akses ke file ini")

    # Increment usage counter
    media.usage_count = (media.usage_count or 0) + 1
    media.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return _to_media_response(media, media.uploader.full_name if media.uploader else "Unknown")


@router.patch("/{media_id}", response_model=MediaFileResponse)
async def update_media_metadata(
    media_id: int,
    update_data: MediaFileUpdate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Update media metadata (tags, description)."""
    result = await db.execute(
        select(MediaFile).where(MediaFile.id == media_id)
    )
    media = result.scalar_one_or_none()

    if not media:
        raise HTTPException(404, "File tidak ditemukan")

    # Authorization: only uploader or admin can update
    if media.uploaded_by != current_user.id and not is_admin_scope_role(current_user.role):
        raise HTTPException(403, "Tidak memiliki akses untuk mengubah file ini")

    # Update fields
    if update_data.tags is not None:
        cleaned_tags = _clean_tags(update_data.tags)
        media.tags = cleaned_tags if cleaned_tags else None
    if update_data.description is not None:
        media.description = _clean_text(update_data.description)

    media.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(media)

    return _to_media_response(media, current_user.full_name)


@router.delete("/{media_id}")
async def delete_media(
    media_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Delete media file (uploader or admin only)."""
    result = await db.execute(
        select(MediaFile).where(MediaFile.id == media_id)
    )
    media = result.scalar_one_or_none()

    if not media:
        raise HTTPException(404, "File tidak ditemukan")

    # Authorization
    if media.uploaded_by != current_user.id and not is_admin_scope_role(current_user.role):
        raise HTTPException(403, "Tidak memiliki akses untuk menghapus file ini")

    # Delete physical file
    try:
        file_path = Path(media.file_path)
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        logger.error(f"Failed to delete file: {e}", exc_info=True)

    # Delete database record
    await db.delete(media)
    await db.commit()

    return {"message": "File berhasil dihapus"}
