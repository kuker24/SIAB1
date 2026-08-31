from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.api.exams import _validate_questions_for_publish


class _ScalarResult:
    def __init__(self, questions: list[SimpleNamespace]) -> None:
        self._questions = questions

    def all(self) -> list[SimpleNamespace]:
        return self._questions


class _ExecuteResult:
    def __init__(self, questions: list[SimpleNamespace]) -> None:
        self._questions = questions

    def scalars(self) -> _ScalarResult:
        return _ScalarResult(self._questions)


class _FakeDb:
    def __init__(self, questions: list[SimpleNamespace]) -> None:
        self._questions = questions

    async def execute(self, _statement: object) -> _ExecuteResult:
        return _ExecuteResult(self._questions)


def _pgk_question(*, use_stimulus: bool, stimulus: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        question_type="multiple_choice_complex",
        pgk_type="checkbox",
        question_text="Pilih semua jawaban yang benar",
        stimulus=stimulus,
        image_url=None,
        video_url=None,
        audio_url=None,
        question_settings={"pgk_type": "checkbox", "use_stimulus": use_stimulus},
        options=[
            SimpleNamespace(option_text=f"Pilihan {index}", is_correct=index < 2)
            for index in range(4)
        ],
    )


@pytest.mark.asyncio
async def test_pgk_can_publish_without_stimulus_when_disabled() -> None:
    db = _FakeDb([_pgk_question(use_stimulus=False, stimulus=None)])

    await _validate_questions_for_publish(1, db)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_pgk_rejects_empty_stimulus_when_enabled() -> None:
    db = _FakeDb([_pgk_question(use_stimulus=True, stimulus="")])

    with pytest.raises(HTTPException) as exc_info:
        await _validate_questions_for_publish(1, db)  # type: ignore[arg-type]

    assert "Stimulus aktif tetapi isinya masih kosong" in str(exc_info.value.detail)
