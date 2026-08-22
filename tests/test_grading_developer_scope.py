from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.api.grading import _apply_grading_query_scope, _can_grade_exam_creator
from app.models.exam import Exam


GRADING_TEMPLATE = Path("templates/admin/grading.html").read_text(encoding="utf-8")


def _user(user_id: int, role: str):
    return SimpleNamespace(id=user_id, role=role)


def _compiled_sql(query) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True}))


def test_developer_can_grade_only_own_exam_creator_id() -> None:
    developer = _user(42, "developer")

    assert _can_grade_exam_creator(developer, 42) is True
    assert _can_grade_exam_creator(developer, 7) is False


def test_teacher_can_grade_only_own_exam_creator_id() -> None:
    teacher = _user(11, "teacher")

    assert _can_grade_exam_creator(teacher, 11) is True
    assert _can_grade_exam_creator(teacher, 42) is False


def test_developer_pending_query_is_scoped_to_own_exams() -> None:
    query = _apply_grading_query_scope(select(Exam.id), _user(42, "developer"))
    sql = _compiled_sql(query)

    assert "exams.creator_id = 42" in sql


def test_admin_query_keeps_existing_non_developer_visibility() -> None:
    query = _apply_grading_query_scope(select(Exam.id), _user(1, "admin"))
    sql = _compiled_sql(query)

    assert "exams.creator_id = 1" not in sql
    assert "developer" in sql


def test_grading_ui_summary_only_is_admin_not_developer() -> None:
    assert "const summaryOnlyRoles = new Set(['admin']);" in GRADING_TEMPLATE
    assert "summaryOnlyRoles = new Set(['admin', 'developer'])" not in GRADING_TEMPLATE


def test_grading_ui_filters_developer_exam_dropdown_to_own_exams() -> None:
    assert "if (currentRole === 'developer')" in GRADING_TEMPLATE
    assert "Number(exam.creator_id) === currentUserId" in GRADING_TEMPLATE
