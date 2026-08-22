"""
Security utilities for input sanitization and validation.
Protects against XSS, injection attacks, and malicious inputs.
"""
import html
import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException


def sanitize_html(text: str) -> str:
    """
    Sanitize HTML input to prevent XSS attacks.
    Removes all HTML tags and leaves only plain text.

    Args:
        text: Input text that may contain HTML

    Returns:
        Sanitized text with HTML removed

    Example:
        >>> sanitize_html("Hello <script>alert('xss')</script>")
        "Hello alert('xss')"
    """
    if not text:
        return text

    # Normalize existing HTML entities first so edits of old content do not
    # keep double-encoded quotes like &quot; or &#x27; in stored question text.
    clean_text = html.unescape(str(text))

    # Remove HTML tags using regex. This keeps the inner text while preventing
    # script/markup from being persisted as active HTML.
    clean_text = re.sub(r'<[^>]+>', '', clean_text)

    # Keep storage as readable plain text for quote characters. Rendering layers
    # escape output before inserting into HTML, so storing &quot;/&#x27; causes
    # double-escape artifacts in exam simulation.
    clean_text = clean_text.replace('<', '&lt;')
    clean_text = clean_text.replace('>', '&gt;')

    return clean_text


def sanitize_optional_text(text: Optional[str], *, max_length: Optional[int] = None) -> Optional[str]:
    """Sanitize optional text input and preserve ``None`` semantics."""
    if text is None:
        return None

    cleaned = sanitize_html(str(text)).strip()
    if max_length is not None:
        cleaned = cleaned[:max_length]
    return cleaned


def sanitize_safe_media_url(url: Optional[str]) -> Optional[str]:
    """
    Allow only same-origin relative URLs or absolute HTTP(S) URLs.

    This blocks ``javascript:``, ``data:``, and similar dangerous schemes that
    could otherwise be injected into ``src``/``href`` attributes.
    """
    if url is None:
        return None

    cleaned = str(url).strip()
    if not cleaned:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme:
        if parsed.scheme.lower() not in {"http", "https"}:
            raise HTTPException(status_code=400, detail="URL media tidak valid")
        return cleaned

    if cleaned.startswith("/"):
        return cleaned

    raise HTTPException(status_code=400, detail="URL media harus relatif atau HTTP/HTTPS")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal attacks.

    Args:
        filename: Original filename

    Returns:
        Safe filename
    """
    # Remove path separators
    safe_name = filename.replace('/', '_').replace('\\', '_')

    # Remove potentially dangerous characters
    safe_name = re.sub(r'[^\w\s\-\.]', '', safe_name)

    # Limit length
    if len(safe_name) > 255:
        safe_name = safe_name[:255]

    return safe_name


def validate_password_strength(password: str) -> bool:
    """
    Validate password meets security requirements.

    Requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 number

    Args:
        password: Password to validate

    Raises:
        HTTPException: If password doesn't meet requirements

    Returns:
        True if password is valid
    """
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password minimal 8 karakter"
        )

    if not re.search(r'[A-Z]', password):
        raise HTTPException(
            status_code=400,
            detail="Password harus mengandung minimal 1 huruf BESAR (A-Z)"
        )

    if not re.search(r'[a-z]', password):
        raise HTTPException(
            status_code=400,
            detail="Password harus mengandung minimal 1 huruf kecil (a-z)"
        )

    if not re.search(r'[0-9]', password):
        raise HTTPException(
            status_code=400,
            detail="Password harus mengandung minimal 1 angka (0-9)"
        )

    return True


def validate_file_upload(
    content_type: str,
    file_size: int,
    filename: str,
    max_size: int = 5 * 1024 * 1024,  # 5MB
    allowed_types: Optional[list] = None
) -> bool:
    """
    Validate uploaded file.

    Args:
        content_type: MIME type of file
        file_size: Size in bytes
        filename: Original filename
        max_size: Maximum allowed size in bytes
        allowed_types: List of allowed MIME types

    Raises:
        HTTPException: If validation fails

    Returns:
        True if file is valid
    """
    if allowed_types is None:
        allowed_types = ['image/jpeg', 'image/png', 'image/gif']

    # Check file size
    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File terlalu besar! Maksimal {max_mb:.1f}MB"
        )

    # Check MIME type
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Tipe file tidak diperbolehkan. Hanya: {', '.join(allowed_types)}"
        )

    # Expanded allowed extensions map
    allowed_extensions_map = {
        'image/jpeg': ['.jpg', '.jpeg'],
        'image/png': ['.png'],
        'image/gif': ['.gif'],
        'image/webp': ['.webp'],
        'image/bmp': ['.bmp'],
        'image/tiff': ['.tiff', '.tif'],
        'image/x-icon': ['.ico'],
        'video/mp4': ['.mp4'],
        'video/webm': ['.webm'],
        'video/quicktime': ['.mov'],
        'video/x-msvideo': ['.avi'],
        # Audio types
        'audio/mpeg': ['.mp3', '.m4a', '.mp4'],  # M4A/MP4 files often detected as audio/mpeg
        'audio/mp3': ['.mp3', '.m4a', '.mp4'],
        'audio/wav': ['.wav'],
        'audio/wave': ['.wav'],
        'audio/x-wav': ['.wav'],
        'audio/ogg': ['.ogg'],
        'audio/aac': ['.aac', '.m4a', '.mp4'],
        'audio/mp4': ['.m4a', '.mp4', '.mp3'],
        'audio/x-m4a': ['.m4a', '.mp4'],
        'audio/webm': ['.webm']
    }

    import os
    ext = os.path.splitext(filename)[1].lower()

    # If mime type is in our map, enforce extension match
    if content_type in allowed_extensions_map:
        if ext not in allowed_extensions_map[content_type]:
             raise HTTPException(
                status_code=400,
                detail=f"Ekstensi file tidak cocok dengan tipe konten ({content_type}). Diharapkan: {', '.join(allowed_extensions_map[content_type])}"
            )
    else:
        # If mime type allows generic/unknown but is in allowed_types list
        # Just ensure extension is not dangerous (blacklist check)
        dangerous_exts = ['.php', '.py', '.sh', '.exe', '.bat', '.cmd', '.js', '.html']
        if ext in dangerous_exts:
             raise HTTPException(
                status_code=400,
                detail="Tipe file berbahaya tidak diizinkan!"
            )

    return True
