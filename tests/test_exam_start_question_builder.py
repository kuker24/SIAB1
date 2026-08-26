from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.api.exams import _build_start_question_responses, _stable_shuffle_with_seed


def _payload(*questions):
    return list(questions)


def _mcq(qid: int, order_index: int, option_ids: list[int]) -> dict:
    return {
        "id": qid,
        "question_text": f"Soal {qid}",
        "stimulus": None,
        "question_type": "multiple_choice",
        "pgk_type": None,
        "difficulty_level": "medium",
        "question_settings": {},
        "points": 1,
        "order_index": order_index,
        "image_url": None,
        "video_url": None,
        "audio_url": None,
        "options": [
            {
                "id": option_id,
                "option_text": f"Opsi {option_id}",
                "order_index": idx,
                "option_group": "standard",
                "pair_id": None,
            }
            for idx, option_id in enumerate(option_ids)
        ],
    }


def test_stable_shuffle_is_deterministic() -> None:
    items = [1, 2, 3, 4, 5]
    seed = "siab1_test_seed"
    assert _stable_shuffle_with_seed(items, seed) == _stable_shuffle_with_seed(items, seed)
    assert _stable_shuffle_with_seed(items, seed) != items


def test_start_builder_hides_correctness_and_keeps_seed() -> None:
    payload = _payload(
        _mcq(11, 0, [1, 2, 3, 4]),
        _mcq(12, 1, [5, 6, 7, 8]),
    )
    kwargs = dict(
        exam_id=9,
        user_id=42,
        shuffle_questions=True,
        shuffle_options=True,
        secret_key="test-secret",
    )
    first = _build_start_question_responses(payload, **kwargs)
    second = _build_start_question_responses(payload, **kwargs)
    assert [q.id for q in first] == [q.id for q in second]
    assert [opt.id for q in first for opt in q.options] == [
        opt.id for q in second for opt in q.options
    ]
    dumped = first[0].model_dump()
    assert "is_correct" not in dumped
    assert all("is_correct" not in opt.model_dump() for opt in first[0].options)


def test_start_builder_rejects_incomplete_option_question() -> None:
    payload = _payload(
        {
            "id": 3,
            "question_text": "Tanpa opsi",
            "question_type": "multiple_choice",
            "question_settings": {},
            "points": 1,
            "order_index": 0,
            "options": [],
        }
    )
    with pytest.raises(HTTPException) as exc:
        _build_start_question_responses(
            payload,
            exam_id=1,
            user_id=1,
            shuffle_questions=False,
            shuffle_options=False,
            secret_key="test-secret",
        )
    assert exc.value.status_code == 500


def test_start_exam_session_delegates_to_builder() -> None:
    source = SimpleNamespace(
        text=__import__("pathlib").Path("app/api/exams.py").read_text(encoding="utf-8")
    )
    assert "_build_start_question_responses(" in source.text
    start_fn = source.text.split("async def start_exam_session")[1].split(
        "\nasync def "
    )[0]
    assert "_build_start_question_responses(" in start_fn
    assert "Depends(get_current_user_hot_path)" in start_fn
