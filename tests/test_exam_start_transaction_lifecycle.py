from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest
import sqlalchemy
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api import exams
from app.services.exam_service import (
    ExamStartCreatorView,
    ExamStartProjection,
    ExamStartSessionRow,
    ExamStartSessionState,
)


class FakeResult:
    def __init__(self, *, rows: list[Any] | None = None) -> None:
        self.rows = rows or []

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list[Any]:
        return self.rows

    def scalar_one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None


class FakeSession:
    def __init__(self, results: Optional[list[FakeResult]] = None) -> None:
        self.results = iter(results or [])
        self.added: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.flush_error: Optional[BaseException] = None
        self.commit_error: Optional[BaseException] = None
        self.log_error: Optional[BaseException] = None

    async def execute(self, _statement: Any) -> FakeResult:
        try:
            return next(self.results)
        except StopIteration:
            return FakeResult()

    def add(self, value: Any) -> None:
        if self.log_error is not None and getattr(value, "event_type", None):
            raise self.log_error
        self.added.append(value)
        if getattr(value, "user_id", None) == 5 and getattr(value, "id", None) is None:
            value.id = 99
            if getattr(value, "start_time", None) is None:
                value.start_time = datetime.now(timezone.utc)
            value.violation_count = getattr(value, "violation_count", 0) or 0
            value.total_paused_seconds = getattr(value, "total_paused_seconds", 0) or 0

    async def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.added.clear()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _projection(**overrides: Any) -> ExamStartProjection:
    now = _now()
    values: dict[str, Any] = {
        "id": 7,
        "creator_id": 11,
        "is_published": True,
        "start_time": now - timedelta(minutes=5),
        "end_time": now + timedelta(minutes=55),
        "max_attempts": 2,
        "allowed_classes": None,
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


def _session_row(**overrides: Any) -> ExamStartSessionRow:
    values: dict[str, Any] = {
        "id": 41,
        "status": "in_progress",
        "start_time": _now() - timedelta(minutes=3),
        "end_time": None,
        "terminated_by_admin": False,
        "emergency_exit_allowed": False,
        "violation_count": 0,
        "total_paused_seconds": 0,
    }
    values.update(overrides)
    return ExamStartSessionRow(**values)


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


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=5, role="student", username="student", student_class="XII")


def _patch_start(
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: ExamStartSessionState,
) -> None:
    class FakeExamService:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_exam_start_projection(self, _exam_id: int) -> ExamStartProjection:
            return _projection()

        async def get_exam_start_session_state(
            self,
            _user_id: int,
            _exam_id: int,
        ) -> ExamStartSessionState:
            return state

        async def get_questions_payload(self, _exam_id: int) -> list[dict[str, Any]]:
            return [
                {
                    "id": 1,
                    "question_text": "Q1",
                    "question_type": "multiple_choice",
                    "points": 1,
                    "order_index": 1,
                    "options": [{"id": 11, "option_text": "A", "order_index": 1}],
                }
            ]

    async def no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(exams, "ExamService", FakeExamService)
    monkeypatch.setattr(exams, "validate_seb_headers", no_op)
    monkeypatch.setattr(exams, "_ensure_exam_start_option_integrity", no_op)
    monkeypatch.setattr(exams, "_ensure_exam_participant_access", lambda *_a, **_k: None)
    monkeypatch.setattr(
        exams,
        "get_client_info",
        lambda _request: {
            "ip_address": "127.0.0.1",
            "user_agent": "test",
            "seb_detected": False,
        },
    )
    monkeypatch.setattr(exams, "get_session_data", no_op)
    monkeypatch.setattr(exams, "store_session_data", no_op)
    monkeypatch.setattr(exams, "_publish_exam_monitor_event", no_op)
    monkeypatch.setattr(exams, "create_session_poll_token", lambda **_k: "tok")


def test_empty_sqlalchemy_commit_is_logical_only() -> None:
    engine = create_engine("sqlite://")
    sql: list[str] = []
    events: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany) -> None:
        sql.append(str(statement))

    def _after_commit(_session) -> None:
        events.append("commit")

    event.listen(engine, "before_cursor_execute", _before)
    event.listen(Session, "after_commit", _after_commit)
    try:
        session = Session(engine, expire_on_commit=False, autoflush=False)
        session.execute(text("SELECT 1"))
        session.commit()
        sql.clear()
        events.clear()
        session.commit()
        session.close()
        assert events == ["commit"]
        assert sql == []
    finally:
        event.remove(engine, "before_cursor_execute", _before)
        event.remove(Session, "after_commit", _after_commit)


def test_start_has_single_explicit_commit() -> None:
    source = Path("app/api/exams.py").read_text(encoding="utf-8")
    fn = source.split("async def start_exam_session")[1].split("async def ", 1)[0]
    assert fn.count("await db.commit()") == 1
    assert fn.count("await db.flush()") == 1
    assert fn.count("await db.rollback()") == 1
    assert "begin_nested" not in fn


def test_get_db_still_commits_on_success() -> None:
    source = Path("app/database.py").read_text(encoding="utf-8")
    fn = source.split("async def get_db()")[1].split("async def ", 1)[0]
    assert "await session.commit()" in fn


@pytest.mark.asyncio
async def test_create_commits_once_before_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[]),
    )
    db = FakeSession()
    response = await exams.start_exam_session(7, _request(), _user(), db)
    assert response.session_id == 99
    assert db.commits == 1
    assert db.rollbacks == 0
    assert any(getattr(item, "event_type", None) == "SESSION_START" for item in db.added)


@pytest.mark.asyncio
async def test_resume_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(
            attempt_count=0,
            existing_sessions=[_session_row()],
        ),
    )
    db = FakeSession()
    response = await exams.start_exam_session(7, _request(), _user(), db)
    assert response.session_id == 41
    assert db.commits == 1


@pytest.mark.asyncio
async def test_recovery_commits_once_with_session_and_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _session_row(status="terminated", terminated_by_admin=False)
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[row]),
    )
    db = FakeSession()
    response = await exams.start_exam_session(7, _request(), _user(), db)
    assert response.session_id == 41
    assert db.commits == 1
    assert any(
        getattr(item, "event_type", None) == "SESSION_AUTO_RESET_NETWORK"
        for item in db.added
    )


@pytest.mark.asyncio
async def test_session_insert_failure_leaves_no_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[]),
    )
    db = FakeSession()
    db.flush_error = RuntimeError("insert failed")
    with pytest.raises(RuntimeError, match="insert failed"):
        await exams.start_exam_session(7, _request(), _user(), db)
    assert db.commits == 0


@pytest.mark.asyncio
async def test_examlog_insert_failure_does_not_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[]),
    )
    db = FakeSession()
    db.log_error = RuntimeError("log failed")
    with pytest.raises(RuntimeError, match="log failed"):
        await exams.start_exam_session(7, _request(), _user(), db)
    assert db.commits == 0


@pytest.mark.asyncio
async def test_commit_failure_does_not_mark_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[]),
    )
    db = FakeSession()
    db.commit_error = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        await exams.start_exam_session(7, _request(), _user(), db)
    assert db.commits == 0


@pytest.mark.asyncio
async def test_integrity_error_race_still_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[]),
    )
    raced = SimpleNamespace(
        id=77,
        status="in_progress",
        start_time=_now(),
        end_time=None,
        violation_count=0,
        total_paused_seconds=0,
    )
    db = FakeSession([FakeResult(rows=[raced])])
    db.flush_error = sqlalchemy.exc.IntegrityError("insert", {}, Exception("dup"))
    response = await exams.start_exam_session(7, _request(), _user(), db)
    assert response.session_id == 77
    assert db.rollbacks == 1
    assert db.commits == 1


@pytest.mark.asyncio
async def test_retry_after_failed_start_can_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[]),
    )
    failing = FakeSession()
    failing.flush_error = RuntimeError("insert failed")
    with pytest.raises(RuntimeError):
        await exams.start_exam_session(7, _request(), _user(), failing)
    retry = FakeSession()
    response = await exams.start_exam_session(7, _request(), _user(), retry)
    assert response.session_id == 99
    assert retry.commits == 1
    assert retry.rollbacks == 0


@pytest.mark.asyncio
async def test_max_attempts_still_blocks_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        state=ExamStartSessionState(attempt_count=2, existing_sessions=[]),
    )
    db = FakeSession()
    with pytest.raises(HTTPException) as exc:
        await exams.start_exam_session(7, _request(), _user(), db)
    assert exc.value.status_code == 400
    assert db.commits == 0
    assert db.added == []
