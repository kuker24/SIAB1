from pathlib import Path


OFFLINE_PACKAGE_SOURCE = Path("app/api/exam_offline_package.py").read_text(encoding="utf-8")


def test_offline_package_uses_backward_compatible_show_exam_timer_fallback() -> None:
    assert (
        '"show_exam_timer": bool(getattr(session.exam, "show_exam_timer", True))'
        in OFFLINE_PACKAGE_SOURCE
    )
