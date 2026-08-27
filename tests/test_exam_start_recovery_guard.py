from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import exams
from app.services.exam_service import ExamStartSessionState


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
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = iter(results)

    async def execute(self, _statement: Any) -> FakeResult:
        return next(self.results)

    def add(self, _value: Any) -> None:
        raise AssertionError("a replacement session must not be created")


@pytest.mark.asyncio
async def test_start_blocks_replacement_after_admin_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    exam = SimpleNamespace(
        id=7,
        creator_id=11,
        is_published=True,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=55),
        max_attempts=2,
        creator=SimpleNamespace(role="teacher", full_name="Guru"),
    )
    terminated_session = SimpleNamespace(
        id=41,
        status="terminated",
        start_time=now - timedelta(minutes=3),
        terminated_by_admin=True,
        violation_count=0,
    )
    db = FakeSession([FakeResult(rows=[])])

    class FakeExamService:
        def __init__(self, _db: FakeSession) -> None:
            pass

        async def get_exam_start_projection(self, _exam_id: int) -> Any:
            return exam

        async def get_exam_start_session_state(
            self,
            _user_id: int,
            _exam_id: int,
        ) -> ExamStartSessionState:
            return ExamStartSessionState(
                attempt_count=0,
                existing_sessions=[terminated_session],
            )

    async def no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def creator_role(*_args: Any, **_kwargs: Any) -> str:
        return "teacher"

    monkeypatch.setattr(exams, "ExamService", FakeExamService)
    monkeypatch.setattr(exams, "validate_seb_headers", no_op)
    monkeypatch.setattr(exams, "_ensure_exam_start_option_integrity", no_op)
    monkeypatch.setattr(exams, "_get_exam_creator_role", creator_role)
    monkeypatch.setattr(exams, "_ensure_exam_participant_access", lambda *_args, **_kwargs: None)

    request = Request(
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
    user = SimpleNamespace(id=5, role="student", username="student", student_class="XII")

    with pytest.raises(HTTPException) as exc_info:
        await exams.start_exam_session(7, request, user, db)

    assert exc_info.value.status_code == 409
    assert "pengawas" in str(exc_info.value.detail).lower()
