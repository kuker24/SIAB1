# Production Safe-Mode Deploy Report — 2026-06-03

## Scope

Adopsi backend mobile-first safe-mode ke VPS production untuk ujian, tanpa build APK baru dan tanpa mengaktifkan hybrid/queue/runtime buffer.

## Source / Commit

- Repository: `kuker24/Ujianonline`
- Branch: `review/sanitized-root-20260531-115153`
- Commit deployed/pushed: `67b2464f631d68a094a6adea4b429b426446a09d`
- VPS path: `/root/ujian_online`
- Catatan: folder VPS bukan git checkout; code disync manual dari branch dengan exclude forbidden files.

## Production Safe-Mode Env

Final env aktif di API container:

```text
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
EXAM_PEAK_MODE=true
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
MOBILE_APK_PRIMARY=true
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
SEB_DEBUG_ENDPOINTS_ENABLED=false
APK_BUILD_ENDPOINT_ENABLED=false
TELEGRAM_ALERTING_ENABLED=false
HEAVY_EXPORT_ENABLED=false
```

Unsafe flags verified absent:

```text
ANSWER_WRITE_MODE=hybrid    absent
ANSWER_WRITE_MODE=queue     absent
ANSWER_QUEUE_ENABLED=true   absent
APK_BUILD_ENDPOINT_ENABLED=true absent
```

## Service Topology

Observed healthy services:

- `nginx`
- `api`, `api2` … `api8`
- `api_admin`, `api_admin2`
- `celery_worker`
- `celery_beat`
- `pgbouncer`
- `postgres`
- `redis`

API/Celery were recreated rolling to apply code/env. PostgreSQL, Redis, and Nginx were not restarted.

## Redis Direct-Mode Verification

```text
PING=PONG
runtime:answer_queue:pending=0
runtime:answer_queue:processing=0
runtime:session:*:dirty_questions count=0
```

## PostgreSQL Preflight / Baseline

```text
pg_stat_activity:
active|1
idle|60
|5

write counters:
answers|6455|168332|601
exam_logs|0|0|0
exam_sessions|671|460|601
```

No real student `in_progress` sessions were observed before rolling API recreate.

## Backend Smoke Test

Synthetic-only backend smoke test passed and synthetic smoke data was cleaned afterward.

```text
login student test: 200
login teacher test: 200
join token test: 200
start exam test: 200
submit-answer x2: 200, 200
final submit: 200
admin monitoring page: 200
cheating/violations summary endpoint: 200
runtime policy endpoint: 200
synthetic smoke residue: users=0, exams=0, sessions=0
```

During smoke testing, one backend bug was found and fixed safely:

```text
NameError: _build_exam_start_validation_cache_key
```

Fix: restored the missing exam-start validation cache-key helper in `app/api/exams.py`. This did not alter DB schema, endpoint contracts, APK validation, or cheating controls.

## APK Decision

```text
APK baru dibuat: TIDAK
APK build endpoint: disabled
```

Reason:

- Existing APK remains the target runtime.
- Backend endpoints remained backward-compatible.
- Building/distributing a new APK immediately before exam increases signing/install/base URL/permission/kiosk risk.
- APK build endpoint must remain disabled during exam.

Physical APK smoke test on Android devices was not performed by the agent because the agent has no physical device access. Panitia should still verify existing APK on 1–3 real Android devices before exam.

## Operational Instruction for Exam Day

Template for panitia:

```text
Peserta masuk bertahap per gelombang 150–200 orang.
Jangan semua login/start bersamaan.
Peserta yang selesai boleh submit bertahap, jangan menunggu detik akhir.
Admin hanya membuka dashboard summary.
Jangan export PDF/Excel/report selama ujian.
Jika aplikasi melakukan retry otomatis, tunggu; jangan spam refresh/login.
```

Monitoring during exam:

- `docker stats --no-stream`
- Redis queue counters: pending/processing/dirty count
- PostgreSQL connection states
- App logs for HTTP 503, final submit errors, DB timeouts, answer write errors, auth errors, Redis errors, crashes/restarts

## Remaining Risks

- Direct 600 VU load test previously showed heavy pressure.
- Hybrid10 600 VU failed with repeated HTTP 503, so hybrid remains off.
- Primary mitigation is operational traffic shaping: stagger login/start/final-submit, summary-only admin dashboard, heavy exports off.

## Final Decision

- GO: backend mobile-first safe-mode direct.
- NO-GO: hybrid/queue/runtime buffer.
- NO-GO: build/distribute APK baru.
- Use existing APK if physical smoke test passes.
