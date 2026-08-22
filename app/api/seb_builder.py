"""
SEB Builder API Endpoints
Build, configure, and distribute Safe Exam Browser .seb files for PC platforms
"""
from fastapi import APIRouter, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from datetime import datetime
from pathlib import Path
from typing import Optional
import hashlib
import os
import logging

from app.database import get_db
from app.models.user import User
from app.models.seb_build import SebBuild
from app.models.seb_config_template import SebConfigTemplate
from app.core.security import get_current_active_admin
from app.core.roles import is_admin_scope_role
from app.config import settings  # Fixed: was app.core.config
from app.core.feature_flags import require_feature_enabled
from app.core.seb import generate_seb_config


def _require_seb_builder_enabled() -> None:
    require_feature_enabled(settings.seb_desktop_legacy_enabled, "seb_desktop_legacy")


router = APIRouter(
    prefix="/api/v1/seb-builder",
    tags=["SEB Builder"],
    dependencies=[Depends(_require_seb_builder_enabled)],
)
logger = logging.getLogger(__name__)

# Directories
BUILD_DIR = Path("static/seb/builds")
BUILD_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# CONFIGURATION MANAGEMENT
# ============================================================================

@router.post("/configure")
async def configure_seb(
    build_name: str = Form(...),
    start_url: str = Form(...),
    platform: str = Form("all"),
    admin_password: str = Form("admin123"),
    quit_password: str = Form("quit123"),
    config_key: Optional[str] = Form(None),
    browser_exam_key: Optional[str] = Form(None),
    use_permissive_filter: bool = Form(True),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Validate and preview SEB configuration.
    Admin only.
    """
    # Use defaults if not provided
    config_key = config_key or settings.seb_default_config_key
    browser_exam_key = browser_exam_key or settings.seb_default_browser_exam_key

    return {
        "success": True,
        "build_name": build_name,
        "start_url": start_url,
        "platform": platform,
        "config_key": config_key,
        "browser_exam_key": browser_exam_key,
        "use_permissive_filter": use_permissive_filter,
        "message": "Configuration validated successfully"
    }


# ============================================================================
# BUILD MANAGEMENT
# ============================================================================

@router.post("/build")
async def create_seb_build(
    build_name: str = Form(...),
    start_url: str = Form(...),
    platform: str = Form("all"),
    admin_password: str = Form("admin123"),
    quit_password: str = Form("quit123"),
    config_key: Optional[str] = Form(None),
    browser_exam_key: Optional[str] = Form(None),
    use_permissive_filter: bool = Form(True),
    config_data: Optional[str] = Form("{}"),  # JSON string
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new SEB build and generate .seb file.
    Admin only.
    """
    import json

    # Parse config_data JSON
    try:
        config_dict = json.loads(config_data) if config_data else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid config_data JSON")

    # Hash passwords
    admin_hash = hashlib.sha256(admin_password.encode()).hexdigest()
    quit_hash = hashlib.sha256(quit_password.encode()).hexdigest()

    # Use defaults if not provided
    config_key = config_key or settings.seb_default_config_key
    browser_exam_key = browser_exam_key or settings.seb_default_browser_exam_key

    # Create build record
    build = SebBuild(
        build_name=build_name,
        platform=platform,
        start_url=start_url,
        config_data=config_dict,
        config_key=config_key,
        browser_exam_key=browser_exam_key,
        admin_password_hash=admin_hash,
        quit_password_hash=quit_hash,
        status="pending",
        created_by=current_user.id
    )
    db.add(build)
    await db.commit()
    await db.refresh(build)

    # Generate .seb file immediately (synchronous for now)
    try:
        # Generate SEB configuration
        seb_bytes = generate_seb_config(
            exam_id=build.id,
            exam_url=start_url,
            admin_password=admin_password,
            quit_password=quit_password,
            config_key=config_key,
            browser_exam_key=browser_exam_key,
            use_permissive_filter=use_permissive_filter
        )

        # Save to file
        build_dir = BUILD_DIR / str(build.id)
        build_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{build_name.replace(' ', '_').lower()}.seb"
        file_path = build_dir / filename

        with open(file_path, "wb") as f:
            f.write(seb_bytes)

        # Update build record
        build.status = "success"
        build.file_path = str(file_path)
        build.file_size = len(seb_bytes)
        build.completed_at = datetime.now()  # Indonesia local time (WIB)

        await db.commit()

        return {
            "success": True,
            "build_id": build.id,
            "status": "success",
            "file_size": len(seb_bytes),
            "download_url": f"/api/v1/seb-builder/download/{build.id}",
            "message": "SEB configuration file generated successfully"
        }

    except Exception as e:
        logger.exception("SEB build failed for '%s'", build_name)

        build.status = "failed"
        build.error_message = str(e)
        build.completed_at = datetime.now()  # Indonesia local time (WIB)
        await db.commit()

        raise HTTPException(500, "Build failed")


@router.get("/builds")
async def list_builds(
    limit: int = 50,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List all SEB builds with pagination and filtering.
    Public endpoint for admin panel.
    """
    query = select(SebBuild).order_by(desc(SebBuild.created_at))

    # Apply filters
    if platform:
        query = query.where(SebBuild.platform == platform)
    if status:
        query = query.where(SebBuild.status == status)

    query = query.limit(limit)

    result = await db.execute(query)
    builds = result.scalars().all()

    return {
        "builds": [build.to_dict() for build in builds],
        "total": len(builds)
    }


@router.get("/download/{build_id}")
async def download_seb(
    build_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Download generated .seb configuration file.
    Admin only.
    """
    result = await db.execute(
        select(SebBuild).where(SebBuild.id == build_id)
    )
    build = result.scalar_one_or_none()

    if not build:
        raise HTTPException(404, "Build not found")

    if build.status != "success":
        raise HTTPException(400, f"Build not ready. Status: {build.status}")

    if not build.file_path or not os.path.exists(build.file_path):
        raise HTTPException(404, "SEB file not found")

    return FileResponse(
        build.file_path,
        media_type="application/x-sebconfig",
        filename=f"{build.build_name.replace(' ', '_')}.seb"
    )


@router.delete("/builds/{build_id}")
async def delete_build(
    build_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a build record and its file.
    Admin only.
    """
    result = await db.execute(
        select(SebBuild).where(SebBuild.id == build_id)
    )
    build = result.scalar_one_or_none()

    if not build:
        raise HTTPException(404, "Build not found")

    # Delete file if exists
    if build.file_path and os.path.exists(build.file_path):
        os.remove(build.file_path)
        # Try to remove directory if empty
        try:
            os.rmdir(os.path.dirname(build.file_path))
        except OSError:
            pass  # Directory not empty or doesn't exist

    await db.delete(build)
    await db.commit()

    return {"success": True, "message": "Build deleted successfully"}


# ============================================================================
# TEMPLATE MANAGEMENT
# ============================================================================

@router.get("/templates")
async def list_templates(
    include_public: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """
    List all configuration templates.
    Returns public and default templates.
    Public endpoint for admin panel.
    """
    from sqlalchemy.orm import selectinload

    query = select(SebConfigTemplate)\
        .options(selectinload(SebConfigTemplate.creator))\
        .order_by(desc(SebConfigTemplate.is_default), desc(SebConfigTemplate.created_at))

    # Show public templates and default presets
    query = query.where(
        or_(
            SebConfigTemplate.is_public == True,
            SebConfigTemplate.is_default == True
        )
    )

    result = await db.execute(query)
    templates = result.scalars().all()

    return {
        "templates": [template.to_dict() for template in templates],
        "total": len(templates)
    }


@router.get("/presets/{preset_type}")
async def get_preset_by_type(
    preset_type: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific preset configuration by type.
    Returns hardcoded fallback if database presets not available.
    Public endpoint - no authentication required.

    preset_type: "strict", "standard", or "permissive"
    """
    # Hardcoded fallback presets (always available)
    FALLBACK_PRESETS = {
        "strict": {
            "id": 0,
            "name": "Strict Security",
            "description": "Maximum security for high-stakes exams",
            "preset_type": "strict",
            "is_default": True,
            "is_public": True,
            "config_data": {
                "browserWindowAllowReload": False,
                "allowBrowsingBackForward": False,
                "enableBrowserWindowToolbar": False,
                "enableZoomPage": False,
                "allowScreenShot": False,
                "enableAltTab": False,
                "killExplorerShell": True,
                "enableF12": False,
                "monitorProcesses": True
            }
        },
        "standard": {
            "id": 0,
            "name": "Standard Balanced",
            "description": "Balanced security and usability",
            "preset_type": "standard",
            "is_default": True,
            "is_public": True,
            "config_data": {
                "browserWindowAllowReload": True,
                "allowBrowsingBackForward": False,
                "enableBrowserWindowToolbar": True,
                "enableZoomPage": True,
                "allowScreenShot": False,
                "enableAltTab": False,
                "killExplorerShell": False,
                "enableF12": False,
                "monitorProcesses": True
            }
        },
        "permissive": {
            "id": 0,
            "name": "Permissive Dev",
            "description": "Minimal restrictions for testing",
            "preset_type": "permissive",
            "is_default": True,
            "is_public": True,
            "config_data": {
                "browserWindowAllowReload": True,
                "allowBrowsingBackForward": True,
                "enableBrowserWindowToolbar": True,
                "enableZoomPage": True,
                "allowScreenShot": True,
                "enableAltTab": True,
                "killExplorerShell": False,
                "enableF12": True,
                "monitorProcesses": False
            }
        }
    }

    # Validate preset type
    valid_types = ["strict", "standard", "permissive"]
    if preset_type not in valid_types:
        raise HTTPException(400, f"Invalid preset type. Must be one of: {', '.join(valid_types)}")

    # Try to get preset from database
    try:
        result = await db.execute(
            select(SebConfigTemplate).where(
                SebConfigTemplate.preset_type == preset_type,
                SebConfigTemplate.is_default == True
            )
        )
        preset = result.scalar_one_or_none()

        if preset:
            return preset.to_dict()
    except Exception as e:
        # Database error - will use fallback
        import logging
        logging.getLogger(__name__).warning(f"Database error loading preset: {e}")

    # Return hardcoded fallback
    return FALLBACK_PRESETS[preset_type]



@router.get("/templates/{template_id}")
async def get_template(
    template_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get specific template configuration.
    Admin only.
    """
    result = await db.execute(
        select(SebConfigTemplate).where(SebConfigTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(404, "Template not found")

    # Check access (owner or public)
    if template.created_by != current_user.id and not template.is_public:
        raise HTTPException(403, "Access denied to this template")

    return template.to_dict()


@router.post("/templates")
async def create_template(
    name: str = Form(...),
    description: str = Form(""),
    config_data: str = Form("{}"),  # JSON string
    preset_type: str = Form("custom"),
    is_public: bool = Form(False),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new configuration template from current settings.
    Admin only.
    """
    import json

    try:
        config_dict = json.loads(config_data)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid config_data JSON")

    # Check if template name already exists for this user
    existing = await db.execute(
        select(SebConfigTemplate).where(
            SebConfigTemplate.name == name,
            SebConfigTemplate.created_by == current_user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Template '{name}' already exists")

    template = SebConfigTemplate(
        name=name,
        description=description,
        config_data=config_dict,
        preset_type=preset_type,
        is_public=is_public,
        created_by=current_user.id
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return {
        "success": True,
        "template": template.to_dict(),
        "message": "Template created successfully"
    }


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete configuration template.
    Admin only. Can only delete own templates (unless admin).
    """
    result = await db.execute(
        select(SebConfigTemplate).where(SebConfigTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(404, "Template not found")

    # Check ownership (only owner can delete, or if it's default and user is admin)
    if template.created_by != current_user.id:
        if not (is_admin_scope_role(current_user.role) and template.is_default):
            raise HTTPException(403, "Cannot delete this template")

    # Prevent deletion of default templates by non-admins
    if template.is_default and not is_admin_scope_role(current_user.role):
        raise HTTPException(403, "Cannot delete default templates")

    await db.delete(template)
    await db.commit()

    return {"success": True, "message": "Template deleted successfully"}
