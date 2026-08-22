# Post-Exam Read-Only SQL Checklist

Query SELECT-only untuk audit pasca-ujian. Sesuaikan nama tabel/kolom dengan schema aktual. Jangan jalankan query berat saat production masih aktif.

## Prasyarat

- Ujian sudah selesai atau safe window disetujui.
- Koneksi database read-only.
- Tidak ada INSERT/UPDATE/DELETE/DROP/TRUNCATE.
- Parameter `:exam_id` harus diganti dengan ID ujian aktual.
- Jangan export jawaban siswa mentah.
- Jangan share PII/answer content di chat.

## Schema Reference (Actual)

Tabel dan kolom aktual dari SQLAlchemy models:

```text
exam_sessions
├── id, user_id, exam_id
├── start_time, end_time
├── status (in_progress, completed, submitted, abandoned)
├── score, violation_count
├── emergency_exit_allowed, terminated_by_admin
├── is_paused, paused_at, total_paused_seconds
├── seb_detected, is_secure_app_verified
├── archived_exam_title, archived_exam_subject
└── ip_address, user_agent

answers
├── id, session_id, question_id
├── selected_option_id (single choice)
├── selected_option_ids (array, multiple choice complex)
├── answer_text (essay/short answer)
├── is_correct, points_earned
├── answer_metadata (jsonb)
└── answered_at

exam_logs
├── id, session_id
├── event_type, event_data (jsonb)
└── created_at

users
├── id, username, password_hash, full_name
├── role (developer, admin, teacher, student, guruplus)
├── student_class, job_title
├── is_active, last_login
└── created_at, profile_picture

exams
├── id, title, description, creator_id
├── duration_minutes, start_time, end_time
├── passing_score, max_attempts
├── shuffle_questions, shuffle_options
├── show_results, allow_review
├── is_published, access_token
├── subject, exam_type, academic_year
├── is_globally_paused, globally_paused_at, globally_paused_by
├── is_deleted, deleted_at, has_ever_had_results
└── created_at, updated_at

questions
├── id, exam_id, question_text, stimulus
├── question_type, question_subtype, pgk_type
├── difficulty_level, points, order_index
├── image_url, video_url, audio_url
└── question_settings (jsonb)

question_options
├── id, question_id, option_text
├── is_correct, order_index
└── option_group, pair_id, option_metadata (jsonb)

security_events
├── id, event_type
├── user_id, session_id
├── ip_address, user_agent, endpoint, method
├── app_signature, app_version, expected_signature
├── extra_data (text/json), severity
└── timestamp

user_activity_logs
├── id, user_id, event_type
├── event_data (jsonb), ip_address
└── created_at
```

## Query 1: Session Status Distribution

```sql
SELECT
    status,
    COUNT(*) AS session_count
FROM exam_sessions
WHERE exam_id = :exam_id
GROUP BY status
ORDER BY session_count DESC;
```

Validasi: terminal status (`submitted` + `completed`) sesuai ekspektasi. `in_progress` = 0 setelah ujian selesai.

## Query 2: Terminal Count (Submitted + Completed)

```sql
SELECT COUNT(*) AS terminal_count
FROM exam_sessions
WHERE exam_id = :exam_id
  AND status IN ('submitted', 'completed');
```

## Query 3: In-Progress / Stuck Sessions

```sql
SELECT
    id,
    user_id,
    start_time,
    end_time,
    status,
    violation_count
FROM exam_sessions
WHERE exam_id = :exam_id
  AND status = 'in_progress'
ORDER BY start_time
LIMIT 50;
```

Jika ada setelah ujian selesai: anomaly, perlu catat.

## Query 4: Answer Count per Terminal Session (Bottom 50)

```sql
SELECT
    es.id AS session_id,
    es.user_id,
    es.status,
    COUNT(a.id) AS answer_count
FROM exam_sessions es
LEFT JOIN answers a ON a.session_id = es.id
WHERE es.exam_id = :exam_id
  AND es.status IN ('submitted', 'completed')
GROUP BY es.id, es.user_id, es.status
ORDER BY answer_count ASC
LIMIT 50;
```

Validasi: semua terminal session (`submitted`/`completed`) memiliki answer_count > 0.

## Query 5: Question Count per Exam

```sql
SELECT
    exam_id,
    COUNT(*) AS question_count
FROM questions
WHERE exam_id = :exam_id
GROUP BY exam_id;
```

## Query 6: Sessions with Zero Answers

```sql
SELECT
    es.id AS session_id,
    es.user_id,
    es.status,
    es.start_time,
    es.end_time,
    es.score
FROM exam_sessions es
LEFT JOIN answers a ON a.session_id = es.id
WHERE es.exam_id = :exam_id
  AND es.status IN ('submitted', 'completed')
  AND a.id IS NULL;
```

Jika ada: **high risk anomaly**. Perlu investigasi segera.

## Query 7: Duplicate Answer Rows

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
HAVING COUNT(*) > 1
LIMIT 50;
```

Seharusnya tidak ada karena constraint `uq_answers_session_question`. Jika ada: schema integrity issue.

## Query 8: Final Submit Timestamp Anomalies

```sql
SELECT
    es.id AS session_id,
    es.user_id,
    es.end_time AS session_end_time,
    MAX(a.answered_at) AS last_answer_time
FROM exam_sessions es
JOIN answers a ON a.session_id = es.id
WHERE es.exam_id = :exam_id
  AND es.status IN ('submitted', 'completed')
GROUP BY es.id, es.user_id, es.end_time
HAVING es.end_time IS NULL
    OR MAX(a.answered_at) > es.end_time + INTERVAL '5 minutes'
LIMIT 50;
```

## Query 9: Answers After Final Submit

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

Jika ada: timestamp anomaly, perlu review.

## Query 10: Terminal Sessions with Score NULL

```sql
SELECT
    id,
    user_id,
    status,
    score,
    end_time,
    violation_count
FROM exam_sessions
WHERE exam_id = :exam_id
  AND status IN ('submitted', 'completed')
  AND score IS NULL
LIMIT 50;
```

Jika ada: grading belum selesai, perlu follow-up.

## Query 11: Ungraded Answers per Session

```sql
SELECT
    es.id AS session_id,
    es.status,
    es.score,
    COUNT(CASE WHEN a.is_correct IS NULL THEN 1 END) AS ungraded_answers,
    COUNT(a.id) AS total_answers
FROM exam_sessions es
JOIN answers a ON a.session_id = es.id
WHERE es.exam_id = :exam_id
  AND es.status IN ('submitted', 'completed')
GROUP BY es.id, es.status, es.score
HAVING COUNT(CASE WHEN a.is_correct IS NULL THEN 1 END) > 0
LIMIT 50;
```

## Query 12: Violation/Event Aggregate from exam_logs

```sql
SELECT
    el.event_type,
    COUNT(*) AS event_count
FROM exam_logs el
JOIN exam_sessions es ON es.id = el.session_id
WHERE es.exam_id = :exam_id
GROUP BY el.event_type
ORDER BY event_count DESC
LIMIT 50;
```

## Query 13: Security Events Aggregate

```sql
SELECT
    se.event_type,
    se.severity,
    COUNT(*) AS event_count
FROM security_events se
JOIN exam_sessions es ON es.id = se.session_id
WHERE es.exam_id = :exam_id
GROUP BY se.event_type, se.severity
ORDER BY event_count DESC
LIMIT 50;
```

## Query 14: Violation Count Distribution

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

## Query 15: Synthetic/Test Residue

```sql
-- Synthetic users
SELECT id, username, role, student_class, is_active
FROM users
WHERE username LIKE '%synthetic%'
   OR username LIKE '%test_%'
   OR username LIKE '%loadtest%'
   OR username LIKE '%dummy%'
LIMIT 50;

-- Synthetic sessions
SELECT
    es.id,
    es.exam_id,
    es.status,
    u.username
FROM exam_sessions es
JOIN users u ON u.id = es.user_id
WHERE u.username LIKE '%synthetic%'
   OR u.username LIKE '%test_%'
   OR u.username LIKE '%loadtest%'
LIMIT 50;
```

## Query 16: Exam-Level Summary

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
    COUNT(DISTINCT CASE WHEN es.status = 'abandoned' THEN es.id END) AS abandoned_sessions,
    COUNT(DISTINCT a.id) AS total_answers,
    ROUND(AVG(es.score)::numeric, 2) AS avg_score,
    MIN(es.score) AS min_score,
    MAX(es.score) AS max_score
FROM exams e
LEFT JOIN exam_sessions es ON es.exam_id = e.id
LEFT JOIN answers a ON a.session_id = es.id
WHERE e.id = :exam_id
GROUP BY e.id, e.title, e.start_time, e.end_time, e.is_published, e.is_deleted, e.has_ever_had_results;
```

## Query 17: Score Distribution

```sql
SELECT
    CASE
        WHEN score >= 90 THEN 'A (>=90)'
        WHEN score >= 80 THEN 'B (80-89)'
        WHEN score >= 70 THEN 'C (70-79)'
        WHEN score >= 60 THEN 'D (60-69)'
        ELSE 'E (<60)'
    END AS grade_band,
    COUNT(*) AS student_count
FROM exam_sessions
WHERE exam_id = :exam_id
  AND status IN ('submitted', 'completed')
  AND score IS NOT NULL
GROUP BY grade_band
ORDER BY grade_band;
```

## Query 18: Answer Type Distribution

```sql
SELECT
    q.question_type,
    COUNT(DISTINCT q.id) AS question_count,
    COUNT(a.id) AS answer_count,
    COUNT(CASE WHEN a.is_correct = true THEN 1 END) AS correct_count,
    COUNT(CASE WHEN a.is_correct = false THEN 1 END) AS incorrect_count,
    COUNT(CASE WHEN a.is_correct IS NULL THEN 1 END) AS ungraded_count
FROM questions q
LEFT JOIN answers a ON a.question_id = q.id
WHERE q.exam_id = :exam_id
GROUP BY q.question_type
ORDER BY question_count DESC;
```

## Warnings

1. Sesuaikan nama tabel/kolom dengan schema aktual jika ada perubahan.
2. Jangan jalankan query berat saat production masih aktif.
3. Jangan export jawaban siswa mentah (answer_text, selected_option_id).
4. Jangan share PII/answer content di chat.
5. Gunakan LIMIT pada query detail.
6. Jalankan query aggregate/summary dulu sebelum detail.
7. Parameter `:exam_id` harus diganti dengan ID ujian aktual.
8. Query ini dirancang untuk PostgreSQL. Sesuaikan syntax jika menggunakan DB lain.
9. Query menggunakan constraint dan index yang ada di schema.
10. Tidak ada query write — semua SELECT-only.
