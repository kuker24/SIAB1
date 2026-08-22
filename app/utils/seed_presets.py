"""
SEB Preset Seeder Utility
Creates default SEB configuration presets if they don't exist
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database import async_session_maker
from app.models.seb_config_template import SebConfigTemplate
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEB_PRESET_LOCK_KEY = 918273645

# Default preset configurations
PRESET_CONFIGS = {
    "strict": {
        "name": "Strict Security",
        "description": "Maximum security for high-stakes exams",
        "preset_type": "strict",
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
        },
        "is_default": True,
        "is_public": True
    },
    "standard": {
        "name": "Standard Balanced",
        "description": "Balanced security and usability",
        "preset_type": "standard",
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
        },
        "is_default": True,
        "is_public": True
    },
    "permissive": {
        "name": "Permissive Dev",
        "description": "Minimal restrictions for testing",
        "preset_type": "permissive",
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
        },
        "is_default": True,
        "is_public": True
    }
}


async def seed_default_presets(db: AsyncSession) -> dict:
    """
    Seed default SEB presets into the database
    Returns dict with status and created presets
    """
    created = []
    updated = []
    skipped = []
    deduplicated = []
    lock_acquired = False

    try:
        # Prevent race-condition when multiple containers start at once.
        lock_result = await db.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": SEB_PRESET_LOCK_KEY},
        )
        lock_acquired = bool(lock_result.scalar())
        if not lock_acquired:
            logger.info("SEB preset seeding skipped: advisory lock busy.")
            return {
                "created": created,
                "updated": updated,
                "skipped": list(PRESET_CONFIGS.keys()),
                "deduplicated": deduplicated,
                "total": len(PRESET_CONFIGS),
                "lock_acquired": False,
            }

        for preset_type, preset_data in PRESET_CONFIGS.items():
            result = await db.execute(
                select(SebConfigTemplate)
                .where(
                    SebConfigTemplate.preset_type == preset_type,
                    SebConfigTemplate.is_default == True,
                )
                .order_by(SebConfigTemplate.id.asc())
            )
            rows = result.scalars().all()
            existing = rows[0] if rows else None

            if len(rows) > 1:
                for duplicate in rows[1:]:
                    await db.delete(duplicate)
                deduplicated.append(preset_type)
                logger.warning(
                    "Removed %s duplicate default preset rows for type '%s'",
                    len(rows) - 1,
                    preset_type,
                )

            if existing:
                existing.name = preset_data["name"]
                existing.description = preset_data["description"]
                existing.config_data = preset_data["config_data"]
                existing.is_public = preset_data["is_public"]
                existing.is_default = True
                updated.append(preset_type)
                logger.info("Updated preset: %s", preset_type)
            else:
                template = SebConfigTemplate(
                    name=preset_data["name"],
                    description=preset_data["description"],
                    preset_type=preset_data["preset_type"],
                    config_data=preset_data["config_data"],
                    is_default=preset_data["is_default"],
                    is_public=preset_data["is_public"],
                    created_by=None,  # System preset
                )
                db.add(template)
                created.append(preset_type)
                logger.info("Created preset: %s", preset_type)

        # Guardrail: prevent duplicates for default canonical presets.
        await db.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_seb_default_core_presets
                ON seb_config_templates (preset_type)
                WHERE is_default = true
                  AND preset_type IN ('strict', 'standard', 'permissive')
                """
            )
        )

        await db.commit()
    finally:
        if lock_acquired:
            try:
                await db.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": SEB_PRESET_LOCK_KEY},
                )
            except Exception:
                logger.warning("Failed to release SEB preset advisory lock", exc_info=True)

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "deduplicated": deduplicated,
        "total": len(PRESET_CONFIGS),
        "lock_acquired": True,
    }


async def check_presets_exist(db: AsyncSession) -> bool:
    """
    Check if all default presets exist
    """
    for preset_type in PRESET_CONFIGS.keys():
        result = await db.execute(
            select(SebConfigTemplate).where(
                SebConfigTemplate.preset_type == preset_type,
                SebConfigTemplate.is_default == True
            )
        )
        if result.scalars().first() is None:
            return False
    return True


async def get_preset_by_type(db: AsyncSession, preset_type: str) -> SebConfigTemplate | None:
    """
    Get a specific preset by type
    """
    result = await db.execute(
        select(SebConfigTemplate)
        .where(
            SebConfigTemplate.preset_type == preset_type,
            SebConfigTemplate.is_default == True
        )
        .order_by(SebConfigTemplate.id.asc())
    )
    return result.scalars().first()


# Convenience function for use in other modules
async def ensure_presets_exist():
    """
    Ensure default presets exist, create if they don't
    Can be called from anywhere in the application
    """
    async with async_session_maker() as db:
        exists = await check_presets_exist(db)
        if not exists:
            logger.info("Default presets not found, creating...")
            result = await seed_default_presets(db)
            logger.info(f"Presets seeded: {result}")
            return result
        else:
            logger.info("Default presets already exist")
            return {"status": "exists"}
