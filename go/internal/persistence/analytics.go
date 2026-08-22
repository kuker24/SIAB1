package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type ExamAnalyticsRow struct {
	TotalParticipants int
	ActiveSessions    int
	CompletedSessions int
	ScoredSessions    int
	AverageScore      *float64
	HighestScore      *float64
	LowestScore       *float64
	PassedSessions    int
	Score0To20        int
	Score21To40       int
	Score41To60       int
	Score61To80       int
	Score81To100      int
	TotalViolations   int
}

type ExamClassRow struct {
	ClassName    string
	Participants int
}

type QuestionDifficultyRow struct {
	QuestionID     int
	OrderIndex     int
	QuestionText   string
	QuestionType   string
	TotalAnswers   int
	CorrectAnswers int
}

type AnalyticsDashboardRow struct {
	TotalSessions          int
	AverageScore           *float64
	TotalViolations        int
	SessionsWithViolations int
	ByDay                  []ActivityCount
}

type ClassPerformanceRow struct {
	TotalStudents int
	TotalSessions int
	AverageScore  *float64
	HighestScore  *float64
	LowestScore   *float64
	PassedCount   int
	GradedCount   int
	TopPerformers []ClassPerformerRow
}

type ClassPerformerRow struct {
	StudentID    int
	Name         string
	AverageScore float64
	ExamsTaken   int
}

type AssessmentParticipantRow struct {
	SessionID   int
	UserID      int
	Name        string
	ClassName   string
	Score       float64
	SubmittedAt *time.Time
}

func (s *Store) ExamAnalytics(ctx context.Context, examID int, passingThreshold float64) (*ExamAnalyticsRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row ExamAnalyticsRow
	err := s.pool.QueryRow(ctx, `
SELECT COUNT(*),
       COUNT(*) FILTER (WHERE status = 'in_progress'),
       COUNT(*) FILTER (WHERE status IN ('completed', 'submitted')),
       COUNT(*) FILTER (WHERE status IN ('completed', 'submitted') AND score IS NOT NULL),
       AVG(score) FILTER (WHERE status IN ('completed', 'submitted') AND score IS NOT NULL),
       MAX(score) FILTER (WHERE status IN ('completed', 'submitted') AND score IS NOT NULL),
       MIN(score) FILTER (WHERE status IN ('completed', 'submitted') AND score IS NOT NULL),
       COUNT(*) FILTER (WHERE status IN ('completed', 'submitted') AND score IS NOT NULL AND score >= $2),
       COUNT(*) FILTER (WHERE status IN ('completed', 'submitted') AND score IS NOT NULL AND score <= 20),
       COUNT(*) FILTER (WHERE status IN ('completed', 'submitted') AND score > 20 AND score <= 40),
       COUNT(*) FILTER (WHERE status IN ('completed', 'submitted') AND score > 40 AND score <= 60),
       COUNT(*) FILTER (WHERE status IN ('completed', 'submitted') AND score > 60 AND score <= 80),
       COUNT(*) FILTER (WHERE status IN ('completed', 'submitted') AND score > 80),
       COALESCE(SUM(violation_count), 0)
  FROM exam_sessions
 WHERE exam_id = $1`, examID, passingThreshold).Scan(
		&row.TotalParticipants, &row.ActiveSessions, &row.CompletedSessions,
		&row.ScoredSessions, &row.AverageScore, &row.HighestScore, &row.LowestScore,
		&row.PassedSessions, &row.Score0To20, &row.Score21To40, &row.Score41To60,
		&row.Score61To80, &row.Score81To100, &row.TotalViolations,
	)
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) ExamClasses(ctx context.Context, examID int) ([]ExamClassRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT TRIM(u.student_class), COUNT(DISTINCT es.user_id)
  FROM exam_sessions es
  JOIN users u ON u.id = es.user_id
 WHERE es.exam_id = $1
   AND es.status IN ('completed', 'submitted')
   AND u.role IN ('student', 'guruplus')
   AND u.is_active = true
   AND COALESCE(TRIM(u.student_class), '') <> ''
 GROUP BY TRIM(u.student_class)
 ORDER BY TRIM(u.student_class)`, examID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []ExamClassRow{}
	for rows.Next() {
		var row ExamClassRow
		if err := rows.Scan(&row.ClassName, &row.Participants); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) QuestionDifficulty(ctx context.Context, examID int) ([]QuestionDifficultyRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT q.id, COALESCE(q.order_index, 0), q.question_text, q.question_type,
       COUNT(a.id) FILTER (WHERE es.status IN ('completed', 'submitted')),
       COUNT(a.id) FILTER (
         WHERE es.status IN ('completed', 'submitted') AND a.is_correct IS TRUE
       )
  FROM questions q
  LEFT JOIN answers a ON a.question_id = q.id
  LEFT JOIN exam_sessions es ON es.id = a.session_id
 WHERE q.exam_id = $1
 GROUP BY q.id, q.order_index, q.question_text, q.question_type
 ORDER BY q.order_index, q.id`, examID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []QuestionDifficultyRow{}
	for rows.Next() {
		var row QuestionDifficultyRow
		if err := rows.Scan(
			&row.QuestionID, &row.OrderIndex, &row.QuestionText, &row.QuestionType,
			&row.TotalAnswers, &row.CorrectAnswers,
		); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) AnalyticsDashboard(ctx context.Context, since time.Time, ownerID int, hideDeveloper bool) (*AnalyticsDashboardRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	extra := ""
	args := []any{since}
	if ownerID > 0 {
		args = append(args, ownerID)
		extra += fmt.Sprintf(" AND e.creator_id = $%d", len(args))
	}
	if hideDeveloper {
		extra += " AND COALESCE(c.role, '') <> 'developer'"
	}
	base := ` FROM exam_sessions es JOIN exams e ON e.id=es.exam_id
 LEFT JOIN users c ON c.id=e.creator_id
 WHERE COALESCE(e.is_deleted,false)=false
 AND es.status IN ('completed','submitted') AND es.end_time >= $1` + extra
	var out AnalyticsDashboardRow
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*), AVG(es.score),
 COALESCE(SUM(es.violation_count),0), COUNT(*) FILTER (WHERE COALESCE(es.violation_count,0)>0)`+base,
		args...).Scan(&out.TotalSessions, &out.AverageScore, &out.TotalViolations, &out.SessionsWithViolations); err != nil {
		return nil, err
	}
	rows, err := s.pool.Query(ctx, `SELECT TO_CHAR(timezone('Asia/Jakarta', es.end_time),'YYYY-MM-DD'), COUNT(*)`+
		base+` GROUP BY 1 ORDER BY 1`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var item ActivityCount
		if err := rows.Scan(&item.Name, &item.Count); err != nil {
			return nil, err
		}
		out.ByDay = append(out.ByDay, item)
	}
	return &out, rows.Err()
}

func (s *Store) ClassPerformance(ctx context.Context, className string, examID, ownerID int, hideDeveloper bool) (*ClassPerformanceRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var out ClassPerformanceRow
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM users
 WHERE lower(trim(student_class))=lower($1) AND role IN ('student','guruplus') AND is_active=true`, className).Scan(&out.TotalStudents); err != nil {
		return nil, err
	}
	if out.TotalStudents == 0 {
		return &out, nil
	}
	args := []any{className}
	extra := ""
	if examID > 0 {
		args = append(args, examID)
		extra += fmt.Sprintf(" AND es.exam_id=$%d", len(args))
	} else if ownerID > 0 {
		args = append(args, ownerID)
		extra += fmt.Sprintf(" AND e.creator_id=$%d", len(args))
	}
	if hideDeveloper {
		extra += " AND COALESCE(c.role,'') <> 'developer'"
	}
	base := ` FROM exam_sessions es JOIN users u ON u.id=es.user_id
 JOIN exams e ON e.id=es.exam_id LEFT JOIN users c ON c.id=e.creator_id
 WHERE lower(trim(u.student_class))=lower($1) AND u.role IN ('student','guruplus')
 AND u.is_active=true AND COALESCE(e.is_deleted,false)=false
 AND es.status IN ('completed','submitted')` + extra
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*),AVG(es.score),MAX(es.score),MIN(es.score),
 COALESCE(SUM(CASE WHEN es.score IS NOT NULL AND es.score>=COALESCE(e.passing_score,70) THEN 1 ELSE 0 END),0),
 COUNT(*) FILTER (WHERE es.score IS NOT NULL)`+base, args...).Scan(
		&out.TotalSessions, &out.AverageScore, &out.HighestScore, &out.LowestScore,
		&out.PassedCount, &out.GradedCount); err != nil {
		return nil, err
	}
	rows, err := s.pool.Query(ctx, `SELECT es.user_id,COALESCE(u.full_name,'-'),AVG(es.score),COUNT(*)`+
		base+` AND es.score IS NOT NULL GROUP BY es.user_id,u.full_name
 ORDER BY AVG(es.score) DESC,u.full_name ASC LIMIT 10`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var item ClassPerformerRow
		if err := rows.Scan(&item.StudentID, &item.Name, &item.AverageScore, &item.ExamsTaken); err != nil {
			return nil, err
		}
		out.TopPerformers = append(out.TopPerformers, item)
	}
	return &out, rows.Err()
}

func (s *Store) AssessmentParticipants(ctx context.Context, examID int, classes []string) ([]AssessmentParticipantRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT session_id,user_id,name,student_class,score,end_time FROM (
  SELECT DISTINCT ON (es.user_id) es.id AS session_id,es.user_id,
         COALESCE(u.full_name,u.username,'Peserta') AS name,
         COALESCE(u.student_class,$3) AS student_class,es.score,es.end_time
    FROM exam_sessions es JOIN users u ON u.id=es.user_id
   WHERE es.exam_id=$1 AND es.status IN ('completed','submitted')
     AND u.role IN ('student','guruplus')
     AND lower(trim(u.student_class))=ANY($2)
   ORDER BY es.user_id,(es.score IS NOT NULL) DESC,es.end_time DESC NULLS LAST,es.id DESC
) selected WHERE score IS NOT NULL
ORDER BY score DESC,name`, examID, lowerStrings(classes), classes[0])
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []AssessmentParticipantRow{}
	for rows.Next() {
		var row AssessmentParticipantRow
		if err := rows.Scan(&row.SessionID, &row.UserID, &row.Name, &row.ClassName, &row.Score, &row.SubmittedAt); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func lowerStrings(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		out = append(out, strings.ToLower(strings.TrimSpace(value)))
	}
	return out
}
