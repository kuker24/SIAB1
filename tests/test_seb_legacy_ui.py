from pathlib import Path


def test_admin_sidebar_labels_seb_as_legacy_pc_when_enabled() -> None:
    layout = Path("templates/admin/layout.html").read_text(encoding="utf-8")
    sidebar_module = Path("static/js/sidebar-loader/modules/00-sidebar-loader-core.js").read_text(encoding="utf-8")
    sidebar_bundle = Path("static/js/sidebar-loader.js").read_text(encoding="utf-8")

    assert "feature_flags.seb_desktop_legacy_enabled" in layout
    assert "SEB Legacy PC" in layout
    assert "SEB Legacy PC" in sidebar_module
    assert "SEB Legacy PC" in sidebar_bundle
    assert "SEB Builder</a>" not in sidebar_bundle


def test_seb_builder_page_marks_pc_builder_as_legacy_optional() -> None:
    template = Path("templates/admin/seb-builder.html").read_text(encoding="utf-8")
    assert "Legacy Opsional" in template
    assert "APK resmi/mobile-first adalah runtime utama" in template
    assert "SEB_DESKTOP_LEGACY_ENABLED=false" in template
    assert "feature_flags.seb_desktop_legacy_enabled" in template
    assert "SEB PC/Desktop legacy sedang dinonaktifkan" in template
    assert "Generate Legacy .seb File" in template


def test_exam_seb_modal_points_mobile_users_to_official_apk() -> None:
    template = Path("templates/admin/exams.html").read_text(encoding="utf-8")
    assert "APK resmi adalah runtime utama ujian siswa" in template
    assert "SEB PC/Desktop" in template
    assert "Legacy Opsional" in template
    assert "APK Android resmi" in template


def test_settings_describes_apk_as_primary_runtime() -> None:
    template = Path("templates/admin/settings.html").read_text(encoding="utf-8")
    assert "APK resmi adalah jalur utama production" in template
    assert "SEB PC/Laptop hanya legacy opsional/fallback" in template
    assert "Runtime utama ujian siswa" in template


def test_seb_builder_js_handles_disabled_legacy_feature() -> None:
    source = Path("static/js/seb-builder/modules/00-seb-pc-core.js").read_text(encoding="utf-8")
    bundle = Path("static/js/seb-builder.js").read_text(encoding="utf-8")
    expected = "SEB PC/Desktop legacy sedang dinonaktifkan"
    assert expected in source
    assert expected in bundle
