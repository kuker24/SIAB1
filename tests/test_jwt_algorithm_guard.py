import pytest

from app.config import Settings


def _minimal_settings_kwargs() -> dict:
    return {
        "secret_key": "test-secret-key",
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/testdb",
    }


def test_settings_allow_hs_jwt_algorithm() -> None:
    settings = Settings(**_minimal_settings_kwargs(), jwt_algorithm="HS256")
    assert settings.jwt_algorithm == "HS256"


def test_settings_reject_es_jwt_algorithm() -> None:
    with pytest.raises(ValueError, match="ECDSA|ES"):
        Settings(**_minimal_settings_kwargs(), jwt_algorithm="ES256")
