# Post-Exam Audit Report Template

Gunakan template ini untuk mencatat hasil audit pasca-ujian. Jangan memasukkan jawaban siswa mentah, password, token, atau PII sensitif.

## Template Singkat

```text
Tanggal audit:
Exam ID/nama:
Audit window:
Auditor:
Data source:
Backup status:
Total peserta:
Session status distribution:
Submitted/completed:
In progress/stuck:
Answer row count:
Sessions with zero answers:
Sessions with answer mismatch:
Final submit anomalies:
Grading/result anomalies:
Cheating/violation monitoring status:
Synthetic/test residue:
Data safety concern: yes/no
Recommended action:
Approval needed:
Follow-up Phase 4:
```

## Template Lengkap

```text
Audit ID:
Tanggal audit:
Jam mulai audit:
Jam selesai audit:
Audit window: (kapan ujian selesai / safe window)

Exam ID:
Exam nama:
Exam start time:
Exam end time:

Auditor:
Data source: (DB direct / API read-only / backup)
Backup status: (ada/tidak, timestamp backup, verified/not verified)

Total peserta:
Total sessions:

Session status distribution:
- submitted:
- completed:
- in_progress:
- abandoned:

Submitted/completed:
In progress/stuck:

Total questions per exam:
Answer row count:
Sessions with zero answers:
Sessions with answer count < question count:
Duplicate answer rows:

Final submit anomalies:
- Sessions with final submit but missing end_time:
- Sessions with end_time but not submitted:
- Answers after final submit:

Grading/result anomalies:
- Sessions with score NULL:
- Sessions with ungraded answers:
- Score distribution:

Cheating/violation monitoring status:
- Total violation events:
- Violation event types:
- Sessions with violation_count > 0:
- Security events aggregate:

Synthetic/test residue:
- Synthetic users found:
- Synthetic sessions found:
- Synthetic answers found:

Admin dashboard load time: (jika diketahui)
API 4xx/5xx during audit: (jika diketahui)
DB pressure during audit: (jika diketahui)

Data safety concern: yes/no
Data safety concern detail:

Anomaly list:
1. [severity] [deskripsi]
2. [severity] [deskripsi]

Recommended action:
- [ ] No action needed
- [ ] Manual review: [detail]
- [ ] Remediation needed: [detail]
- [ ] Escalation needed: [detail]

Approval needed:
- Decision owner:
- Scope approval:
- Backup verified:

Follow-up Phase 4:
- Performance bottleneck:
- Slow query:
- DB pressure:
- API latency:
- Dashboard issue:
- Redis backlog:
- Nginx error:

Notes:
```

## Severity Reference

- **Low risk**: anomali minor, tidak mempengaruhi data siswa.
- **Needs manual review**: perlu investigasi, tidak otomatis remediasi.
- **High risk / data safety**: risiko kehilangan atau korupsi data siswa.

## Report Output

Simpan report sebagai:

```text
docs/reports/post-exam-audit-[exam-id]-[date].md
```

Jangan commit report ke git jika mengandung data sensitif. Simpan di local atau secure storage.
