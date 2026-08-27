import json
from pathlib import Path

from app.api.exams import _build_start_question_responses, _stable_shuffle_with_seed


FIXTURE = json.loads(
    Path("go/internal/exam/testdata/fastapi_start_parity.json").read_text(encoding="utf-8")
)


def _options() -> list[dict]:
    return [
        {
            "id": option_id,
            "option_text": chr(64 + option_id),
            "order_index": option_id - 1,
            "option_group": "standard",
            "pair_id": None,
        }
        for option_id in range(1, 5)
    ]


def _question(question_id: int, order_index: int) -> dict:
    return {
        "id": question_id,
        "question_text": f"Q{question_id}",
        "stimulus": None,
        "question_type": "multiple_choice",
        "pgk_type": None,
        "question_settings": {},
        "points": 1,
        "order_index": order_index,
        "image_url": None,
        "video_url": None,
        "audio_url": None,
        "options": _options(),
    }


def test_fastapi_shuffle_matches_shared_go_fixture() -> None:
    assert _stable_shuffle_with_seed(
        [1, 2, 3, 4, 5], "siab1_test_seed"
    ) == FIXTURE["stable_shuffle"]
    questions = _build_start_question_responses(
        [_question(question_id, index) for index, question_id in enumerate((11, 12, 13, 14))],
        exam_id=9,
        user_id=42,
        shuffle_questions=True,
        shuffle_options=True,
        secret_key="test-secret",
    )
    assert [question.id for question in questions] == FIXTURE["question_order"]
    question_11 = next(question for question in questions if question.id == 11)
    assert [option.id for option in question_11.options] == FIXTURE["option_order_question_11"]


def test_fastapi_table_and_image_rules_match_shared_go_fixture() -> None:
    table = {
        "id": 21,
        "question_text": "Tabel",
        "stimulus": None,
        "question_type": "multiple_choice_complex",
        "pgk_type": "table_validation",
        "question_settings": {
            "allow_table_statement_shuffle": True,
            "statements": ["A", "B", "C"],
        },
        "points": 1,
        "order_index": 0,
        "image_url": None,
        "video_url": None,
        "audio_url": None,
        "options": [],
    }
    image = {
        "id": 22,
        "question_text": "",
        "stimulus": None,
        "question_type": "multiple_choice",
        "pgk_type": None,
        "question_settings": {
            "is_placeholder": True,
            "placeholder_source": "image",
            "allow_placeholder_shuffle": True,
        },
        "points": 1,
        "order_index": 1,
        "image_url": "/static/q.png",
        "video_url": None,
        "audio_url": None,
        "options": _options(),
    }
    questions = _build_start_question_responses(
        [table, image],
        exam_id=3,
        user_id=7,
        shuffle_questions=False,
        shuffle_options=True,
        secret_key="test-secret",
    )
    table_settings = questions[0].question_settings or {}
    assert [
        statement["original_index"]
        for statement in table_settings["statements"]
    ] == FIXTURE["table_statement_order"]
    assert questions[1].question_text == FIXTURE["image_placeholder_text"]
    assert [option.id for option in questions[1].options] == FIXTURE[
        "image_placeholder_option_order"
    ]


def test_fastapi_start_json_keys_and_points_match_shared_go_fixture() -> None:
    from app.schemas.exam import ExamStartResponse, QuestionResponse
    from datetime import datetime, timezone, timedelta

    payload = _question(1, 0)
    payload["options"] = [
        {
            "id": 1,
            "option_text": "A",
            "order_index": 0,
            "option_group": "standard",
            "pair_id": None,
        },
        {
            "id": 2,
            "option_text": "B",
            "order_index": 1,
            "option_group": "standard",
            "pair_id": None,
        },
    ]
    questions = _build_start_question_responses(
        [payload],
        exam_id=7,
        user_id=5,
        shuffle_questions=False,
        shuffle_options=False,
        secret_key="app-secret",
    )
    dumped = json.loads(questions[0].model_dump_json())
    assert list(dumped.keys()) == FIXTURE["question_keys"]
    assert list(dumped["options"][0].keys()) == FIXTURE["option_keys"]
    assert dumped["difficulty_level"] == FIXTURE["difficulty_default"]
    assert dumped["points"] == FIXTURE["points"]["int_like"]

    hard = dict(payload)
    hard["difficulty_level"] = "hard"
    hard_built = _build_start_question_responses(
        [hard],
        exam_id=7,
        user_id=5,
        shuffle_questions=False,
        shuffle_options=False,
        secret_key="app-secret",
    )
    assert json.loads(hard_built[0].model_dump_json())["difficulty_level"] == "hard"

    omitted = dict(payload)
    omitted.pop("difficulty_level", None)
    omitted_built = _build_start_question_responses(
        [omitted],
        exam_id=7,
        user_id=5,
        shuffle_questions=False,
        shuffle_options=False,
        secret_key="app-secret",
    )
    assert json.loads(omitted_built[0].model_dump_json())["difficulty_level"] == FIXTURE[
        "difficulty_default"
    ]

    point_cases = {
        "int_like": 1,
        "from_1_00": "1.00",
        "fractional": "1.25",
        "zero": None,
    }
    for label, raw_points in point_cases.items():
        item = dict(payload)
        item["points"] = raw_points
        built = _build_start_question_responses(
            [item],
            exam_id=7,
            user_id=5,
            shuffle_questions=False,
            shuffle_options=False,
            secret_key="app-secret",
        )
        assert json.loads(built[0].model_dump_json())["points"] == FIXTURE["points"][label]

    now = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
    response = ExamStartResponse(
        session_id=99,
        exam_id=7,
        exam_title="Ujian",
        duration_minutes=60,
        question_count=1,
        start_time=now,
        end_time=now + timedelta(minutes=60),
        server_time=now,
        show_results=False,
        show_teacher_name=True,
        teacher_name="Guru",
        subject="MTK",
        exam_type="UH",
        shuffle_questions=False,
        shuffle_options=False,
        session_poll_token="tok",
        session_poll_token_expires_minutes=15,
        questions=questions,
    )
    assert list(json.loads(response.model_dump_json()).keys()) == FIXTURE["response_keys"]
    assert isinstance(questions[0], QuestionResponse)
