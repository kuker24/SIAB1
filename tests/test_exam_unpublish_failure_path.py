from types import SimpleNamespace
from typing import Any

import pytest

from app.api import exam_crud


class FakeResult:
    def __init__(
        self,
        *,
        scalar_value: Any = None,
        rows: list[Any] | None = None,
        rowcount: int = 0,
    ) -> None:
        self.scalar_value = scalar_value
        self.rows = rows or []
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> Any:
        return self.scalar_value

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list[Any]:
        return self.rows


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = iter(results)
        self.commit_count = 0

    async def execute(self, _statement: Any) -> FakeResult:
        return next(self.results)

    async def commit(self) -> None:
        self.commit_count += 1


@pytest.mark.asyncio
async def test_unpublish_monitor_failure_does_not_break_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exam = SimpleNamespace(id=7, creator_id=3, is_published=True)
    db = FakeSession(
        [
            FakeResult(scalar_value=exam),
            FakeResult(rows=[]),
            FakeResult(rowcount=2),
        ]
    )
    user = SimpleNamespace(
        id=3,
        role="teacher",
        username="teacher",
        full_name="Teacher",
    )

    async def no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def monitor_failure(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("monitor unavailable")

    monkeypatch.setattr(exam_crud, "_enforce_exam_owner_or_admin_access", no_op)
    monkeypatch.setattr(exam_crud, "is_pengawas_user", lambda _user: False)
    monkeypatch.setattr(exam_crud, "_publish_exam_monitor_event", monitor_failure)

    result = await exam_crud.toggle_publish_exam(7, user, db)

    assert result["is_published"] is False
    assert db.commit_count == 3
