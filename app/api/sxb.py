from fastapi import APIRouter, Depends
from app.config import settings
from app.core.sxb_security import SXBSecurity, verify_app_signature

router = APIRouter(
    prefix="/config",
    tags=["SXB Configuration"],
    dependencies=[Depends(verify_app_signature)]
)

@router.get("/init")
async def get_initial_config():
    """
    Get encrypted configuration for SXB Client initialization.
    Requires valid Private Handshake (X-App-Signature).
    """

    # 1. Prepare Configuration
    # In a real app, this might come from DB based on device ID or user group
    config_payload = {
        "exam_urls": [
             f"{settings.base_url}/student/login",
             # Fallback or secondary exams
        ],
        "kiosk_mode": True,
        "security_level": "high",
        "allowed_hosts": [
            settings.domain,
            "fonts.googleapis.com",
            "gstatic.com"
        ],
        "features": {
            "camera": False,
            "microphone": False,
            "clipboard": False
        }
    }

    # 2. Encrypt Payload (AES-256)
    encrypted_response = SXBSecurity.encrypt_data(config_payload)

    # 3. Return Encrypted Data
    # The client MUST decrypt this to get the JSON
    return {
        "status": "success",
        "payload": encrypted_response
    }
