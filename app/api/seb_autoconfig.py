"""
SEB Auto-Configuration API Router
==================================
Dynamic SEB configuration generation for any deployment URL.
Supports Safe Exam Browser (Windows/macOS/iOS) and Exambro (Android).

Features:
- Dynamic URL detection from request (works with localhost, IP, domain)
- QR code generation with seb:// protocol for mobile apps
- Pre-configured .seb file download for desktop apps

IMPORTANT: Uses shared URL filter rules from app.core.seb
"""

import plistlib
import hashlib
import os
from io import BytesIO
from typing import Optional

import qrcode
from fastapi import APIRouter, Request, Query
from fastapi.responses import Response, StreamingResponse, JSONResponse

from app.config import settings
from app.core.feature_flags import require_feature_enabled
from app.core.seb import get_url_filter_rules


router = APIRouter(prefix="/api/seb", tags=["SEB Auto-Configuration"])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_dynamic_base_url(request: Request) -> str:
    """
    Extract base URL dynamically from the incoming request.
    Supports reverse proxy headers (X-Forwarded-*) for production deployments.

    Returns:
        Base URL string (e.g., "http://localhost:8000" or "https://exam.domain.com")
    """
    # Check for reverse proxy headers first (Nginx, Apache, etc.)
    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    forwarded_host = request.headers.get("X-Forwarded-Host")

    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}"

    # Fallback to request URL
    scheme = request.url.scheme
    netloc = request.url.netloc  # Includes host:port

    # FIX: Use configured domain if set to valid LAN/Public IP (allows downloading from localhost)
    if "192.168" in settings.domain or "10." in settings.domain or settings.app_env == "production":
        return settings.base_url

    return f"{scheme}://{netloc}"


def get_seb_protocol_url(request: Request, path: str = "", use_sebs: bool = False) -> str:
    """
    Generate SEB protocol URL for mobile app launch.

    Args:
        request: FastAPI request object
        path: Path to append
        use_sebs: Use sebs:// (secure) instead of seb://

    Returns:
        SEB protocol URL (e.g., "seb://192.168.1.100:8000/student/")
    """
    # Get host without scheme
    forwarded_host = request.headers.get("X-Forwarded-Host")
    if forwarded_host:
        host = forwarded_host
    else:
        # FIX: Use configured domain if valid LAN/Public IP
        if "192.168" in settings.domain or "10." in settings.domain or settings.app_env == "production":
            # Remove protocol if present
            host = settings.domain.replace("http://", "").replace("https://", "")
        else:
            host = request.url.netloc

    protocol = "sebs" if use_sebs else "seb"
    return f"{protocol}://{host}{path}"


def generate_dynamic_seb_config(
    base_url: str,
    start_path: str = "/student/",
    admin_password: Optional[str] = None,
    quit_password: Optional[str] = None,
    config_key: Optional[str] = None,
    browser_exam_key: Optional[str] = None,
) -> bytes:
    """
    Generate SEB configuration file with dynamic base URL.

    This creates an XML Plist format .seb file that is compatible with:
    - Safe Exam Browser (Windows, macOS, iOS)
    - Exambro (Android)

    Args:
        base_url: Dynamic base URL (e.g., "http://localhost:8000")
        start_path: Starting path for the exam (default: "/student/")
        admin_password: Admin password for SEB settings
        quit_password: Password to quit SEB
        config_key: SEB config key (uses default if not provided)
        browser_exam_key: Browser exam key (uses default if not provided)

    Returns:
        Bytes of the XML Plist configuration
    """
    # Build full start URL
    start_url = f"{base_url}{start_path}"

    # Extract domain/host from base_url for URL filtering
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    domain_host = parsed.netloc  # e.g., "localhost:8000" or "exam.domain.com"

    # Avoid weak static defaults by deriving fallback from deployment secrets.
    effective_admin_password = admin_password or settings.seb_default_config_key
    effective_quit_password = quit_password or settings.seb_default_browser_exam_key

    # Hash passwords
    admin_hash = hashlib.sha256(effective_admin_password.encode()).hexdigest()
    quit_hash = hashlib.sha256(effective_quit_password.encode()).hexdigest()

    # Generate random salt
    exam_key_salt = os.urandom(32).hex()

    # Use provided keys or defaults
    config_key = config_key or settings.seb_default_config_key
    browser_exam_key = browser_exam_key or settings.seb_default_browser_exam_key

    # SEB configuration dictionary
    seb_config = {
        # ============== STARTUP URL ==============
        'startURL': start_url,
        'startURLAllowDeepLink': True,
        'startURLAppendQueryParameter': False,

        # ============== BROWSER SETTINGS ==============
        'browserWindowAllowReload': True,
        'allowBrowsingBackForward': True,
        'enableBrowserWindowToolbar': True,
        'showMenuBar': False,
        'showTaskBar': False,
        'enableTouchExit': False,
        'enableZoomPage': True,
        'enableZoomText': True,
        'browserWindowShowURL': 2,  # 2 = always show URL
        'newBrowserWindowByLinkPolicy': 0,  # 0 = block
        'newBrowserWindowByScriptPolicy': 0,  # 0 = block
        'newBrowserWindowByLinkBlockForeign': True,

        # ============== SECURITY KEYS ==============
        'examKeySalt': exam_key_salt,
        'browserExamKey': browser_exam_key,
        'configKey': config_key,
        'sendBrowserExamKey': True,

        # ============== PASSWORDS (HASHED) ==============
        'hashedAdminPassword': admin_hash,
        'hashedQuitPassword': quit_hash,

        # ============== URL FILTERING (PERMISSIVE for VirtualBox/NAT) ==============
        # Using regex .* to allow ALL URLs - required for dynamic IP environments
        'URLFilterEnable': True,
        'URLFilterEnableContentFilter': False,  # IMPORTANT: Disable content filter
        'URLFilterRules': get_url_filter_rules(base_url, domain_host),

        # ============== NETWORK SETTINGS ==============
        'allowWlan': True,  # CRITICAL: Allow WiFi connections
        'allowMobileSync': True,

        # ============== ANTI-CHEAT: CLIPBOARD & INPUT ==============
        'enablePrivateClipboard': True,
        'enableJavaScript': True,
        'blockPopUpWindows': True,
        'enableRightMouse': True,
        'enableF12': True,  # Enable DevTools for diagnostics

        # ============== ANTI-CHEAT: SCREEN & PROCESSES ==============
        'allowScreenShot': False,
        'allowScreenSharing': False,
        'monitorProcesses': True,
        'allowVirtualMachine': True,  # Allow VMs for testing

        # ============== KEYBOARD CONTROL ==============
        'enableF5': True,
        'enableEsc': True,
        'enableAltTab': True,  # Allow task switching if stuck
        'enableCtrlAltDel': False,
        'enablePrintScreen': False,

        # ============== OS SPECIFIC ==============
        'killExplorerShell': False,  # Don't kill explorer (safer)
        'enableWindowsTouch': True,

        # ============== macOS SPECIFIC ==============
        'allowPreferencesWindow': False,
        'enablePinchZoom': True,

        # ============== EXIT SETTINGS ==============
        'quitURLConfirm': True,
        'ignoreExitKeys': False,
        'exitKey1': 2,   # Ctrl
        'exitKey2': 81,  # Q key code
        'exitKey3': 0,

        # ============== LOGGING ==============
        'enableAppSwitcherCheck': True,
        'forceAppFolderInstall': False,

        # ============== USER AGENT ==============
        'browserUserAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SEB/3.5',
        'browserUserAgentWinDesktopModeEnabled': False,
    }

    # Write to bytes buffer as XML Plist
    buffer = BytesIO()
    plistlib.dump(seb_config, buffer, fmt=plistlib.FMT_XML)

    return buffer.getvalue()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/download-config")
async def download_dynamic_seb_config(request: Request):
    """
    Download dynamically generated SEB configuration file.

    The configuration is generated based on the current deployment URL,
    making it work seamlessly across localhost, IP, or domain deployments.

    Returns:
        .seb file (application/seb) for download
    """
    require_feature_enabled(settings.seb_desktop_legacy_enabled, "seb_desktop_legacy")
    # Get dynamic base URL from request
    base_url = get_dynamic_base_url(request)

    # Generate SEB config
    seb_config = generate_dynamic_seb_config(
        base_url=base_url,
        start_path="/student/",
        config_key=settings.seb_default_config_key,
        browser_exam_key=settings.seb_default_browser_exam_key
    )

    return Response(
        content=seb_config,
        media_type="application/seb",
        headers={
            "Content-Disposition": 'attachment; filename="ujian-online-config.seb"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.get("/qr-code")
async def generate_seb_qr_code(
    request: Request,
    size: int = Query(default=300, ge=100, le=500, description="QR code size in pixels"),
    protocol: str = Query(default="seb", pattern="^(seb|sebs|http)$", description="URL protocol")
):
    """
    Generate QR code for SEB/Exambro mobile app configuration.

    The QR code contains an SEB protocol URL that, when scanned by
    Exambro or SEB mobile app, will:
    1. Trigger the app to open
    2. Download the configuration
    3. Auto-configure for this server

    Args:
        size: QR code image size (100-500 pixels)
        protocol: URL protocol - "seb" (Android/default), "sebs" (iOS secure), or "http" (direct)

    Returns:
        PNG image of the QR code
    """
    require_feature_enabled(settings.seb_qr_enabled, "seb_qr")
    # Build QR code content based on protocol
    if protocol == "http":
        # Direct HTTPS URL for browsers
        base_url = get_dynamic_base_url(request)
        qr_content = f"{base_url}/api/seb/download-config"
    else:
        # SEB protocol URL for mobile apps
        qr_content = get_seb_protocol_url(
            request,
            path="/api/seb/download-config",
            use_sebs=(protocol == "sebs")
        )

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,  # Medium error correction
        box_size=10,
        border=2,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)

    # Create image
    img = qr.make_image(fill_color="black", back_color="white")

    # Resize if needed
    if size != 300:
        from PIL import Image
        img = img.resize((size, size), Image.Resampling.LANCZOS)

    # Save to buffer
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
    )


@router.get("/config-info")
async def get_config_info(request: Request):
    """
    Get SEB configuration metadata (JSON).

    Useful for debugging and verification.

    Returns:
        JSON with configuration URLs and metadata
    """
    require_feature_enabled(settings.seb_desktop_legacy_enabled, "seb_desktop_legacy")
    base_url = get_dynamic_base_url(request)

    # Parse to get domain_host for filter rules preview
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    domain_host = parsed.netloc

    # Get first 5 filter rules as sample
    sample_rules = get_url_filter_rules(base_url, domain_host)[:5]

    return JSONResponse({
        "status": "ok",
        "server": {
            "base_url": base_url,
            "domain_host": domain_host,
            "detected_from": "request"
        },
        "endpoints": {
            "download_config": f"{base_url}/api/seb/download-config",
            "qr_code": f"{base_url}/api/seb/qr-code",
            "qr_code_large": f"{base_url}/api/seb/qr-code?size=400"
        },
        "mobile_protocols": {
            "android_exambro": get_seb_protocol_url(request, "/api/seb/download-config", use_sebs=False),
            "ios_seb": get_seb_protocol_url(request, "/api/seb/download-config", use_sebs=True),
            "direct_access": get_seb_protocol_url(request, "/student/", use_sebs=False)
        },
        "url_filter_sample": [
            {"expression": r["expression"], "action": "ALLOW" if r["action"] == 1 else "BLOCK"}
            for r in sample_rules
        ],
        "instructions": {
            "desktop": [
                "1. Install Safe Exam Browser from safeexambrowser.org",
                "2. Download the .seb config file",
                "3. Double-click the file to open SEB with this configuration"
            ],
            "mobile_android": [
                "1. Install 'Exambro' from Google Play Store",
                "2. Open Exambro and select 'Scan QR'",
                "3. Scan the QR code to auto-configure"
            ],
            "mobile_ios": [
                "1. Install 'Safe Exam Browser' from App Store",
                "2. Open SEB and select 'Scan QR' or 'Open URL'",
                "3. Scan the QR code to auto-configure"
            ]
        }
    })


@router.get("/exam/{exam_id}/download-config")
async def download_exam_specific_config(
    request: Request,
    exam_id: int
):
    """
    Download SEB configuration for a specific exam.

    This generates a config that goes directly to the exam start page.

    Args:
        exam_id: The exam ID to configure for

    Returns:
        .seb file configured for the specific exam
    """
    require_feature_enabled(settings.seb_desktop_legacy_enabled, "seb_desktop_legacy")
    base_url = get_dynamic_base_url(request)

    # Generate config pointing to exam start page
    seb_config = generate_dynamic_seb_config(
        base_url=base_url,
        start_path=f"/seb/{exam_id}",  # Goes to SEB landing page for this exam
        config_key=settings.seb_default_config_key,
        browser_exam_key=settings.seb_default_browser_exam_key
    )

    return Response(
        content=seb_config,
        media_type="application/seb",
        headers={
            "Content-Disposition": f'attachment; filename="ujian-{exam_id}-config.seb"',
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )


@router.get("/exam/{exam_id}/qr-code")
async def generate_exam_qr_code(
    request: Request,
    exam_id: int,
    size: int = Query(default=300, ge=100, le=500)
):
    """
    Generate QR code for a specific exam.

    Args:
        exam_id: The exam ID
        size: QR code size in pixels

    Returns:
        PNG image of the QR code for this exam
    """
    require_feature_enabled(settings.seb_qr_enabled, "seb_qr")
    # Build QR content with SEB protocol pointing to exam config
    qr_content = get_seb_protocol_url(
        request,
        path=f"/api/seb/exam/{exam_id}/download-config",
        use_sebs=False
    )

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    if size != 300:
        from PIL import Image
        img = img.resize((size, size), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"}
    )


@router.get("/debug/url-rules")
async def debug_url_rules(request: Request):
    """
    Debug endpoint to see all URL filter rules that would be generated.

    Useful for troubleshooting "Page Blocked" errors in SEB.

    Returns:
        JSON with all URL filter rules
    """
    require_feature_enabled(settings.seb_debug_endpoints_enabled, "seb_debug_endpoints")
    base_url = get_dynamic_base_url(request)

    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    domain_host = parsed.netloc

    rules = get_url_filter_rules(base_url, domain_host)

    return JSONResponse({
        "base_url": base_url,
        "domain_host": domain_host,
        "total_rules": len(rules),
        "rules": [
            {
                "index": i,
                "action": "ALLOW" if r["action"] == 1 else "BLOCK",
                "expression": r["expression"],
                "regex": r["regex"]
            }
            for i, r in enumerate(rules)
        ]
    })
