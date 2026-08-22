import asyncio
import os
import uuid
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from app.core.security import get_current_teacher

router = APIRouter(prefix="/api/upload", tags=["upload"])
logger = logging.getLogger(__name__)

UPLOAD_DIR = "static/uploads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB for videos
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB for images (increased from 5MB)

# Expanded image format support
ALLOWED_IMAGE_TYPES = [
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",      # BMP support
    "image/tiff",     # TIFF support
    "image/x-icon"    # ICO support
]

ALLOWED_VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime", "video/x-msvideo"]

# Audio format support for listening questions
ALLOWED_AUDIO_TYPES = [
    "audio/mpeg",      # MP3
    "audio/mp3",       # MP3 (alternative MIME type)
    "audio/wav",       # WAV
    "audio/wave",      # WAV (alternative MIME type)
    "audio/x-wav",     # WAV (alternative MIME type)
    "audio/ogg",       # OGG
    "audio/aac",       # AAC
    "audio/mp4",       # M4A
    "audio/x-m4a",     # M4A (alternative MIME type)
    "audio/webm"       # WebM audio
]

MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50MB for audio files


def _measure_upload_size(upload_file: UploadFile) -> int:
    current_position = upload_file.file.tell()
    upload_file.file.seek(0, os.SEEK_END)
    size = int(upload_file.file.tell() or 0)
    upload_file.file.seek(current_position)
    return size


def _save_upload_stream(upload_file: UploadFile, file_path: str) -> None:
    upload_file.file.seek(0)
    with open(file_path, "wb") as buffer:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)

@router.post("/image", response_model=dict)
async def upload_image(file: UploadFile = File(...), current_user = Depends(get_current_teacher)):
    """Upload image, video, or audio file for questions"""
    # ✅ SECURITY FIX #2: Enhanced file upload validation
    from app.core.sanitization import validate_file_upload, sanitize_filename

    # Ensure directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Determine file type
    is_video = file.content_type in ALLOWED_VIDEO_TYPES
    is_image = file.content_type in ALLOWED_IMAGE_TYPES
    is_audio = file.content_type in ALLOWED_AUDIO_TYPES

    if is_image:
        max_size = MAX_IMAGE_SIZE
        allowed_types = ALLOWED_IMAGE_TYPES
    elif is_video:
        max_size = MAX_FILE_SIZE
        allowed_types = ALLOWED_VIDEO_TYPES
    elif is_audio:
        max_size = MAX_AUDIO_SIZE
        allowed_types = ALLOWED_AUDIO_TYPES
    else:
        raise HTTPException(400, "File type is not allowed")

    file_size = await asyncio.to_thread(_measure_upload_size, file)
    validate_file_upload(
        content_type=file.content_type,
        file_size=file_size,
        filename=file.filename,
        max_size=max_size,
        allowed_types=allowed_types
    )

    # Reset file position
    await file.seek(0)

    # Sanitize original filename
    safe_original_name = sanitize_filename(file.filename)

    # Generate unique filename
    ext = os.path.splitext(safe_original_name)[1].lower()
    if not ext:
        ext = ".jpg" if is_image else ".mp4" if is_video else ".mp3"

    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        await asyncio.to_thread(_save_upload_stream, file, file_path)
    except Exception:
        logger.exception("Failed to save uploaded file")
        raise HTTPException(500, "Failed to save file")

    # Determine file type for response
    file_type = "image"
    if is_video:
        file_type = "video"
    elif is_audio:
        file_type = "audio"

    return {"url": f"/static/uploads/{filename}", "type": file_type}
