import asyncio
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects import postgresql

from app.api import exams


def _stats(**overrides: Any) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "total_participants": 6,
        "active_sessions": 1,
        "completed_sessions": 4,
        "scored_sessions": 3,
        "average_score": Decimal("45.3333333333"),
        "highest_score": Decimal("81"),
        "lowest_score": Decimal("15"),
        "passed_sessions": 2,
        "score_0_20": 1,
        "score_21_40": 1,
        "score_41_60": 0,
        "score_61_80": 0,
        "score_81_100": 1,
        "total_violations": 8,
    }
    stats.update(overrides)
    return stats


def test_exam_analytics_aggregate_stats_preserve_legacy_score_semantics() -> None:
    analytics = exams._build_exam_analytics_from_aggregate_row(
        677,
        Decimal("40"),
        _stats(),
    )

    assert analytics.exam_id == 677
    assert analytics.total_participants == 6
    assert analytics.active_sessions == 1
    assert analytics.completed_sessions == 4
    assert analytics.average_score == 45.33
    assert analytics.highest_score == 81.0
    assert analytics.lowest_score == 15.0
    assert analytics.pass_rate == 50.0
    assert analytics.score_distribution == {
        "0-20": 1,
        "21-40": 1,
        "41-60": 0,
        "61-80": 0,
        "81-100": 1,
    }
    assert analytics.difficult_questions == []
    assert analytics.violation_stats == {"total_violations": 8}


def test_exam_analytics_aggregate_stats_keep_legacy_falsy_passing_score() -> None:
    analytics = exams._build_exam_analytics_from_aggregate_row(
        677,
        Decimal("0"),
        _stats(passed_sessions=0),
    )

    assert analytics.pass_rate == 75.0


def test_exam_analytics_aggregate_stats_keep_empty_session_response() -> None:
    analytics = exams._build_exam_analytics_from_aggregate_row(
        677,
        Decimal("70"),
        _stats(
            total_participants=0,
            active_sessions=0,
            completed_sessions=0,
            scored_sessions=0,
            total_violations=0,
        ),
    )

    assert analytics.model_dump() == {
        "exam_id": 677,
        "total_participants": 0,
        "active_sessions": 0,
        "completed_sessions": 0,
        "average_score": 0.0,
        "highest_score": 0.0,
        "lowest_score": 0.0,
        "pass_rate": 0.0,
        "score_distribution": {},
        "difficult_questions": [],
        "violation_stats": {},
    }


class _MappingResult:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row

    def mappings(self) -> "_MappingResult":
        return self

    def one_or_none(self) -> dict[str, Any]:
        return self.row

    def one(self) -> dict[str, Any]:
        return self.row


class _AnalyticsDB:
    def __init__(self) -> None:
        self.statements: list[Any] = []
        self._results = [
            _MappingResult({"creator_id": 85132, "passing_score": Decimal("40")}),
            _MappingResult(_stats()),
        ]

    async def execute(self, statement: Any) -> _MappingResult:
        self.statements.append(statement)
        return self._results.pop(0)


def test_exam_analytics_uses_scalar_queries_without_relationship_loading() -> None:
    async def allow_access(*_args: Any, **_kwargs: Any) -> str:
        return "developer"

    original_access_check = exams._enforce_exam_owner_or_admin_access
    exams._enforce_exam_owner_or_admin_access = allow_access
    try:
        db = _AnalyticsDB()
        analytics = asyncio.run(exams.get_exam_analytics(677, object(), db))
    finally:
        exams._enforce_exam_owner_or_admin_access = original_access_check

    assert analytics.total_participants == 6
    assert len(db.statements) == 2

    exam_sql = str(
        db.statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    stats_sql = str(
        db.statements[1].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "FROM exams" in exam_sql
    assert "JOIN" not in exam_sql
    assert "FROM exam_sessions" in stats_sql
    assert "JOIN" not in stats_sql
    assert " answers" not in stats_sql
    assert " exam_logs" not in stats_sql
    assert " users" not in stats_sql
