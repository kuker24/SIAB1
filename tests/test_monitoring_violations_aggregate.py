from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import monitoring


@pytest.mark.asyncio
async def test_violations_dashboard_auto_uses_aggregate_when_peak_mode(monkeypatch) -> None:
    called = {}

    async def fake_title(db, exam_id, current_user):
        return "Exam A"

    async def fake_aggregate(db, **kwargs):
        called.update(kwargs)
        return {"aggregate_only": True, "summary_only": True}

    monkeypatch.setattr(monitoring.settings, "exam_peak_mode", True)
    monkeypatch.setattr(monitoring.settings, "admin_monitoring_detail_level", "standard")
    monkeypatch.setattr(monitoring, "_resolve_selected_exam_title", fake_title)
    monkeypatch.setattr(monitoring, "_build_violations_aggregate_payload", fake_aggregate)

    result = await monitoring.get_violations_dashboard(
        exam_id=123,
        date_from=datetime.now(timezone.utc),
        date_to=datetime.now(timezone.utc),
        detail_level="auto",
        current_user=SimpleNamespace(id=7, role="teacher"),
        db=SimpleNamespace(),
    )

    assert result["aggregate_only"] is True
    assert called["exam_id"] == 123
    assert called["selected_exam_title"] == "Exam A"


@pytest.mark.asyncio
async def test_violations_dashboard_rejects_invalid_detail_level() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await monitoring.get_violations_dashboard(
            detail_level="full",
            current_user=SimpleNamespace(id=7, role="teacher"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_violations_dashboard_summary_detail_level_does_not_load_raw_logs(monkeypatch) -> None:
    async def fake_title(db, exam_id, current_user):
        return "Exam Summary"

    async def fake_aggregate(db, **kwargs):
        return {"detail_level": "summary", "selected_exam_title": kwargs["selected_exam_title"]}

    class _NoRawDb:
        async def execute(self, _stmt):
            raise AssertionError("raw logs should not be loaded in summary mode")

    monkeypatch.setattr(monitoring.settings, "exam_peak_mode", False)
    monkeypatch.setattr(monitoring, "_resolve_selected_exam_title", fake_title)
    monkeypatch.setattr(monitoring, "_build_violations_aggregate_payload", fake_aggregate)

    result = await monitoring.get_violations_dashboard(
        exam_id=123,
        detail_level="summary",
        current_user=SimpleNamespace(id=7, role="teacher"),
        db=_NoRawDb(),
    )

    assert result["detail_level"] == "summary"
    assert result["selected_exam_title"] == "Exam Summary"


@pytest.mark.asyncio
async def test_violations_dashboard_detail_level_loads_raw_logs(monkeypatch) -> None:
    called = {"execute": 0}

    class _Scalars:
        def all(self):
            return []

    class _Result:
        def scalars(self):
            return _Scalars()

    class _DetailDb:
        async def execute(self, stmt):
            called["execute"] += 1
            assert stmt == "detail-query"
            return _Result()

    async def fake_title(db, exam_id, current_user):
        return "Exam Detail"

    def fake_payload(logs, **kwargs):
        return {"detail_level": "detail", "logs": logs, "title": kwargs["selected_exam_title"]}

    monkeypatch.setattr(monitoring.settings, "exam_peak_mode", False)
    monkeypatch.setattr(monitoring.settings, "admin_monitoring_detail_level", "detail")
    monkeypatch.setattr(monitoring, "_build_violations_query", lambda **_kwargs: "detail-query")
    monkeypatch.setattr(monitoring, "_resolve_selected_exam_title", fake_title)
    monkeypatch.setattr(monitoring, "_build_violations_dashboard_payload", fake_payload)

    result = await monitoring.get_violations_dashboard(
        exam_id=123,
        detail_level="detail",
        current_user=SimpleNamespace(id=7, role="teacher"),
        db=_DetailDb(),
    )

    assert result["detail_level"] == "detail"
    assert called["execute"] == 1


@pytest.mark.asyncio
async def test_violations_export_disabled_when_heavy_exports_inactive(monkeypatch) -> None:
    monkeypatch.setattr(monitoring.settings, "heavy_export_enabled", False)
    monkeypatch.setattr(monitoring.settings, "exam_peak_mode", False)

    with pytest.raises(HTTPException) as exc_info:
        await monitoring.export_violations_dashboard(
            current_user=SimpleNamespace(id=7, role="teacher"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 503
