"""Feature-flag helpers for mobile-first runtime simplification."""

from fastapi import HTTPException, status


def feature_disabled_exception(
    feature_name: str,
    *,
    status_code: int = status.HTTP_404_NOT_FOUND,
    message: str | None = None,
) -> HTTPException:
    """Build a consistent HTTPException for disabled optional/legacy features."""
    return HTTPException(
        status_code=status_code,
        detail={
            "error": "FEATURE_DISABLED",
            "feature": feature_name,
            "message": message or f"Fitur {feature_name} sedang dinonaktifkan.",
        },
    )


def require_feature_enabled(
    enabled: bool,
    feature_name: str,
    *,
    status_code: int = status.HTTP_404_NOT_FOUND,
    message: str | None = None,
) -> None:
    """Raise a safe disabled-feature response when a feature flag is off."""
    if not enabled:
        raise feature_disabled_exception(
            feature_name,
            status_code=status_code,
            message=message,
        )
