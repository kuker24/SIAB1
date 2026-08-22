from pathlib import Path


MODULE_CORE = Path(
    "static/js/admin/monitoring/modules/00-core-ops-and-sessions.js"
).read_text(encoding="utf-8")
MODULE_MODAL = Path(
    "static/js/admin/monitoring/modules/10-pause-websocket-student-detail.js"
).read_text(encoding="utf-8")
MODULE_RECOVERY_DETAIL = Path(
    "static/js/admin/monitoring/modules/15-recovery-center-student-detail.js"
).read_text(encoding="utf-8")
BUNDLE_SOURCE = Path("static/js/admin/monitoring.js").read_text(encoding="utf-8")


def test_ops_auto_restart_modal_uses_overlay_activation() -> None:
    assert "function showOverlayModal(modalEl)" in MODULE_CORE
    assert "function hideOverlayModal(modalEl)" in MODULE_CORE
    assert "modalEl.classList.add('active')" in MODULE_CORE
    assert "modalEl.classList.remove('active')" in MODULE_CORE
    assert "showOverlayModal(modalEl);" in MODULE_CORE
    assert "hideOverlayModal(modalEl);" in MODULE_CORE


def test_session_and_student_modals_use_overlay_helpers() -> None:
    assert "async function openSessionStatusModal(examId)" in MODULE_MODAL
    assert "function closeSessionStatusModal()" in MODULE_MODAL
    assert "async function openStudentDetailModal(studentId, examId)" in MODULE_RECOVERY_DETAIL
    assert "function closeStudentDetailModal()" in MODULE_RECOVERY_DETAIL
    assert "if (typeof showOverlayModal === 'function')" in MODULE_MODAL
    assert "if (typeof hideOverlayModal === 'function')" in MODULE_MODAL
    assert "if (typeof showOverlayModal === 'function')" in MODULE_RECOVERY_DETAIL
    assert "if (typeof hideOverlayModal === 'function')" in MODULE_RECOVERY_DETAIL


def test_monitoring_bundle_exports_inline_button_handlers() -> None:
    assert "Object.assign(window, {" in BUNDLE_SOURCE
    required_handlers = [
        "toggleAutoRestartFromOps",
        "saveOpsAutoRestartSchedule",
        "toggleAutoModeFromOps",
        "toggleAutoHealingFromOps",
        "runAutoHealingNowFromOps",
        "restartSystemSafelyFromOps",
        "openSessionStatusModal",
        "openStudentDetailModal",
        "launchFullscreenMonitor",
        "toggleViolationSound",
    ]
    for handler in required_handlers:
        assert f"{handler}," in BUNDLE_SOURCE
