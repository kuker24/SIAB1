# 04 - AI Review Prompt for GitHub / ChatGPT Connector

Gunakan prompt ini untuk meminta AI reviewer menilai kapasitas VPS dan desain runtime Ujian Online.

---

## Prompt

You are reviewing a production online exam system running on a single VPS. Please read all files in:

```text
docs/vps-capacity-review-20260602/
```

Focus on capacity, reliability, database pressure, and safe exam-day mitigations. Do not ask for secrets. Do not suggest destructive commands during active exams.

### Production context

The app is an online exam platform with FastAPI, PostgreSQL, PgBouncer, Redis, Celery, and Nginx. Students take exams concurrently. During exam time, preserving answer autosave and final submit is more important than admin monitoring and violation logging.

### Current VPS snapshot

- Ubuntu 22.04.5 LTS
- 16 vCPU
- 15 GiB RAM
- 60G disk, about 44% used
- Docker Compose production
- 8 FastAPI student replicas
- 2 FastAPI admin/control replicas
- PostgreSQL container
- PgBouncer container
- Redis container
- Nginx container
- Prometheus/Grafana

### Incident summary

On 2026-06-02 morning exam traffic caused overload:

- Load average reached ~80-117.
- PostgreSQL CPU reached >200%.
- PgBouncer CPU reached ~40%.
- Many API containers approached 960 MiB memory limit.
- Admin/guru/pengawas dashboards became inaccessible or slow.
- Students were degraded but not fully disconnected.
- Nginx logs showed many 499/502/503.
- Hot endpoints were:
  - `/api/student/exams/auto-save-batch`
  - `/api/exams/answer-journal/sync`
  - `/api/exams/log-violation`
  - `/api/exams/auto-save-batch`

### Emergency mitigations applied

- Terminated stale PostgreSQL `idle in transaction` sessions.
- Set `idle_in_transaction_session_timeout = 30s` for application role/database.
- Temporarily changed Nginx so `/api/exams/log-violation` returns `204 No Content` to protect answer autosave/final submit.
- Did not restart containers during active exam.
- Did not block final submit.

### Please review and answer

1. Is the current single VPS capacity sufficient for future 300-600 concurrent exam users?
2. Should we upgrade single VPS or split database into a dedicated server?
3. What CPU/RAM/disk sizing would you recommend?
4. Is PgBouncer configuration likely too permissive for this DB size?
5. What permanent code changes should be prioritized?
   - autosave backoff
   - answer journal batching
   - async violation logging
   - final submit priority
   - DB transaction hygiene
6. What emergency runbook should be used during active exams?
7. What should be rolled back after exam day?
8. What metrics should be monitored and thresholded?
9. Are there risks with keeping `/api/exams/log-violation -> 204` during exams?
10. Provide a prioritized action plan: P0 today, P1 this week, P2 infrastructure.

### Constraints

- Do not propose deleting volumes or rebooting during active exams.
- Do not propose changing student exam flow during active exams unless extremely low-risk.
- Do not expose or request secrets.
- Preserve final submit and answer persistence as highest priority.
- SEB/SXB/security enforcement should not be weakened except for the already documented temporary violation-log traffic shed, which must be reviewed explicitly.

---

## Expected output

Please produce:

1. Executive summary.
2. Root cause analysis.
3. Infrastructure recommendation.
4. App/database tuning recommendation.
5. Exam-day emergency runbook.
6. Rollback plan for emergency mitigations.
7. Prioritized implementation checklist.
