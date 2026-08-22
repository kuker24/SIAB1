from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "maintenance_year_rollover_cleanup.py"
)
SPEC = importlib.util.spec_from_file_location("maintenance_year_rollover_cleanup", SCRIPT_PATH)
assert SPEC and SPEC.loader
cleanup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cleanup
SPEC.loader.exec_module(cleanup)


def test_normalize_class_name_variants():
    assert cleanup.normalize_class_name("XA") == "X A"
    assert cleanup.normalize_class_name("X-A") == "X A"
    assert cleanup.normalize_class_name("x a") == "X A"
    assert cleanup.normalize_class_name("XIA ") == "XI A"
    assert cleanup.normalize_class_name("XII D") == "XII D"
    assert cleanup.normalize_class_name("XIIA") == "XII A"
    assert cleanup.normalize_class_name("") is None


def test_class_grade_distinguishes_xi_and_xii():
    assert cleanup.class_grade("XI A") == "XI"
    assert cleanup.class_grade("XII A") == "XII"
    assert cleanup.class_grade("X B") == "X"
    assert cleanup.is_class_twelve("XII IPA 1") is True
    assert cleanup.is_class_twelve("XI A") is False
    assert cleanup.is_class_ten_or_eleven("X A") is True
    assert cleanup.is_class_ten_or_eleven("XII A") is False


def test_normalize_person_name():
    assert cleanup.normalize_person_name("  Afdhal Almer Raziq ") == "AFDHAL ALMER RAZIQ"
    assert cleanup.normalize_person_name("AL JANNATU MU'ALANNUR") == "AL JANNATU MU'ALANNUR"
    assert "  " not in cleanup.normalize_person_name("A   B")


def test_classify_exams_excludes_active_by_default():
    now = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
    rows = [
        {
            "exam_id": 1,
            "lifecycle": "draft",
        },
        {
            "exam_id": 2,
            "lifecycle": "finished",
        },
        {
            "exam_id": 3,
            "lifecycle": "active",
        },
        {
            "exam_id": 4,
            "lifecycle": "other_published",
        },
    ]
    plan = cleanup.classify_exams(rows, include_other_published=False)
    assert plan.draft_ids == [1]
    assert plan.finished_ids == [2]
    assert plan.active_ids == [3]
    assert plan.other_ids == [4]
    assert plan.target_ids == [1, 2]

    plan2 = cleanup.classify_exams(rows, include_other_published=True)
    assert plan2.target_ids == [1, 2, 4]


def test_exam_delete_order_contains_critical_steps():
    statements = cleanup.exam_delete_statements([10, 11])
    labels = [label for label, _ in statements]
    assert labels == [
        "security_events_by_session",
        "exam_logs",
        "answers",
        "answers_by_question",
        "null_selected_option_id",
        "exam_sessions",
        "question_tags_map",
        "question_options",
        "questions",
        "scheduled_publications",
        "exams",
    ]
    joined = " ".join(sql.lower() for _, sql in statements)
    assert "delete from security_events" in joined
    assert "delete from exam_sessions" in joined
    assert "delete from exams" in joined
    assert "insert " not in joined


def test_plan_student_sync_match_create_ambiguous_deactivate():
    roster = [
        cleanup.RosterStudent("Afdhal Almer Raziq", "X A", "XA", 1),
        cleanup.RosterStudent("Siswa Baru", "XI B", "XIB", 2),
        cleanup.RosterStudent("Nama Kembar", "X C", "XC", 3),
    ]
    db_students = [
        cleanup.DbStudent(1, "afdhal", "Afdhal Almer Raziq", "XI A", True),
        cleanup.DbStudent(2, "kembar1", "Nama Kembar", "X A", True),
        cleanup.DbStudent(3, "kembar2", "Nama Kembar", "X B", True),
        cleanup.DbStudent(4, "lama", "Siswa Lama", "XI C", True),
        cleanup.DbStudent(5, "xii", "Alumni", "XII A", True),
    ]
    plan = cleanup.plan_student_sync(roster, db_students)
    assert len(plan.matched_updates) == 1
    assert plan.matched_updates[0]["user_id"] == 1
    assert plan.matched_updates[0]["new_class"] == "X A"
    assert len(plan.create_new) == 1
    assert plan.create_new[0]["full_name"] == "Siswa Baru"
    assert len(plan.ambiguous) == 1
    assert set(plan.ambiguous[0]["candidate_ids"]) == {2, 3}
    assert len(plan.deactivate) == 1
    assert plan.deactivate[0]["user_id"] == 4


def test_unique_usernames_avoids_collisions():
    names = cleanup.unique_usernames(
        ["Afdhal Almer", "Afdhal Almer", "???"],
        {"afdhalalmer", "guru1"},
    )
    assert names[0] == "afdhalalmer2"
    assert names[1] == "afdhalalmer3"
    assert names[2].startswith("siswa")
    assert len(set(names)) == 3


def test_production_safety_blocks_apply_without_flag():
    with pytest.raises(cleanup.CleanupError, match="produksi"):
        cleanup.check_production_safety(
            "postgresql://user:pass@103.175.218.56:5432/exam",
            allow_production_write=False,
            apply=True,
        )
    cleanup.check_production_safety(
        "postgresql://user:pass@103.175.218.56:5432/exam",
        allow_production_write=True,
        apply=True,
    )
    cleanup.check_production_safety(
        "postgresql://user:pass@103.175.218.56:5432/exam",
        allow_production_write=False,
        apply=False,
    )


def test_redacted_database_identity_hides_secrets():
    identity = cleanup.redacted_database_identity(
        "postgresql+asyncpg://secret_user:secret_password@db.example:5432/siab1"
    )
    assert identity == "postgresql://db.example:5432/siab1"
    assert "secret" not in identity


def test_load_excel_roster_reads_x_xi_only():
    excel = Path(
        "/home/fahmiagent/Downloads/LAB GITHUB/LAB FINAL/SIAB1/SIAB1 akun/"
        "PEMBAGIAN KELAS TP 2026-2027 terbaru Agustus.xlsx"
    )
    if not excel.exists():
        pytest.skip("Excel roster tidak ada di mesin ini")
    roster = cleanup.load_excel_roster(excel)
    grades = {cleanup.class_grade(item.student_class) for item in roster}
    assert grades <= {"X", "XI"}
    assert "XII" not in grades
    assert len(roster) >= 300
    assert any(item.student_class == "X A" for item in roster)
    assert any(item.student_class == "XI A" for item in roster)


def test_sheet_to_class_label_ignores_xii():
    assert cleanup.sheet_to_class_label("XA") == "X A"
    assert cleanup.sheet_to_class_label("XIB") == "XI B"
    assert cleanup.sheet_to_class_label("XIIA") is None
    assert cleanup.sheet_to_class_label("XII IIS ") is None


def test_generate_password_has_mixed_classes():
    password = cleanup.generate_password(12)
    assert len(password) == 12
    assert any(ch.islower() for ch in password)
    assert any(ch.isupper() for ch in password)
    assert any(ch.isdigit() for ch in password)
