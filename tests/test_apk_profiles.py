from app.core.apk_profiles import (
    TOKEN_V2_PREFIX,
    SIGNATURES_V2_PREFIX,
    encode_signature_profiles,
    encode_token_profiles,
    get_allowed_tokens,
    get_token_label,
    parse_signature_profiles,
    parse_token_profiles,
)


def test_parse_legacy_token_profile() -> None:
    profile = parse_token_profiles("BUILD-20260305120000-ABC123")
    assert profile["stable"] == "BUILD-20260305120000-ABC123"
    assert profile["new_update"] is None
    assert profile["tokens"] == ["BUILD-20260305120000-ABC123"]


def test_parse_v2_token_profile() -> None:
    raw = (
        f"{TOKEN_V2_PREFIX}"
        '{"stable":"BUILD-20260305120000-ABC123","new_update":"BUILD-20260306101010-XYZ789"}'
    )
    profile = parse_token_profiles(raw)
    assert profile["stable"] == "BUILD-20260305120000-ABC123"
    assert profile["new_update"] == "BUILD-20260306101010-XYZ789"
    assert profile["tokens"] == [
        "BUILD-20260305120000-ABC123",
        "BUILD-20260306101010-XYZ789",
    ]
    assert get_token_label(raw, "BUILD-20260306101010-XYZ789") == "new update"


def test_parse_v2_token_profile_respects_stable_toggle() -> None:
    raw = (
        f"{TOKEN_V2_PREFIX}"
        '{"stable":"BUILD-20260305120000-ABC123","new_update":"BUILD-20260306101010-XYZ789","stable_enabled":false}'
    )
    profile = parse_token_profiles(raw)
    assert profile["stable"] == "BUILD-20260305120000-ABC123"
    assert profile["stable_enabled"] is False
    assert profile["tokens"] == ["BUILD-20260306101010-XYZ789"]
    assert get_token_label(raw, "BUILD-20260305120000-ABC123") is None
    assert get_token_label(raw, "BUILD-20260306101010-XYZ789") == "new update"


def test_encode_token_profiles_dual_roundtrip() -> None:
    encoded = encode_token_profiles(
        "build-20260305120000-abc123",
        "BUILD-20260306101010-XYZ789",
    )
    assert encoded is not None and encoded.startswith(TOKEN_V2_PREFIX)
    assert get_allowed_tokens(encoded) == [
        "BUILD-20260305120000-ABC123",
        "BUILD-20260306101010-XYZ789",
    ]


def test_encode_token_profiles_stable_disabled_keeps_payload_v2() -> None:
    encoded = encode_token_profiles(
        "BUILD-20260305120000-ABC123",
        None,
        stable_enabled=False,
    )
    assert encoded is not None and encoded.startswith(TOKEN_V2_PREFIX)
    assert len(encoded) <= 100
    profile = parse_token_profiles(encoded)
    assert profile["stable"] == "BUILD-20260305120000-ABC123"
    assert profile["stable_enabled"] is False
    assert profile["tokens"] == []


def test_parse_signature_profiles_dual() -> None:
    raw = (
        f"{SIGNATURES_V2_PREFIX}"
        '{"stable":["AA:BB:CC","ddee"],"new_update":["1122","33:44"]}'
    )
    profile = parse_signature_profiles(raw)
    assert profile["stable"] == ["aabbcc", "ddee"]
    assert profile["new_update"] == ["1122", "3344"]
    assert profile["all_signatures"] == ["aabbcc", "ddee", "1122", "3344"]


def test_encode_signature_profiles_legacy_when_single_profile() -> None:
    encoded = encode_signature_profiles(["AA:BB:CC", "ddee"], [])
    assert encoded == "aabbcc,ddee"
