# config/security.py
"""
Security configuration for APK signature validation

DEPRECATED: Signature validation is now 100% managed via Admin Panel (Database).
This file is kept for backward compatibility but all functions now delegate
to database-based validation via system_settings.
"""

# Security settings
ENFORCE_SIGNATURE_CHECK = True  # Set to False to disable (NOT recommended for production)
LOG_SIGNATURE_MISMATCHES = True  # Always log mismatches even if not enforcing
BLOCK_MODIFIED_APK = True  # Block requests from modified APKs


def is_signature_valid(signature: str) -> bool:
    """
    Check if app signature is valid.

    DEPRECATED: This function always returns True now.
    Signature validation is handled by the SXB enforcer middleware
    which checks against the database (system_settings.allowed_signatures).

    Args:
        signature: SHA-256 fingerprint from app

    Returns:
        True (validation delegated to database-based middleware)
    """
    if not signature:
        return False

    # Signature validation is now handled by SXB enforcer middleware
    # which reads allowed signatures from the database.
    # This function is kept for backward compatibility only.
    return True


def should_enforce_check() -> bool:
    """
    Determine if signature check should be enforced.

    Returns:
        True if should enforce, False otherwise
    """
    return ENFORCE_SIGNATURE_CHECK
