# Performance Risk Register — Phase 4

This register tracks direct-mode performance risks for `kuker24/Ujianonline` before any future hybrid/queue rollout. It is intentionally operational and reversible: no production change is authorized by this document.

| ID | Risk | Evidence | Impact | Likelihood | Mitigation | Status |
|---|---|---|---|---|---|---|
| P4-R1 | Direct single-answer path commits each answer | Source review of `AnswerSyncService.accept_single_answer`; direct 600 pressure observed | High DB transaction pressure | High | Keep direct safe; Phase 4.3.2G skips physical UPDATE for identical duplicate payloads; prefer existing batch/journal where UX supports it | Partially mitigated pending revalidation |
| P4-R2 | Repeated SELECT before/around answer write | Session probe, question validation fallback, lock/load, progress fallback | Extra DB round trips under concurrency | High | Cache-first validation; skip progress DB fallback/broadcast during peak | Partially mitigated pending revalidation |
| P4-R3 | Session-level lock serializes bursts | Advisory lock + row lock protect answer correctness | Latency spikes if one session sends overlapping requests | Medium | Keep for correctness; reduce overlapping client sends if needed | Open |
| P4-R4 | Progress monitoring DB/publish side effect adds pressure | `_publish_progress_if_needed` could count answers or publish progress after each answer interval | Non-critical DB/publish work during answer hot path | Medium | Phase 4.3.2G skips progress broadcast entirely during `EXAM_PEAK_MODE=true` | Mitigated pending revalidation |
| P4-R5 | Final submit loads questions/options/answers and writes logs | Final submit service eager loads grading data and writes two `ExamLog` rows | Submit-wave latency/DB pressure | Medium | Preserve priority; test submit waves; do not remove audit logs without review | Open |
| P4-R6 | Admin dashboard detail usage during peak | Monitoring module has many query paths; Phase 2 requires summary-only | Can compete with answer/final-submit DB capacity | Medium | `ADMIN_MONITORING_DETAIL_LEVEL=summary`; use aggregate dashboard only | Guarded |
| P4-R7 | Heavy exports during exam peak | PDF/results exports are DB/CPU heavy | Can starve hot paths | Medium | `HEAVY_EXPORT_ENABLED=false` during peak; `heavy_exports_active` requires non-peak | Guarded |
| P4-R8 | Violation logging sync fallback | Sync path updates session + log + publish | DB writes competing with answer path | Low if async remains true | Keep `VIOLATION_ASYNC_ENABLED=true`; do not remove async path | Guarded |
| P4-R9 | DB/PgBouncer pool saturation | Direct 600 and hybrid10 600 symptoms; Redis backlog stayed 0 | 503/timeouts under concurrency | Medium | Measure pool usage in staging; avoid production load tests | Open |
| P4-R10 | Hybrid rollout before direct stabilizes | Hybrid10 600 produced many 503 | Production instability | High if rushed | Block Phase 5 until direct-mode gates pass | Blocked |
| P4-R11 | Schema/index change applied without staging | Potential future index proposal | Migration lock/risk | Low if policy followed | Proposal-only, staging test, safe-window approval | Guarded |
| P4-R12 | Sensitive artifacts committed during perf work | Repo has APK/docs/data-adjacent workflows | Secret/data leak | Medium | Forbidden file check before commit | Guarded |

## Immediate Watch List for Local/Staging Load Tests

1. `/api/exams/submit-answer` p95/p99 and status `0` client exceptions.
2. `/api/exams/submit` final submit 5xx and latency.
3. PostgreSQL active connections and statement timeout symptoms.
4. PgBouncer client wait count if available.
5. Redis answered-count availability; progress broadcast should be skipped during peak and must not hit DB if Redis fails.
6. Admin monitoring usage during test: summary only.
7. Violation async status: true.

## Decision Rules

- If direct 300 has 5xx: stop and fix direct path before 600.
- If direct 600 has repeated 5xx, final-submit failures, or severe p95/p99 latency/DB pressure: no hybrid rollout.
- If final submit regresses: revert Phase 4 runtime patch and investigate.
- If Redis backlog remains 0 but DB pressure rises: prioritize DB/write-path and pool diagnostics, not queue activation.
- If any production action is needed: require review, safe window, backup/rollback plan, and explicit approval.
