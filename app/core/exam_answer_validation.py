"""
Question payload caching and answer validation logic for hot submit paths.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.answer_review_helpers import coerce_bool
from app.core.exam_session_helpers import safe_int
from app.models.question import Question, QuestionOption

QUESTION_VALIDATION_LOCAL_CACHE_TTL_SECONDS = 600
_question_validation_local_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}


def _safe_int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


async def get_question_validation_payload_cached(
    db: AsyncSession,
    *,
    exam_id: int,
    question_id: int,
) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    cached_entry = _question_validation_local_cache.get(question_id)
    if cached_entry and now < cached_entry[0]:
        cached_payload = cached_entry[1]
        if safe_int(cached_payload.get("exam_id")) == exam_id:
            return cached_payload

    row_result = await db.execute(
        select(
            Question.id,
            Question.exam_id,
            Question.question_type,
            Question.pgk_type,
            Question.points,
            Question.question_settings,
        ).where(
            Question.id == question_id,
            Question.exam_id == exam_id,
        )
    )
    row = row_result.first()
    if row is None:
        return None

    resolved_question_id = int(row[0])
    resolved_exam_id = int(row[1])
    resolved_question_type = str(row[2] or "").strip()
    resolved_pgk_type = (str(row[3]).strip() if row[3] is not None else "") or None
    resolved_points = float(row[4] or 0.0)
    question_settings_raw = row[5]
    question_settings = (
        dict(question_settings_raw)
        if isinstance(question_settings_raw, dict)
        else {}
    )

    effective_pgk_type = str(
        resolved_pgk_type or question_settings.get("pgk_type") or "checkbox"
    ).strip()
    needs_option_table = resolved_question_type in {
        "multiple_choice",
        "true_false",
        "multiple_choice_complex",
    }
    is_table_validation = (
        resolved_question_type == "multiple_choice_complex"
        and effective_pgk_type == "table_validation"
    )

    options_payload: List[Dict[str, Any]] = []
    if needs_option_table and not is_table_validation:
        options_result = await db.execute(
            select(QuestionOption.id, QuestionOption.is_correct).where(
                QuestionOption.question_id == resolved_question_id
            )
        )
        options_payload = [
            {"id": int(opt_id), "is_correct": bool(is_correct)}
            for opt_id, is_correct in options_result.all()
        ]

    payload: Dict[str, Any] = {
        "id": resolved_question_id,
        "exam_id": resolved_exam_id,
        "question_type": resolved_question_type,
        "pgk_type": resolved_pgk_type,
        "points": resolved_points,
        "question_settings": question_settings,
        "options": options_payload,
    }

    _question_validation_local_cache[resolved_question_id] = (
        now + QUESTION_VALIDATION_LOCAL_CACHE_TTL_SECONDS,
        payload,
    )

    # Keep cache bounded for long-running processes.
    if len(_question_validation_local_cache) > 50000:
        stale_keys = [
            qid
            for qid, (expires_at, _) in _question_validation_local_cache.items()
            if expires_at <= now
        ]
        for stale_qid in stale_keys[:10000]:
            _question_validation_local_cache.pop(stale_qid, None)

    return payload


def validate_answer_with_cached_payload(
    payload: Dict[str, Any],
    *,
    selected_option_id: Optional[int],
    selected_option_ids: Optional[List[int]],
    answer_text: Optional[str],
    statement_answers: Optional[Dict[str, Any]],
) -> Tuple[Optional[bool], Optional[float]]:
    question_type = str(payload.get("question_type") or "").strip()
    points = float(payload.get("points") or 0.0)
    question_settings = payload.get("question_settings")
    settings: Dict[str, Any] = (
        dict(question_settings) if isinstance(question_settings, dict) else {}
    )
    options = payload.get("options") if isinstance(payload.get("options"), list) else []
    correct_option_ids = {
        int(opt["id"])
        for opt in options
        if isinstance(opt, dict) and bool(opt.get("is_correct"))
    }

    if question_type in {"multiple_choice", "true_false"}:
        normalized_selected_id = _safe_int_or_none(selected_option_id)
        if normalized_selected_id is None:
            return False, 0.0
        if normalized_selected_id in correct_option_ids:
            return True, points
        return False, 0.0

    if question_type == "multiple_choice_complex":
        pgk_type = str(payload.get("pgk_type") or settings.get("pgk_type") or "checkbox").strip()
        if pgk_type == "table_validation":
            normalized_student_answers = {}
            if isinstance(statement_answers, dict):
                normalized_student_answers = {
                    str(key): coerce_bool(val)
                    for key, val in statement_answers.items()
                }

            correct_answers: Dict[str, Optional[bool]] = {}
            configured_list = settings.get("statement_answers", [])
            configured_map = settings.get("correct_statements", {})
            if isinstance(configured_list, list) and configured_list:
                correct_answers = {
                    str(idx): coerce_bool(value)
                    for idx, value in enumerate(configured_list)
                }
            elif isinstance(configured_map, dict) and configured_map:
                correct_answers = {
                    str(key): coerce_bool(value)
                    for key, value in configured_map.items()
                }

            total_statements = len(correct_answers)
            if total_statements == 0:
                return False, 0.0

            correct_count = 0
            for statement_id, expected_value in correct_answers.items():
                if expected_value is None:
                    continue
                student_value = normalized_student_answers.get(statement_id)
                if student_value is not None and student_value == expected_value:
                    correct_count += 1

            score_ratio = correct_count / total_statements
            points_earned = points * score_ratio
            return score_ratio == 1.0, points_earned

        normalized_selected_ids = {
            selected_id
            for selected_id in (
                _safe_int_or_none(item) for item in (selected_option_ids or [])
            )
            if selected_id is not None
        }
        if not normalized_selected_ids:
            return False, 0.0

        total_correct = len(correct_option_ids)
        if total_correct == 0:
            return False, 0.0

        partial_scoring = bool(settings.get("partial_scoring", False))
        if partial_scoring:
            correct_count = len(normalized_selected_ids & correct_option_ids)
            incorrect_count = len(normalized_selected_ids - correct_option_ids)
            score_ratio = max(0.0, (correct_count - incorrect_count) / total_correct)
            points_earned = points * score_ratio
            return score_ratio >= 0.5, points_earned

        is_correct = normalized_selected_ids == correct_option_ids
        return is_correct, points if is_correct else 0.0

    if question_type == "essay":
        return None, None

    if question_type == "short_answer":
        student_answer = str(answer_text or "").strip()
        if not student_answer:
            return None, None
        if bool(settings.get("require_manual_grading", False)):
            return None, None

        acceptable_answers = settings.get("acceptable_answers", [])
        if not isinstance(acceptable_answers, list) or len(acceptable_answers) == 0:
            return None, None

        case_sensitive = bool(settings.get("case_sensitive", False))
        normalized_acceptable = [str(answer).strip() for answer in acceptable_answers]
        if not case_sensitive:
            student_answer = student_answer.lower()
            normalized_acceptable = [item.lower() for item in normalized_acceptable]

        is_correct = student_answer in normalized_acceptable
        return is_correct, points if is_correct else 0.0

    return False, 0.0


__all__ = [
    "get_question_validation_payload_cached",
    "validate_answer_with_cached_payload",
]
