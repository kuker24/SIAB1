# VPS Access, Reboot, and Testing Status — 2026-06-04

Dokumen ini mencatat status akses VPS setelah operator memberi approval eksplisit untuk restart VPS dan melanjutkan persiapan testing sistem.

## Scope

Tujuan status ini:

1. Mencatat bahwa VPS production sudah bisa diakses kembali.
2. Mencatat restart/reboot yang dilakukan dalam safe window.
3. Mencatat health post-reboot.
4. Mencatat bahwa safe-mode production tetap aktif.
5. Mencatat batas testing berikutnya agar tidak memakai data siswa asli atau artifact sensitif.

## Operator Approval

Operator memberi approval eksplisit untuk:

- restart VPS;
- melanjutkan progress update/testing sistem di VPS;
- mem-publish status progress ke GitHub.

## Pre-Reboot Safety Check

Waktu server sebelum reboot:

```text
Thu Jun 4 00:05:49 WIB 2026
```

Preflight DB aggregate:

| Check | Result |
|---|---:|
| Active published exam windows | 0 |
| `exam_sessions.status='in_progress'` | 0 |

Next published exams:

| Exam | Start WIB | End WIB |
|---|---:|---:|
| Fisika X/XI variants | 2026-06-04 07:30 | 2026-06-04 09:00 |
| Geografi/Bahasa Arab variants | 2026-06-04 09:30 | 2026-06-04 11:00 |

Decision: reboot was safe to perform because there was no active exam window and no in-progress session.

## Reboot Action

Reboot requested:

```text
Thu Jun 4 00:06:02 WIB 2026
```

SSH returned:

```text
Thu Jun 4 00:07:09 WIB 2026
```

Observed SSH downtime from polling: approximately 40 seconds.

## Post-Reboot Health

Stabilized check time:

```text
Thu Jun 4 00:08:38 WIB 2026
```

Uptime at stabilized check:

```text
up 2 min
```

Container health after stabilization:

- `ujian_online-api-1` through `ujian_online-api8-1`: healthy
- `ujian_online-api_admin-1`: healthy
- `ujian_online-api_admin2-1`: healthy
- `ujian_online-nginx-1`: healthy
- `ujian_online-db-1`: healthy
- `ujian_online-pgbouncer-1`: healthy
- `ujian_online-redis-1`: healthy
- `ujian_online-celery_worker-1`: healthy
- `ujian_online-celery_beat-1`: healthy
- `prometheus`: healthy
- `grafana`: healthy

Local Nginx `/health` checks after reboot:

| Attempt | HTTP | Time |
|---:|---:|---:|
| 1 | 200 | 0.017719s |
| 2 | 200 | 0.022964s |
| 3 | 200 | 0.019498s |

Health response:

```json
{"status":"healthy","app":"Ujian Online","version":"1.0.0"}
```

## Post-Reboot Data Safety Check

Post-reboot DB aggregate:

| Check | Result |
|---|---:|
| `exam_sessions.status='in_progress'` | 0 |
| Long active query sample | none observed in post-reboot aggregate |

DB connection state sample:

| State | Wait Event Type | Count |
|---|---|---:|
| idle | Client | 60 |
| activity/system | Activity | 5 |
| active | none | 1 |

Redis sample:

| Metric | Value |
|---|---:|
| `instantaneous_ops_per_sec` | 87 |
| `rejected_connections` | 0 |
| `evicted_keys` | 0 |

## Safe-Mode Environment After Reboot

API container env sample confirms production remains direct safe-mode:

```env
ADMIN_MONITORING_DETAIL_LEVEL=summary
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
ANSWER_WRITE_MODE=direct
APK_BUILD_ENDPOINT_ENABLED=false
EXAM_PEAK_MODE=true
HEAVY_EXPORT_ENABLED=false
MOBILE_APK_PRIMARY=true
SEB_DEBUG_ENDPOINTS_ENABLED=false
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
TELEGRAM_ALERTING_ENABLED=false
VIOLATION_ASYNC_ENABLED=true
```

No hybrid/queue/runtime-buffer rollout was activated.

## Final-Submit Endpoint Probe

Unauthenticated local probes were run only to verify the security boundary and routing surface; no token/session/answer was used.

| Endpoint | HTTP | Interpretation |
|---|---:|---|
| `/api/student/exams/submit` | 403 | blocked by APK/SEB/SXB security boundary, expected for unauthenticated/non-APK probe |
| `/api/exams/submit` | 403 | blocked by APK/SEB/SXB security boundary, expected for unauthenticated/non-APK probe |

This does not prove a successful final-submit transaction. It only confirms the security boundary is active and not weakened.

## What Was Not Done

- No deploy.
- No code sync.
- No migration.
- No DB schema change.
- No APK/AAB build or upload.
- No hybrid/queue/runtime-buffer activation.
- No raw answer export.
- No raw token/session export.
- No synthetic sessions CSV committed.
- No summary JSON committed.
- No direct 100/300/600 execution yet.
- No final-submit sample transaction yet.
- No answer consistency test yet.

## Testing Status

Phase 4.3.2 direct-mode execution remains **not passed** because direct-mode load tiers still require safe synthetic setup.

| Tier | Status | Reason |
|---|---|---|
| direct-100 | not executed | synthetic sessions CSV not prepared for approved test run |
| direct-300 | not executed | direct-100 has not passed |
| direct-600 | not executed | direct-300 has not passed |
| final-submit sample | not executed | no synthetic session/token transaction run yet |
| answer consistency | not executed | no synthetic write test run yet |

## Next Safe Plan

Before direct 100/300/600 can be claimed:

1. Prepare synthetic-only dataset; no real student data.
2. Generate synthetic sessions CSV under `/tmp` only.
3. Keep summary JSON under `/tmp` only.
4. Confirm the test window remains outside active exam hours.
5. Run dry-run first.
6. Execute direct-100 only after dry-run confirms target and endpoint.
7. Run SELECT-only answer consistency checks after direct-100.
8. Escalate to direct-300 only if direct-100 passes.
9. Escalate to direct-600 only if direct-300 passes.
10. Record sanitized aggregate results only.

## Current Decision

- VPS access: **confirmed**.
- VPS reboot: **completed successfully**.
- Production health after reboot: **healthy**.
- Safe-mode: **still active**.
- Phase 4.3.2: **continue**.
- Phase 5: **still blocked** until direct 100/300/600 and consistency gates are actually evidenced.
