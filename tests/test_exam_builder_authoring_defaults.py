from pathlib import Path


BOOTSTRAP = Path(
    "static/js/exam-builder/modules/00-bootstrap-settings-events.js"
).read_text(encoding="utf-8")
RENDERING = Path(
    "static/js/exam-builder/modules/10-question-core-rendering.js"
).read_text(encoding="utf-8")
TEMPLATE = Path("templates/admin/exam-builder.html").read_text(encoding="utf-8")


def test_builder_defaults_key_only_off_unless_explicitly_enabled() -> None:
    assert "authoring_defaults_version: 2" in BOOTSTRAP
    assert "default_mc_key_only: false" in BOOTSTRAP
    assert "default_pgk_key_only: false" in BOOTSTRAP
    assert "default_mc_key_only: raw.default_mc_key_only === true" in BOOTSTRAP
    assert "default_pgk_key_only: raw.default_pgk_key_only === true" in BOOTSTRAP
    assert "settings.use_key_only_mode === true" in BOOTSTRAP
    assert "settings.use_key_only_mode !== false" not in BOOTSTRAP


def test_legacy_exam_defaults_do_not_force_new_questions_into_key_only_mode() -> None:
    assert "function normalizePersistedBuilderSettings" in BOOTSTRAP
    assert "normalizePersistedBuilderSettings(exam.builder_settings)" in BOOTSTRAP
    assert "default_mc_key_only: false" in BOOTSTRAP
    assert "default_pgk_key_only: false" in BOOTSTRAP


def test_pgk_type_b_keeps_benar_salah_and_shuffle_opt_out() -> None:
    assert "Tipe B: Tabel Benar/Salah" in RENDERING
    assert "pilih Benar atau Salah" in RENDERING
    assert "Kunci Benar/Salah tetap menempel pada pernyataan." in RENDERING
    assert "question.allow_table_statement_shuffle = true" in RENDERING


def test_exam_builder_cache_buster_matches_authoring_fix() -> None:
    assert "exam-builder.js?v=20260831-pgk-authoring2" in TEMPLATE
