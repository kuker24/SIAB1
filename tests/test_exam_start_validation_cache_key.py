from pathlib import Path

import pytest

from app.api import exams


def test_build_exam_start_validation_cache_key_uses_stable_prefix() -> None:
    assert (
        exams._build_exam_start_validation_cache_key(123)
        == f"{exams.EXAM_START_VALIDATION_CACHE_PREFIX}:123"
    )


def test_build_exam_start_validation_cache_key_coerces_exam_id_to_int() -> None:
    assert (
        exams._build_exam_start_validation_cache_key("123")
        == f"{exams.EXAM_START_VALIDATION_CACHE_PREFIX}:123"
    )


def test_exam_start_validation_cache_key_helper_is_defined_before_integrity_checker() -> None:
    source = Path("app/api/exams.py").read_text()

    assert source.index("def _build_exam_start_validation_cache_key") < source.index(
        "async def _ensure_exam_start_option_integrity"
    )


@pytest.mark.asyncio
async def test_exam_start_validation_does_not_raise_missing_cache_key_helper(monkeypatch) -> None:
    exam_id = "456"
    expected_key = f"{exams.EXAM_START_VALIDATION_CACHE_PREFIX}:456"
    calls: list[tuple[str, str]] = []

    class FakeRedis:
        async def get(self, key: str) -> str | None:
            calls.append(("get", key))
            if key == expected_key:
                return "1"
            return None

    class ExplodingDb:
        async def execute(self, _statement):  # pragma: no cover - should not be reached
            raise AssertionError("DB should not be queried when exam-start validation cache hits")

    async def fake_get_redis() -> FakeRedis:
        return FakeRedis()

    monkeypatch.setattr(exams, "_exam_start_validation_local_cache", {})
    monkeypatch.setattr(exams, "get_redis", fake_get_redis)

    await exams._ensure_exam_start_option_integrity(ExplodingDb(), exam_id)

    assert ("get", expected_key) in calls
