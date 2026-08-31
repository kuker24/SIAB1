from html.parser import HTMLParser
from pathlib import Path


class _InputValueParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.value = None

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.value = dict(attrs).get("value")


def _parse_input_value(html: str) -> str:
    parser = _InputValueParser()
    parser.feed(html)
    return parser.value


def test_exam_builder_escape_html_escapes_quotes_for_value_attributes():
    sources = [
        Path("static/js/exam-builder/modules/00-bootstrap-settings-events.js").read_text(),
        Path("static/js/exam-builder/modules/30-media-modal-publish-time-points.js").read_text(),
        Path("static/js/exam-builder.js").read_text(),
    ]

    for source in sources:
        assert ".replace(/\"/g, '&quot;')" in source
        assert ".replace(/'/g, '&#39;')" in source


def test_exam_builder_template_uses_quote_fix_cache_buster():
    source = Path("templates/admin/exam-builder.html").read_text()

    assert "exam-builder.js?v=20260831-pgk-stimulus1" in source


def test_html_attribute_encoded_quotes_round_trip_to_editor_value():
    rendered = '<input type="text" value="must&quot;n&#39;t">'

    assert _parse_input_value(rendered) == 'must"n\'t'


def test_unescaped_double_quote_would_truncate_input_value_regression_example():
    broken = '<input type="text" value="must"not">'

    assert _parse_input_value(broken) != 'must"not'
