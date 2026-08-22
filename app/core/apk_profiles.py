"""
Helpers for storing and reading dual APK token/signature profiles.

Storage is backward-compatible with legacy single-token fields:
- system_settings.minimum_apk_token
- system_settings.allowed_signatures
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TOKEN_V2_PREFIX = "TOKENS_V2:"
SIGNATURES_V2_PREFIX = "SIGS_V2:"
TOKEN_PATTERN = re.compile(r"^BUILD-\d{14}-[A-Z0-9]{6}$")


def normalize_signature(value: str) -> str:
    """Normalize signature/hash for robust comparison."""
    return str(value or "").strip().replace(":", "").lower()


def clean_token(value: Optional[str]) -> Optional[str]:
    token = str(value or "").strip().upper()
    if not token:
        return None
    if not TOKEN_PATTERN.match(token):
        return None
    return token


def _dedupe_ordered(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _normalize_signature_list(raw_values: Any) -> List[str]:
    values: List[str] = []
    if isinstance(raw_values, str):
        candidates = raw_values.split(",")
    elif isinstance(raw_values, list):
        candidates = raw_values
    else:
        candidates = []

    for candidate in candidates:
        normalized = normalize_signature(str(candidate or ""))
        if normalized:
            values.append(normalized)
    return _dedupe_ordered(values)


def parse_token_profiles(raw_value: Optional[str]) -> Dict[str, Any]:
    """
    Parse token profile from legacy or V2 serialized value.

    Returns:
    {
      "stable": Optional[str],
      "stable_enabled": bool,
      "new_update": Optional[str],
      "tokens": List[str],
      "labels_by_token": Dict[str, str],
      "is_v2": bool
    }
    """
    stable_token: Optional[str] = None
    new_update_token: Optional[str] = None
    stable_enabled = True
    is_v2 = False

    raw = str(raw_value or "").strip()
    if raw.startswith(TOKEN_V2_PREFIX):
        is_v2 = True
        payload_raw = raw[len(TOKEN_V2_PREFIX) :].strip()
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
            if isinstance(payload, dict):
                stable_token = clean_token(
                    payload.get("stable") or payload.get("stable_token") or payload.get("s")
                )
                new_update_token = clean_token(
                    payload.get("new_update")
                    or payload.get("new update")
                    or payload.get("new_update_token")
                    or payload.get("n")
                )
                raw_stable_enabled = payload.get("stable_enabled")
                if raw_stable_enabled is None:
                    raw_stable_enabled = payload.get("se")
                if isinstance(raw_stable_enabled, bool):
                    stable_enabled = raw_stable_enabled
                elif raw_stable_enabled is not None:
                    stable_enabled = str(raw_stable_enabled).strip().lower() in (
                        "1",
                        "true",
                        "yes",
                        "on",
                    )
        except Exception:
            logger.warning("Failed to parse token V2 payload, fallback to legacy mode")

    if stable_token is None and raw:
        # Legacy single-token mode
        stable_token = clean_token(raw)

    tokens_raw: List[str] = []
    if stable_token and stable_enabled:
        tokens_raw.append(stable_token)
    if new_update_token:
        tokens_raw.append(new_update_token)
    tokens = _dedupe_ordered(tokens_raw)
    labels_by_token: Dict[str, str] = {}
    if stable_token and stable_enabled:
        labels_by_token[stable_token] = "stable"
    if new_update_token:
        labels_by_token[new_update_token] = "new update"

    return {
        "stable": stable_token,
        "stable_enabled": stable_enabled,
        "new_update": new_update_token,
        "tokens": tokens,
        "labels_by_token": labels_by_token,
        "is_v2": is_v2,
    }


def parse_signature_profiles(raw_value: Optional[str]) -> Dict[str, Any]:
    """
    Parse signature/hash profiles from legacy or V2 serialized value.

    Returns:
    {
      "stable": List[str],
      "new_update": List[str],
      "all_signatures": List[str],
      "is_v2": bool
    }
    """
    stable_signatures: List[str] = []
    new_update_signatures: List[str] = []
    is_v2 = False

    raw = str(raw_value or "").strip()
    if raw.startswith(SIGNATURES_V2_PREFIX):
        is_v2 = True
        payload_raw = raw[len(SIGNATURES_V2_PREFIX) :].strip()
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
            if isinstance(payload, dict):
                stable_signatures = _normalize_signature_list(payload.get("stable"))
                new_update_signatures = _normalize_signature_list(
                    payload.get("new_update") or payload.get("new update")
                )
        except Exception:
            logger.warning(
                "Failed to parse signatures V2 payload, fallback to legacy mode"
            )

    if not stable_signatures and raw and not raw.startswith(SIGNATURES_V2_PREFIX):
        stable_signatures = _normalize_signature_list(raw)

    all_signatures = _dedupe_ordered(stable_signatures + new_update_signatures)
    return {
        "stable": stable_signatures,
        "new_update": new_update_signatures,
        "all_signatures": all_signatures,
        "is_v2": is_v2,
    }


def encode_token_profiles(
    stable_token: Optional[str],
    new_update_token: Optional[str],
    *,
    stable_enabled: bool = True,
) -> Optional[str]:
    """Serialize token profiles into legacy or V2 format."""
    stable = clean_token(stable_token)
    new_update = clean_token(new_update_token)
    if not stable and not new_update:
        return None
    if stable and not new_update and stable_enabled:
        return stable
    payload: Dict[str, Any] = {}
    if stable:
        payload["s"] = stable
    if new_update:
        payload["n"] = new_update
    # Keep flag only when stable profile is explicitly disabled.
    if stable and not stable_enabled:
        payload["se"] = 0
    return f"{TOKEN_V2_PREFIX}{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"


def encode_signature_profiles(
    stable_signatures: List[str],
    new_update_signatures: List[str],
) -> Optional[str]:
    """Serialize signature profiles into legacy or V2 format."""
    stable = _normalize_signature_list(stable_signatures)
    new_update = _normalize_signature_list(new_update_signatures)
    if not stable and not new_update:
        return None
    if stable and not new_update:
        return ",".join(stable)
    payload = {
        "stable": stable,
        "new_update": new_update,
    }
    return f"{SIGNATURES_V2_PREFIX}{json.dumps(payload, ensure_ascii=False)}"


def get_allowed_tokens(raw_value: Optional[str]) -> List[str]:
    """Return all accepted tokens from serialized token field."""
    return parse_token_profiles(raw_value).get("tokens", [])


def get_token_label(raw_value: Optional[str], token: Optional[str]) -> Optional[str]:
    """Return token label ('stable'/'new update') for a token if known."""
    normalized = clean_token(token)
    if not normalized:
        return None
    profiles = parse_token_profiles(raw_value)
    return profiles.get("labels_by_token", {}).get(normalized)
