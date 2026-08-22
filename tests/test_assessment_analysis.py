from app.api.analytics import (
    _build_pan_thresholds,
    _classify_pan_letter,
    _classify_pan_scale10,
    _classify_pap_letter,
)


def test_pan_letter_thresholds_follow_expected_order():
    thresholds = _build_pan_thresholds(mean_score=75.0, std_dev=10.0)
    assert thresholds["a_min"] == 90.0
    assert thresholds["b_min"] == 80.0
    assert thresholds["c_min"] == 70.0
    assert thresholds["d_min"] == 60.0


def test_pan_letter_classification_with_zero_std_defaults_to_c():
    assert _classify_pan_letter(score=75.0, mean_score=75.0, std_dev=0.0) == "C"
    assert _classify_pan_letter(score=100.0, mean_score=75.0, std_dev=0.0) == "C"


def test_pan_scale10_classification_works_for_high_and_low_scores():
    assert _classify_pan_scale10(score=95.0, mean_score=75.0, std_dev=10.0) == 9
    assert _classify_pan_scale10(score=45.0, mean_score=75.0, std_dev=10.0) == 0


def test_pap_letter_classification_uses_fixed_bands():
    assert _classify_pap_letter(95.0) == "A"
    assert _classify_pap_letter(84.5) == "B"
    assert _classify_pap_letter(70.0) == "C"
    assert _classify_pap_letter(62.0) == "D"
    assert _classify_pap_letter(55.0) == "E"
