"""
Helpers for finalizing exam submissions consistently across entry points.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.question import Question
from app.models.session import Answer, ExamSession
import logging

logger = logging.getLogger(__name__)


@dataclass
class SubmissionFinalizeResult:
    total_points: float
    points_earned: float
    percentage: float
    score_breakdown: List[Dict[str, Any]]


def _statement_answers_from_metadata(answer: Answer) -> Optional[Dict[str, Any]]:
    answer_metadata = answer.answer_metadata or {}
    statement_answers = answer_metadata.get("statement_answers")
    if isinstance(statement_answers, dict):
        return statement_answers

    legacy_statement_answers = getattr(answer, "statement_answers", None)
    if isinstance(legacy_statement_answers, dict):
        return legacy_statement_answers

    return None


def _apply_answer_score(answer: Answer, question: Question, is_correct: Any, points: Any) -> None:
    if question.question_type in ["essay", "short_answer"]:
        require_manual = question.get_setting("require_manual_grading", False)
        acceptable_answers = question.get_setting("acceptable_answers", [])
        if require_manual or question.question_type == "essay" or not acceptable_answers:
            answer.is_correct = None
            answer.points_earned = None
            return

    answer.is_correct = is_correct
    answer.points_earned = points


def _grade_answer(answer: Answer, question: Question) -> tuple[Any, Any]:
    answer_data = {
        "selected_option_id": answer.selected_option_id,
        "selected_option_ids": answer.selected_option_ids,
        "answer_text": answer.answer_text,
        "statement_answers": _statement_answers_from_metadata(answer),
    }
    return question.validate_answer(answer_data)


def _can_reuse_persisted_score(answer: Answer, question: Question) -> bool:
    """
    Decide whether answer score can be reused without re-validating options.

    During submit bursts (1000-2000 participants), re-validating every answer
    can become CPU/DB heavy. For objective question types where score already
    exists from submit-answer hot path, we can safely reuse persisted values.
    """
    if answer.points_earned is None:
        return False

    if question.question_type in ["multiple_choice", "true_false", "multiple_choice_complex"]:
        # Reuse score only when correctness flag is already known.
        # Some write paths (auto-save/journal) intentionally store answers without
        # grading and keep `is_correct` as NULL; those must be re-graded on submit.
        return answer.is_correct is not None

    if question.question_type == "short_answer":
        require_manual = bool(question.get_setting("require_manual_grading", False))
        acceptable_answers = question.get_setting("acceptable_answers", []) or []
        if not require_manual and acceptable_answers:
            return answer.is_correct is not None

    return False


def _pick_latest_answers_per_question(answers: List[Answer]) -> List[Answer]:
    """
    Deduplicate answers by question and keep only the latest payload.

    This protects scoring from historical duplicate rows produced by race conditions.
    """
    latest_by_question: Dict[int, Answer] = {}
    for answer in answers:
        existing = latest_by_question.get(answer.question_id)
        if existing is None:
            latest_by_question[answer.question_id] = answer
            continue

        answer_ts = answer.answered_at or datetime.min.replace(tzinfo=timezone.utc)
        existing_ts = existing.answered_at or datetime.min.replace(tzinfo=timezone.utc)
        if (answer_ts, answer.id or 0) >= (existing_ts, existing.id or 0):
            latest_by_question[answer.question_id] = answer

    return list(latest_by_question.values())


def finalize_exam_session_submission(
    session: ExamSession,
    *,
    submitted_at: Optional[datetime] = None,
) -> SubmissionFinalizeResult:
    """
    Grade all persisted answers and update the session to submitted state.

    The caller is responsible for loading:
    - session.exam.questions
    - each question.options
    - session.answers
    - session.exam (for has_ever_had_results flag)
    """
    submitted_at = submitted_at or datetime.now(timezone.utc)

    question_map = {question.id: question for question in session.exam.questions}
    score_breakdown: List[Dict[str, Any]] = []
    answers_to_grade = _pick_latest_answers_per_question(session.answers)

    for answer in answers_to_grade:
        question = question_map.get(answer.question_id)
        if not question:
            continue

        try:
            if _can_reuse_persisted_score(answer, question):
                is_correct = answer.is_correct
            else:
                is_correct, points = _grade_answer(answer, question)
                _apply_answer_score(answer, question, is_correct, points)

            score_breakdown.append(
                {
                    "question_id": str(question.id),
                    "question_type": question.question_type,
                    "points_earned": (
                        float(answer.points_earned) if answer.points_earned is not None else None
                    ),
                    "max_points": float(question.points),
                    "is_correct": is_correct,
                    "partial_scoring": question.get_setting("partial_scoring", False),
                }
            )
        except Exception as exc:
            logger.error(
                "Failed to finalize answer grading for question %s in session %s: %s",
                question.id,
                session.id,
                str(exc),
                exc_info=True,
            )
            answer.is_correct = False
            answer.points_earned = 0
            score_breakdown.append(
                {
                    "question_id": str(question.id),
                    "question_type": question.question_type,
                    "points_earned": 0,
                    "max_points": float(question.points),
                    "is_correct": False,
                    "partial_scoring": question.get_setting("partial_scoring", False),
                    "error": str(exc),
                }
            )

    total_points = sum(float(question.points) for question in session.exam.questions)
    points_earned = sum(float(answer.points_earned or 0) for answer in answers_to_grade)
    percentage = (points_earned / total_points * 100) if total_points > 0 else 0.0

    session.status = "submitted"
    session.end_time = submitted_at
    session.score = round(percentage, 2)

    if hasattr(session.exam, "has_ever_had_results") and not session.exam.has_ever_had_results:
        session.exam.has_ever_had_results = True

    return SubmissionFinalizeResult(
        total_points=total_points,
        points_earned=points_earned,
        percentage=round(percentage, 2),
        score_breakdown=score_breakdown,
    )
