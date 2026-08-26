from pathlib import Path

EXAM_DIR = Path("static/js/exam")
ORDER = (
    "core.js",
    "bridge.js",
    "autosave.js",
    "security.js",
    "reconnect.js",
    "timer.js",
    "navigation.js",
)
BUNDLE = Path("static/js/exam-system.js")


def test_exam_modules_exist_in_plan_order() -> None:
    for name in ORDER:
        path = EXAM_DIR / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name


def test_exam_class_opens_and_closes_across_modules() -> None:
    security = (EXAM_DIR / "security.js").read_text(encoding="utf-8")
    navigation = (EXAM_DIR / "navigation.js").read_text(encoding="utf-8")
    assert "class ExamSystem" in security
    assert "window.examSystem = null;" in navigation


def test_bridge_keeps_flutter_handler_names() -> None:
    bridge = (EXAM_DIR / "bridge.js").read_text(encoding="utf-8")
    assert "callFlutterHandler" in bridge
    assert "answerJournalEvent" in bridge
    assert "examStateUpdate" in bridge
    assert "timerSync" in bridge


def test_generated_bundle_contains_modules() -> None:
    bundle = BUNDLE.read_text(encoding="utf-8")
    assert "Source modules: static/js/exam/*.js" in bundle
    assert "class ExamSystem" in bundle
    assert "function callFlutterHandler" in bundle


def test_leftover_exam_system_modules_tree_is_gone() -> None:
    leftover = Path("static/js/exam-system")
    assert not leftover.exists()


def test_js_journal_worker_owns_flush_with_ten_second_jitter() -> None:
    autosave = (EXAM_DIR / "autosave.js").read_text(encoding="utf-8")
    navigation = (EXAM_DIR / "navigation.js").read_text(encoding="utf-8")
    timer = (EXAM_DIR / "timer.js").read_text(encoding="utf-8")
    kiosk = Path(
        "android-kiosk/app/src/main/java/id/siab1/kiosk/ui/ExamActivity.kt"
    ).read_text(encoding="utf-8")
    bundle = BUNDLE.read_text(encoding="utf-8")

    assert "class AnswerJournalWorker" in autosave
    assert "this.baseIntervalMs = 10000" in autosave
    assert "/api/exams/answer-journal/sync" in autosave
    assert "Math.random() * this.baseIntervalMs" in autosave
    assert "journalWorker.enqueue" in navigation
    assert "journalWorker.stop()" in navigation
    assert "new AnswerJournalWorker" in timer
    assert "class AnswerJournalWorker" in bundle
    assert "/api/exams/answer-journal/sync" in bundle
    assert "Prefs.answerJournal = queue.toString()" in kiosk
    assert "answer-journal/sync" not in kiosk
