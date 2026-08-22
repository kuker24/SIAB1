"""
Performance Analytics API endpoints.
Provides student and class-level performance tracking.
"""
from typing import Optional, List, Dict, Any, Tuple, Iterable
from datetime import datetime, timezone, timedelta
import logging
import math
import re
import statistics
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, case, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.database import get_db_read
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question
from app.models.session import ExamSession, Answer
from app.core.analytics_helpers import build_local_day_windows, display_question_number
from app.core.security import get_current_teacher
from app.core.roles import (
    ROLE_DEVELOPER,
    is_admin_scope_role,
    is_developer_exam_hidden_for_viewer,
    is_developer_role,
)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
logger = logging.getLogger(__name__)

PARTICIPANT_ROLES = ("student", "guruplus")
PAN_UM_MAPPING: Dict[str, Dict[str, str]] = {
    "A": {"um_range": "90 - 95", "predicate": "Sangat Baik", "um_min": "90", "um_max": "95"},
    "B": {"um_range": "85 - 89", "predicate": "Baik", "um_min": "85", "um_max": "89"},
    "C": {"um_range": "80 - 84", "predicate": "Cukup", "um_min": "80", "um_max": "84"},
    "D": {"um_range": "75 - 79", "predicate": "Kurang", "um_min": "75", "um_max": "79"},
    "E": {"um_range": "70 - 74", "predicate": "Sangat Kurang", "um_min": "70", "um_max": "74"},
}
PAP_GRADE_BANDS: List[Tuple[str, float, float, str]] = [
    ("A", 90.0, 100.0, "90 - 100"),
    ("B", 80.0, 89.9999, "80 - 89"),
    ("C", 70.0, 79.9999, "70 - 79"),
    ("D", 60.0, 69.9999, "60 - 69"),
    ("E", float("-inf"), 59.9999, "< 60"),
]
UAM_EXAM_TYPE_ALIASES: Tuple[str, ...] = (
    "ujian akhir madrasah",
    "ujian madrasah",
)


# === Schemas ===

class ScoreTrendItem(BaseModel):
    exam_id: int
    exam_title: str
    score: float
    date: Optional[str]


class StudentPerformance(BaseModel):
    student_id: int
    student_name: str
    student_class: Optional[str]
    total_exams: int
    average_score: float
    highest_score: float
    lowest_score: float
    pass_rate: float
    score_trend: List[ScoreTrendItem]
    total_violations: int


class ClassPerformance(BaseModel):
    class_name: str
    total_students: int
    total_exams_taken: int
    average_score: float
    highest_score: float
    lowest_score: float
    pass_rate: float
    top_performers: List[Dict[str, Any]]


class ExamClassItem(BaseModel):
    class_name: str
    participants: int


# === Internal Helpers ===
async def _ensure_exam_access(exam_id: int, current_user: User, db: AsyncSession):
    """Validate exam exists and current user may access it."""
    exam_result = await db.execute(
        select(Exam.id, Exam.creator_id, User.role.label("creator_role"))
        .join(User, User.id == Exam.creator_id)
        .where(
            Exam.id == exam_id,
            Exam.is_deleted == False
        )
    )
    exam_row = exam_result.first()
    if not exam_row:
        raise HTTPException(404, "Exam not found")

    if is_developer_exam_hidden_for_viewer(current_user.role, exam_row.creator_role):
        raise HTTPException(404, "Exam not found")

    if current_user.role == "teacher" and exam_row.creator_id != current_user.id:
        raise HTTPException(403, "Tidak memiliki akses ke exam ini")

    return exam_row


def _split_csv_classes(value: Optional[str]) -> List[str]:
    if value is None:
        return []
    class_items: List[str] = []
    seen_lower: set[str] = set()
    for raw_item in str(value).split(","):
        normalized = str(raw_item or "").strip()
        if not normalized:
            continue
        normalized_lower = normalized.lower()
        if normalized_lower in seen_lower:
            continue
        seen_lower.add(normalized_lower)
        class_items.append(normalized)
    return class_items


def _normalize_assessment_class_scope(
    class_name: Optional[str],
    class_names: Optional[str],
) -> List[str]:
    # Compatibility rules:
    # - Prefer class_names (CSV) when provided.
    # - Fallback to legacy single class_name.
    normalized_multi = _split_csv_classes(class_names)
    if normalized_multi:
        return normalized_multi

    normalized_single = str(class_name or "").strip()
    if normalized_single:
        return [normalized_single]

    raise HTTPException(status_code=400, detail="class_name atau class_names wajib diisi")


def _normalize_exam_type_text(value: Optional[str]) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _is_uam_exam_type(exam_type: Optional[str], exam_title: Optional[str] = None) -> bool:
    normalized_type = _normalize_exam_type_text(exam_type)
    if any(alias in normalized_type for alias in UAM_EXAM_TYPE_ALIASES):
        return True

    # Backward compatibility for legacy data where exam_type was left empty,
    # but title already carries UM/UAM naming.
    normalized_title = _normalize_exam_type_text(exam_title)
    if not normalized_title:
        return False
    if "ujian akhir madrasah" in normalized_title or "ujian madrasah" in normalized_title:
        return True
    if re.search(r"\buam\b", normalized_title):
        return True
    if re.search(r"\bum\b", normalized_title):
        return True
    return False


def _has_uam_sibling_with_same_title(
    exam_title: Optional[str],
    sibling_exam_items: Iterable[Tuple[Optional[str], Optional[str]]],
) -> bool:
    normalized_title = _normalize_exam_type_text(exam_title)
    if not normalized_title:
        return False

    for sibling_exam_type, sibling_exam_title in sibling_exam_items:
        if _normalize_exam_type_text(sibling_exam_title) != normalized_title:
            continue
        if _is_uam_exam_type(sibling_exam_type, sibling_exam_title):
            return True
    return False


async def _is_effective_uam_exam(exam: Exam, db: AsyncSession) -> bool:
    if _is_uam_exam_type(getattr(exam, "exam_type", None), getattr(exam, "title", None)):
        return True

    normalized_title = _normalize_exam_type_text(getattr(exam, "title", None))
    if not normalized_title:
        return False

    sibling_rows_result = await db.execute(
        select(Exam.exam_type, Exam.title)
        .where(
            Exam.is_deleted == False,
            Exam.creator_id == exam.creator_id,
            Exam.id != exam.id,
            func.lower(func.trim(Exam.title)) == normalized_title,
        )
    )
    sibling_items = [
        (row.exam_type, row.title)
        for row in sibling_rows_result
    ]
    return _has_uam_sibling_with_same_title(
        exam_title=getattr(exam, "title", None),
        sibling_exam_items=sibling_items,
    )


def _validate_assessment_scope_for_exam(
    is_uam_exam: bool,
    class_scope: List[str],
) -> None:
    if len(class_scope) > 1 and not is_uam_exam:
        raise HTTPException(
            status_code=400,
            detail="Gabungan kelas hanya tersedia untuk Ujian Akhir Madrasah",
        )


def _build_assessment_class_label(class_scope: List[str]) -> str:
    if len(class_scope) <= 1:
        return class_scope[0]
    return f"Gabungan Kelas: {', '.join(class_scope)}"


def _round_float(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _safe_percentage(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(value) / float(total)) * 100.0, 2)


def _format_wib_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        aware = value.replace(tzinfo=timezone.utc)
    else:
        aware = value
    wib_tz = timezone(timedelta(hours=7))
    return aware.astimezone(wib_tz).strftime("%d %B %Y %H:%M WIB")


def _build_pan_thresholds(mean_score: float, std_dev: float) -> Dict[str, float]:
    return {
        "a_min": mean_score + (1.5 * std_dev),
        "b_min": mean_score + (0.5 * std_dev),
        "c_min": mean_score - (0.5 * std_dev),
        "d_min": mean_score - (1.5 * std_dev),
    }


def _build_pan_scale10_thresholds(mean_score: float, std_dev: float) -> Dict[str, float]:
    return {
        "10_min": mean_score + (2.25 * std_dev),
        "9_min": mean_score + (1.75 * std_dev),
        "8_min": mean_score + (1.25 * std_dev),
        "7_min": mean_score + (0.75 * std_dev),
        "6_min": mean_score + (0.25 * std_dev),
        "5_min": mean_score - (0.25 * std_dev),
        "4_min": mean_score - (0.75 * std_dev),
        "3_min": mean_score - (1.25 * std_dev),
        "2_min": mean_score - (1.75 * std_dev),
        "1_min": mean_score - (2.25 * std_dev),
        "0_max": mean_score - (2.25 * std_dev),
    }


def _classify_pan_letter(score: float, mean_score: float, std_dev: float) -> str:
    if std_dev <= 0:
        return "C"
    thresholds = _build_pan_thresholds(mean_score, std_dev)
    if score >= thresholds["a_min"]:
        return "A"
    if score >= thresholds["b_min"]:
        return "B"
    if score >= thresholds["c_min"]:
        return "C"
    if score >= thresholds["d_min"]:
        return "D"
    return "E"


def _classify_pan_scale10(score: float, mean_score: float, std_dev: float) -> int:
    if std_dev <= 0:
        return 5
    thresholds = _build_pan_scale10_thresholds(mean_score, std_dev)
    if score >= thresholds["10_min"]:
        return 10
    if score >= thresholds["9_min"]:
        return 9
    if score >= thresholds["8_min"]:
        return 8
    if score >= thresholds["7_min"]:
        return 7
    if score >= thresholds["6_min"]:
        return 6
    if score >= thresholds["5_min"]:
        return 5
    if score >= thresholds["4_min"]:
        return 4
    if score >= thresholds["3_min"]:
        return 3
    if score >= thresholds["2_min"]:
        return 2
    if score >= thresholds["1_min"]:
        return 1
    return 0


def _classify_pap_letter(score: float) -> str:
    for grade, min_score, max_score, _ in PAP_GRADE_BANDS:
        if score >= min_score and score <= max_score:
            return grade
    return "E"


def _clamp_ratio(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _pick_latest_session_with_score_per_user(rows: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Select best session candidate per user from pre-sorted rows.

    Rows are expected to be ordered by:
    - user_id asc
    - end_time desc
    - session_id desc

    Selection rule:
    1. Prefer latest row with non-null score.
    2. If none has score, fallback to latest row.
    """
    latest_any: Dict[int, Dict[str, Any]] = {}
    latest_scored: Dict[int, Dict[str, Any]] = {}

    for row in rows:
        user_id = int(row["user_id"])
        if user_id not in latest_any:
            latest_any[user_id] = row
        if row.get("score") is not None and user_id not in latest_scored:
            latest_scored[user_id] = row

    selected: Dict[int, Dict[str, Any]] = {}
    for user_id, any_row in latest_any.items():
        selected[user_id] = latest_scored.get(user_id, any_row)
    return selected


def _compute_um_score(
    score: float,
    pan_letter: str,
    thresholds: Dict[str, float],
    lowest_score: float,
    highest_score: float,
) -> int:
    mapping = PAN_UM_MAPPING.get(str(pan_letter or "").upper(), {})
    try:
        um_min = int(float(mapping.get("um_min", "0")))
        um_max = int(float(mapping.get("um_max", "0")))
    except (TypeError, ValueError):
        um_min = 0
        um_max = 0

    if um_max <= um_min:
        return um_min

    a_min = float(thresholds.get("a_min", 0.0))
    b_min = float(thresholds.get("b_min", 0.0))
    c_min = float(thresholds.get("c_min", 0.0))
    d_min = float(thresholds.get("d_min", 0.0))

    lower = 0.0
    upper = 0.0
    grade = str(pan_letter or "").upper()
    if grade == "A":
        lower = a_min
        upper = max(highest_score, a_min)
    elif grade == "B":
        lower = b_min
        upper = max(a_min, b_min)
    elif grade == "C":
        lower = c_min
        upper = max(b_min, c_min)
    elif grade == "D":
        lower = d_min
        upper = max(c_min, d_min)
    else:
        lower = min(lowest_score, d_min)
        upper = max(d_min, lower)

    if upper <= lower:
        ratio = 0.5
    else:
        ratio = _clamp_ratio((float(score) - lower) / (upper - lower))

    return int(round(um_min + (ratio * (um_max - um_min))))


def _resolve_exam_teacher_name(exam: Exam) -> str:
    creator = getattr(exam, "creator", None)
    if creator:
        return str(creator.full_name or creator.username or "-")
    return "-"


async def _build_assessment_analysis_payload(
    exam_id: int,
    class_name: Optional[str],
    class_names: Optional[str],
    current_user: User,
    db: AsyncSession,
) -> Dict[str, Any]:
    class_scope = _normalize_assessment_class_scope(class_name, class_names)

    exam_result = await db.execute(
        select(Exam)
        .options(selectinload(Exam.creator))
        .where(Exam.id == exam_id, Exam.is_deleted == False)
    )
    exam = exam_result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if is_developer_exam_hidden_for_viewer(current_user.role, getattr(getattr(exam, "creator", None), "role", None)):
        raise HTTPException(status_code=404, detail="Exam not found")

    if current_user.role == "teacher" and exam.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke exam ini")

    is_uam_exam = await _is_effective_uam_exam(exam, db)
    _validate_assessment_scope_for_exam(is_uam_exam=is_uam_exam, class_scope=class_scope)

    class_scope_lower = [item.lower() for item in class_scope]
    class_filter = func.lower(func.trim(User.student_class)).in_(class_scope_lower)
    rows_result = await db.execute(
        select(
            ExamSession.id.label("session_id"),
            ExamSession.user_id.label("user_id"),
            ExamSession.score.label("score"),
            ExamSession.end_time.label("end_time"),
            User.full_name.label("full_name"),
            User.username.label("username"),
            User.student_class.label("student_class"),
        )
        .select_from(ExamSession)
        .join(User, User.id == ExamSession.user_id)
        .where(
            ExamSession.exam_id == exam_id,
            ExamSession.status.in_(["completed", "submitted"]),
            User.role.in_(PARTICIPANT_ROLES),
            class_filter,
        )
        .order_by(
            ExamSession.user_id.asc(),
            ExamSession.end_time.desc(),
            ExamSession.id.desc(),
        )
    )
    rows = [dict(item) for item in rows_result.mappings().all()]

    latest_session_by_user = _pick_latest_session_with_score_per_user(rows)

    participant_rows: List[Dict[str, Any]] = []
    for row in latest_session_by_user.values():
        if row.get("score") is None:
            continue
        score_value = float(row["score"])
        participant_rows.append(
            {
                "session_id": int(row["session_id"]),
                "user_id": int(row["user_id"]),
                "name": str(row.get("full_name") or row.get("username") or "Peserta"),
                "student_class": str(row.get("student_class") or class_scope[0]),
                "score": round(score_value, 2),
                "submitted_at": row.get("end_time"),
            }
        )

    participant_rows.sort(key=lambda item: (-float(item["score"]), item["name"].lower()))
    for index, row in enumerate(participant_rows, start=1):
        row["rank"] = index

    scores = [float(item["score"]) for item in participant_rows]
    kkm = float(exam.passing_score) if exam.passing_score is not None else 70.0
    score_count = len(scores)
    mean_score = statistics.mean(scores) if scores else 0.0
    std_dev = statistics.pstdev(scores) if len(scores) > 1 else 0.0
    highest_score = max(scores) if scores else 0.0
    lowest_score = min(scores) if scores else 0.0
    score_range = highest_score - lowest_score if scores else 0.0
    class_count = 1
    if score_count > 1:
        class_count = max(1, int(round(1 + (3.3 * math.log10(score_count)))))
    interval = (score_range / class_count) if class_count > 0 else 0.0

    thresholds = _build_pan_thresholds(mean_score, std_dev)
    scale10_thresholds = _build_pan_scale10_thresholds(mean_score, std_dev)

    pan_letter_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    pap_letter_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    pass_count = 0

    for row in participant_rows:
        score_value = float(row["score"])
        pan_letter = _classify_pan_letter(score_value, mean_score, std_dev)
        pan_scale10 = _classify_pan_scale10(score_value, mean_score, std_dev)
        t_score = 50.0 if std_dev <= 0 else 50.0 + (((score_value - mean_score) / std_dev) * 10.0)
        pap_letter = _classify_pap_letter(score_value)
        pap_passed = score_value >= kkm
        row["pan_letter"] = pan_letter
        row["pan_scale10"] = pan_scale10
        row["t_score"] = round(t_score, 2)
        row["pap_letter"] = pap_letter
        row["pap_status"] = "TUNTAS" if pap_passed else "TIDAK TUNTAS"
        mapping = PAN_UM_MAPPING.get(pan_letter, {})
        row["um_category"] = mapping.get("um_range", "-")
        row["um_predicate"] = mapping.get("predicate", "-")
        row["um_score"] = _compute_um_score(
            score=score_value,
            pan_letter=pan_letter,
            thresholds=thresholds,
            lowest_score=lowest_score,
            highest_score=highest_score,
        )
        pan_letter_counts[pan_letter] = int(pan_letter_counts.get(pan_letter, 0)) + 1
        pap_letter_counts[pap_letter] = int(pap_letter_counts.get(pap_letter, 0)) + 1
        if pap_passed:
            pass_count += 1

    fail_count = max(0, score_count - pass_count)

    pan_letter_distribution: List[Dict[str, Any]] = []
    pan_ranges = {
        "A": f">= {_round_float(thresholds['a_min'])}",
        "B": f"{_round_float(thresholds['b_min'])} - < {_round_float(thresholds['a_min'])}",
        "C": f"{_round_float(thresholds['c_min'])} - < {_round_float(thresholds['b_min'])}",
        "D": f"{_round_float(thresholds['d_min'])} - < {_round_float(thresholds['c_min'])}",
        "E": f"< {_round_float(thresholds['d_min'])}",
    }
    if std_dev <= 0:
        pan_ranges = {
            "A": "-",
            "B": "-",
            "C": f"= {_round_float(mean_score)}",
            "D": "-",
            "E": "-",
        }

    for grade in ["A", "B", "C", "D", "E"]:
        count = int(pan_letter_counts.get(grade, 0))
        pan_letter_distribution.append(
            {
                "grade": grade,
                "range": pan_ranges.get(grade, "-"),
                "count": count,
                "percentage": _safe_percentage(count, score_count),
            }
        )

    pap_distribution: List[Dict[str, Any]] = []
    for grade, _min_score, _max_score, range_text in PAP_GRADE_BANDS:
        count = int(pap_letter_counts.get(grade, 0))
        pap_distribution.append(
            {
                "grade": grade,
                "range": range_text,
                "count": count,
                "percentage": _safe_percentage(count, score_count),
            }
        )

    pan_um_summary: List[Dict[str, Any]] = []
    for grade in ["A", "B", "C", "D", "E"]:
        grade_rows = [item for item in participant_rows if item["pan_letter"] == grade]
        names = ", ".join(item["name"] for item in grade_rows[:8])
        if len(grade_rows) > 8:
            names = f"{names}, ..."
        mapping = PAN_UM_MAPPING.get(grade, {"um_range": "-", "predicate": "-"})
        pan_um_summary.append(
            {
                "category": grade,
                "pan_range": pan_ranges.get(grade, "-"),
                "count": len(grade_rows),
                "percentage": _safe_percentage(len(grade_rows), score_count),
                "um_range": mapping["um_range"],
                "predicate": mapping["predicate"],
                "student_names": names or "-",
            }
        )

    exam_date_text = _format_wib_datetime(exam.start_time)
    generated_at = _format_wib_datetime(datetime.now(timezone.utc))
    class_scope_label = _build_assessment_class_label(class_scope)

    return {
        "exam": {
            "id": int(exam.id),
            "title": str(exam.title or "-"),
            "subject": str(exam.subject or "-"),
            "exam_type": str(getattr(exam, "exam_type", "") or ""),
            "teacher_name": _resolve_exam_teacher_name(exam),
            "date_text": exam_date_text,
        },
        "class_name": class_scope_label,
        "class_names": class_scope,
        "is_combined_class_scope": len(class_scope) > 1,
        "generated_at": generated_at,
        "stats": {
            "participant_count": score_count,
            "average": _round_float(mean_score),
            "std_dev": _round_float(std_dev),
            "highest": _round_float(highest_score),
            "lowest": _round_float(lowest_score),
        },
        "pan": {
            "mean": _round_float(mean_score),
            "std_dev": _round_float(std_dev),
            "score_range": _round_float(score_range),
            "class_count": class_count,
            "interval": _round_float(interval),
            "thresholds": {
                key: _round_float(value)
                for key, value in thresholds.items()
            },
            "scale10_thresholds": {
                key: _round_float(value)
                for key, value in scale10_thresholds.items()
            },
            "letter_distribution": pan_letter_distribution,
            "um_conversion_summary": pan_um_summary,
        },
        "pap": {
            "kkm": _round_float(kkm),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_percentage": _safe_percentage(pass_count, score_count),
            "grade_distribution": pap_distribution,
        },
        "participants": participant_rows,
    }


# === Endpoints ===

@router.get("/student/{student_id}")
async def get_student_performance(
    student_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Get comprehensive performance analytics for a student.

    Returns:
    - Total exams taken
    - Average, highest, lowest scores
    - Pass rate
    - Score trend (last 10 exams)
    - Total violations
    """

    # Get student info
    student_result = await db.execute(select(User).where(User.id == student_id))
    student = student_result.scalar_one_or_none()

    if not student:
        raise HTTPException(404, "Student not found")

    if student.role not in PARTICIPANT_ROLES:
        raise HTTPException(400, "User is not an exam participant")

    # Get all completed sessions with exam info
    sessions_result = await db.execute(
        select(ExamSession)
        .options(selectinload(ExamSession.exam))
        .where(
            ExamSession.user_id == student_id,
            ExamSession.status.in_(['completed', 'submitted'])
        )
        .order_by(ExamSession.end_time.desc())
    )
    sessions = sessions_result.scalars().all()

    if not sessions:
        return {
            "student_id": student_id,
            "student_name": student.full_name,
            "student_class": student.student_class,
            "total_exams": 0,
            "average_score": 0,
            "highest_score": 0,
            "lowest_score": 0,
            "pass_rate": 0,
            "score_trend": [],
            "total_violations": 0,
            "message": "No exam data available"
        }

    # Calculate statistics
    scores = [float(s.score) for s in sessions if s.score is not None]

    if not scores:
        avg_score = 0
        max_score = 0
        min_score = 0
        pass_rate = 0
    else:
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)

        # Calculate pass rate using exam-configured passing score.
        # Keep a consistent fallback (70.0) when passing_score is unset.
        passed_count = 0
        for session in sessions:
            if session.exam and session.score is not None:
                passing_score = (
                    float(session.exam.passing_score)
                    if session.exam.passing_score is not None
                    else 70.0
                )
                if float(session.score) >= passing_score:
                    passed_count += 1

        pass_rate = (passed_count / len(scores) * 100) if scores else 0

    # Build score trend (last 10 exams, reversed for chronological order)
    trend = []
    for s in sessions[:10]:
        if s.score is not None:
            trend.append(ScoreTrendItem(
                exam_id=s.exam_id,
                exam_title=s.exam.title if s.exam else "Unknown",
                score=float(s.score),
                date=s.end_time.isoformat() if s.end_time else None
            ))

    # Total violations
    total_violations = sum(s.violation_count or 0 for s in sessions)

    return StudentPerformance(
        student_id=student_id,
        student_name=student.full_name,
        student_class=student.student_class,
        total_exams=len(sessions),
        average_score=round(avg_score, 2),
        highest_score=max_score,
        lowest_score=min_score,
        pass_rate=round(pass_rate, 2),
        score_trend=trend,
        total_violations=total_violations
    )


async def _build_class_performance_payload(
    class_name: str,
    current_user: User,
    db: AsyncSession,
    exam_id: Optional[int] = None,
):
    """
    Get performance analytics for an entire class.

    Returns:
    - Total students
    - Total exams taken
    - Average, highest, lowest scores
    - Top performers
    """

    normalized_class_name = (class_name or "").strip()
    if not normalized_class_name:
        raise HTTPException(400, "class_name is required")

    # Optional exam scope:
    # - If exam_id is provided, lock analytics to that exam only.
    # - If teacher requests global class analytics (no exam_id), scope to teacher-owned exams.
    session_filters = []
    if exam_id is not None:
        await _ensure_exam_access(exam_id, current_user, db)
        session_filters.append(ExamSession.exam_id == exam_id)
    elif current_user.role == "teacher":
        teacher_exam_ids_result = await db.execute(
            select(Exam.id).where(
                Exam.creator_id == current_user.id,
                Exam.is_deleted == False
            )
        )
        teacher_exam_ids = [int(eid) for eid in teacher_exam_ids_result.scalars().all()]
        if teacher_exam_ids:
            session_filters.append(ExamSession.exam_id.in_(teacher_exam_ids))
        else:
            # Keep class roster visible, but force empty session scope for teachers without exams.
            session_filters.append(ExamSession.exam_id == -1)

    normalized_class_name_lower = normalized_class_name.lower()
    class_match_filter = func.lower(func.trim(User.student_class)) == normalized_class_name_lower

    # Count active students in class using trimmed/case-insensitive match.
    total_students_result = await db.execute(
        select(func.count(User.id)).where(
            class_match_filter,
            User.role.in_(PARTICIPANT_ROLES),
            User.is_active == True
        )
    )
    total_students = int(total_students_result.scalar() or 0)

    if total_students == 0:
        return {
            "class_name": normalized_class_name,
            "total_students": 0,
            "message": "No students found in this class"
        }

    base_session_filters = [
        ExamSession.status.in_(["completed", "submitted"]),
        User.role.in_(PARTICIPANT_ROLES),
        User.is_active == True,
        class_match_filter,
        *session_filters,
    ]

    passed_count_expr = func.coalesce(
        func.sum(
            case(
                (
                    and_(
                        ExamSession.score.is_not(None),
                        ExamSession.score >= func.coalesce(Exam.passing_score, 70.0),
                    ),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    )
    graded_count_expr = func.coalesce(
        func.sum(case((ExamSession.score.is_not(None), 1), else_=0)),
        0,
    )

    summary_result = await db.execute(
        select(
            func.count(ExamSession.id).label("total_sessions"),
            func.avg(ExamSession.score).label("avg_score"),
            func.max(ExamSession.score).label("max_score"),
            func.min(ExamSession.score).label("min_score"),
            passed_count_expr.label("passed_count"),
            graded_count_expr.label("graded_count"),
        )
        .select_from(ExamSession)
        .join(User, User.id == ExamSession.user_id)
        .join(Exam, Exam.id == ExamSession.exam_id)
        .where(*base_session_filters)
    )
    summary_row = summary_result.one()

    total_exams_taken = int(summary_row.total_sessions or 0)
    if total_exams_taken == 0:
        return ClassPerformance(
            class_name=normalized_class_name,
            total_students=total_students,
            total_exams_taken=0,
            average_score=0,
            highest_score=0,
            lowest_score=0,
            pass_rate=0,
            top_performers=[],
        )

    avg_score = float(summary_row.avg_score or 0.0)
    max_score = float(summary_row.max_score or 0.0)
    min_score = float(summary_row.min_score or 0.0)
    passed_count = int(summary_row.passed_count or 0)
    graded_count = int(summary_row.graded_count or 0)
    pass_rate = (passed_count / graded_count * 100.0) if graded_count > 0 else 0.0

    top_rows_result = await db.execute(
        select(
            ExamSession.user_id.label("student_id"),
            User.full_name.label("student_name"),
            func.avg(ExamSession.score).label("avg_score"),
            func.count(ExamSession.id).label("exams_taken"),
        )
        .select_from(ExamSession)
        .join(User, User.id == ExamSession.user_id)
        .where(
            *base_session_filters,
            ExamSession.score.is_not(None),
        )
        .group_by(ExamSession.user_id, User.full_name)
        .order_by(func.avg(ExamSession.score).desc(), User.full_name.asc())
        .limit(10)
    )

    top_performers = [
        {
            "student_id": int(row.student_id),
            "name": str(row.student_name or "-"),
            "average_score": round(float(row.avg_score or 0.0), 2),
            "exams_taken": int(row.exams_taken or 0),
        }
        for row in top_rows_result
    ]

    return ClassPerformance(
        class_name=normalized_class_name,
        total_students=total_students,
        total_exams_taken=total_exams_taken,
        average_score=round(avg_score, 2),
        highest_score=max_score,
        lowest_score=min_score,
        pass_rate=round(pass_rate, 2),
        top_performers=top_performers,
    )


@router.get("/class/{class_name}")
async def get_class_performance_by_path(
    class_name: str,
    exam_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    return await _build_class_performance_payload(class_name, current_user, db, exam_id=exam_id)


@router.get("/class")
async def get_class_performance_by_query(
    class_name: str = Query(..., min_length=1),
    exam_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    return await _build_class_performance_payload(class_name, current_user, db, exam_id=exam_id)


@router.get("/exam/{exam_id}/classes")
async def get_exam_classes(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Return class list that already has completed/submitted sessions for selected exam.
    Used by exam-analytics class selector to keep class scope aligned with chosen exam.
    """
    await _ensure_exam_access(exam_id, current_user, db)

    class_expr = func.trim(User.student_class)
    rows_result = await db.execute(
        select(
            class_expr.label("class_name"),
            func.count(func.distinct(ExamSession.user_id)).label("participants")
        )
        .select_from(ExamSession)
        .join(User, User.id == ExamSession.user_id)
        .where(
            ExamSession.exam_id == exam_id,
            ExamSession.status.in_(["completed", "submitted"]),
            User.role.in_(PARTICIPANT_ROLES),
            User.is_active == True,
            User.student_class.is_not(None),
            func.coalesce(class_expr, "") != ""
        )
        .group_by(class_expr)
        .order_by(class_expr.asc())
    )

    classes: List[ExamClassItem] = [
        ExamClassItem(
            class_name=str(row.class_name),
            participants=int(row.participants or 0)
        )
        for row in rows_result
    ]

    return {
        "exam_id": exam_id,
        "classes": [item.model_dump() for item in classes]
    }


@router.get("/exam/{exam_id}/question-difficulty")
async def get_question_difficulty_analysis(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Analyze question difficulty based on student responses.

    Returns percentage of correct answers per question.
    Useful for identifying problematic questions.
    """
    await _ensure_exam_access(exam_id, current_user, db)

    # Get all questions for this exam
    questions_result = await db.execute(
        select(Question)
        .where(Question.exam_id == exam_id)
        .order_by(Question.order_index)
    )
    questions = questions_result.scalars().all()

    if not questions:
        return {"exam_id": exam_id, "questions": [], "message": "No questions found"}

    question_ids = [q.id for q in questions]
    stats_result = await db.execute(
        select(
            Answer.question_id,
            func.count(Answer.id).label("total_answers"),
            func.coalesce(
                func.sum(case((Answer.is_correct.is_(True), 1), else_=0)),
                0
            ).label("correct_answers"),
        )
        .join(ExamSession, ExamSession.id == Answer.session_id)
        .where(
            Answer.question_id.in_(question_ids),
            ExamSession.status.in_(["completed", "submitted"]),
        )
        .group_by(Answer.question_id)
    )
    stats_map = {
        int(row.question_id): (int(row.total_answers or 0), int(row.correct_answers or 0))
        for row in stats_result
    }

    question_stats = []

    for index, q in enumerate(questions, start=1):
        total, correct = stats_map.get(q.id, (0, 0))

        difficulty = "unknown"
        correct_rate = 0

        if total > 0:
            correct_rate = (correct / total) * 100

            # Classify difficulty
            if correct_rate >= 80:
                difficulty = "easy"
            elif correct_rate >= 50:
                difficulty = "medium"
            else:
                difficulty = "hard"

        question_stats.append({
            "question_id": q.id,
            "question_number": display_question_number(q.order_index, index),
            "question_text": q.question_text[:100] + "..." if len(q.question_text) > 100 else q.question_text,
            "question_type": q.question_type,
            "total_answers": total,
            "correct_answers": correct,
            "correct_rate": round(correct_rate, 2),
            "difficulty": difficulty
        })

    return {
        "exam_id": exam_id,
        "total_questions": len(questions),
        "questions": question_stats
    }


@router.get("/exam/{exam_id}/assessment")
async def get_exam_assessment_analysis(
    exam_id: int,
    class_name: Optional[str] = Query(default=None),
    class_names: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read),
):
    """
    Build Analisis Asesmen payload (PAN + PAP) for selected exam and class.
    """
    return await _build_assessment_analysis_payload(
        exam_id=exam_id,
        class_name=class_name,
        class_names=class_names,
        current_user=current_user,
        db=db,
    )


@router.get("/exam/{exam_id}/assessment/export")
async def export_exam_assessment_docx(
    exam_id: int,
    class_name: Optional[str] = Query(default=None),
    class_names: Optional[str] = Query(default=None),
    model: str = Query(default="pan", pattern="^(pan|pap)$"),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read),
):
    """
    Export Analisis Hasil Asesmen as DOCX using PAN/PAP templates.
    """
    from app.core.assessment_docx_generator import (
        AssessmentTemplateValidationError,
        DOCX_AVAILABLE,
        DOCX_MIME_TYPE,
        generate_assessment_docx,
    )

    if not DOCX_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Export DOCX tidak tersedia. Install python-docx terlebih dahulu.",
        )

    payload = await _build_assessment_analysis_payload(
        exam_id=exam_id,
        class_name=class_name,
        class_names=class_names,
        current_user=current_user,
        db=db,
    )

    normalized_model = str(model or "").strip().lower()
    try:
        file_bytes = generate_assessment_docx(normalized_model, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AssessmentTemplateValidationError as exc:
        logger.exception("Assessment template fill validation failed")
        raise HTTPException(
            status_code=500,
            detail="Template export asesmen belum terisi sempurna.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - guarded runtime errors
        logger.exception("Failed generating assessment docx")
        raise HTTPException(status_code=500, detail="Gagal membuat dokumen asesmen") from exc

    safe_title = re.sub(r"[^\w\s-]", "", str(payload["exam"]["title"])).strip()
    safe_title = re.sub(r"\s+", "_", safe_title) or f"exam_{exam_id}"
    safe_class = re.sub(r"[^\w\s-]", "", str(payload["class_name"])).strip()
    safe_class = re.sub(r"\s+", "_", safe_class) or "kelas"
    filename = (
        f"analisis_asesmen_{normalized_model}_{safe_title}_{safe_class}_"
        f"{datetime.now().strftime('%Y%m%d')}.docx"
    )

    return Response(
        content=file_bytes,
        media_type=DOCX_MIME_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard")
async def get_analytics_dashboard(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Get analytics dashboard data.

    Returns summary statistics for the specified time period.
    """

    day_windows = build_local_day_windows(days)
    window_start_utc = day_windows[0][1]

    # Get active (non-deleted) exam IDs
    active_exams_query = select(Exam.id).where(Exam.is_deleted == False)
    if current_user.role == 'teacher':
        active_exams_query = active_exams_query.where(Exam.creator_id == current_user.id)
    elif is_admin_scope_role(current_user.role):
        if not is_developer_role(current_user.role):
            active_exams_query = active_exams_query.join(User, User.id == Exam.creator_id).where(
                User.role != ROLE_DEVELOPER
            )

    active_exams_result = await db.execute(active_exams_query)
    active_exam_ids = [e for e in active_exams_result.scalars()]

    # Build base query filters - only include sessions from active exams
    session_filter = [
        ExamSession.status.in_(['completed', 'submitted']),
        ExamSession.end_time >= window_start_utc,
        ExamSession.exam_id.in_(active_exam_ids)  # Only active exams
    ]

    # Total completed sessions
    total_sessions_result = await db.execute(
        select(func.count(ExamSession.id)).where(*session_filter)
    )
    total_sessions = total_sessions_result.scalar() or 0

    # Average score
    avg_score_result = await db.execute(
        select(func.avg(ExamSession.score)).where(
            *session_filter,
            ExamSession.score.isnot(None)
        )
    )
    avg_score = avg_score_result.scalar() or 0

    # Total violations
    violations_result = await db.execute(
        select(func.sum(ExamSession.violation_count)).where(*session_filter)
    )
    total_violations = violations_result.scalar() or 0

    # Session integrity counts
    sessions_with_violations_result = await db.execute(
        select(func.count(ExamSession.id)).where(
            *session_filter,
            ExamSession.violation_count.isnot(None),
            ExamSession.violation_count > 0,
        )
    )
    sessions_with_violations = sessions_with_violations_result.scalar() or 0
    sessions_clean = max(0, total_sessions - sessions_with_violations)

    # Daily completion trend
    daily_trend = []
    for label, day_start, day_end in day_windows:

        count_result = await db.execute(
            select(func.count(ExamSession.id)).where(
                *session_filter,
                ExamSession.end_time >= day_start,
                ExamSession.end_time < day_end
            )
        )
        count = count_result.scalar() or 0

        daily_trend.append({
            "date": label,
            "count": count
        })

    return {
        "period_days": days,
        "total_sessions": total_sessions,
        "average_score": round(float(avg_score), 2) if avg_score else 0,
        "total_violations": total_violations or 0,
        "sessions_with_violations": sessions_with_violations,
        "sessions_clean": sessions_clean,
        "daily_trend": daily_trend
    }


# ============== IRT ANALYSIS (Phase 4) ==============

class IRTItemResponse(BaseModel):
    """IRT analysis result for a single item."""
    question_id: int
    question_number: int
    discrimination: float
    difficulty: float
    ctt_difficulty: float
    discrimination_label: str
    difficulty_label: str
    recommendation: str

class IRTAnalysisResponse(BaseModel):
    """Complete IRT analysis response."""
    exam_id: int
    total_questions: int
    total_responses: int
    items: List[IRTItemResponse]
    test_reliability: float
    weak_items: List[int]
    strong_items: List[int]


@router.get("/exam/{exam_id}/irt-analysis", response_model=IRTAnalysisResponse)
async def get_irt_analysis(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Perform IRT 2-Parameter Logistic analysis on exam responses.

    Returns:
    - Item discrimination (a) and difficulty (b) parameters
    - CTT difficulty (p-value)
    - Interpretation labels
    - Recommendations for weak/strong items

    Requires at least 10 completed sessions for reliable estimates.
    """
    import numpy as np
    from app.core.irt_analysis import TwoParameterLogisticIRT

    await _ensure_exam_access(exam_id, current_user, db)

    # Get all completed sessions for this exam
    sessions_result = await db.execute(
        select(ExamSession)
        .options(selectinload(ExamSession.answers))
        .where(
            ExamSession.exam_id == exam_id,
            ExamSession.status.in_(['completed', 'submitted'])
        )
    )
    sessions = sessions_result.scalars().all()

    if len(sessions) < 5:
        raise HTTPException(
            400,
            f"Minimal 5 sesi ujian diperlukan untuk analisis IRT. Saat ini: {len(sessions)}"
        )

    # Get questions
    questions_result = await db.execute(
        select(Question)
        .where(Question.exam_id == exam_id)
        .order_by(Question.order_index)
    )
    questions = questions_result.scalars().all()

    if not questions:
        raise HTTPException(404, "Tidak ada soal ditemukan")

    # Build response matrix (N students x M items)
    # 1 = correct, 0 = incorrect, np.nan = not answered
    n_students = len(sessions)
    n_items = len(questions)
    question_map = {q.id: idx for idx, q in enumerate(questions)}

    response_matrix = np.full((n_students, n_items), np.nan)

    for i, session in enumerate(sessions):
        for answer in session.answers:
            if answer.question_id in question_map:
                j = question_map[answer.question_id]
                response_matrix[i, j] = 1.0 if answer.is_correct else 0.0

    # Run IRT analysis
    irt = TwoParameterLogisticIRT()
    item_params = irt.estimate_item_parameters(response_matrix)

    # Build response
    items = []
    weak_items = []
    strong_items = []

    for j, q in enumerate(questions):
        if j in item_params:
            ip = item_params[j]
            interp = ip.interpretation

            item_response = IRTItemResponse(
                question_id=q.id,
                question_number=display_question_number(q.order_index, j + 1),
                discrimination=ip.discrimination,
                difficulty=ip.difficulty,
                ctt_difficulty=round(ip.ctt_difficulty, 3),
                discrimination_label=interp["discrimination"],
                difficulty_label=interp["difficulty"],
                recommendation=interp["recommendation"]
            )
            items.append(item_response)

            # Classify items
            if ip.discrimination < 0.5:
                weak_items.append(q.id)
            elif ip.discrimination >= 1.0:
                strong_items.append(q.id)

    # Simple reliability estimate (average discrimination)
    discriminations = [ip.discrimination for ip in item_params.values()]
    avg_disc = sum(discriminations) / len(discriminations) if discriminations else 0
    reliability = min(0.95, max(0.5, avg_disc * 0.8))  # Rough Cronbach's alpha proxy

    return IRTAnalysisResponse(
        exam_id=exam_id,
        total_questions=n_items,
        total_responses=n_students,
        items=items,
        test_reliability=round(reliability, 3),
        weak_items=weak_items,
        strong_items=strong_items
    )


@router.get("/exam-summary-mv/{exam_id}")
async def get_exam_summary_mv(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Get exam summary from Materialized View (Ultra Fast).
    """
    await _ensure_exam_access(exam_id, current_user, db)
    try:
        query = text("""
            SELECT total_participants, avg_score, highest_score, lowest_score, passed_count, last_updated
            FROM exam_results_summary
            WHERE exam_id = :eid
        """)
        result = await db.execute(query, {"eid": exam_id})
        row = result.fetchone()

        if row:
            return {
                "source": "materialized_view",
                "exam_id": exam_id,
                "total_participants": row[0],
                "average_score": float(row[1]) if row[1] else 0,
                "highest_score": float(row[2]) if row[2] else 0,
                "lowest_score": float(row[3]) if row[3] else 0,
                "passed_count": row[4],
                "last_updated": row[5]
            }
    except Exception as exc:
        logger.warning(
            "Materialized view exam_results_summary unavailable for exam_id=%s: %s",
            exam_id,
            str(exc),
            exc_info=True,
        )

    # Fallback to real-time calculation if MV missing or empty
    return {"message": "Data not available in optimized view, use standard analytics endpoint."}
