# Parity checklist — Native-Lean v2

Kontrak yang harus sama sebelum cutover. Python/Flutter masih hidup.

## JS bridge (nama identik)

| Handler | Arah | Kotlin |
| --- | --- | --- |
| openImagePreview | JS → native | ExamActivity |
| securityHandler | JS → native | no-op log |
| setSessionId | JS → native | kiosk on + session |
| answerJournalEvent | JS → native journal | Prefs/queue |
| examStateUpdate | JS → native | resume snapshot |
| timerSync | JS → native | drift guard |
| examSubmitted | JS → native | kiosk off |
| logViolation | JS → API | ApiClient |
| userLogout | JS → native | clear + exit |
| forceKicked | JS → native | dialog + exit |
| forceSubmit | JS → native | toast; web submit |
| examCancelled | JS → native | kiosk off |

Polyfill wajib: `window.flutter_inappwebview.callHandler`.

## Header SXB/APK

- User-Agent: `SEB/3.5 Exambro/1.0`
- `X-Build-Token`, `X-App-Signature`, `X-App-Timestamp`, `X-App-Version`, `X-App-Build`
- `X-SafeExamBrowser-ConfigKeyHash` jika config key ada
- Authorization Bearer setelah login

## Rute HTTP (prefix)

- `/health`
- `/api/auth/*`
- `/api/exams` (start, auto-save, submit, submit-answer, session runtime)
- `/api/validate-apk-token`
- `/student/*`, `/admin/*`
- `/static/*`
- Admin/control: users, questions, monitoring, websocket, apk, seb, grading, analytics

Go dual-run: `PYTHON_UPSTREAM` mem-proxy `/api/*` dan `/ws/*` ke FastAPI.

Native Go (JWT 120 menit, pool Postgres):
- `POST /api/exams/auto-save`
- `POST /api/exams/submit-answer`
- `GET /api/exams/session/{id}/answers`
- `POST /api/exams/{id}/start` (soal tanpa `is_correct`)
- `GET /api/exams/session/{id}/remaining-time`
- `POST /api/exams/submit` (grading + idempotent)
- `POST /api/exams/auto-save-batch`
- `POST /api/exams/answer-journal/sync`
- `POST /api/exams/log-violation` (202)
- `GET /api/exams/session/{id}/status`
- `GET /api/exams/session/{id}/resume`
- `GET /api/auth/me`
- `POST /api/auth/login` + `/signin` + `/student/login` + `/student/signin`
- `POST /api/student/auth/login` + `/signin`
- `POST /api/auth/{control,admin,teacher,pengawas}/login` + namespace `/api/{lane}/auth/login`
- Prefix `/api/{student,control,admin,teacher,pengawas}/*` di-rewrite ke `/api/*` (kecuali login lane)
- `GET /api/apk/version` + `/config` + `POST /api/apk/validate-token`
- `POST /api/auth/refresh`
- `POST /api/exams/join`
- `GET /api/exams` (siswa/guruplus + staf: guru/pengawas/admin/developer)
- `GET /api/exams/{id}` (siswa/guruplus + staf)
- `GET /api/exams/{id}/pause-status`
- `POST /api/exams` + `PUT/DELETE /api/exams/{id}`
- `GET/POST /api/templates[/]` + `GET/PUT/DELETE /api/templates/{id}` + `POST /api/templates/{id}/create-exam`
- `POST/PATCH /api/exams/{id}/publish` (tanpa autofill opsi placeholder)
- `GET /api/questions/{id}/all`
- `POST /api/questions/{exam_id}` + `PUT/DELETE /api/questions/{question_id}`
- `GET/POST /api/questions/categories` + `/tags`
- `GET /api/exams/{id}/preview` + `POST /duplicate` + `POST /regenerate-token`
- `GET /api/users/student-classes` + `GET /api/users/students-by-class`
- `GET/POST /api/subjects` + `DELETE /api/subjects/{id}`
- `GET /api/monitoring/active-exams` + `/exam/{id}/live-stats` + `/sessions`
- `POST /api/exams/{id}/pause-all` + `/resume-all`
- `POST /api/exams/{id}/cleanup-sessions` (hapus hanya sesi `in_progress`)
- `POST /api/monitoring/sessions/{id}/kick` + `/reset` + `/reopen-override`
- `GET /api/monitoring/sessions/{id}/recovery-status` + `/exam/{id}/recovery-candidates`
- `POST /api/exams/sessions/{id}/force-submit`
- `GET /api/monitoring/violation-types`
- `GET /api/monitoring/violations` (JSON; ekspor PDF tetap fallback)
- `POST /api/exams/sessions/{id}/emergency-exit` + `/revoke-emergency-exit`
- `GET/POST /api/users` + `GET/PUT/DELETE /api/users/{id}` + `GET /api/users/advanced-search`
- `POST /api/users/batch-create` + `PATCH /batch-update` + `DELETE /batch-delete` + `POST /export` + `GET /template/csv`
- `GET /api/stats/dashboard`
- `GET /api/exams/{id}/sessions/{session_id}/review`
- `GET /api/exams/{id}/analytics`
- `GET /api/analytics/exam/{id}/classes` + `/question-difficulty`
- `GET /api/analytics/dashboard` + `/class`
- `GET /api/analytics/exam/{id}/assessment`
- `GET /api/activity/logs` + `/stats` + `DELETE /logs/reset`
- `POST /api/scheduled/exams/{id}/schedule` + `GET /schedules` + `DELETE /scheduled/schedules/{id}`
- `GET /api/v1/settings/timezone`
- `POST /api/questions/search`
- `GET /api/grading/pending-essays` + `/stats` + `/answer/{id}`
- `POST /api/grading/grade-essay` + `/batch-grade`
- `GET /api/exams/{id}/results` + `participation-summary` + `/exams/results/all`
- `GET /api/exams/my-results`
- `GET /api/runtime/policy`
- `POST /api/validate-apk-token`
- `GET /ws/health`
- Prefix `/api/student/*` di-rewrite ke `/api/*` (kecuali login siswa)
- `GET /api/exams/default-seb-config.seb` + `GET /api/seb/download-config` (flag `SEB_DESKTOP_LEGACY_ENABLED`)
- `GET /api/exams/{id}/seb-config.seb`
- `GET /seb/{id}` + `GET /exam/{id}/start`
- `GET /ws/exam/{exam_id}/{user_id}` (in-process; Redis monitor masih Python)

Admin/control login lane, CAPTCHA Redis, dan grading HOTS lanjutan masih bisa fallback Python.

## Worker

| Tugas | Interval |
| --- | --- |
| publications | 60s | Go native |
| close-expired-sessions | 30s | Go native |
| answer queue | 5s | Python/Celery fallback (Redis) |
| analytics views | 300s | Python/Celery fallback |
| exam_logs partitions | 02:15 UTC daily | Python/Celery fallback |
| DR drill | Minggu 03:40 UTC | Python/operasional fallback |

No-op timer tidak boleh dianggap parity. Worker Go hanya mendaftarkan pekerjaan yang benar-benar diimplementasikan.

## Fallback eksplisit

Fallback berikut dipertahankan karena bergantung pada kontrak eksternal atau output biner, bukan karena route DB-only belum dipindah:

- Redis: CAPTCHA/account-lockout, answer queue, online presence, dan `/ws/monitor/{exam_id}` pub/sub multi-replica.
- File/toolchain: media/image upload, SEB desktop build artifact, APK builder Flutter/Android, backup import/export, dan GPG.
- Dokumen: PDF/DOCX/Excel analytics, hasil, partisipasi, dan violations (ReportLab/python-docx parity).
- Operasional: Telegram, host metrics, warmup, auto-intelligence, safe restart/Docker, partition maintenance, dan DR drill.
- System settings mutation tetap FastAPI karena cache invalidation, freeze policy, APK profile encoding, dan notifikasi maintenance harus atomik lintas runtime.

## JWT / kebijakan

- JWT ujian 120 menit
- `redirect_slashes` tidak 307-kan body
- HTTPS redirect mati (Cloudflare)
- SXB enforce path student exam + start/submit/answer

## UI

- Admin Bootstrap 5.3. Ujian Inter + exam.css. Jangan restyle.
- APK splash/login: #0f172a / #3b82f6 / gradient #0b2f6f.

## Pintu cutover

- [ ] APK Kotlin: login, WebView, autosave, kiosk, SXB header
- [ ] Bundle `exam-system.js` dari `static/js/exam/` lulus tes zoom + `node --check`
- [ ] Go `/health` + SXB tes
- [ ] Shadow Compose `--profile native-lean` tanpa ganti Nginx lane siswa
- [ ] Fase D VPS hanya dengan permintaan operasional terpisah
