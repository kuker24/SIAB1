# Phase 3 Post-Exam Audit & Data Safety — 2026-06-03

Dokumen ini adalah panduan audit pasca-ujian. Audit hanya boleh dilakukan setelah ujian selesai atau pada safe window yang disetujui oleh decision owner.

## 1. Tujuan Phase 3

1. Memastikan tidak ada jawaban siswa hilang.
2. Memastikan final submit valid dan idempotent.
3. Memastikan session status konsisten.
4. Memastikan grading/skor benar tersimpan.
5. Memastikan cheating detection/violation log tetap tersedia.
6. Tidak melakukan destructive action.
7. Audit pertama harus read-only.
8. Export/report berat hanya setelah safe window.
9. Semua anomaly dicatat untuk follow-up Phase 4.

## 2. Prasyarat

Audit hanya boleh dilakukan jika:

- Ujian sudah selesai, atau
- Safe window sudah disetujui, atau
- Decision owner memberikan approval eksplisit.

Audit berat (full-table count, rekap besar) tidak boleh dijalankan saat:

- Ujian masih aktif.
- Final-submit peak masih berlangsung.
- Production masih dipakai siswa.

## 3. Non-Destructive Audit Principle

Audit Phase 3 bersifat non-destruktif:

- SELECT-only.
- Tidak ada UPDATE/DELETE/INSERT.
- Tidak ada TRUNCATE/DROP.
- Tidak ada migration.
- Tidak ada cleanup data siswa.
- Tidak ada mark submitted manual.
- Tidak ada regenerate grading massal.
- Capture counts/summary, bukan jawaban siswa mentah.

## 4. Data Safety Priority

Prioritas audit:

1. **Answer safety**: semua jawaban siswa tersimpan.
2. **Final-submit integrity**: semua final submit tercatat dengan benar.
3. **Session consistency**: status session konsisten.
4. **Grading completeness**: skor tersimpan untuk semua terminal session (`submitted` + `completed`).
5. **Violation availability**: cheating/violation data tersedia untuk review.
6. **No residue**: tidak ada data synthetic/test yang tertinggal.

## 5. Production Safe-Mode Reminder

Audit tidak mengubah safe-mode production:

```text
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
APK_BUILD_ENDPOINT_ENABLED=false
HEAVY_EXPORT_ENABLED=false (saat peak; boleh true hanya setelah safe window dan approval)
```

## 6. Tables/Entities yang Diaudit

### exam_sessions

Tabel utama tracking session ujian siswa.

Kolom penting:

- `id`, `user_id`, `exam_id`
- `status`: in_progress, completed, submitted, abandoned
- `score`: skor akhir (NULL jika belum di-grade)
- `start_time`, `end_time`
- `violation_count`
- `emergency_exit_allowed`, `terminated_by_admin`
- `is_paused`, `paused_at`, `total_paused_seconds`
- `archived_exam_title`, `archived_exam_subject`

### answers

Tabel jawaban siswa per pertanyaan.

Kolom penting:

- `id`, `session_id`, `question_id`
- `selected_option_id` (single choice)
- `selected_option_ids` (multiple choice complex)
- `answer_text` (essay/short answer)
- `is_correct`, `points_earned`
- `answered_at`

Constraint: `uq_answers_session_question` — satu jawaban per session per question.

### exam_logs

Audit trail dan violation tracking.

Kolom penting:

- `session_id`, `event_type`, `event_data`, `created_at`

### users

Data pengguna.

Kolom penting:

- `id`, `username`, `role`, `student_class`, `is_active`

Catatan: tidak audit PII sensitif (password_hash, profile_picture).

### exams

Data ujian.

Kolom penting:

- `id`, `title`, `start_time`, `end_time`
- `is_published`, `is_deleted`
- `has_ever_had_results`

### questions / question_options

Data soal dan opsi jawaban.

Kolom penting:

- `questions`: `exam_id`, `question_type`, `points`, `order_index`
- `question_options`: `question_id`, `is_correct`

### security_events

Event keamanan/violation.

Kolom penting:

- `event_type`, `user_id`, `session_id`, `severity`, `timestamp`

### user_activity_logs

Log aktivitas pengguna.

Kolom penting:

- `user_id`, `event_type`, `event_data`, `created_at`

## 7. Audit Checklist

### 7.1 Session Status Distribution

```sql
SELECT
    status,
    COUNT(*) AS session_count
FROM exam_sessions
WHERE exam_id = :exam_id
GROUP BY status
ORDER BY session_count DESC;
```

Validasi:

- Terminal count (`submitted` + `completed`) sesuai ekspektasi.
- `in_progress` = 0 setelah ujian selesai.
- `abandoned` masuk akal.

### 7.2 Terminal Count (Submitted + Completed)

```sql
SELECT COUNT(*) AS terminal_count
FROM exam_sessions
WHERE exam_id = :exam_id
  AND status IN ('submitted', 'completed');
```

### 7.3 In-Progress / Stuck Sessions

```sql
SELECT
    id,
    user_id,
    start_time,
    end_time,
    status
FROM exam_sessions
WHERE exam_id = :exam_id
  AND status = 'in_progress'
ORDER BY start_time
LIMIT 50;
```

Jika ada session `in_progress` setelah ujian selesai, catat sebagai anomaly.

### 7.4 Answer Count vs Question Count

```sql
-- Total questions per exam
SELECT exam_id, COUNT(*) AS question_count
FROM questions
WHERE exam_id = :exam_id
GROUP BY exam_id;

-- Answer count per session
SELECT
    es.id AS session_id,
    es.status,
    COUNT(a.id) AS answer_count
FROM exam_sessions es
LEFT JOIN answers a ON a.session_id = es.id
WHERE es.exam_id = :exam_id AND es.status IN ('submitted', 'completed')
GROUP BY es.id, es.status
ORDER BY answer_count ASC
LIMIT 50;
```

Validasi: semua terminal session (`submitted`/`completed`) memiliki answer_count > 0.

### 7.5 Sessions with Zero Answers

```sql
SELECT
    es.id AS session_id,
    es.user_id,
    es.status,
    es.start_time,
    es.end_time
FROM exam_sessions es
LEFT JOIN answers a ON a.session_id = es.id
WHERE es.exam_id = :exam_id
  AND es.status IN ('submitted', 'completed')
  AND a.id IS NULL;
```

Jika ada: anomaly tinggi, perlu investigasi.

### 7.6 Duplicate Answer Rows

Batasan `uq_answers_session_question` seharusnya mencegah duplikat, tapi audit tetap perlu dicek:

```sql
SELECT
    session_id,
    question_id,
    COUNT(*) AS row_count
FROM answers
WHERE session_id IN (
    SELECT id FROM exam_sessions WHERE exam_id = :exam_id
)
GROUP BY session_id, question_id
HAVING COUNT(*) > 1;
```

Jika ada: anomaly schema/data integrity.

### 7.7 Final Submit Timestamp Consistency

```sql
SELECT
    es.id AS session_id,
    es.user_id,
    es.end_time AS session_end_time,
    MAX(a.answered_at) AS last_answer_time
FROM exam_sessions es
JOIN answers a ON a.session_id = es.id
WHERE es.exam_id = :exam_id AND es.status IN ('submitted', 'completed')
GROUP BY es.id, es.user_id, es.end_time
HAVING es.end_time IS NULL
    OR MAX(a.answered_at) > es.end_time + INTERVAL '5 minutes';
```

Jika ada jawaban setelah `end_time`: anomaly timestamp.

### 7.8 Answers After Final Submit

```sql
SELECT
    a.session_id,
    a.question_id,
    a.answered_at,
    es.end_time
FROM answers a
JOIN exam_sessions es ON es.id = a.session_id
WHERE es.exam_id = :exam_id
  AND es.status IN ('submitted', 'completed')
  AND es.end_time IS NOT NULL
  AND a.answered_at > es.end_time
LIMIT 50;
```

### 7.9 Terminal Sessions with Missing Score

```sql
SELECT
    id,
    user_id,
    status,
    score,
    end_time
FROM exam_sessions
WHERE exam_id = :exam_id
  AND status IN ('submitted', 'completed')
  AND score IS NULL;
```

Jika ada: grading belum selesai, perlu follow-up.

### 7.10 Grading/Result Completeness

```sql
SELECT
    es.id AS session_id,
    es.status,
    es.score,
    COUNT(CASE WHEN a.is_correct IS NULL THEN 1 END) AS ungraded_answers,
    COUNT(a.id) AS total_answers
FROM exam_sessions es
JOIN answers a ON a.session_id = es.id
WHERE es.exam_id = :exam_id AND es.status IN ('submitted', 'completed')
GROUP BY es.id, es.status, es.score
HAVING COUNT(CASE WHEN a.is_correct IS NULL THEN 1 END) > 0
LIMIT 50;
```

### 7.11 Cheating/Violation Aggregate

```sql
-- From exam_logs
SELECT
    event_type,
    COUNT(*) AS event_count
FROM exam_logs el
JOIN exam_sessions es ON es.id = el.session_id
WHERE es.exam_id = :exam_id
  AND el.event_type ILIKE '%violation%'
   OR el.event_type ILIKE '%cheat%'
   OR el.event_type ILIKE '%suspicious%'
GROUP BY event_type
ORDER BY event_count DESC;

-- From security_events
SELECT
    event_type,
    severity,
    COUNT(*) AS event_count
FROM security_events se
JOIN exam_sessions es ON es.id = se.session_id
WHERE es.exam_id = :exam_id
GROUP BY event_type, severity
ORDER BY event_count DESC;
```

### 7.12 Violation Count Distribution

```sql
SELECT
    violation_count,
    COUNT(*) AS session_count
FROM exam_sessions
WHERE exam_id = :exam_id
  AND violation_count > 0
GROUP BY violation_count
ORDER BY violation_count DESC;
```

### 7.13 Synthetic/Test Residue Check

```sql
-- Check for synthetic/test users
SELECT id, username, role, student_class
FROM users
WHERE username LIKE '%synthetic%'
   OR username LIKE '%test_%'
   OR username LIKE '%loadtest%'
   OR username LIKE '%dummy%'
LIMIT 50;

-- Check for synthetic sessions
SELECT COUNT(*)
FROM exam_sessions es
JOIN users u ON u.id = es.user_id
WHERE u.username LIKE '%synthetic%'
   OR u.username LIKE '%test_%'
   OR u.username LIKE '%loadtest%';
```

### 7.14 Exam-Level Summary

```sql
SELECT
    e.id AS exam_id,
    e.title,
    e.start_time,
    e.end_time,
    e.is_published,
    e.is_deleted,
    e.has_ever_had_results,
    COUNT(DISTINCT es.id) AS total_sessions,
    COUNT(DISTINCT CASE WHEN es.status = 'submitted' THEN es.id END) AS submitted_sessions,
    COUNT(DISTINCT CASE WHEN es.status = 'completed' THEN es.id END) AS completed_sessions,
    COUNT(DISTINCT CASE WHEN es.status IN ('submitted', 'completed') THEN es.id END) AS terminal_sessions,
    COUNT(DISTINCT CASE WHEN es.status = 'in_progress' THEN es.id END) AS in_progress_sessions,
    COUNT(DISTINCT a.id) AS total_answers,
    AVG(es.score) AS avg_score,
    MIN(es.score) AS min_score,
    MAX(es.score) AS max_score
FROM exams e
LEFT JOIN exam_sessions es ON es.exam_id = e.id
LEFT JOIN answers a ON a.session_id = es.id
WHERE e.id = :exam_id
GROUP BY e.id, e.title, e.start_time, e.end_time, e.is_published, e.is_deleted, e.has_ever_had_results;
```

## 8. Safe Query Rules

1. **SELECT-only**: tidak ada INSERT/UPDATE/DELETE/DROP/TRUNCATE.
2. **LIMIT/SAMPLE untuk detail**: query detail menggunakan LIMIT 50 atau lebih kecil.
3. **Bounded aggregation**: query count/summary lebih dulu, baru detail jika perlu.
4. **Run during safe window**: jangan jalankan query berat saat production masih aktif.
5. **Capture counts only**: tidak mencetak jawaban siswa mentah.
6. **No PII export**: tidak export password_hash, answer_text, atau data pribadi.
7. **Parameterized**: gunakan parameter `:exam_id`, bukan string concatenation.

## 9. Backup Checklist Before Any Remediation

Jika ditemukan anomaly yang memerlukan remediation (write action):

1. Pastikan backup database sudah ada dan terverifikasi.
2. Catat scope remediation secara tertulis.
3. Siapkan rollback plan.
4. Dapatkan approval dari decision owner.
5. Jalankan remediation di transaction terkontrol.
6. Verifikasi hasil remediation.
7. Simpan log remediation.

## 10. Anomaly Triage

### Low Risk

- 1–2 session `in_progress` setelah ujian selesai (kemungkinan siswa disconnect).
- Sedikit timestamp anomaly tidak signifikan.
- `abandoned` count wajar.

Tindakan: catat, tidak perlu remediasi.

### Needs Manual Review

- Terminal session (`submitted`/`completed`) tapi `score` NULL (grading belum jalan).
- Terminal session (`submitted`/`completed`) tapi answer_count = 0.
- Banyak session `in_progress` setelah ujian selesai.
- Jawaban setelah `end_time`.

Tindakan: catat, investigasi, eskalasi ke backend reviewer.

### High Risk / Data Safety

- Banyak final submit hilang/tidak tercatat.
- Banyak jawaban hilang untuk terminal session (`submitted`/`completed`).
- Score tidak terhitung untuk sebagian besar session.
- Data integrity constraint violation.
- Synthetic residue di production data.

Tindakan: stop semua action, backup dulu, eskalasi ke decision owner.

## 11. Remediation Rule

Tidak ada write action tanpa:

1. Backup database sudah ada dan terverifikasi.
2. Approval dari decision owner.
3. Rollback plan tertulis.
4. Scope remediation jelas.
5. Test remediation di staging jika memungkinkan.

Contoh remediation yang butuh approval:

- Update session status stuck.
- Regenerate grading.
- Cleanup synthetic residue.
- Fix timestamp anomaly.

## 12. Output Report Format

Gunakan template `docs/post-exam-audit-report-template.md`.

Report harus memuat:

- Total peserta.
- Session status distribution.
- Answer completeness.
- Final submit anomalies.
- Grading completeness.
- Cheating/violation aggregate.
- Synthetic residue status.
- Data safety concern (yes/no).
- Recommended action.
- Follow-up Phase 4.

## 13. Handoff to Phase 4

Anomaly performance dan bottleneck yang ditemukan selama audit harus dicatat untuk Phase 4:

- Slow query / timeout.
- DB connection pressure pattern.
- API latency pattern.
- Dashboard performance issue.
- Redis queue/backlog pattern.
- Nginx error pattern.

Phase 3 berfokus pada data safety. Phase 4 berfokus pada performance bottleneck fix.

## 14. Operational Decision Phase 3

GO:

- Audit dilakukan setelah ujian selesai / safe window.
- Audit pertama read-only.
- Backup sebelum remediation.
- Report anomaly dibuat.
- Data safety lebih penting daripada export cepat.

NO-GO:

- Write/delete/update data siswa tanpa approval.
- Migration production.
- Cleanup real data.
- Manual session/result modification tanpa backup dan prosedur.
- Export jawaban mentah/PII ke luar sistem.
- Load test production.
- Build APK.
- Hybrid/queue/runtime buffer.
