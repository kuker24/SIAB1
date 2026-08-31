from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.exam_crud import regenerate_exam_token, toggle_publish_exam
from app.api.exams import get_exam_results, get_session_answer_review
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
