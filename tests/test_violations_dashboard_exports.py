from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.monitoring import (
    _build_violations_dashboard_payload,
)
from app.core.violations_dashboard import _coerce_violations_date_range
from app.core.pdf_generator import (
    REPORTLAB_AVAILABLE,
    ViolationsReportPDF,
    generate_violations_report_pdf,
)


def _make_log(
    *,
    log_id: int,
    created_at: datetime,
    event_type: str,
    event_data: dict,
    user_id: int,
    name: str,
    username: str,
    student_class: str,
    exam_id: int,
    exam_title: str,
    session_id: int,
):
    user = SimpleNamespace(
        id=user_id,
        full_name=name,
        username=username,
        student_class=student_class,
    )
    exam = SimpleNamespace(title=exam_title)
    session = SimpleNamespace(
        id=session_id,
        exam_id=exam_id,
        user=user,
        exam=exam,
        archived_exam_title=None,
    )
    return SimpleNamespace(
        id=log_id,
        session_id=session_id,
        event_type=event_type,
        event_data=event_data,
        created_at=created_at,
        session=session,
    )


def _build_payload():
    now = datetime(2026, 3, 6, 8, 0, tzinfo=timezone.utc)
    logs = [
        _make_log(
            log_id=1,
            created_at=now,
            event_type="violation_copy",
            event_data={"details": "Menekan Ctrl+C pada soal nomor 4", "action": "keyboard_ctrl_c", "source": "web"},
            user_id=10,
            name="Budi Santoso",
            username="budi",
            student_class="XII IPA 1",
            exam_id=101,
            exam_title="Try Out Matematika",
            session_id=1001,
        ),
        _make_log(
            log_id=2,
            created_at=now - timedelta(minutes=7),
            event_type="violation_copy",
            event_data={"details": "Percobaan copy ulang", "action": "keyboard_ctrl_c", "source": "web"},
            user_id=10,
            name="Budi Santoso",
            username="budi",
            student_class="XII IPA 1",
            exam_id=101,
            exam_title="Try Out Matematika",
            session_id=1001,
        ),
        _make_log(
            log_id=3,
            created_at=now - timedelta(minutes=15),
            event_type="violation_overlay_app",
            event_data={
                "details": "Aplikasi overlay terdeteksi",
                "overlay_apps": ["WhatsApp Bubble", "Clipboard Pro"],
                "source": "flutter_app",
            },
            user_id=11,
            name="Siti Rahma",
            username="siti",
            student_class="XII IPA 2",
            exam_id=102,
            exam_title="Simulasi Biologi",
            session_id=1002,
        ),
    ]
    return _build_violations_dashboard_payload(
        logs,
        exam_id=None,
        date_from=now - timedelta(days=1),
        date_to=now,
        selected_exam_title=None,
    )


def test_build_violations_dashboard_payload_includes_detailed_breakdowns():
    payload = _build_payload()
    type_index = {item["violation_type"]: item for item in payload["type_breakdown"]}

    assert payload["total_violations"] == 3
    assert payload["unique_offender_count"] == 2
    assert payload["top_offenders"][0]["username"] == "budi"
    assert payload["top_offenders"][0]["count"] == 2
    assert payload["top_offenders"][0]["type_breakdown"][0]["violation_type"] == "copy"
    assert type_index["overlay_app"]["offenders"][0]["username"] == "siti"
    assert type_index["copy"]["count"] == 2
    assert type_index["copy"]["explanation"]["simple"].startswith("Peserta mencoba menyalin")
    assert "kertas kecil" in type_index["copy"]["explanation"]["analogy"]
    assert payload["violations"][0]["detail_summary"] == "Menekan Ctrl+C pada soal nomor 4 | Aksi: keyboard ctrl c | Sumber: web"

def test_generate_violations_report_pdf_smoke():
    if not REPORTLAB_AVAILABLE:
        return

    payload = _build_payload()
    pdf_bytes = generate_violations_report_pdf(payload)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 3000


def test_violations_pdf_management_summary_mentions_key_findings():
    if not REPORTLAB_AVAILABLE:
        return

    payload = _build_payload()
    generator = ViolationsReportPDF()
    summary = generator._build_management_summary(payload, generator._resolve_risk(payload))
    top_label = payload["type_breakdown"][0]["label"]

    assert "Budi Santoso" in summary
    assert top_label in summary
    assert "3" in summary


def test_coerce_violations_date_range_naive_treated_as_wib_and_normalized_utc():
    date_from = datetime(2026, 3, 12, 0, 0, 0)  # Naive from HTML date input (WIB day start)
    date_to = datetime(2026, 3, 12, 23, 59, 59)  # Naive from HTML date input (WIB day end)

    effective_from, effective_to = _coerce_violations_date_range(date_from, date_to)

    assert effective_from.tzinfo == timezone.utc
    assert effective_to.tzinfo == timezone.utc
    assert effective_from.isoformat() == "2026-03-11T17:00:00+00:00"
    assert effective_to.isoformat() == "2026-03-12T16:59:59+00:00"
