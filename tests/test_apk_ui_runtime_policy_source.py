from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_native_login_ready_copy_and_server_url_hidden() -> None:
    source = (ROOT / "flutter_client_code/lib/pages/native_login_page.dart").read_text()

    assert "Ujian siap dimulai." in source
    assert "Keamanan APK siap" not in source
    assert "_apiService.serverUrl" not in source
    assert "Server ujian belum siap" not in source


def test_exam_connection_badge_hidden_when_online_and_synced() -> None:
    source = (ROOT / "flutter_client_code/lib/pages/exam_page.dart").read_text()

    assert "state == _ConnectionStateUi.online && totalQueue <= 0" in source
    assert "return const SizedBox.shrink();" in source
    assert "bottom: 10" in source


def test_apk_runtime_policy_suppresses_non_critical_violations_only() -> None:
    source = (ROOT / "flutter_client_code/lib/pages/exam_page.dart").read_text()

    assert "_isViolationTemporarilyDisabled" in source
    assert "_canForceSubmitForViolation" in source
    assert "SCREENSHOT_ATTEMPT" in source
    assert "tabViolationType" in source
