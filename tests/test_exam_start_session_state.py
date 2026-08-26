from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest
import sqlalchemy
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from app.api import exams
from app.services.exam_service import (
    COMPLETED_ATTEMPT_STATUSES,
    START_EXISTING_SESSION_LIMIT,
    START_EXISTING_SESSION_STATUSES,
    ExamService,
    ExamStartCreatorView,
    ExamStartProjection,
    ExamStartSessionRow,
    ExamStartSessionState,
    build_exam_start_session_state_statement,
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

    def scalar_one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None


class FakeSession:
    def __init__(self, results: Optional[list[FakeResult]] = None) -> None:
        self.results = iter(results or [])
        self.added: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.flush_error: Optional[BaseException] = None

    async def execute(self, _statement: Any) -> FakeResult:
        try:
            return next(self.results)
        except StopIteration:
            return FakeResult()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


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
        "max_attempts": 1,
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


def _user(**overrides: Any) -> SimpleNamespace:
    values = {
        "id": 5,
        "role": "student",
        "username": "student",
        "student_class": "XII",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch_start(
    monkeypatch: pytest.MonkeyPatch,
    *,
    projection: ExamStartProjection,
    state: ExamStartSessionState,
    questions: Optional[list[dict[str, Any]]] = None,
) -> None:
    payload = questions if questions is not None else [
        {
            "id": 1,
            "question_text": "Q1",
            "question_type": "multiple_choice",
            "points": 1,
            "order_index": 1,
            "options": [{"id": 11, "option_text": "A", "order_index": 1}],
        }
    ]

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
            return state

        async def get_questions_payload(self, _exam_id: int) -> list[dict[str, Any]]:
            return payload

    async def no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def no_data(*_args: Any, **_kwargs: Any) -> None:
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
    monkeypatch.setattr(exams, "get_session_data", no_data)
    monkeypatch.setattr(exams, "store_session_data", no_op)
    monkeypatch.setattr(exams, "_publish_exam_monitor_event", no_op)
    monkeypatch.setattr(exams, "create_session_poll_token", lambda **_k: "tok")


def test_merged_statement_is_one_index_friendly_select() -> None:
    stmt = build_exam_start_session_state_statement(5, 7)
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert sql.count("select") >= 3
    assert "count(" in sql
    assert "left outer join" in sql
    assert "limit" in sql
    assert "completed" in sql
    assert "submitted" in sql
    assert "in_progress" in sql
    assert "terminated" in sql
    assert "start_time" in sql
    assert "password" not in sql
    assert "for update" not in sql
    assert "selectin" not in sql


def test_status_sets_stay_disjoint() -> None:
    assert set(COMPLETED_ATTEMPT_STATUSES).isdisjoint(START_EXISTING_SESSION_STATUSES)
    assert START_EXISTING_SESSION_LIMIT == 16


@pytest.mark.asyncio
async def test_state_parser_keeps_count_when_no_existing_rows() -> None:
    row = SimpleNamespace(
        attempt_count=2,
        id=None,
        status=None,
        start_time=None,
        end_time=None,
        terminated_by_admin=None,
        emergency_exit_allowed=None,
        violation_count=None,
        total_paused_seconds=None,
    )
    service = ExamService(FakeSession([FakeResult(rows=[row])]))
    state = await service.get_exam_start_session_state(5, 7)
    assert state.attempt_count == 2
    assert state.existing_sessions == []


@pytest.mark.asyncio
async def test_state_parser_keeps_existing_order() -> None:
    newer = SimpleNamespace(
        attempt_count=1,
        id=9,
        status="in_progress",
        start_time=_now(),
        end_time=None,
        terminated_by_admin=False,
        emergency_exit_allowed=False,
        violation_count=0,
        total_paused_seconds=0,
    )
    older = SimpleNamespace(
        attempt_count=1,
        id=8,
        status="terminated",
        start_time=_now() - timedelta(hours=1),
        end_time=_now(),
        terminated_by_admin=False,
        emergency_exit_allowed=False,
        violation_count=1,
        total_paused_seconds=12,
    )
    service = ExamService(FakeSession([FakeResult(rows=[newer, older])]))
    state = await service.get_exam_start_session_state(5, 7)
    assert state.attempt_count == 1
    assert [row.id for row in state.existing_sessions] == [9, 8]
    assert state.existing_sessions[1].total_paused_seconds == 12


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attempt_count", "max_attempts"),
    [
        (1, 1),
        (2, 1),
        (3, 3),
        (4, 3),
    ],
)
async def test_max_attempts_blocks_before_resume(
    monkeypatch: pytest.MonkeyPatch,
    attempt_count: int,
    max_attempts: int,
) -> None:
    if attempt_count < max_attempts:
        pytest.skip("not a blocking fixture")
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=max_attempts),
        state=ExamStartSessionState(
            attempt_count=attempt_count,
            existing_sessions=[_session_row(status="in_progress")],
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await exams.start_exam_session(7, _request(), _user(), FakeSession())
    assert exc.value.status_code == 400
    assert "percobaan" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_zero_prior_attempts_creates_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=1),
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[]),
    )
    created = SimpleNamespace(
        id=99,
        status="in_progress",
        start_time=_now(),
        end_time=None,
        violation_count=0,
        total_paused_seconds=0,
    )

    class CreatingSession(FakeSession):
        def add(self, value: Any) -> None:
            super().add(value)
            if getattr(value, "user_id", None) == 5:
                value.id = created.id
                value.start_time = created.start_time
                value.status = created.status
                value.violation_count = 0
                value.total_paused_seconds = 0

    db = CreatingSession()
    response = await exams.start_exam_session(7, _request(), _user(), db)
    assert response.session_id == 99
    assert any(getattr(item, "event_type", None) == "SESSION_START" for item in db.added)


@pytest.mark.asyncio
async def test_one_completed_below_max_creates_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=2),
        state=ExamStartSessionState(attempt_count=1, existing_sessions=[]),
    )

    class CreatingSession(FakeSession):
        def add(self, value: Any) -> None:
            super().add(value)
            if getattr(value, "exam_id", None) == 7:
                value.id = 100
                value.start_time = _now()
                value.violation_count = 0
                value.total_paused_seconds = 0

    response = await exams.start_exam_session(7, _request(), _user(), CreatingSession())
    assert response.session_id == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["in_progress", "active"])
async def test_resume_existing_live_session(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    row = _session_row(id=41, status=status)
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=2),
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[row]),
    )
    db = FakeSession()
    response = await exams.start_exam_session(7, _request(), _user(), db)
    assert response.session_id == 41
    assert db.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["submitted", "completed"])
async def test_finished_status_is_not_resumed(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=2),
        state=ExamStartSessionState(attempt_count=1, existing_sessions=[]),
    )

    class CreatingSession(FakeSession):
        def add(self, value: Any) -> None:
            super().add(value)
            if getattr(value, "exam_id", None) == 7:
                value.id = 101
                value.start_time = _now()
                value.violation_count = 0
                value.total_paused_seconds = 0

    response = await exams.start_exam_session(7, _request(), _user(), CreatingSession())
    assert response.session_id == 101
    assert status in COMPLETED_ATTEMPT_STATUSES
    assert status not in START_EXISTING_SESSION_STATUSES


@pytest.mark.asyncio
async def test_terminated_network_recovers_same_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _session_row(id=41, status="terminated", terminated_by_admin=False)
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=2),
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[row]),
    )
    db = FakeSession([FakeResult(rows=[])])
    response = await exams.start_exam_session(7, _request(), _user(), db)
    assert response.session_id == 41
    assert row.status == "in_progress"
    assert any(
        getattr(item, "event_type", None) == "SESSION_AUTO_RESET_NETWORK"
        for item in db.added
    )


@pytest.mark.asyncio
async def test_kicked_network_recovers_same_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _session_row(id=42, status="kicked", terminated_by_admin=False)
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=2),
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[row]),
    )
    db = FakeSession([FakeResult(rows=[])])
    response = await exams.start_exam_session(7, _request(), _user(), db)
    assert response.session_id == 42


@pytest.mark.asyncio
async def test_active_plus_prior_completed_resumes_when_under_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _session_row(id=41, status="in_progress")
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=2),
        state=ExamStartSessionState(attempt_count=1, existing_sessions=[row]),
    )
    response = await exams.start_exam_session(7, _request(), _user(), FakeSession())
    assert response.session_id == 41


@pytest.mark.asyncio
async def test_integrity_error_resumes_raced_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=1),
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


@pytest.mark.asyncio
async def test_integrity_error_without_raced_session_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_start(
        monkeypatch,
        projection=_projection(max_attempts=1),
        state=ExamStartSessionState(attempt_count=0, existing_sessions=[]),
    )
    db = FakeSession([FakeResult(rows=[])])
    db.flush_error = sqlalchemy.exc.IntegrityError("insert", {}, Exception("dup"))
    with pytest.raises(HTTPException) as exc:
        await exams.start_exam_session(7, _request(), _user(), db)
    assert exc.value.status_code == 409
    assert db.rollbacks == 1


def test_merged_query_is_scoped_per_user_and_exam() -> None:
    sql = str(
        build_exam_start_session_state_statement(5, 7).compile(
            dialect=postgresql.dialect()
        )
    )
    assert sql.count("user_id") >= 2
    assert sql.count("exam_id") >= 2


def test_start_source_does_not_cache_session_state() -> None:
    start_fn = __import__("pathlib").Path("app/api/exams.py").read_text(encoding="utf-8")
    start_only = start_fn.split("async def start_exam_session")[1].split(
        "async def ",
        1,
    )[0]
    assert "get_exam_start_session_state" in start_only
    assert "cache_manager" not in start_only
    helper = __import__("pathlib").Path("app/services/exam_service.py").read_text(
        encoding="utf-8"
    )
    fn = helper.split("async def get_exam_start_session_state")[1].split(
        "async def ",
        1,
    )[0]
    assert "cache" not in fn.lower()
    assert "for update" not in fn.lower()
