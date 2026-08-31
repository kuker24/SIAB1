from pathlib import Path


BOOTSTRAP = Path(
    "static/js/exam-builder/modules/00-bootstrap-settings-events.js"
).read_text(encoding="utf-8")
RENDERING = Path(
    "static/js/exam-builder/modules/10-question-core-rendering.js"
).read_text(encoding="utf-8")
PAYLOAD = Path(
    "static/js/exam-builder/modules/20-advanced-preview-publish-validate.js"
).read_text(encoding="utf-8")
VALIDATION = Path(
    "static/js/exam-builder/modules/30-media-modal-publish-time-points.js"
).read_text(encoding="utf-8")


def test_new_pgk_stimulus_is_optional_and_off_by_default() -> None:
    assert "let use_stimulus = false" in RENDERING
    assert "Gunakan Stimulus / Konteks" in RENDERING
    assert "Opsional untuk PGK Tipe A dan B" in RENDERING
    assert "toggleStimulus(${index}, this.checked)" in RENDERING


def test_existing_stimulus_remains_enabled_without_legacy_flag() -> None:
    assert "settings.use_stimulus === true" in BOOTSTRAP
    assert "settings.use_stimulus !== false && persistedStimulus.trim() !== ''" in BOOTSTRAP


def test_disabled_stimulus_is_not_sent_or_previewed() -> None:
    assert "const stimulusValue = useStimulus ? (q.stimulus || '') : null" in PAYLOAD
    assert "use_stimulus: useStimulus" in PAYLOAD
    assert "q.use_stimulus === true && q.stimulus" in PAYLOAD


def test_enabled_empty_stimulus_is_validated_but_disabled_is_not() -> None:
    assert "q.use_stimulus === true && (!q.stimulus || !q.stimulus.trim())" in VALIDATION
    assert "Stimulus/bacaan wajib diisi untuk soal HOTS" not in VALIDATION
