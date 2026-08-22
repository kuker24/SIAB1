# Direct Mode Performance Review

Scope: Phase 4 local source review for answer/final-submit paths. This document summarizes bottleneck candidates and safe optimization posture for direct mode. It does not authorize production deployment or production load testing.

## Reviewed Code Paths

| Path | File | Contract Status |
|---|---|---|
| `POST /api/exams/submit-answer` | `app/api/answer_sync.py`, `app/services/answer_sync_service.py` | unchanged |
| legacy autosave | `app/api/exam_answer_sync.py`, `app/services/answer_sync_service.py` | unchanged |
| batch autosave | `app/api/exam_answer_sync.py`, `app/services/answer_sync_service.py` | unchanged |
| answer journal sync | `app/api/exam_answer_sync.py`, `app/services/answer_sync_service.py` | unchanged |
| final submit | `app/api/final_submit.py`, `app/services/final_submit_service.py` | unchanged |
| violation logging | `app/api/violation_events.py` | unchanged |
| admin monitoring | `app/api/monitoring.py` | unchanged |
| heavy exports | `app/api/exam_exports.py` | unchanged |

## Single Answer Direct Path

Observed flow:

1. Rate limit check.
2. Session probe SELECT.
3. SEB/SXB/header validation.
4. Question validation payload via cache/DB fallback.
5. Session advisory lock + row lock.
6. Optional queue/hybrid gating remains off under safe defaults.
7. PostgreSQL upsert into `answers`.
8. Commit.
9. Redis answered marker/runtime snapshot update.
10. Throttled progress monitor publish.

Performance notes:

- Correctness is strong because direct write is committed before best-effort monitoring.
- Per-answer DB write + commit is expected in direct mode.
- Advisory lock + row lock serialize concurrent writes for the same session, reducing race risk.
- Progress broadcast is non-critical and must not increase DB pressure during peak.

Phase 4 patch:

- If `EXAM_PEAK_MODE=true` and runtime/Redis answered count is unavailable, skip the DB answered-count fallback for progress broadcast.
- Saved answers and final submit are unaffected.

Phase 4.3.2G patch:

- Identical duplicate single-answer payloads no longer force a physical PostgreSQL UPDATE; `ON CONFLICT DO UPDATE` now has a `WHERE` condition based on payload/score changes and intentionally excludes `answered_at` from the duplicate comparison.
- During `EXAM_PEAK_MODE=true`, non-critical progress broadcast is skipped entirely after the answer is safely committed. Runtime answered-count Redis updates remain best-effort, and final submit is unchanged.

## Batch Autosave Path

Observed flow:

1. Session SELECT.
2. Runtime buffer gate; default safe-mode directs to DB path.
3. Deduplicate answers by question.
4. Validate question IDs with one SELECT.
5. Acquire session lock and row lock.
6. Load existing answers in one SELECT.
7. Apply only changed rows.
8. Commit once if changes exist.
9. Redis/runtime answered count update.

Performance posture:

- Better than single-answer for high-frequency client sync because multiple answers share one transaction.
- Existing no-op update skip reduces write amplification.
- Conflict retry path can be expensive because it serializes and may inspect answers individually, but that should be rare.

## Answer Journal Sync Path

Observed flow:

1. Session SELECT.
2. Validate max event count.
3. Valid question ID SELECT.
4. Redis idempotency check via pipeline.
5. Deduplicate latest event by question.
6. Session lock/row lock.
7. Load existing answers in one SELECT.
8. Apply changed rows.
9. Commit once if changes exist.
10. Redis event ack set and runtime answered marker.

Performance posture:

- Good direct-mode consolidation path.
- Idempotency uses Redis pipeline and avoids repeated DB writes for duplicate client events.
- Keep default event cap to avoid huge sync bursts.

## Final Submit Path

Observed flow:

1. Rate limit check.
2. Session probe with exam metadata.
3. Idempotent response if already submitted/completed.
4. SEB validation.
5. Queue/runtime buffer flush gates; off under direct safe-mode.
6. Session advisory lock + row lock.
7. Load exam/questions/options/answers.
8. Grade in memory.
9. Update answer scores where needed, session status/end_time/score, exam result flag.
10. Write `EXAM_SUBMITTED` and `SCORE_BREAKDOWN` logs.
11. Commit.
12. Best-effort cache invalidation/Redis/publish.

Performance posture:

- Final submit is heavier than single answer but less frequent.
- It already handles submitted/completed idempotency.
- Objective answers can reuse persisted score when available.
- Transient DB pressure maps to 503 with `Retry-After` in key steps.
- Do not defer/remove score logs without an audit/reporting dependency review.

## Violation Logging

Default safe posture:

- `VIOLATION_ASYNC_ENABLED=true`.
- Public path returns accepted response based on enqueue service.
- Sync fallback is write-heavy and should not be enabled during peak.

Important operational note:

- Nginx emergency shedding for `/api/exams/log-violation` is outside this local Phase 4 patch. Do not alter production nginx without safe-window approval.

## Admin Dashboard and Exports

Expected safe posture:

- `ADMIN_MONITORING_DETAIL_LEVEL=summary` during active exam.
- Dashboard detail should remain lazy/on-demand.
- `HEAVY_EXPORT_ENABLED=false` during peak, implemented through `settings.heavy_exports_active` requiring non-peak mode.

## Bottleneck Candidates Ranked

| Rank | Candidate | Confidence | Impact | Complexity | Current Action |
|---:|---|---|---|---|---|
| 1 | Per-answer DB commit/upsert in direct mode | high | high | high to change safely | keep direct; Phase 4.3.2G skips identical duplicate physical updates; prefer existing batch/journal in client flow |
| 2 | Non-critical progress broadcast/fallback | high | medium under peak/autosave bursts | low | Phase 4 skipped fallback; Phase 4.3.2G skips broadcast entirely during peak |
| 3 | Final submit eager load and score/log writes | medium | medium-high during submit wave | medium-high | document, test, keep priority |
| 4 | Admin monitoring detail queries during peak | medium | medium | low-operational | enforce summary default and docs |
| 5 | DB/PgBouncer pool saturation | medium | high | infra + tuning | measure in local/staging; no prod change |
| 6 | Violation sync fallback writes | low if async remains true | medium | low | keep async true |

## Measurement Plan

Before and after any further patch:

- API status counts by endpoint.
- p50/p95/p99 latency for submit-answer and final-submit.
- 5xx/429 count.
- DB connection usage and pool timeouts if available.
- PgBouncer active/waiting clients if available.
- Redis pending/processing/dirty queues.
- Final submit success rate.
- Answer row count consistency in synthetic dataset.

## Recommendation

Proceed with Phase 4.3.2G review and rerun direct-mode validation only after explicit deployment/revalidation approval (or in isolated staging). Do not start Phase 5 hybrid rollout until direct 300/600 latency and DB pressure improve materially and the previous hybrid10 503 issue is explained or mitigated.
