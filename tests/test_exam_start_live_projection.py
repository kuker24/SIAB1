from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import exams
from app.services.exam_service import (
    ExamStartCreatorView,
    ExamStartProjection,
    ExamStartSessionState,
)


class FakeResult:
    def __init__(self, *, scalar_value: Any = None, rows: list[Any] | None = None) -> None:
        self.scalar_value = scalar_value
        self.rows = rows or []

    def scalar(self) -> Any:
        return self.scalar_value

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list[Any]:
        return self.rows


class FakeSession:
    def __init__(self, results: Optional[list[FakeResult]] = None) -> None:
        self.results = iter(results or [])

    async def execute(self, _statement: Any) -> FakeResult:
        return next(self.results)


def _projection(**overrides: Any) -> ExamStartProjection:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "id": 7,
        "creator_id": 11,
        "is_published": True,
        "start_time": now - timedelta(minutes=5),
        "end_time": now + timedelta(minutes=55),
        "max_attempts": 1,
        "allowed_classes": "XII",
        "allowed_students": None,
        "duration_minutes": 60,
        "shuffle_questions": False,
        "shuffle_options": False,
        "title": "Ujian",
        "subject": "MTK",
        "exam_type": "UH",
        "show_results": False,
        "show_teacher_name": True,
        "creator": ExamStartCreatorView(full_name="Guru", role="teacher"),
    }
    values.update(overrides)
    return ExamStartProjection(**values)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/exams/7/start",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


def _patch_start_deps(
    monkeypatch: pytest.MonkeyPatch,
    projection: ExamStartProjection,
) -> None:
    class FakeExamService:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_exam_start_projection(self, _exam_id: int) -> ExamStartProjection:
            return projection

        async def get_exam_start_session_state(
            self,
            _user_id: int,
            _exam_id: int,
        ) -> ExamStartSessionState:
            return ExamStartSessionState(attempt_count=0, existing_sessions=[])

    async def no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(exams, "ExamService", FakeExamService)
    monkeypatch.setattr(exams, "validate_seb_headers", no_op)
    monkeypatch.setattr(exams, "_ensure_exam_start_option_integrity", no_op)


async def _start(projection: ExamStartProjection, user: Any, db: FakeSession) -> Any:
    return await exams.start_exam_session(7, _request(), user, db)


@pytest.mark.asyncio
async def test_start_rejects_unpublished_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start_deps(monkeypatch, _projection(is_published=False))
    user = SimpleNamespace(id=5, role="student", username="s", student_class="XII")
    with pytest.raises(HTTPException) as exc:
        await _start(_projection(is_published=False), user, FakeSession())
    assert exc.value.status_code == 400
    assert "dipublikasikan" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_start_rejects_future_window(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    projection = _projection(
        start_time=now + timedelta(minutes=10),
        end_time=now + timedelta(minutes=70),
    )
    _patch_start_deps(monkeypatch, projection)
    user = SimpleNamespace(id=5, role="student", username="s", student_class="XII")
    with pytest.raises(HTTPException) as exc:
        await _start(projection, user, FakeSession())
    assert exc.value.status_code == 400
    assert "belum dimulai" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_start_rejects_ended_window(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    projection = _projection(
        start_time=now - timedelta(minutes=70),
        end_time=now - timedelta(minutes=10),
    )
    _patch_start_deps(monkeypatch, projection)
    user = SimpleNamespace(id=5, role="student", username="s", student_class="XII")
    with pytest.raises(HTTPException) as exc:
        await _start(projection, user, FakeSession())
    assert exc.value.status_code == 400
    assert "sudah berakhir" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_start_uses_live_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    projection = _projection(max_attempts=1)
    class FakeExamService:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_exam_start_projection(self, _exam_id: int) -> ExamStartProjection:
            return projection

        async def get_exam_start_session_state(
            self,
            _user_id: int,
            _exam_id: int,
        ) -> ExamStartSessionState:
            return ExamStartSessionState(attempt_count=1, existing_sessions=[])

    async def no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(exams, "ExamService", FakeExamService)
    monkeypatch.setattr(exams, "validate_seb_headers", no_op)
    monkeypatch.setattr(exams, "_ensure_exam_start_option_integrity", no_op)
    user = SimpleNamespace(id=5, role="student", username="s", student_class="XII")
    with pytest.raises(HTTPException) as exc:
        await _start(projection, user, FakeSession())
    assert exc.value.status_code == 400
    assert "percobaan" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_start_uses_live_allow_list(monkeypatch: pytest.MonkeyPatch) -> None:
    projection = _projection(allowed_classes="X", allowed_students=None)
    _patch_start_deps(monkeypatch, projection)
    user = SimpleNamespace(id=5, role="student", username="s", student_class="XII")
    with pytest.raises(HTTPException) as exc:
        await _start(projection, user, FakeSession())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_start_uses_live_creator_role_for_guruplus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = _projection(
        allowed_classes="GuruPlus",
        creator=ExamStartCreatorView(full_name="Guru", role="teacher"),
    )
    _patch_start_deps(monkeypatch, projection)
    user = SimpleNamespace(
        id=5,
        role="guruplus",
        username="gp",
        student_class="GuruPlus",
    )
    with pytest.raises(HTTPException) as exc:
        await _start(projection, user, FakeSession())
    assert exc.value.status_code == 403
    assert "developer" in str(exc.value.detail).lower()


def test_start_projection_has_no_process_cache() -> None:
    source = __import__("pathlib").Path("app/services/exam_service.py").read_text(
        encoding="utf-8"
    )
    projection_fn = source.split("async def get_exam_start_projection")[1].split(
        "async def ",
        1,
    )[0]
    assert "cache" not in projection_fn.lower()
    assert "_exam_start" not in projection_fn
