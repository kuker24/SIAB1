"""Runtime policy endpoints for APK/mobile-first clients."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.runtime_policy import get_mobile_runtime_policy

router = APIRouter(prefix="/api/runtime", tags=["Runtime Policy"])


@router.get("/policy")
async def get_runtime_policy_endpoint():
    """Return adaptive APK/web sync policy without requiring an APK rebuild."""
    policy = await get_mobile_runtime_policy(force_refresh=False)
    return JSONResponse(
        policy,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Runtime-Policy-Version": str(policy.get("policy_version") or ""),
        },
    )
