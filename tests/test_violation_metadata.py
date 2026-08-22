from app.core.violation_metadata import (
    AUTO_SUBMIT_VIOLATION_THRESHOLD,
    KNOWN_VIOLATION_EVENT_TYPES,
    canonical_violation_event_type,
    canonical_violation_key,
    get_violation_warning_message,
)


def test_violation_aliases_normalize_to_canonical_keys():
    assert canonical_violation_key("TAB_SWITCH") == "tab_switch"
    assert canonical_violation_key("window_blur") == "focus_lost"
    assert canonical_violation_key("devtools_attempt") == "devtools_open"
    assert canonical_violation_key("SCREENSHOT_ATTEMPT") == "screenshot_attempt"


def test_clipboard_violation_uses_action_hint():
    assert canonical_violation_key(
        "clipboard_violation",
        {"action": "keyboard_ctrl_v"},
    ) == "paste"
    assert canonical_violation_event_type(
        "clipboard_violation",
        {"action": "cut"},
    ) == "violation_cut"


def test_known_violation_event_types_covers_legacy_and_canonical_names():
    assert "tab_switch" in KNOWN_VIOLATION_EVENT_TYPES
    assert "violation_tab_switch" in KNOWN_VIOLATION_EVENT_TYPES
    assert "copy_paste_attempt" in KNOWN_VIOLATION_EVENT_TYPES
    assert "devtools_attempt" in KNOWN_VIOLATION_EVENT_TYPES


def test_violation_warning_message_tracks_auto_submit_threshold():
    assert get_violation_warning_message(2) is None
    assert get_violation_warning_message(3) == "Peringatan: Anda sudah melakukan 3 pelanggaran."
    assert (
        get_violation_warning_message(AUTO_SUBMIT_VIOLATION_THRESHOLD - 1)
        == "PERINGATAN TERAKHIR! Ujian akan dikumpulkan otomatis pada pelanggaran berikutnya."
    )
    assert (
        get_violation_warning_message(AUTO_SUBMIT_VIOLATION_THRESHOLD)
        == "Batas pelanggaran tercapai. Ujian akan dikumpulkan otomatis."
    )
