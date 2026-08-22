from pathlib import Path


EXAM_PAGE = Path("flutter_client_code/lib/pages/exam_page.dart")


def _exam_page_source() -> str:
    return EXAM_PAGE.read_text(encoding="utf-8")


def test_flutter_exam_page_registers_native_image_preview_handler() -> None:
    source = _exam_page_source()

    assert "handlerName: 'openImagePreview'" in source
    assert "_handleOpenImagePreview(args)" in source
    assert "_resolveImagePreviewUrl" in source


def test_flutter_native_image_preview_uses_interactive_viewer_dialog() -> None:
    source = _exam_page_source()

    assert "InteractiveViewer" in source
    assert "TransformationController" in source
    assert "minScale: 1" in source
    assert "maxScale: 5" in source
    assert "panEnabled: true" in source
    assert "scaleEnabled: true" in source
    assert "Matrix4.identity()..scale(2.5)" in source
    assert "PopScope" in source
    assert "Image.network" in source
    assert "CircularProgressIndicator" in source
    assert "Gambar gagal dimuat" in source


def test_flutter_native_image_preview_keeps_auth_and_sxb_headers() -> None:
    source = _exam_page_source()

    assert "_buildImagePreviewHeaders" in source
    assert "_apiService.getSebHeaders(imageUrl)" in source
    assert "_apiService.getToken()" in source
    assert "headers['Authorization'] = 'Bearer $token';" in source
