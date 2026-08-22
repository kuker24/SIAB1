from pathlib import Path


EXAMS_SOURCE = Path("app/api/exams.py").read_text(encoding="utf-8")
SINGLE_ANSWER_API_SOURCE = Path("app/api/answer_sync.py").read_text(encoding="utf-8")
ANSWER_SYNC_API_SOURCE = Path("app/api/exam_answer_sync.py").read_text(encoding="utf-8")
FINAL_SUBMIT_API_SOURCE = Path("app/api/final_submit.py").read_text(encoding="utf-8")
VIOLATION_EVENTS_API_SOURCE = Path("app/api/violation_events.py").read_text(encoding="utf-8")
SESSION_RUNTIME_API_SOURCE = Path("app/api/exam_session_runtime.py").read_text(encoding="utf-8")
OFFLINE_PACKAGE_API_SOURCE = Path("app/api/exam_offline_package.py").read_text(encoding="utf-8")
PAUSE_CONTROL_API_SOURCE = Path("app/api/exam_pause_control.py").read_text(encoding="utf-8")
EXPORTS_API_SOURCE = Path("app/api/exam_exports.py").read_text(encoding="utf-8")
CRUD_API_SOURCE = Path("app/api/exam_crud.py").read_text(encoding="utf-8")
MAIN_SOURCE = Path("app/main.py").read_text(encoding="utf-8")
ANSWER_SYNC_SCHEMA_SOURCE = Path("app/schemas/answer_sync.py").read_text(encoding="utf-8")


def test_single_answer_route_lives_outside_large_exams_module() -> None:
    assert "async def submit_answer" not in EXAMS_SOURCE
    assert "async def submit_answer" in SINGLE_ANSWER_API_SOURCE
    assert '@router.post("/submit-answer"' in SINGLE_ANSWER_API_SOURCE


def test_answer_sync_routes_live_outside_large_exams_module() -> None:
    assert "async def auto_save_answers" not in EXAMS_SOURCE
    assert "async def auto_save_batch" not in EXAMS_SOURCE
    assert "async def sync_answer_journal" not in EXAMS_SOURCE
    assert "async def get_session_answers" not in EXAMS_SOURCE

    assert "async def auto_save_answers" in ANSWER_SYNC_API_SOURCE
    assert "async def auto_save_batch" in ANSWER_SYNC_API_SOURCE
    assert "async def sync_answer_journal" in ANSWER_SYNC_API_SOURCE
    assert "async def get_session_answers" in ANSWER_SYNC_API_SOURCE


def test_answer_sync_router_is_registered_in_main() -> None:
    assert "answer_sync" in MAIN_SOURCE
    assert "exam_answer_sync" in MAIN_SOURCE
    assert "app.include_router(answer_sync.router)" in MAIN_SOURCE
    assert "app.include_router(exam_answer_sync.router)" in MAIN_SOURCE


def test_final_submit_route_lives_outside_large_exams_module() -> None:
    assert "async def submit_exam" not in EXAMS_SOURCE
    assert "async def submit_exam" in FINAL_SUBMIT_API_SOURCE
    assert '@router.post("/submit"' in FINAL_SUBMIT_API_SOURCE
    assert "get_final_submit_service" in FINAL_SUBMIT_API_SOURCE


def test_final_submit_router_is_registered_in_main() -> None:
    assert "final_submit" in MAIN_SOURCE
    assert "app.include_router(final_submit.router)" in MAIN_SOURCE


def test_violation_log_route_lives_outside_large_exams_module() -> None:
    assert "async def log_violation" not in EXAMS_SOURCE
    assert "async def log_violation" in VIOLATION_EVENTS_API_SOURCE
    assert '@router.post("/log-violation"' in VIOLATION_EVENTS_API_SOURCE
    assert "enqueue_violation_event" in VIOLATION_EVENTS_API_SOURCE


def test_violation_events_router_is_registered_in_main() -> None:
    assert "violation_events" in MAIN_SOURCE
    assert "app.include_router(violation_events.router)" in MAIN_SOURCE


def test_session_runtime_routes_live_outside_large_exams_module() -> None:
    assert "async def get_session_status" not in EXAMS_SOURCE
    assert "async def get_remaining_time" not in EXAMS_SOURCE
    assert "async def resume_session" not in EXAMS_SOURCE
    assert "class PreciseTimerResponse" not in EXAMS_SOURCE
    assert "class SessionResumeResponse" not in EXAMS_SOURCE

    assert "async def get_session_status" in SESSION_RUNTIME_API_SOURCE
    assert "async def get_remaining_time" in SESSION_RUNTIME_API_SOURCE
    assert "async def resume_session" in SESSION_RUNTIME_API_SOURCE
    assert "class PreciseTimerResponse" in SESSION_RUNTIME_API_SOURCE
    assert "class SessionResumeResponse" in SESSION_RUNTIME_API_SOURCE


def test_session_runtime_router_is_registered_in_main() -> None:
    assert "exam_session_runtime" in MAIN_SOURCE
    assert "app.include_router(exam_session_runtime.router)" in MAIN_SOURCE


def test_offline_package_route_lives_outside_large_exams_module() -> None:
    assert "async def get_offline_exam_package" not in EXAMS_SOURCE
    assert "_sign_offline_package_payload" not in EXAMS_SOURCE
    assert "OFFLINE_PACKAGE_TTL_SECONDS" not in EXAMS_SOURCE

    assert "async def get_offline_exam_package" in OFFLINE_PACKAGE_API_SOURCE
    assert "_sign_offline_package_payload" in OFFLINE_PACKAGE_API_SOURCE
    assert "OFFLINE_PACKAGE_TTL_SECONDS" in OFFLINE_PACKAGE_API_SOURCE
    assert "signature_algorithm" in OFFLINE_PACKAGE_API_SOURCE


def test_offline_package_router_is_registered_in_main() -> None:
    assert "exam_offline_package" in MAIN_SOURCE
    assert "app.include_router(exam_offline_package.router)" in MAIN_SOURCE


def test_pause_control_routes_live_outside_large_exams_module() -> None:
    assert "async def pause_exam_globally" not in EXAMS_SOURCE
    assert "async def resume_exam_globally" not in EXAMS_SOURCE
    assert "async def get_pause_status" not in EXAMS_SOURCE
    assert "class PauseResponse" not in EXAMS_SOURCE

    assert "async def pause_exam_globally" in PAUSE_CONTROL_API_SOURCE
    assert "async def resume_exam_globally" in PAUSE_CONTROL_API_SOURCE
    assert "async def get_pause_status" in PAUSE_CONTROL_API_SOURCE
    assert "class PauseResponse" in PAUSE_CONTROL_API_SOURCE


def test_pause_control_router_is_registered_in_main() -> None:
    assert "exam_pause_control" in MAIN_SOURCE
    assert "app.include_router(exam_pause_control.router)" in MAIN_SOURCE


def test_pdf_export_routes_live_outside_large_exams_module() -> None:
    assert "async def get_exam_analytics_pdf" not in EXAMS_SOURCE
    assert "async def get_exam_results_pdf" not in EXAMS_SOURCE
    assert "async def get_session_certificate" not in EXAMS_SOURCE

    assert "async def get_exam_analytics_pdf" in EXPORTS_API_SOURCE
    assert "async def get_exam_results_pdf" in EXPORTS_API_SOURCE
    assert "async def get_session_certificate" in EXPORTS_API_SOURCE
    assert "heavy_exports_active" in EXPORTS_API_SOURCE


def test_exam_exports_router_is_registered_in_main() -> None:
    assert "exam_exports" in MAIN_SOURCE
    assert "app.include_router(exam_exports.router)" in MAIN_SOURCE


def test_exam_crud_routes_live_outside_large_exams_module() -> None:
    moved_handlers = [
        "list_exams",
        "get_exam",
        "create_exam",
        "update_exam",
        "delete_exam",
        "publish_exam",
        "toggle_publish_exam",
        "regenerate_exam_token",
        "create_exam_from_template",
        "duplicate_exam",
    ]
    for handler in moved_handlers:
        assert f"async def {handler}(" not in EXAMS_SOURCE
        assert f"async def {handler}(" in CRUD_API_SOURCE

    assert "_validate_questions_for_publish" in CRUD_API_SOURCE
    assert "_autofill_placeholder_options_for_publish" in CRUD_API_SOURCE


def test_exam_crud_router_is_registered_in_main() -> None:
    assert "exam_crud" in MAIN_SOURCE
    assert "app.include_router(exam_crud.router)" in MAIN_SOURCE


def test_batch_autosave_schemas_live_in_schema_module() -> None:
    assert "class BatchAnswerItem" not in EXAMS_SOURCE
    assert "class BatchAutoSaveRequest" not in EXAMS_SOURCE
    assert "class BatchAutoSaveResponse" not in EXAMS_SOURCE

    assert "class BatchAnswerItem" in ANSWER_SYNC_SCHEMA_SOURCE
    assert "class BatchAutoSaveRequest" in ANSWER_SYNC_SCHEMA_SOURCE
    assert "class BatchAutoSaveResponse" in ANSWER_SYNC_SCHEMA_SOURCE


def test_split_exam_routers_import_without_circular_dependency() -> None:
    import app.api.answer_sync as single_answer_router
    import app.api.exam_answer_sync as batch_answer_router
    import app.api.exam_crud as crud_router
    import app.api.exam_offline_package as offline_router
    import app.api.exam_pause_control as pause_router
    import app.api.exam_session_runtime as runtime_router
    import app.api.final_submit as final_submit_router
    import app.api.violation_events as violation_router

    routers = [
        single_answer_router.router,
        batch_answer_router.router,
        crud_router.router,
        offline_router.router,
        pause_router.router,
        runtime_router.router,
        final_submit_router.router,
        violation_router.router,
    ]
    assert all(router.routes for router in routers)
