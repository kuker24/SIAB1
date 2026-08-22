from app.core.sanitization import sanitize_optional_text


def test_question_text_sanitizer_preserves_single_and_double_quotes():
    text = 'Dia berkata "setuju" dan \'siap\'.'

    assert sanitize_optional_text(text) == text


def test_question_text_sanitizer_decodes_existing_quote_entities():
    text = "Al-Qur&#x27;an disebut &quot;pedoman&quot; dan &#39;petunjuk&#39;."

    assert sanitize_optional_text(text) == "Al-Qur'an disebut \"pedoman\" dan 'petunjuk'."


def test_question_text_sanitizer_still_strips_html_tags():
    text = "<script>alert('x')</script> Guru berkata \"aman\"."

    assert sanitize_optional_text(text) == "alert('x') Guru berkata \"aman\"."
