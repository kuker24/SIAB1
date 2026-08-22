from pathlib import Path


SYSTEM_CHECK_SOURCE = Path("scripts/system_check.py").read_text(encoding="utf-8")


def test_system_check_uses_existing_exam_templates_page() -> None:
    assert "/admin/exam-templates.html" in SYSTEM_CHECK_SOURCE
    assert "/admin/templates.html" not in SYSTEM_CHECK_SOURCE


def test_system_check_accepts_docs_disabled_in_production() -> None:
    assert "Swagger UI (optional in production)" in SYSTEM_CHECK_SOURCE
    assert "expected_status=(200, 404)" in SYSTEM_CHECK_SOURCE


def test_system_check_skips_optional_role_logins_without_passwords() -> None:
    assert "if GURU_PASSWORD:" in SYSTEM_CHECK_SOURCE
    assert "if SISWA_PASSWORD:" in SYSTEM_CHECK_SOURCE
    assert "Teacher login check dilewati" in SYSTEM_CHECK_SOURCE
    assert "Student login check dilewati" in SYSTEM_CHECK_SOURCE
