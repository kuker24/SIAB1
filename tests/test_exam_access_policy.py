from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.exam_access_policy import (
    ensure_exam_participant_access,
    ensure_student_exam_access,
    is_exam_participant_role,
    parse_csv_restriction_values,
    participant_has_exam_access,
    student_has_exam_access,
)


def test_parse_csv_restriction_values_handles_trim_and_case() -> None:
    assert parse_csv_restriction_values(" 1,2 , 3 ,,") == {"1", "2", "3"}
    assert parse_csv_restriction_values("xii a, xii b", uppercase=True) == {"XII A", "XII B"}
    assert parse_csv_restriction_values(None) == set()


def test_student_has_exam_access_when_student_id_is_whitelisted() -> None:
    exam = SimpleNamespace(allowed_students="10,11", allowed_classes=None)
    student = SimpleNamespace(id=11, student_class="XII A")
    assert student_has_exam_access(exam, student) is True


def test_student_has_exam_access_when_class_is_allowed() -> None:
    exam = SimpleNamespace(allowed_students=None, allowed_classes="XII A, XII B")
    student = SimpleNamespace(id=99, student_class="xii b")
    assert student_has_exam_access(exam, student) is True


def test_student_access_denied_when_only_whitelist_exists_and_user_not_listed() -> None:
    exam = SimpleNamespace(allowed_students="10,11", allowed_classes=None)
    student = SimpleNamespace(id=12, student_class="XII A")
    assert student_has_exam_access(exam, student) is False


def test_ensure_student_exam_access_raises_with_class_message() -> None:
    exam = SimpleNamespace(allowed_students=None, allowed_classes="XII C")
    student = SimpleNamespace(id=12, student_class="XII A")

    with pytest.raises(HTTPException) as exc:
        ensure_student_exam_access(exam, student)

    assert exc.value.status_code == 403
    assert "Kelas Anda" in str(exc.value.detail)


def test_ensure_student_exam_access_raises_with_whitelist_message() -> None:
    exam = SimpleNamespace(allowed_students="10,11", allowed_classes=None)
    student = SimpleNamespace(id=12, student_class="XII A")

    with pytest.raises(HTTPException) as exc:
        ensure_student_exam_access(exam, student)

    assert exc.value.status_code == 403
    assert "tidak termasuk peserta" in str(exc.value.detail)


def test_is_exam_participant_role_supports_guruplus() -> None:
    assert is_exam_participant_role("student") is True
    assert is_exam_participant_role("guruplus") is True
    assert is_exam_participant_role("teacher") is False


def test_guruplus_access_allowed_for_developer_exam_with_class_target() -> None:
    exam = SimpleNamespace(allowed_students=None, allowed_classes="XII A,GuruPlus")
    participant = SimpleNamespace(id=55, role="guruplus", student_class="GuruPlus")

    assert participant_has_exam_access(
        exam,
        participant,
        exam_creator_role="developer",
    ) is True


def test_guruplus_access_denied_when_exam_not_created_by_developer() -> None:
    exam = SimpleNamespace(allowed_students=None, allowed_classes="GuruPlus")
    participant = SimpleNamespace(id=55, role="guruplus", student_class="GuruPlus")

    assert participant_has_exam_access(
        exam,
        participant,
        exam_creator_role="teacher",
    ) is False


def test_ensure_exam_participant_access_for_guruplus_requires_explicit_target() -> None:
    exam = SimpleNamespace(allowed_students=None, allowed_classes="XII A")
    participant = SimpleNamespace(id=55, role="guruplus", student_class="GuruPlus")

    with pytest.raises(HTTPException) as exc:
        ensure_exam_participant_access(
            exam,
            participant,
            exam_creator_role="developer",
        )

    assert exc.value.status_code == 403
    assert "GuruPlus" in str(exc.value.detail)
