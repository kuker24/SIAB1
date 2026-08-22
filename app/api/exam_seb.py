"""
SEB (Safe Exam Browser) configuration API endpoints.
Handles SEB config file generation, QR codes, and mobile launch URLs.
"""
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import qrcode

from app.database import get_db
from app.models.exam import Exam
from app.models.user import User
from app.schemas.exam import SEBLaunchResponse
from app.core.seb import generate_seb_config, get_mobile_launch_url
from app.core.security import get_current_teacher
from app.config import settings
from app.core.feature_flags import require_feature_enabled
from app.core.roles import is_developer_exam_hidden_for_viewer

router = APIRouter(prefix="/api/exams", tags=["SEB Configuration"])
public_router = APIRouter(prefix="/api/exams", tags=["SEB Configuration"])


async def _assert_exam_owner_or_admin(db: AsyncSession, exam: Exam, current_user: User) -> None:
    """Ensure SEB exam config endpoints are only accessible by exam owner or admin."""
    creator_role_result = await db.execute(select(User.role).where(User.id == exam.creator_id))
    creator_role = creator_role_result.scalar_one_or_none()
    if is_developer_exam_hidden_for_viewer(current_user.role, creator_role):
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")
    if exam.creator_id != current_user.id and not bool(getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke konfigurasi SEB ujian ini")


# ============== PUBLIC SEB ENDPOINTS ==============

@public_router.get("/default-seb-config.seb")
async def download_default_seb_config():
    """Download default/global SEB configuration file for student login."""
    require_feature_enabled(settings.seb_desktop_legacy_enabled, "seb_desktop_legacy")
    # Generate config pointing to student login page
    login_url = f"{settings.base_url}/student/"
    seb_config = generate_seb_config(
        exam_id=0,
        exam_url=login_url,
        config_key=settings.seb_default_config_key,
        browser_exam_key=settings.seb_default_browser_exam_key
    )

    return Response(
        content=seb_config,
        media_type="application/seb",
        headers={
            "Content-Disposition": 'attachment; filename="siab1-seb-config.seb"',
            "Cache-Control": "public, max-age=86400"
        }
    )


@public_router.get("/seb-qrcode")
async def get_seb_qrcode(url: str = None):
    """Generate QR code for SEB config download URL."""
    require_feature_enabled(settings.seb_qr_enabled, "seb_qr")
    if not url:
        url = f"{settings.base_url}/api/exams/default-seb-config.seb"

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"}
    )


# ============== AUTHENTICATED SEB ENDPOINTS ==============

@router.get("/{exam_id}/seb-config.seb")
async def download_seb_config(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Download SEB configuration file."""
    require_feature_enabled(settings.seb_desktop_legacy_enabled, "seb_desktop_legacy")
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")
    await _assert_exam_owner_or_admin(db, exam, current_user)

    # Generate config
    exam_url = f"{settings.base_url}/exam/{exam_id}/start"
    seb_config = generate_seb_config(
        exam_id=exam_id,
        exam_url=exam_url,
        config_key=exam.seb_config_key,
        browser_exam_key=exam.seb_browser_exam_key
    )

    return Response(
        content=seb_config,
        media_type="application/seb",
        headers={
            "Content-Disposition": f'attachment; filename="exam_{exam_id}.seb"',
            "Cache-Control": "public, max-age=3600"
        }
    )


@router.get("/{exam_id}/seb-launch-mobile", response_model=SEBLaunchResponse)
async def get_mobile_launch(
    exam_id: int,
    platform: str = Query(..., pattern="^(ios|android)$"),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Get mobile SEB launch URL."""
    require_feature_enabled(settings.seb_qr_enabled, "seb_qr")
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")
    await _assert_exam_owner_or_admin(db, exam, current_user)

    launch_data = get_mobile_launch_url(exam_id, platform)
    return SEBLaunchResponse(**launch_data)


@router.get("/{exam_id}/seb-qr")
async def generate_seb_qr(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Generate QR code for SEB config download."""
    require_feature_enabled(settings.seb_qr_enabled, "seb_qr")
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")
    await _assert_exam_owner_or_admin(db, exam, current_user)

    # Generate QR code
    config_url = f"{settings.base_url}/api/exams/{exam_id}/seb-config.seb"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(config_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")
