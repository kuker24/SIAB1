package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type ResultSession struct {
	SessionID  int
	UserID     int
	StartTime  *time.Time
	EndTime    *time.Time
	Score      *float64
	Violations int
	Status     string
	FullName   string
	Username   string
	Class      *string
}

type AnswerScore struct {
	SessionID  int
	QuestionID int
	IsCorrect  *bool
	Points     *float64
}

type SessionUser struct {
	SessionID int
	UserID    int
	Status    string
	StartTime *time.Time
	EndTime   *time.Time
	Username  string
	FullName  string
	Class     *string
}

type TargetStudent struct {
	ID       int
	Username string
	FullName string
	Class    *string
}

func (s *Store) ListResultSessions(ctx context.Context, examID int) ([]ResultSession, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT es.id, es.user_id, es.start_time, es.end_time, es.score,
       COALESCE(es.violation_count, 0), COALESCE(es.status, ''),
       COALESCE(u.full_name, u.username, ''), COALESCE(u.username, ''), u.student_class
  FROM exam_sessions es
  JOIN users u ON u.id = es.user_id
 WHERE es.exam_id = $1 AND es.status IN ('submitted', 'completed')
 ORDER BY es.end_time DESC NULLS LAST, es.id DESC`, examID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ResultSession
	for rows.Next() {
		var row ResultSession
		if err := rows.Scan(&row.SessionID, &row.UserID, &row.StartTime, &row.EndTime, &row.Score,
			&row.Violations, &row.Status, &row.FullName, &row.Username, &row.Class); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) ListAnswerScores(ctx context.Context, sessionIDs []int) ([]AnswerScore, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if len(sessionIDs) == 0 {
		return nil, nil
	}
	rows, err := s.pool.Query(ctx, `
SELECT session_id, question_id, is_correct, points_earned
  FROM answers WHERE session_id = ANY($1)`, sessionIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []AnswerScore
	for rows.Next() {
		var row AnswerScore
		if err := rows.Scan(&row.SessionID, &row.QuestionID, &row.IsCorrect, &row.Points); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) ListExamSessionUsers(ctx context.Context, examID int) ([]SessionUser, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT es.id, es.user_id, COALESCE(es.status, ''), es.start_time, es.end_time,
       COALESCE(u.username, ''), COALESCE(u.full_name, u.username, ''), u.student_class
  FROM exam_sessions es
  JOIN users u ON u.id = es.user_id
 WHERE es.exam_id = $1
 ORDER BY es.start_time DESC NULLS LAST, es.id DESC`, examID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []SessionUser
	for rows.Next() {
		var row SessionUser
		if err := rows.Scan(&row.SessionID, &row.UserID, &row.Status, &row.StartTime, &row.EndTime,
			&row.Username, &row.FullName, &row.Class); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) ListTargetStudents(ctx context.Context, classes, studentIDs []string) ([]TargetStudent, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	q := `
SELECT id, username, COALESCE(full_name, username, ''), student_class
  FROM users
 WHERE role = 'student' AND COALESCE(is_active, true) = true`
	args := []any{}
	if len(classes) > 0 || len(studentIDs) > 0 {
		q += ` AND (false`
		if len(classes) > 0 {
			args = append(args, classes)
			q += fmt.Sprintf(` OR student_class = ANY($%d)`, len(args))
		}
		if len(studentIDs) > 0 {
			args = append(args, studentIDs)
			q += fmt.Sprintf(` OR id::text = ANY($%d)`, len(args))
		}
		q += `)`
	}
	q += ` ORDER BY student_class ASC, full_name ASC, username ASC`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []TargetStudent
	for rows.Next() {
		var row TargetStudent
		if err := rows.Scan(&row.ID, &row.Username, &row.FullName, &row.Class); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) ListExamsWithResults(ctx context.Context, creatorID int) ([]ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	q := examSelect + `
 WHERE COALESCE(e.is_deleted, false) = false
   AND COALESCE(e.is_published, false) = true
   AND (
     (e.end_time < NOW() AND COALESCE(e.has_ever_had_results, false) = false)
     OR e.id IN (
       SELECT DISTINCT exam_id FROM exam_sessions WHERE status IN ('submitted', 'completed')
     )
   )`
	args := []any{}
	if creatorID > 0 {
		q += ` AND e.creator_id = $1`
		args = append(args, creatorID)
	}
	q += ` ORDER BY e.created_at DESC`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ExamRow
	for rows.Next() {
		var e ExamRow
		if err := rows.Scan(examScan(&e)...); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

func IgnoreNoRows(err error) error {
	if err == pgx.ErrNoRows {
		return nil
	}
	return err
}
