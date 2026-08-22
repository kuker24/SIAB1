"""
Shared exam participant access policy helpers.
"""
from typing import Optional, Protocol, Set

from fastapi import HTTPException
from app.core.roles import ROLE_DEVELOPER

GURUPLUS_ROLE = "guruplus"
GURUPLUS_CLASS_NAME = "GuruPlus"


class ExamAccessPolicyExamLike(Protocol):
    allowed_students: Optional[str]
    allowed_classes: Optional[str]


class ExamAccessPolicyStudentLike(Protocol):
    id: int
    role: str
    student_class: Optional[str]


def parse_csv_restriction_values(raw_value: Optional[str], *, uppercase: bool = False) -> Set[str]:
    """
    Parse comma-separated restriction values from exam configuration.
    """
    if not raw_value:
        return set()

    values: Set[str] = set()
    for part in raw_value.split(","):
        normalized = part.strip()
        if not normalized:
            continue
        if uppercase:
            normalized = normalized.upper()
        values.add(normalized)
    return values


def normalize_role(role: Optional[str]) -> str:
    return str(role or "").strip().lower()


def is_exam_participant_role(role: Optional[str]) -> bool:
    normalized = normalize_role(role)
    return normalized in {"student", GURUPLUS_ROLE}


def student_has_exam_access(
    exam: ExamAccessPolicyExamLike,
    student: ExamAccessPolicyStudentLike,
) -> bool:
    """
    Evaluate class/student restriction consistently across join/start/list flows.
    """
    allowed_students = parse_csv_restriction_values(exam.allowed_students)
    if allowed_students and str(student.id) in allowed_students:
        return True

    allowed_classes = parse_csv_restriction_values(exam.allowed_classes, uppercase=True)
    if allowed_classes:
        student_class = (student.student_class or "").strip().upper()
        if student_class and student_class in allowed_classes:
            return True
        return False

    # If only explicit student list exists and the student is not listed -> blocked.
    if allowed_students:
        return False

    return True


def guruplus_has_exam_access(
    exam: ExamAccessPolicyExamLike,
    participant: ExamAccessPolicyStudentLike,
    *,
    exam_creator_role: Optional[str],
) -> bool:
    """
    GuruPlus access policy:
    - exam creator must be developer
    - participant must be explicitly targeted via class or allowed_students
    """
    if normalize_role(participant.role) != GURUPLUS_ROLE:
        return False

    if normalize_role(exam_creator_role) != ROLE_DEVELOPER:
        return False

    allowed_students = parse_csv_restriction_values(exam.allowed_students)
    if allowed_students and str(participant.id) in allowed_students:
        return True

    allowed_classes = parse_csv_restriction_values(exam.allowed_classes, uppercase=True)
    participant_class = (participant.student_class or "").strip()
    if not participant_class:
        return False

    if participant_class.upper() in allowed_classes:
        return True

    return False


def participant_has_exam_access(
    exam: ExamAccessPolicyExamLike,
    participant: ExamAccessPolicyStudentLike,
    *,
    exam_creator_role: Optional[str] = None,
) -> bool:
    role = normalize_role(participant.role)
    if role == "student":
        return student_has_exam_access(exam, participant)
    if role == GURUPLUS_ROLE:
        return guruplus_has_exam_access(
            exam,
            participant,
            exam_creator_role=exam_creator_role,
        )
    return False


def ensure_student_exam_access(
    exam: ExamAccessPolicyExamLike,
    student: ExamAccessPolicyStudentLike,
) -> None:
    """
    Raise HTTP 403 with user-friendly detail when student is not allowed.
    """
    if student_has_exam_access(exam, student):
        return

    if exam.allowed_classes:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Kelas Anda ({student.student_class or 'belum diatur'}) "
                "tidak diizinkan mengikuti ujian ini"
            ),
        )

    raise HTTPException(
        status_code=403,
        detail="Anda tidak termasuk peserta yang diizinkan untuk ujian ini",
    )


def ensure_guruplus_exam_access(
    exam: ExamAccessPolicyExamLike,
    participant: ExamAccessPolicyStudentLike,
    *,
    exam_creator_role: Optional[str],
) -> None:
    if guruplus_has_exam_access(
        exam,
        participant,
        exam_creator_role=exam_creator_role,
    ):
        return

    if normalize_role(exam_creator_role) != ROLE_DEVELOPER:
        raise HTTPException(
            status_code=403,
            detail="Akun GuruPlus hanya dapat mengikuti ujian yang dibuat developer.",
        )

    raise HTTPException(
        status_code=403,
        detail=(
            "Akun GuruPlus hanya dapat mengikuti ujian yang ditargetkan ke kelas "
            f"{GURUPLUS_CLASS_NAME} atau ditambahkan sebagai peserta khusus."
        ),
    )


def ensure_exam_participant_access(
    exam: ExamAccessPolicyExamLike,
    participant: ExamAccessPolicyStudentLike,
    *,
    exam_creator_role: Optional[str] = None,
) -> None:
    role = normalize_role(participant.role)
    if role == "student":
        ensure_student_exam_access(exam, participant)
        return
    if role == GURUPLUS_ROLE:
        ensure_guruplus_exam_access(
            exam,
            participant,
            exam_creator_role=exam_creator_role,
        )
        return

    raise HTTPException(
        status_code=403,
        detail="Role akun tidak diizinkan mengikuti ujian peserta.",
    )
