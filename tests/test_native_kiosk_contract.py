import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_kiosk_login_requires_security_context_and_persists_auth() -> None:
    login = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/ui/LoginActivity.kt"
    )
    api = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/net/ApiClient.kt"
    )

    assert "prepareSecurityContext()" in login
    assert "if (!securityReady)" in login
    assert 'Prefs.token = token' in api
    assert 'role != "student" && role != "guruplus"' in api


def test_kiosk_webview_and_headers_are_limited_to_the_server_origin() -> None:
    config = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/AppConfig.kt"
    )
    activity = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/ui/ExamActivity.kt"
    )
    api = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/net/ApiClient.kt"
    )

    assert "fun isTrustedUrl" in config
    assert "setOf(AppConfig.trustedOrigin())" in activity
    assert 'setOf("*")' not in activity
    assert "if (!request.isForMainFrame) return false" in activity
    assert "if (!AppConfig.isTrustedUrl(url)) return true" in activity
    assert "AppConfig.isTrustedUrl(original.url.toString())" in api
    assert "if (!AppConfig.isTrustedUrl(url)) return null" in api
    assert 'headers["Authorization"] = "Bearer $token"' in api
    assert 'headers["X-Build-Token"]' not in api
    assert '"X-Build-Token" to AppConfig.buildToken' in api
    assert 'headers["X-App-Signature"] = signature' in api


def test_kiosk_persists_autosave_state_and_enforces_exam_lock() -> None:
    activity = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/ui/ExamActivity.kt"
    )
    kiosk = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/kiosk/KioskController.kt"
    )

    assert '"answerJournalEvent" -> handleAnswerJournal(args)' in activity
    assert "Prefs.answerJournal = queue.toString()" in activity
    assert "Prefs.examState = payload.toString()" in activity
    assert "Prefs.timerSync = payload.toString()" in activity
    assert "kiosk.startExamLock()" in activity
    assert "activity.startLockTask()" in kiosk
    assert "fun currentLockState(): LockState" in kiosk
    assert "ActivityManager.LOCK_TASK_MODE_PINNED -> LockState.PINNED" in kiosk
    assert "showKioskWarning()" in activity
    assert "continue_limited_protection" in activity
    assert "!lockActivationInProgress" in activity
    assert "WindowManager.LayoutParams.FLAG_SECURE" in kiosk


def test_kiosk_exits_to_home_after_exam_submit() -> None:
    activity = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/ui/ExamActivity.kt"
    )
    submitted = activity.split("private fun handleExamSubmitted()")[1].split(
        "private fun ",
        1,
    )[0]

    assert '"examSubmitted" -> handleExamSubmitted()' in activity
    assert "if (examClosed) return true" in activity
    assert "if (examClosed) {" in activity
    assert "examClosed = true" in submitted
    assert "kiosk.stopExamLock()" in submitted
    assert "stopLoading()" in submitted
    assert "Prefs.clearAuth()" in submitted
    assert "finishAndRemoveTask()" in submitted
    assert "goLogin()" not in submitted
    assert "loadDashboard()" not in submitted
    assert "loadUrl(" not in submitted


def test_release_build_never_uses_debug_signing() -> None:
    build = _source("android-kiosk/app/build.gradle.kts")
    script = _source("tools/build_native_kiosk_apk.sh")

    assert 'signingConfigs.getByName("debug")' not in build
    assert 'signingConfigs.getByName("release")' in build
    assert 'environmentVariable("SIAB1_RELEASE_KEYSTORE")' in build
    assert 'environmentVariable("SIAB1_SERVER_URL")' in build
    assert "BuildConfig.SIAB1_SERVER_URL" in _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/AppConfig.kt"
    )
    assert "SIAB1_SERVER_URL" in script
    assert "SIAB1_RELEASE_KEYSTORE" in script
    assert "SIAB1_RELEASE_KEY_PASSWORD" in script


def test_release_build_requires_a_safe_https_server_and_versioned_token() -> None:
    build = _source("android-kiosk/app/build.gradle.kts")
    config = _source(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/AppConfig.kt"
    )

    assert 'uri.scheme.equals("https", ignoreCase = true)' in build
    assert '!uri.host.equals("siab1.invalid", ignoreCase = true)' in build
    assert "uri.userInfo == null" in build
    assert "uri.query == null" in build
    assert "uri.fragment == null" in build
    assert 'versionCode = 4' in build
    assert 'versionName = "2.0.2"' in build
    assert re.search(r'buildToken: String = "BUILD-\d{14}-[A-Z0-9]{6}"', config)
