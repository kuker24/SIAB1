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
