from types import SimpleNamespace

from app.core.answer_review_helpers import (
    build_option_map,
    coerce_bool,
    option_label,
    resolve_question_statements,
    resolve_statement_keys,
    status_from_answer,
)


def test_option_label_supports_multi_letters() -> None:
    assert option_label(0) == "A"
    assert option_label(25) == "Z"
    assert option_label(26) == "AA"
    assert option_label(27) == "AB"


def test_coerce_bool_supports_localized_values() -> None:
    assert coerce_bool(True) is True
    assert coerce_bool("benar") is True
    assert coerce_bool("salah") is False
    assert coerce_bool("0") is False
    assert coerce_bool("unknown") is None


def test_build_option_map_sorts_by_order_and_assigns_labels() -> None:
    options = [
        SimpleNamespace(id=2, order_index=2, option_text="Dua", is_correct=False),
        SimpleNamespace(id=1, order_index=1, option_text="Satu", is_correct=True),
    ]
    option_map = build_option_map(options)

    assert option_map[1]["label"] == "A"
    assert option_map[2]["label"] == "B"
    assert option_map[1]["is_correct"] is True


def test_status_from_answer_handles_partial_and_pending() -> None:
    assert status_from_answer(None, 5.0) == "not_answered"
    assert (
        status_from_answer(SimpleNamespace(points_earned=None, is_correct=None), 5.0)
        == "pending"
    )
    assert (
        status_from_answer(SimpleNamespace(points_earned=2.5, is_correct=None), 5.0)
        == "partial"
    )
    assert (
        status_from_answer(SimpleNamespace(points_earned=0, is_correct=False), 5.0)
        == "incorrect"
    )


def test_resolve_statement_keys_and_statements() -> None:
    settings = {
        "statement_answers": ["true", "false", None],
        "statements": [{"text": "A"}, "B"],
    }
    keyed = resolve_statement_keys(settings, statements_count=2)
    statements = resolve_question_statements(settings)

    assert keyed["0"] is True
    assert keyed["1"] is False
    assert statements == ["A", "B"]
