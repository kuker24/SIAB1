from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.orm import joinedload, noload, selectinload

from app.models.exam import Exam
from app.models.question import Question
from app.models.session import Answer, ExamLog, ExamSession
from app.models.user import User


EXAMS_SOURCE = Path("app/api/exams.py").read_text(encoding="utf-8")
EXAM_SERVICE_SOURCE = Path("app/services/exam_service.py").read_text(encoding="utf-8")
ANSWER_SYNC_SOURCE = Path("app/services/answer_sync_service.py").read_text(encoding="utf-8")
ANSWER_SYNC_API_SOURCE = Path("app/api/exam_answer_sync.py").read_text(encoding="utf-8")
SECURITY_SOURCE = Path("app/core/security.py").read_text(encoding="utf-8")
RUNTIME_BUFFER_SOURCE = Path("app/services/answer_runtime_buffer.py").read_text(encoding="utf-8")
FINAL_SUBMIT_SOURCE = Path("app/services/final_submit_service.py").read_text(encoding="utf-8")


def _extract_async_function(source: str, function_name: str) -> str:
    pattern = re.compile(
        rf"async def {re.escape(function_name)}\([\s\S]*?(?=\n@router|\n    async def |\nasync def |\n    def |\ndef |\nclass |\Z)",
        re.MULTILINE,
    )
    match = pattern.search(source)
    assert match is not None, f"Function {function_name} not found"
    return match.group(0)


def _selectin_keys(model) -> set[str]:
    return {
        relationship.key
        for relationship in model.__mapper__.relationships
        if relationship.lazy == "selectin"
    }


def test_global_selectin_mappings_are_unchanged() -> None:
    assert _selectin_keys(Exam) == {"creator", "questions", "sessions"}
    assert _selectin_keys(User) == {"created_exams", "exam_sessions"}
    assert _selectin_keys(ExamSession) == {"user", "exam", "answers", "logs"}
    assert _selectin_keys(Question) >= {"exam", "category", "tags", "options", "answers"}
    assert _selectin_keys(Answer) == {"session", "question"}
    assert _selectin_keys(ExamLog) == {"session"}


def test_join_exam_blocks_implicit_exam_graph() -> None:
    fn = _extract_async_function(EXAMS_SOURCE, "join_exam_by_token")
    assert '.options(noload("*"))' in fn
    assert "select(func.count(ExamSession.id))" in fn
    assert "select(func.count(Question.id))" in fn
    assert "selectinload(Exam.questions)" not in fn
    assert "selectinload(Exam.sessions)" not in fn


def test_start_session_row_queries_block_implicit_graph() -> None:
    fn = _extract_async_function(EXAMS_SOURCE, "start_exam_session")
    assert "get_exam_start_session_state" in fn
    assert "select(func.count(ExamSession.id))" not in fn
    assert fn.count('.options(noload("*"))') >= 2
    assert "selectinload(ExamSession.answers)" not in fn
    assert "selectinload(ExamSession.user)" not in fn
    assert "selectinload(ExamSession.exam)" not in fn
    assert "selectinload(ExamSession.logs)" not in fn


def test_exam_settings_query_loads_creator_only() -> None:
    fn = _extract_async_function(EXAM_SERVICE_SOURCE, "get_exam_with_settings")
    assert 'noload("*")' in fn
    assert "joinedload(Exam.creator)" in fn
    assert "selectinload(Exam.questions)" not in fn
    assert "selectinload(Exam.sessions)" not in fn


def test_start_uses_live_column_projection() -> None:
    start_fn = _extract_async_function(EXAMS_SOURCE, "start_exam_session")
    projection_fn = _extract_async_function(
        EXAM_SERVICE_SOURCE,
        "get_exam_start_projection",
    )
    assert "get_exam_start_projection" in start_fn
    assert "get_exam_start_session_state" in start_fn
    assert "get_exam_with_settings" not in start_fn
    assert "_get_exam_creator_role" not in start_fn
    assert "password_hash" not in projection_fn
    assert "seb_config_key" not in projection_fn
    assert "builder_settings" not in projection_fn
    assert "Exam.is_published" in projection_fn
    assert "Exam.start_time" in projection_fn
    assert "Exam.end_time" in projection_fn
    assert "Exam.max_attempts" in projection_fn
    assert "Exam.allowed_classes" in projection_fn
    assert "User.role" in projection_fn
    assert "User.full_name" in projection_fn
    assert "is_globally_paused" not in start_fn
    assert "is_globally_paused" not in projection_fn


def test_question_payload_query_does_not_reuse_exam_collection() -> None:
    fn = _extract_async_function(EXAM_SERVICE_SOURCE, "get_questions_payload")
    assert "select(Question)" in fn
    assert "selectinload(Question.options)" in fn
    assert 'noload("*")' in fn
    assert "select(Exam)" not in fn
    assert "selectinload(Exam.questions)" not in fn


def test_answer_lock_and_autosave_queries_are_row_only() -> None:
    lock_fn = _extract_async_function(ANSWER_SYNC_SOURCE, "_lock_session_for_single_answer")
    autosave_fn = _extract_async_function(ANSWER_SYNC_SOURCE, "accept_legacy_autosave")
    batch_fn = _extract_async_function(ANSWER_SYNC_SOURCE, "accept_batch")
    ensure_fn = _extract_async_function(ANSWER_SYNC_SOURCE, "_ensure_session_in_progress_for_user")
    for fn in (lock_fn, autosave_fn, batch_fn, ensure_fn):
        assert '.options(noload("*"))' in fn
        assert "selectinload(ExamSession" not in fn


def test_session_answer_restore_query_is_row_only() -> None:
    fn = _extract_async_function(ANSWER_SYNC_API_SOURCE, "get_session_answers")
    assert fn.count('.options(noload("*"))') >= 1
    assert 'select(Answer).options(noload("*"))' in fn


def test_join_auth_lookup_does_not_load_user_collections() -> None:
    fn = _extract_async_function(SECURITY_SOURCE, "_resolve_authenticated_user")
    assert 'select(User).options(noload("*"))' in fn


def test_final_submit_keeps_explicit_grading_graph() -> None:
    fn = _extract_async_function(FINAL_SUBMIT_SOURCE, "_load_session_for_finalize")
    assert 'noload("*")' in fn
    assert "selectinload(ExamSession.exam)" in fn
    assert "selectinload(Exam.questions)" in fn
    assert "selectinload(Question.options)" in fn
    assert "selectinload(ExamSession.answers)" in fn


def test_runtime_buffer_session_queries_are_row_only() -> None:
    assert RUNTIME_BUFFER_SOURCE.count('.options(noload("*"))') >= 3


def test_hotpath_select_options_compile() -> None:
    exam_stmt = (
        select(Exam)
        .options(noload("*"), joinedload(Exam.creator).options(noload("*")))
        .where(Exam.id == 1)
    )
    question_stmt = (
        select(Question)
        .options(noload("*"), selectinload(Question.options).options(noload("*")))
        .where(Question.exam_id == 1)
    )
    session_stmt = select(ExamSession).options(noload("*")).where(ExamSession.id == 1)
    assert exam_stmt._with_options
    assert question_stmt._with_options
    assert session_stmt._with_options
    compiled = str(session_stmt.compile())
    assert "exam_sessions" in compiled.lower()
