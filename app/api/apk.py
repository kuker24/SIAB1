"""
APK Builder API Router
======================
API endpoints for APK configuration and download.
Provides server configuration for mobile apps and APK file serving.
"""
from pathlib import Path
from typing import Optional
from datetime import datetime
import asyncio
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.feature_flags import require_feature_enabled
from app.database import get_db, get_db_write, async_session_write
from app.core.apk_profiles import get_allowed_tokens, get_token_label
from app.models.system_settings import SystemSettings
from app.models.apk_build import ApkBuild
from app.models.user import User
from app.core.security import get_current_active_admin
from app.utils.apk_validation import APKTokenValidator

router = APIRouter(prefix="/api/v1/apk", tags=["APK Builder"])
legacy_builder_router = APIRouter(prefix="/api/v1/apk-builder", tags=["APK Builder Legacy"])

PROJECT_ROOT = Path(__file__).parent.parent.parent
APK_BUILD_DIR = PROJECT_ROOT / "apk_builds"
LEGACY_APK_DIR = PROJECT_ROOT / "static" / "apk"
LEGACY_APK_FILENAME = "secure-exam-browser.apk"
LEGACY_APK_BUILDS_DIR = LEGACY_APK_DIR / "builds"
LEGACY_APK_ICONS_DIR = LEGACY_APK_DIR / "icons"


def _iter_artifacts():
    """Collect APK/AAB artifacts from current and legacy locations."""
    artifacts = []

    if APK_BUILD_DIR.exists():
        for ext in ("*.apk", "*.aab"):
            for file in APK_BUILD_DIR.rglob(ext):
                if file.is_file():
                    artifacts.append(file)

    if LEGACY_APK_DIR.exists():
        legacy_file = LEGACY_APK_DIR / LEGACY_APK_FILENAME
        if legacy_file.is_file():
            artifacts.append(legacy_file)
        builds_dir = LEGACY_APK_DIR / "builds"
        if builds_dir.exists():
            for ext in ("*.apk", "*.aab"):
                for file in builds_dir.rglob(ext):
                    if file.is_file():
                        artifacts.append(file)

    # Deduplicate by resolved path and sort latest first.
    unique = {str(file.resolve()): file for file in artifacts}
    return sorted(unique.values(), key=lambda item: item.stat().st_mtime, reverse=True)


def _artifact_to_dict(file: Path):
    stat = file.stat()
    return {
        "filename": file.name,
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "modified": stat.st_mtime,
        "download_url": f"/api/v1/apk/download?filename={file.name}",
        "artifact_type": file.suffix.lower().replace(".", ""),
    }


def _find_legacy_build_artifact(build_id: int) -> Optional[Path]:
    candidates = []
    by_build_dir = LEGACY_APK_BUILDS_DIR / str(build_id)
    if by_build_dir.exists():
        for ext in ("*.apk", "*.aab"):
            candidates.extend([p for p in by_build_dir.glob(ext) if p.is_file()])

    if not candidates and APK_BUILD_DIR.exists():
        for ext in ("*.apk", "*.aab"):
            candidates.extend([p for p in APK_BUILD_DIR.glob(ext) if p.is_file()])

    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]


async def _run_legacy_apk_build_job(
    build_id: int,
    app_name: str,
    icon_path: Optional[str],
    build_mode: str,
) -> None:
    cmd = ["python3", "scripts/build_apk.py", str(build_id), app_name]
    if icon_path:
        cmd.append(icon_path)
    cmd.append(build_mode)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    stdout_text = (stdout or b"").decode("utf-8", errors="ignore")
    stderr_text = (stderr or b"").decode("utf-8", errors="ignore")
    combined_log = f"{stdout_text}\n{stderr_text}".strip()
    combined_log = combined_log[-200_000:]

    async with async_session_write() as db:
        result = await db.execute(select(ApkBuild).where(ApkBuild.id == build_id))
        build = result.scalar_one_or_none()
        if not build:
            return

        build.build_log = combined_log or build.build_log
        build.completed_at = datetime.now()

        artifact = _find_legacy_build_artifact(build_id)
        if process.returncode == 0 and artifact and artifact.exists():
            build.status = "success"
            build.file_path = str(artifact)
            build.file_size = int(artifact.stat().st_size)
            build.error_message = None
        else:
            build.status = "failed"
            err_msg = stderr_text.strip() or f"Build process exited with code {process.returncode}"
            build.error_message = err_msg[:4000]

        await db.commit()


@router.get("/config")
async def get_apk_config(request: Request):
    """
    Get server configuration for mobile app.

    This endpoint is called by the Android app to get:
    - Server URL
    - SEB configuration settings
    - App version info

    Returns:
        JSON with server configuration
    """
    # Get base URL from request
    protocol = request.headers.get("X-Forwarded-Proto", "http")
    host = request.headers.get("X-Forwarded-Host", request.headers.get("Host", "localhost:8000"))
    base_url = f"{protocol}://{host}"

    return {
        "status": "ok",
        "server": {
            "url": base_url,
            "name": settings.app_name,
            "version": "1.0.0",
        },
        "config": {
            "exam_url": f"{base_url}/student/",
            "api_url": f"{base_url}/api",
            "seb_config_url": f"{base_url}/api/seb/download-config",
            "qr_code_url": f"{base_url}/api/seb/qr-code",
        },
        "security": {
            "seb_required": True,
            "challenge_enabled": settings.seb_challenge_enabled,
            "strict_mode": settings.seb_strict_mode,
        },
        "app": {
            "min_version": "1.0.0",
            "update_url": None,
            "force_update": False,
        }
    }


@router.get("/download")
async def download_apk(filename: Optional[str] = None):
    """
    Download the Secure Exam Browser APK file.

    Returns:
        APK file for download
    """
    artifacts = _iter_artifacts()
    if not artifacts:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "APK_NOT_FOUND",
                "message": "Artifact Android belum tersedia. Silakan build APK/AAB terlebih dahulu.",
                "instructions": [
                    "1. Install Flutter SDK di komputer Anda",
                    "2. Clone project flutter_client_code",
                    "3. Jalankan builder GUI atau scripts/build_apk.py",
                    f"4. Pastikan output tersimpan di: {APK_BUILD_DIR}"
                ],
                "artifact_dir": str(APK_BUILD_DIR)
            }
        )

    selected = artifacts[0]
    if filename:
        selected = next((item for item in artifacts if item.name == filename), selected)

    media_type = "application/octet-stream"
    if selected.suffix.lower() == ".apk":
        media_type = "application/vnd.android.package-archive"

    return FileResponse(
        path=selected,
        media_type=media_type,
        filename=selected.name,
        headers={
            "Content-Disposition": f"attachment; filename={selected.name}"
        }
    )


@router.get("/info")
async def get_apk_info():
    """
    Get APK file information.

    Returns:
        JSON with APK availability and metadata
    """
    artifacts = _iter_artifacts()
    if not artifacts:
        return {
            "available": False,
            "message": "Artifact Android belum tersedia. Silakan build terlebih dahulu.",
            "build_instructions": {
                "step1": "cd flutter_client_code",
                "step2": "flutter pub get",
                "step3": "flutter build apk --release  # atau appbundle",
                "step4": f"Copy artifact ke {APK_BUILD_DIR}",
            },
            "artifact_dir": str(APK_BUILD_DIR),
        }

    latest = artifacts[0]
    return {
        "available": True,
        "latest": _artifact_to_dict(latest),
        "artifacts": [_artifact_to_dict(item) for item in artifacts[:10]],
    }


@router.get("/version")
async def get_app_version():
    """
    Get current app version info.

    Used by mobile app to check for updates.
    """
    return {
        "current_version": "1.0.0",
        "min_version": "1.0.0",
        "force_update": False,
        "update_message": None,
        "changelog": [
            {"version": "1.0.0", "changes": ["Initial release", "Kiosk mode", "Anti-cheat features"]}
        ]
    }


class TokenValidationRequest(BaseModel):
    token: str
    timestamp: Optional[int] = None


@router.post("/validate-token")
async def validate_apk_token(
    request: TokenValidationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Validate APK build token against server's minimum required token.

    This endpoint is called by the mobile app on startup to verify
    the APK version is still valid. Admin can set minimum required
    token to invalidate older APK versions.

    Returns:
        JSON with validation result
    """
    try:
        # Get system settings
        result = await db.execute(select(SystemSettings))
        settings = result.scalar_one_or_none()

        # Validation is intentionally disabled by admin (tokens remain stored)
        if settings and bool(getattr(settings, "token_validation_bypass", False)):
            return {
                "valid": True,
                "message": "",
                "update_required": False,
                "validation_enabled": False,
            }

        # If no settings or no minimum token set, allow all
        if not settings or not settings.minimum_apk_token:
            return {
                "valid": True,
                "message": "",
                "update_required": False
            }

        app_token = request.token.strip()
        if not APKTokenValidator.validate_token_format(app_token):
            return {
                "valid": False,
                "message": "Token aplikasi tidak valid. Silakan install ulang APK resmi.",
                "update_required": True,
            }

        allowed_tokens = get_allowed_tokens(settings.minimum_apk_token)
        if not allowed_tokens:
            return {
                "valid": False,
                "message": "Tidak ada profil token APK yang aktif. Hubungi admin.",
                "update_required": True,
                "accepted_tokens": [],
            }
        if allowed_tokens and app_token not in allowed_tokens:
            return {
                "valid": False,
                "message": "Versi aplikasi tidak sesuai. Silakan gunakan APK stable/new update resmi dari admin.",
                "update_required": True,
                "current_token": app_token,
                "accepted_tokens": allowed_tokens,
            }
        return {
            "valid": True,
            "message": "",
            "update_required": False,
            "accepted_label": get_token_label(settings.minimum_apk_token, app_token),
        }

    except Exception:
        # On error, allow app to continue (fail-open for availability)
        return {
            "valid": True,
            "message": "",
            "update_required": False,
        }


# ============================================================================
# Legacy APK Builder Compatibility Endpoints
# ============================================================================


@legacy_builder_router.post("/build")
async def legacy_build_apk(
    app_name: str = Form(...),
    package_name: str = Form("com.ujianonline.seb"),
    server_url: str = Form(""),
    build_mode: str = Form("universal_apk"),
    icon: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_write),
):
    """
    Backward-compatible endpoint for old SEB builder UI.
    Creates a build record and runs scripts/build_apk.py asynchronously.
    """
    require_feature_enabled(
        settings.apk_build_endpoint_enabled,
        "apk_build_endpoint",
        status_code=503,
        message="Build APK dari server production sedang dinonaktifkan. Gunakan build lokal/CI.",
    )
    if build_mode not in {"universal_apk", "split_apk", "app_bundle"}:
        build_mode = "universal_apk"

    build = ApkBuild(
        app_name=app_name,
        package_name=package_name or "com.ujianonline.seb",
        status="building",
        build_log="Build queued. Waiting worker process...",
        created_by=current_user.id,
        error_message=None,
    )
    db.add(build)
    await db.commit()
    await db.refresh(build)

    icon_path: Optional[str] = None
    if icon and icon.filename:
        ext = Path(icon.filename).suffix.lower() or ".png"
        safe_ext = ext if ext in {".png", ".jpg", ".jpeg", ".webp"} else ".png"
        icon_dir = LEGACY_APK_ICONS_DIR / str(build.id)
        icon_dir.mkdir(parents=True, exist_ok=True)
        icon_file = icon_dir / f"icon{safe_ext}"
        icon_bytes = await icon.read()
        icon_file.write_bytes(icon_bytes)
        icon_path = str(icon_file)
        build.icon_path = icon_path
        build.build_log = (
            (build.build_log or "")
            + f"\nServer URL: {server_url or '-'}"
            + f"\nIcon uploaded: {icon.filename}"
        )
    else:
        build.build_log = (build.build_log or "") + f"\nServer URL: {server_url or '-'}"

    await db.commit()
    asyncio.create_task(_run_legacy_apk_build_job(build.id, app_name, icon_path, build_mode))

    return {
        "success": True,
        "build_id": build.id,
        "status": "building",
        "message": "Build APK dimulai. Silakan pantau status secara berkala.",
    }


@legacy_builder_router.get("/status/{build_id}")
async def legacy_apk_build_status(
    build_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ApkBuild).where(ApkBuild.id == build_id))
    build = result.scalar_one_or_none()
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    return build.to_dict()


@legacy_builder_router.get("/builds")
@legacy_builder_router.get("/builds/")
async def legacy_list_apk_builds(
    limit: int = 20,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    safe_limit = min(max(limit, 1), 100)
    result = await db.execute(
        select(ApkBuild).order_by(ApkBuild.created_at.desc()).limit(safe_limit)
    )
    builds = result.scalars().all()
    return {"builds": [item.to_dict() for item in builds], "total": len(builds)}


@legacy_builder_router.delete("/builds/{build_id}")
async def legacy_delete_apk_build(
    build_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_write),
):
    result = await db.execute(select(ApkBuild).where(ApkBuild.id == build_id))
    build = result.scalar_one_or_none()
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")

    if build.file_path:
        path_obj = Path(build.file_path)
        if path_obj.exists():
            try:
                path_obj.unlink()
            except OSError:
                pass

    build_dir = LEGACY_APK_BUILDS_DIR / str(build_id)
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
    icon_dir = LEGACY_APK_ICONS_DIR / str(build_id)
    if icon_dir.exists():
        shutil.rmtree(icon_dir, ignore_errors=True)

    await db.delete(build)
    await db.commit()
    return {"success": True, "message": "Build deleted", "build_id": build_id}


@legacy_builder_router.get("/download/{build_id}")
async def legacy_download_apk_build(
    build_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_write),
):
    result = await db.execute(select(ApkBuild).where(ApkBuild.id == build_id))
    build = result.scalar_one_or_none()
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    if build.status != "success":
        raise HTTPException(status_code=400, detail=f"Build not ready. Status: {build.status}")

    artifact_path = Path(build.file_path) if build.file_path else None
    if not artifact_path or not artifact_path.exists():
        recovered = _find_legacy_build_artifact(build_id)
        if recovered and recovered.exists():
            artifact_path = recovered
            build.file_path = str(recovered)
            build.file_size = int(recovered.stat().st_size)
            await db.commit()

    if not artifact_path or not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Build artifact not found")

    media_type = "application/octet-stream"
    if artifact_path.suffix.lower() == ".apk":
        media_type = "application/vnd.android.package-archive"

    return FileResponse(
        path=artifact_path,
        media_type=media_type,
        filename=artifact_path.name,
        headers={"Content-Disposition": f"attachment; filename={artifact_path.name}"},
    )
