from pathlib import Path


STUDENT_EXAM_TEMPLATE = Path("templates/student/exam.html")
EXAM_SYSTEM_MODULE = Path("static/js/exam-system/modules/00-runtime-utils-storage-sync.js")
EXAM_SYSTEM_BUNDLE = Path("static/js/exam-system.js")


def _student_exam_template() -> str:
    return STUDENT_EXAM_TEMPLATE.read_text(encoding="utf-8")


def test_student_image_zoom_has_touch_close_controls() -> None:
    template = _student_exam_template()

    assert 'class="zoom-close-btn"' in template
    assert 'onclick="closeImageZoom(event)"' in template
    assert 'ontouchend="closeImageZoom(event)"' in template
    assert 'class="zoom-exit-btn"' in template
    assert 'Tutup gambar' in template


def test_student_image_zoom_close_stops_event_propagation() -> None:
    template = _student_exam_template()

    assert "function closeImageZoom(event)" in template
    assert "event.preventDefault();" in template
    assert "event.stopPropagation();" in template
    assert "if (zoomCloseTimer) clearTimeout(zoomCloseTimer);" in template


def test_student_image_zoom_can_close_from_backdrop_at_normal_zoom() -> None:
    template = _student_exam_template()

    assert "target.closest('.zoom-close-btn, .zoom-exit-btn')" in template
    assert "currentZoom <= 1" in template
    assert "target.classList.contains('image-zoom-container')" in template


def test_student_image_zoom_selector_includes_exam_and_option_images() -> None:
    template = _student_exam_template()

    assert "const ZOOMABLE_EXAM_IMAGE_SELECTOR" in template
    assert "'img.question-image'" in template
    assert "'.question-content img'" in template
    assert "'.question-card img'" in template
    assert "'.question-text img'" in template
    assert "'.question-options img'" in template
    assert "'.option-item img'" in template
    assert "'.option-btn img'" in template
    assert "'img[data-zoomable=\"true\"]'" in template
    assert "target.closest(ZOOMABLE_EXAM_IMAGE_SELECTOR)" in template


def test_student_image_zoom_blocks_explicit_no_zoom_and_small_decorative_images() -> None:
    template = _student_exam_template()

    assert "function isZoomableExamImage(img)" in template
    assert "img.dataset.noZoom === 'true'" in template
    assert "img.closest('.no-image-zoom')" in template
    assert "width < 120 && height < 120" in template
    assert "forcedZoom" in template


def test_student_image_zoom_allows_direct_image_tap_inside_options_only() -> None:
    template = _student_exam_template()

    assert "const directImg = target.tagName && target.tagName.toLowerCase() === 'img' ? target : null" in template
    assert "const interactiveTarget = target.closest('button, a, input, textarea, select, label, [role=\"button\"]')" in template
    assert "if (interactiveTarget && !directImg) return null" in template


def test_student_image_zoom_native_bridge_and_js_fallback_are_present() -> None:
    template = _student_exam_template()

    assert "function openNativeImagePreview(src, alt)" in template
    assert "window.flutter_inappwebview.callHandler('openImagePreview', src, alt || '')" in template
    assert "if (opened === false) openImageZoom(src);" in template
    assert "openImageZoom(src);" in template


def test_student_image_zoom_uses_ratio_based_pinch_and_modal_active_guard() -> None:
    template = _student_exam_template()

    assert "let pinchStartDistance = null" in template
    assert "let pinchStartZoom = 1" in template
    assert "let lastTouchTapTime = 0" in template
    assert "const ratio = currentDistance / pinchStartDistance" in template
    assert "currentZoom = pinchStartZoom * ratio" in template
    assert "if (zoomModal && zoomModal.classList.contains('active')) return;" in template
    assert "e.stopPropagation();" in template


def test_render_question_image_marks_exam_images_zoomable() -> None:
    for path in (EXAM_SYSTEM_MODULE, EXAM_SYSTEM_BUNDLE):
        source = path.read_text(encoding="utf-8")
        assert "data-zoomable=\"true\"" in source
        assert "hasZoomAttribute" in source
        assert "data-(?:no-)?zoom" in source
