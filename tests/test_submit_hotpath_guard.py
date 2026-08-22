from pathlib import Path
import re


EXAMS_SOURCE = Path("app/api/exams.py").read_text(encoding="utf-8")
ANSWER_SYNC_SOURCE = Path("app/api/answer_sync.py").read_text(encoding="utf-8")
FINAL_SUBMIT_SOURCE = Path("app/api/final_submit.py").read_text(encoding="utf-8")
VIOLATION_EVENTS_SOURCE = Path("app/api/violation_events.py").read_text(encoding="utf-8")
EXAM_ANSWER_SYNC_SOURCE = Path("app/api/exam_answer_sync.py").read_text(encoding="utf-8")
EXAM_SESSION_RUNTIME_SOURCE = Path("app/api/exam_session_runtime.py").read_text(encoding="utf-8")
ANSWER_SYNC_SERVICE_SOURCE = Path("app/services/answer_sync_service.py").read_text(encoding="utf-8")
SECURITY_SOURCE = Path("app/core/security.py").read_text(encoding="utf-8")
AUTH_SOURCE = Path("app/api/auth.py").read_text(encoding="utf-8")
WEBSOCKET_SOURCE = Path("app/api/websocket.py").read_text(encoding="utf-8")


def _extract_async_function(source: str, function_name: str) -> str:
    pattern = re.compile(
        rf"async def {re.escape(function_name)}\([\s\S]*?(?=\n@router|\nasync def |\nclass |\Z)",
        re.MULTILINE,
    )
    match = pattern.search(source)
    assert match is not None, f"Function {function_name} not found"
    return match.group(0)


def test_submit_answer_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(ANSWER_SYNC_SOURCE, "submit_answer")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_submit_exam_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(FINAL_SUBMIT_SOURCE, "submit_exam")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_start_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(EXAMS_SOURCE, "start_exam_session")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_status_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(EXAM_SESSION_RUNTIME_SOURCE, "get_session_status")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_remaining_time_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(EXAM_SESSION_RUNTIME_SOURCE, "get_remaining_time")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_auto_save_batch_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(EXAM_ANSWER_SYNC_SOURCE, "auto_save_batch")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_auto_save_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(EXAM_ANSWER_SYNC_SOURCE, "auto_save_answers")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_get_session_answers_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(EXAM_ANSWER_SYNC_SOURCE, "get_session_answers")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_log_violation_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(VIOLATION_EVENTS_SOURCE, "log_violation")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_resume_session_uses_hot_path_auth_dependency() -> None:
    fn = _extract_async_function(EXAM_SESSION_RUNTIME_SOURCE, "resume_session")
    assert "current_user: AuthenticatedUser = Depends(get_current_user_hot_path)" in fn


def test_submit_answer_service_uses_advisory_lock_update_insert_strategy() -> None:
    endpoint_fn = _extract_async_function(ANSWER_SYNC_SOURCE, "submit_answer")
    assert "accept_single_answer(answer_data, request)" in endpoint_fn

    service_fn = _extract_async_function(ANSWER_SYNC_SERVICE_SOURCE, "accept_single_answer")
    direct_write_fn = _extract_async_function(ANSWER_SYNC_SERVICE_SOURCE, "_write_single_answer_direct")
    assert "_lock_session_for_single_answer" in service_fn
    assert "pg_insert(Answer)" in direct_write_fn
    assert "on_conflict_do_update" in direct_write_fn
    assert "pg_advisory_xact_lock" in ANSWER_SYNC_SERVICE_SOURCE
    assert "update(Answer)" in direct_write_fn
    assert "no unique or exclusion constraint" in direct_write_fn


def test_hot_path_auth_exists_and_skips_db_dependency() -> None:
    fn = _extract_async_function(SECURITY_SOURCE, "get_current_user_hot_path")
    assert "credentials: HTTPAuthorizationCredentials = Depends(security)" in fn
    assert "db:" not in fn
    assert "_get_cached_authenticated_user(token)" in fn
    assert "decode_token(token, verify_exp=True)" in fn


def test_websocket_auth_skips_db_lookup() -> None:
    fn = _extract_async_function(WEBSOCKET_SOURCE, "_authenticate_ws_user")
    assert "db:" not in fn
    assert "decode_token(token, verify_exp=True)" in fn
    assert "select(User)" not in fn


def test_auth_tokens_include_student_class_claim_for_cross_replica_hot_path() -> None:
    # Login/refresh token payload must include student_class so class checks on
    # hot-path auth dependency remain accurate across replicas.
    assert '"student_class": user.student_class' in AUTH_SOURCE
    assert '"student_class": current_user.student_class' in AUTH_SOURCE


def test_auth_me_loads_full_user_profile_from_db() -> None:
    fn = _extract_async_function(AUTH_SOURCE, "get_me")
    assert "db: AsyncSession = Depends(get_db_read)" in fn
    assert "return await _load_user_response(db, current_user.id)" in fn


def test_refresh_returns_user_response_from_db_profile() -> None:
    fn = _extract_async_function(AUTH_SOURCE, "refresh_token")
    assert "db: AsyncSession = Depends(get_db_read)" in fn
    assert "user=await _load_user_response(db, current_user.id)" in fn


def test_student_login_lane_accepts_guruplus_role() -> None:
    fn = _extract_async_function(AUTH_SOURCE, "login_student")
    assert '{"student", "guruplus"}' in fn
