"""
Safe Exam Browser (SEB) configuration generator and validation.
Generates XML Plist format .seb files for cross-platform compatibility.

ENHANCED VERSION (v2.0):
- Strict URL whitelist for production
- Challenge-response anti-spoofing mechanism
- Redis-based challenge storage with TTL
- Explicit blocking of search engines, AI tools, social media

Author: System Upgrade
Version: 2.0 (Security Hardening)
"""
import plistlib
import hashlib
import hmac
import os
import secrets
import json
from typing import Optional, List
from datetime import datetime
from io import BytesIO

from app.config import settings


# ============================================================================
# CHALLENGE-RESPONSE MECHANISM (Anti Header Spoofing)
# ============================================================================

async def generate_seb_challenge(exam_id: int) -> dict:
    """
    Generate time-limited challenge for SEB client.

    This prevents header spoofing attacks where attackers use
    curl/Postman to fake SEB headers.

    Args:
        exam_id: Exam ID for context

    Returns:
        dict with challenge_token and expires_in seconds
    """
    from app.core.redis_pubsub import get_redis

    challenge_token = secrets.token_urlsafe(32)
    expires_in = 30  # 30 seconds validity

    redis_client = await get_redis()
    challenge_key = f"{settings.seb_challenge_redis_prefix}{challenge_token}"

    challenge_data = {
        "exam_id": exam_id,
        "created_at": datetime.utcnow().isoformat(),
        "used": False
    }

    # Store in Redis with TTL
    await redis_client.set(
        challenge_key,
        json.dumps(challenge_data),
        ex=expires_in
    )

    return {
        "challenge": challenge_token,
        "expires_in": expires_in
    }


async def validate_seb_challenge_response(
    challenge_token: str,
    response_hash: str,
    exam_id: int
) -> bool:
    """
    Validate SEB client's response to challenge.

    Expected response_hash: SHA256(challenge_token + seb_config_key + exam_id)

    This ensures:
    1. Challenge exists (not fabricated)
    2. Not expired (30s TTL)
    3. Not already used (replay attack prevention)
    4. Response hash matches expected value

    Args:
        challenge_token: Token from X-SEB-Challenge-Token header
        response_hash: Hash from X-SEB-Challenge-Response header
        exam_id: Exam being accessed

    Returns:
        True if validation passes, False otherwise
    """
    if not challenge_token or not response_hash:
        return False

    from app.core.redis_pubsub import get_redis

    redis_client = await get_redis()
    challenge_key = f"{settings.seb_challenge_redis_prefix}{challenge_token}"

    # Get challenge data from Redis
    raw_data = await redis_client.get(challenge_key)
    if not raw_data:
        # Challenge doesn't exist or expired
        return False

    challenge_data = json.loads(raw_data)

    # Check if already used (replay attack)
    if challenge_data.get("used", False):
        await redis_client.delete(challenge_key)
        return False

    # Verify exam_id matches
    if challenge_data.get("exam_id") != exam_id:
        return False

    # Calculate expected hash
    expected_hash = hashlib.sha256(
        f"{challenge_token}{settings.seb_default_config_key}{exam_id}".encode()
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(response_hash.lower(), expected_hash.lower()):
        return False

    # Mark as used
    challenge_data["used"] = True
    await redis_client.set(
        challenge_key,
        json.dumps(challenge_data),
        ex=5  # Keep for 5 more seconds for logging, then auto-delete
    )

    return True


# ============================================================================
# URL FILTER RULES - STRICT MODE (PRODUCTION)
# ============================================================================

def get_url_filter_rules(base_url: str, domain_host: str) -> List[dict]:
    """
    Generate URL filter rules for SEB.

    In STRICT MODE (production): Only exam domain + essential CDNs allowed
    In PERMISSIVE MODE (dev): Allow all URLs with regex .*

    Controlled by settings.seb_strict_mode
    """
    if settings.seb_strict_mode:
        return get_strict_url_filter_rules(base_url, domain_host)
    else:
        return get_permissive_url_filter_rules(base_url, domain_host)


def get_permissive_url_filter_rules(base_url: str, domain_host: str) -> List[dict]:
    """
    Generate PERMISSIVE URL filter rules for development/testing.

    WARNING: Only use in development environments!
    """
    rules = []

    # Allow EVERYTHING with regex .*
    rules.append({
        'action': 1,        # ALLOW
        'active': True,
        'expression': '.*',
        'regex': True
    })

    return rules


def get_strict_url_filter_rules(base_url: str, domain_host: str) -> List[dict]:
    """
    Generate STRICT URL filter rules for PRODUCTION use.

    Security Principles:
    - Explicit whitelist: Only exam domain + essential CDNs
    - Explicit blocklist: Search engines, AI tools, social media
    - DEFAULT DENY: Block everything not explicitly allowed

    Order matters! Allow rules first, then block specific, then catch-all block.
    """

    rules = []

    # ==================== SECTION 1: ALLOW RULES ====================

    # 1.1 Allow exam domain (primary URL)
    rules.append({
        'action': 1,  # ALLOW
        'active': True,
        'expression': f'{base_url}/*',
        'regex': False
    })
    rules.append({
        'action': 1,
        'active': True,
        'expression': f'{domain_host}/*',
        'regex': False
    })

    # 1.2 Allow localhost variants (for dev/testing environments)
    common_ports = ['8000', '8080', '80', '443']
    for port in common_ports:
        rules.append({'action': 1, 'active': True, 'expression': f'http://localhost:{port}/*', 'regex': False})
        rules.append({'action': 1, 'active': True, 'expression': f'http://127.0.0.1:{port}/*', 'regex': False})

    # 1.3 Allow LAN IPs (for VirtualBox/NAT environments)
    rules.append({'action': 1, 'active': True, 'expression': 'http://192.168.*/*', 'regex': False})
    rules.append({'action': 1, 'active': True, 'expression': 'http://10.*/*', 'regex': False})
    rules.append({'action': 1, 'active': True, 'expression': '192.168.*/*', 'regex': False})
    rules.append({'action': 1, 'active': True, 'expression': '10.*/*', 'regex': False})

    # 1.4 Allow ONLY essential CDNs (fonts, CSS frameworks)
    allowed_cdns = [
        'https://fonts.googleapis.com/*',
        'https://fonts.gstatic.com/*',
        'https://cdn.jsdelivr.net/*',
        'https://cdnjs.cloudflare.com/*',
    ]
    for cdn in allowed_cdns:
        rules.append({'action': 1, 'active': True, 'expression': cdn, 'regex': False})

    # 1.5 Allow technical resources
    rules.append({'action': 1, 'active': True, 'expression': 'data:*', 'regex': False})
    rules.append({'action': 1, 'active': True, 'expression': 'blob:*', 'regex': False})
    rules.append({'action': 1, 'active': True, 'expression': 'about:*', 'regex': False})

    # ==================== SECTION 2: EXPLICIT BLOCK RULES ====================
    # These MUST come after allow rules but before catch-all

    # 2.1 Block SEARCH ENGINES
    search_engines = [
        '*google.com*',
        '*google.co.*',
        '*bing.com*',
        '*duckduckgo.com*',
        '*yahoo.com*',
        '*baidu.com*',
        '*yandex.*',
        '*ask.com*',
    ]
    for domain in search_engines:
        rules.append({'action': 0, 'active': True, 'expression': domain, 'regex': False})

    # 2.2 Block AI ASSISTANTS (CRITICAL)
    ai_tools = [
        '*chatgpt.com*',
        '*chat.openai.com*',
        '*openai.com*',
        '*claude.ai*',
        '*anthropic.com*',
        '*perplexity.ai*',
        '*bard.google.com*',
        '*gemini.google.com*',
        '*copilot.microsoft.com*',
        '*bing.com/chat*',
        '*character.ai*',
        '*poe.com*',
        '*replika.ai*',
        '*phind.com*',
        '*you.com*',
    ]
    for domain in ai_tools:
        rules.append({'action': 0, 'active': True, 'expression': domain, 'regex': False})

    # 2.3 Block SOCIAL MEDIA
    social_media = [
        '*facebook.com*',
        '*fb.com*',
        '*twitter.com*',
        '*x.com*',
        '*instagram.com*',
        '*tiktok.com*',
        '*linkedin.com*',
        '*reddit.com*',
        '*discord.com*',
        '*telegram.org*',
        '*whatsapp.com*',
        '*snapchat.com*',
    ]
    for domain in social_media:
        rules.append({'action': 0, 'active': True, 'expression': domain, 'regex': False})

    # 2.4 Block REFERENCE/CHEATING SITES
    reference_sites = [
        '*wikipedia.org*',
        '*wiki*',
        '*stackoverflow.com*',
        '*stackexchange.com*',
        '*quora.com*',
        '*brainly.com*',
        '*chegg.com*',
        '*coursehero.com*',
        '*studocu.com*',
        '*scribd.com*',
        '*pastebin.com*',
        '*github.com*',
        '*gitlab.com*',
    ]
    for domain in reference_sites:
        rules.append({'action': 0, 'active': True, 'expression': domain, 'regex': False})

    # 2.5 Block VIDEO/STREAMING
    video_sites = [
        '*youtube.com*',
        '*youtu.be*',
        '*vimeo.com*',
        '*twitch.tv*',
        '*netflix.com*',
        '*dailymotion.com*',
    ]
    for domain in video_sites:
        rules.append({'action': 0, 'active': True, 'expression': domain, 'regex': False})

    # ==================== SECTION 3: DEFAULT DENY ====================
    # This MUST be the LAST rule - blocks everything not explicitly allowed
    rules.append({
        'action': 0,  # BLOCK
        'active': True,
        'expression': '*',  # Catch-all
        'regex': False
    })

    return rules


def generate_seb_config(
    exam_id: int,
    exam_url: str,
    admin_password: Optional[str] = None,
    quit_password: Optional[str] = None,
    config_key: Optional[str] = None,
    browser_exam_key: Optional[str] = None,
    use_permissive_filter: bool = True,  # NEW: Default to permissive for dev
) -> bytes:
    """
    Generate SEB configuration file in XML Plist format.

    Args:
        exam_id: Exam identifier
        exam_url: Full URL to navigate to
        admin_password: Password for SEB admin settings
        quit_password: Password to quit SEB
        config_key: SEB config key for validation
        browser_exam_key: Browser exam key for request validation
        use_permissive_filter: If True, use regex .* to allow all URLs

    Returns:
        Bytes of XML Plist configuration
    """
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

    # Parse URL for filtering
    from urllib.parse import urlparse
    parsed = urlparse(exam_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    domain_host = parsed.netloc

    # Get URL filter rules (permissive or strict)
    if use_permissive_filter:
        url_rules = get_url_filter_rules(base_url, domain_host)
    else:
        url_rules = get_strict_url_filter_rules(base_url, domain_host)

    # SEB configuration dictionary
    seb_config = {
        # ============== STARTUP URL ==============
        'startURL': exam_url,
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
        'browserWindowShowURL': 2,  # Always show URL
        'newBrowserWindowByLinkPolicy': 0,
        'newBrowserWindowByScriptPolicy': 0,
        'newBrowserWindowByLinkBlockForeign': True,

        # ============== SECURITY KEYS ==============
        'examKeySalt': exam_key_salt,
        'browserExamKey': browser_exam_key,
        'configKey': config_key,
        'sendBrowserExamKey': True,

        # ============== PASSWORDS ==============
        'hashedAdminPassword': admin_hash,
        'hashedQuitPassword': quit_hash,

        # ============== URL FILTERING (PERMISSIVE) ==============
        'URLFilterEnable': True,
        'URLFilterEnableContentFilter': False,  # Disable content filter
        'URLFilterRules': url_rules,

        # ============== NETWORK ==============
        'allowWlan': True,  # Allow WiFi connections
        'allowMobileSync': True,

        # ============== SECURITY SETTINGS ==============
        'enablePrivateClipboard': True,
        'enableJavaScript': True,
        'blockPopUpWindows': True,
        'enableRightMouse': False,  # Disable right-click for exam security
        'enableF12': False,  # Disable developer tools

        # ============== SCREEN & PROCESSES ==============
        'allowScreenShot': False,
        'allowScreenSharing': False,
        'monitorProcesses': True,
        'allowVirtualMachine': True,  # Set to False in strict production

        # ============== KEYBOARD ==============
        'enableF5': True,
        'enableEsc': False,  # Disable Esc key during exam
        'enableAltTab': False,  # CRITICAL: Disable Alt+Tab to prevent app switching
        'enableCtrlAltDel': False,
        'enablePrintScreen': False,

        # ============== OS SPECIFIC (LAPTOP KIOSK MODE) ==============
        'killExplorerShell': True,  # Enable kiosk mode on Windows laptops
        'enableWindowsTouch': True,
        'allowPreferencesWindow': False,
        'enablePinchZoom': True,

        # ============== EXIT ==============
        'quitURLConfirm': True,
        'ignoreExitKeys': False,
        'exitKey1': 2,
        'exitKey2': 81,
        'exitKey3': 0,

        # ============== LOGGING ==============
        'enableAppSwitcherCheck': True,
        'forceAppFolderInstall': False,

        # ============== USER AGENT ==============
        'browserUserAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SEB/3.5',
        'browserUserAgentWinDesktopModeEnabled': False,
    }

    # Write to bytes buffer as XML Plist
    buffer = BytesIO()
    plistlib.dump(seb_config, buffer, fmt=plistlib.FMT_XML)

    return buffer.getvalue()


def get_mobile_launch_url(exam_id: int, platform: str) -> dict:
    """Generate mobile launch URL for SEB."""
    if platform == 'ios':
        protocol = "sebs://"
    elif platform == 'android':
        protocol = "seb://"
    else:
        raise ValueError(f"Platform tidak valid: {platform}")

    base_domain = settings.domain
    config_url = f"{settings.base_url}/api/exams/{exam_id}/seb-config.seb"
    launch_url = f"{protocol}{base_domain}/api/exams/{exam_id}/start?configUrl={config_url}"

    return {
        "launch_url": launch_url,
        "display_text": "Buka Ujian dengan Safe Exam Browser",
        "instructions": "Ketuk tombol untuk membuka ujian di SEB"
    }


def validate_seb_config_key_hash(received_hash: str, expected_config_key: str) -> bool:
    """Validate SEB Config Key Hash."""
    expected_hash = hashlib.sha256(expected_config_key.encode()).hexdigest()
    return hmac.compare_digest(received_hash.lower(), expected_hash.lower())


def validate_seb_request_hash(
    received_hash: str,
    browser_exam_key: str,
    request_url: str
) -> bool:
    """Validate SEB Request Hash."""
    expected_hash = hmac.new(
        browser_exam_key.encode(),
        request_url.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(received_hash.lower(), expected_hash.lower())


def generate_config_key_hash(config_key: str) -> str:
    """Generate SHA256 hash of config key."""
    return hashlib.sha256(config_key.encode()).hexdigest()
