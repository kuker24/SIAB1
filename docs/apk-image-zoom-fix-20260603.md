# APK Image Zoom Fix — 2026-06-03

## Problem

Android APK/WebView users could open an exam image preview but image zoom was unreliable. The earlier patch made the close controls more robust, but did not address the root causes for APK/WebView image zoom:

- The web selector only targeted `img.question-image`.
- Images inside answer options were blocked by the old `.option-item/.option-btn` guard.
- The JS pinch algorithm used additive deltas (`currentZoom += delta * 0.005`), which can jump in Android WebView.
- APK WebView zoom settings are not enough because the exam page uses a custom JS modal.
- Native Flutter has a more stable pinch/pan surface via `InteractiveViewer`.

## Root Cause

The exam page depended on a narrow JS image selector and custom WebView touch handling. Android WebView can deliver touch/click sequences differently from desktop browsers, so option images and pinch gestures were fragile.

## Web Template Patch

`templates/student/exam.html` now:

- Uses `isZoomableExamImage(img)` and `ZOOMABLE_EXAM_IMAGE_SELECTOR`.
- Supports:
  - `img.question-image`
  - `.question-content img`
  - `.question-card img`
  - `.question-text img`
  - `.question-options img`
  - `.option-item img`
  - `.option-btn img`
  - `img[data-zoomable="true"]`
- Blocks decorative/non-content images via:
  - `data-no-zoom="true"`
  - `.no-image-zoom`
  - small image guard under `120x120`, unless `data-zoomable="true"`
- Allows tapping directly on an option image to open preview.
- Leaves tapping option area outside the image to normal answer selection.
- Adds a Flutter bridge function `openNativeImagePreview(src, alt)`.
- Falls back to the JS modal when native preview is unavailable.

## JS Pinch Patch

The JS fallback modal now uses ratio-based pinch:

```text
pinchStartDistance = getDistance(e.touches)
pinchStartZoom = currentZoom
ratio = currentDistance / pinchStartDistance
currentZoom = pinchStartZoom * ratio
```

It also keeps the previous robust close controls:

- Close button right/top.
- Bottom `Tutup gambar` button.
- Backdrop close at normal zoom.
- Guard so body `touchend` does not reopen zoom while the modal is active.

## Native Flutter Preview

`flutter_client_code/lib/pages/exam_page.dart` now registers:

```dart
controller.addJavaScriptHandler(
  handlerName: 'openImagePreview',
  callback: (args) async => await _handleOpenImagePreview(args),
);
```

The native preview:

- Resolves absolute and relative image URLs.
- Adds SXB/SEB headers from `ApiService.getSebHeaders(imageUrl)`.
- Adds `Authorization: Bearer ...` when a token is available.
- Opens a fullscreen black dialog.
- Uses `InteractiveViewer` with `minScale: 1`, `maxScale: 5`, pan and scale enabled.
- Supports double tap zoom toggle `1x / 2.5x`.
- Shows loading and error states.
- Lets Android back close the image preview dialog without exiting the exam.
- Does not stop kiosk, timers, answer sync, or security monitoring.

## Manual APK Test Checklist

Run after an APK build/distribution is explicitly approved:

1. Build debug/release APK.
2. Install on 1–3 real Android devices.
3. Login using a test student account.
4. Start a test exam with at least one main question image.
5. Tap the question image.
6. Verify native fullscreen preview opens.
7. Pinch zoom.
8. Pan while zoomed.
9. Double tap to toggle zoom.
10. Tap `Tutup`.
11. Reopen image and press Android back.
12. Verify Android back closes preview only, not the exam.
13. Test an image inside an answer option.
14. Tap option area outside the image and verify it still selects the answer.
15. Continue answering.
16. Final submit.
17. Confirm no false cheating violation is triggered by image preview interactions.

## Rollback

Code rollback:

```bash
git revert <commit-that-added-this-fix>
```

Operational rollback for VPS web-only template patch:

```bash
cp /opt/loadtest/ujianonline/deploy-backups/student-exam-before-image-zoom-fix-*.html \
  /root/ujian_online/templates/student/exam.html
```

If reverting native Flutter preview after an APK release, build and distribute a replacement APK only after normal approval/testing.

## Non-Changes

- No DB schema change.
- No public endpoint contract change.
- No answer/final-submit flow change.
- No SXB/APK signature validation weakening.
- No cheating detection removal.
- No APK/AAB artifact committed.
