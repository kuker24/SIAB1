"""
Asset Helper - Template functions for fingerprinted assets.

Usage in templates or API:
    from app.core.assets import asset_url

    # In Jinja2 template:
    <link rel="stylesheet" href="{{ asset_url('/static/css/admin.css') }}">

    # In Python:
    css_url = asset_url('/static/css/admin.css')
"""
import json
from pathlib import Path
from typing import Optional

# Path to manifest file
MANIFEST_PATH = Path(__file__).parent.parent.parent / "static" / "dist" / "manifest.json"

# Cache for manifest data
_manifest_cache: Optional[dict] = None
_manifest_mtime: float = 0


def _load_manifest() -> dict:
    """Load manifest with file modification check."""
    global _manifest_cache, _manifest_mtime

    if not MANIFEST_PATH.exists():
        return {'files': {}}

    current_mtime = MANIFEST_PATH.stat().st_mtime

    if _manifest_cache is None or current_mtime != _manifest_mtime:
        with open(MANIFEST_PATH) as f:
            _manifest_cache = json.load(f)
        _manifest_mtime = current_mtime

    return _manifest_cache


def asset_url(original_url: str, use_fingerprinted: bool = True) -> str:
    """
    Get the URL for a static asset.

    In production, returns fingerprinted URL from manifest.
    Falls back to original URL if manifest doesn't exist or file not found.

    Args:
        original_url: Original asset URL (e.g., '/static/css/admin.css')
        use_fingerprinted: Set to False to always return original URL

    Returns:
        Fingerprinted URL if available, otherwise original URL
    """
    if not use_fingerprinted:
        return original_url

    manifest = _load_manifest()
    return manifest.get('files', {}).get(original_url, original_url)


def get_all_assets() -> dict:
    """Get all asset mappings from manifest."""
    return _load_manifest().get('files', {})


def get_manifest_version() -> Optional[str]:
    """Get manifest build version/timestamp."""
    return _load_manifest().get('version')


# Jinja2 context processor
def asset_context_processor():
    """
    Jinja2 context processor for asset URLs.

    Usage in FastAPI:
        from app.core.assets import asset_context_processor
        templates.env.globals.update(asset_context_processor())
    """
    return {
        'asset_url': asset_url,
        'manifest_version': get_manifest_version
    }


# CDN Support
class CDNConfig:
    """CDN configuration for static assets."""

    def __init__(
        self,
        enabled: bool = False,
        base_url: str = "",
        fallback_to_local: bool = True
    ):
        self.enabled = enabled
        self.base_url = base_url.rstrip('/')
        self.fallback_to_local = fallback_to_local

    def get_url(self, path: str) -> str:
        """Get CDN URL for a path."""
        if not self.enabled or not self.base_url:
            return path

        # Remove leading /static if present
        clean_path = path
        if clean_path.startswith('/static'):
            clean_path = clean_path[7:]  # Remove '/static'

        return f"{self.base_url}{clean_path}"


# Default CDN config (disabled)
cdn_config = CDNConfig(enabled=False)


def configure_cdn(base_url: str, enabled: bool = True):
    """
    Configure CDN for static assets.

    Usage:
        from app.core.assets import configure_cdn
        configure_cdn('https://cdn.example.com/static', enabled=True)
    """
    global cdn_config
    cdn_config = CDNConfig(enabled=enabled, base_url=base_url)


def cdn_asset_url(original_url: str) -> str:
    """
    Get CDN URL for an asset.

    Combines fingerprinting and CDN:
    1. Gets fingerprinted URL from manifest
    2. Prepends CDN base URL if configured
    """
    fingerprinted = asset_url(original_url)
    return cdn_config.get_url(fingerprinted)
