-- 1. Exam Results Summary
CREATE MATERIALIZED VIEW IF NOT EXISTS exam_results_summary AS
SELECT 
    e.id as exam_id,
    e.title as exam_title,
    e.subject,
    e.creator_id,
    COUNT(es.id) as total_sessions,
    COUNT(DISTINCT es.user_id) as total_participants,
    ROUND(AVG(es.score), 2) as avg_score,
    MAX(es.score) as highest_score,
    MIN(es.score) as lowest_score,
    COUNT(CASE WHEN es.score >= COALESCE(e.passing_score, 0) THEN 1 END) as passed_count,
    NOW() as last_updated
FROM exams e
JOIN exam_sessions es ON e.id = es.exam_id
WHERE es.status IN ('completed', 'submitted')
GROUP BY e.id, e.title, e.subject, e.creator_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_exam_results_summary_id ON exam_results_summary (exam_id);

-- 2. Class Exam Performance
CREATE MATERIALIZED VIEW IF NOT EXISTS class_exam_performance AS
SELECT 
    u.student_class as class_name,
    e.id as exam_id,
    e.title as exam_title,
    COUNT(DISTINCT es.user_id) as total_students,
    ROUND(AVG(es.score), 2) as avg_score,
    MAX(es.score) as highest_score,
    MIN(es.score) as lowest_score,
    COUNT(CASE WHEN es.score >= COALESCE(e.passing_score, 0) THEN 1 END) as passed_count,
    NOW() as last_updated
FROM exam_sessions es
JOIN users u ON es.user_id = u.id
JOIN exams e ON es.exam_id = e.id
WHERE es.status IN ('completed', 'submitted') 
  AND u.student_class IS NOT NULL
GROUP BY u.student_class, e.id, e.title;

CREATE UNIQUE INDEX IF NOT EXISTS idx_class_exam_perf_class_exam ON class_exam_performance (class_name, exam_id);
