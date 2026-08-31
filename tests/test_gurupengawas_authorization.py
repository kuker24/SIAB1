from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.exam_crud import regenerate_exam_token, toggle_publish_exam
from app.api.exams import get_exam_results, get_session_answer_review
from app.api.websocket import monitor_websocket_deny_reason
from app.core.roles import (
    ROLE_GURUPENGAWAS,
    can_assign_role,
    is_gurupengawas_role,
    is_monitor_scope_role,
    is_teacher_scope_role,
)
from app.core.security import (
    get_current_exam_monitor,
    get_current_teacher,
    is_pengawas_identity,
    is_pengawas_user,
)

ROOT = Path(__file__).resolve().parents[1]


class _DatabaseMustNotBeUsed:
    async def execute(self, _statement):
        raise AssertionError("authorization must be checked before database access")


def _monitor_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=41,
        role=ROLE_GURUPENGAWAS,
        job_title="Pengawas",
        is_admin=False,
        is_teacher=False,
    )


def test_gurupengawas_identity_is_role_based() -> None:
    assert is_gurupengawas_role(ROLE_GURUPENGAWAS) is True
    assert is_pengawas_identity(ROLE_GURUPENGAWAS, None) is True
    assert is_pengawas_identity("teacher", "Pengawas") is False
    assert is_pengawas_user(SimpleNamespace(role="teacher", job_title="Pengawas")) is False
    assert is_pengawas_user(_monitor_user()) is True
    assert is_teacher_scope_role(ROLE_GURUPENGAWAS) is False
    assert is_monitor_scope_role(ROLE_GURUPENGAWAS) is True
    assert can_assign_role("admin", ROLE_GURUPENGAWAS) is True


@pytest.mark.asyncio
async def test_gurupengawas_login_skips_apk_token_requirement(monkeypatch) -> None:
    from app.utils.apk_validation import APKTokenValidator

    async def _no_bypass():
        return False

    monkeypatch.setattr(APKTokenValidator, "is_bypass_enabled", staticmethod(_no_bypass))
    monkeypatch.setattr("app.core.cache.is_developer_mode_enabled", _no_bypass)
    result = await APKTokenValidator.validate_apk_token(
        None,
        ROLE_GURUPENGAWAS,
        "pengawas1",
        "Mozilla/5.0",
    )
    assert result["valid"] is True
    assert "staff" in result["reason"]


@pytest.mark.asyncio
async def test_get_current_teacher_rejects_gurupengawas() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_current_teacher(current_user=_monitor_user())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_exam_monitor_allows_gurupengawas() -> None:
    user = await get_current_exam_monitor(current_user=_monitor_user())
    assert user.role == ROLE_GURUPENGAWAS


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [toggle_publish_exam, regenerate_exam_token])
async def test_gurupengawas_cannot_mutate_exam(endpoint) -> None:
    with pytest.raises(HTTPException) as exc:
        await endpoint(
            exam_id=7,
            current_user=_monitor_user(),
            db=_DatabaseMustNotBeUsed(),
        )
    assert exc.value.status_code == 403
    assert "Pengawas" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_gurupengawas_cannot_request_result_breakdown() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_exam_results(
            exam_id=7,
            include_breakdown=True,
            current_user=_monitor_user(),
            db=_DatabaseMustNotBeUsed(),
        )
    assert exc.value.status_code == 403
    assert "rincian" in str(exc.value.detail).lower() or "Pengawas" in str(exc.value.detail)


def test_gurupengawas_can_open_published_monitor_websocket() -> None:
    published = SimpleNamespace(id=7, creator_id=9, is_published=True, is_deleted=False)
    unpublished = SimpleNamespace(id=8, creator_id=9, is_published=False, is_deleted=False)
    foreign = SimpleNamespace(id=9, creator_id=99, is_published=True, is_deleted=False)
    pengawas = SimpleNamespace(id=41, role=ROLE_GURUPENGAWAS, job_title="Guru Pengawas")
    teacher = SimpleNamespace(id=9, role="teacher", job_title="Guru")
    student = SimpleNamespace(id=51, role="student", job_title=None)

    assert monitor_websocket_deny_reason(pengawas, published) is None
    denied_draft = monitor_websocket_deny_reason(pengawas, unpublished)
    assert denied_draft is not None and denied_draft[0] == 4403
    assert monitor_websocket_deny_reason(pengawas, None) == (4404, "Exam not found")
    assert monitor_websocket_deny_reason(teacher, published) is None
    denied_foreign = monitor_websocket_deny_reason(teacher, foreign)
    assert denied_foreign is not None and denied_foreign[0] == 4403
    denied_student = monitor_websocket_deny_reason(student, published)
    assert denied_student is not None and denied_student[0] == 4403


def test_pengawas_live_monitor_page_skips_admin_ops_and_busts_cache() -> None:
    template = (ROOT / "templates/admin/monitoring.html").read_text(encoding="utf-8")
    core = (ROOT / "static/js/admin/monitoring/modules/00-core-ops-and-sessions.js").read_text(
        encoding="utf-8"
    )
    pause = (ROOT / "static/js/admin/monitoring/modules/10-pause-websocket-student-detail.js").read_text(
        encoding="utf-8"
    )
    bundle = (ROOT / "static/js/admin/monitoring.js").read_text(encoding="utf-8")
    assert "monitoring.js?v=20260831-gpmonitor1" in template
    for source in (core, bundle):
        assert "auth.requireAuth(['admin', 'developer', 'teacher', 'gurupengawas'])" in source
        assert "const hideOpsSummary = isTeacher || isPengawas;" in source
        assert "if (hideOpsSummary) {\n                    await loadActiveExams();" in source
    for source in (pause, bundle):
        assert "if (!hideOpsSummary) {\n                    await loadOpsSummary();" in source


@pytest.mark.asyncio
async def test_gurupengawas_cannot_review_answers_via_teacher_gate() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_session_answer_review(
            exam_id=7,
            session_id=9,
            current_user=_monitor_user(),
            db=_DatabaseMustNotBeUsed(),
        )
    assert exc.value.status_code == 403
