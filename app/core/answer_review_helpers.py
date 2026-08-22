"""
Helpers for building detailed answer review payloads.
"""
from typing import Any, Dict, List, Optional, Protocol


class AnswerReviewOptionLike(Protocol):
    id: int
    order_index: int
    option_text: Optional[str]
    is_correct: bool


class AnswerReviewAnswerLike(Protocol):
    points_earned: Optional[float]
    is_correct: Optional[bool]


QUESTION_TYPE_LABELS = {
    "multiple_choice": "Pilihan Ganda",
    "multiple_choice_complex": "PG Kompleks",
    "true_false": "Benar / Salah",
    "essay": "Essay",
    "short_answer": "Isian Singkat",
}


def option_label(order_index: int) -> str:
    """Convert zero-based option index to label (A, B, ... Z, AA, AB ...)."""
    normalized = max(int(order_index), 0)
    label = ""
    while True:
        normalized, rem = divmod(normalized, 26)
        label = chr(65 + rem) + label
        if normalized == 0:
            break
        normalized -= 1
    return label


def coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "benar"}:
            return True
        if lowered in {"false", "0", "no", "n", "salah"}:
            return False
    return None


def build_option_map(options: List[AnswerReviewOptionLike]) -> Dict[int, Dict[str, Any]]:
    option_map: Dict[int, Dict[str, Any]] = {}
    sorted_options = sorted(options, key=lambda o: (o.order_index, o.id))
    for idx, opt in enumerate(sorted_options):
        option_map[int(opt.id)] = {
            "id": int(opt.id),
            "label": option_label(idx),
            "text": str(opt.option_text or "").strip(),
            "is_correct": bool(opt.is_correct),
        }
    return option_map


def status_from_answer(answer: Optional[AnswerReviewAnswerLike], max_points: float) -> str:
    if not answer:
        return "not_answered"
    if answer.points_earned is None:
        return "pending"

    points = float(answer.points_earned or 0.0)
    max_points = max(max_points, 0.0)

    if answer.is_correct is True:
        return "correct"
    if answer.is_correct is False and points <= 0:
        return "incorrect"
    if max_points > 0:
        if points >= max_points:
            return "correct"
        if points > 0:
            return "partial"
    return "incorrect"


def resolve_statement_keys(
    settings: Dict[str, Any],
    statements_count: int,
) -> Dict[str, Optional[bool]]:
    keyed: Dict[str, Optional[bool]] = {}
    statement_answers = settings.get("statement_answers")
    correct_statements = settings.get("correct_statements")

    if isinstance(statement_answers, list):
        for idx, value in enumerate(statement_answers):
            keyed[str(idx)] = coerce_bool(value)
    elif isinstance(correct_statements, dict):
        for key, value in correct_statements.items():
            keyed[str(key)] = coerce_bool(value)

    if statements_count > 0:
        for idx in range(statements_count):
            keyed.setdefault(str(idx), None)

    return keyed


def resolve_question_statements(settings: Dict[str, Any]) -> List[str]:
    statements = settings.get("statements") or []
    if not isinstance(statements, list):
        return []
    normalized: List[str] = []
    for item in statements:
        if isinstance(item, dict):
            text_value = str(item.get("text") or item.get("statement") or "").strip()
        else:
            text_value = str(item or "").strip()
        normalized.append(text_value)
    return normalized
