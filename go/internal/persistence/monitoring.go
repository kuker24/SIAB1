package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type MonitorSession struct {
	SessionID  int
	UserID     int
	FullName   string
	Username   string
	Class      *string
	StartTime  *time.Time
	Status     string
	Score      *float64
	Violations int
	IPAddress  *string
	Terminated bool
	Answered   int
}

type ActiveExamStat struct {
	ExamID          int
	Title           string
	StartTime       time.Time
	EndTime         time.Time
	DurationMinutes int
	TotalSessions   int
	InProgress      int
	Completed       int
	Violations      int
}

func (s *Store) ListMonitorSessions(ctx context.Context, examID int, status string) ([]MonitorSession, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	q := `
SELECT es.id, es.user_id, COALESCE(u.full_name, u.username, ''), COALESCE(u.username, ''),
       u.student_class, es.start_time, COALESCE(es.status, ''), es.score,
       COALESCE(es.violation_count, 0), es.ip_address, COALESCE(es.terminated_by_admin, false)
  FROM exam_sessions es
  JOIN users u ON u.id = es.user_id
 WHERE es.exam_id = $1`
	args := []any{examID}
	if status != "" {
		q += ` AND es.status = $2`
		args = append(args, status)
	}
	q += ` ORDER BY es.start_time DESC NULLS LAST, es.id DESC`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []MonitorSession
	ids := make([]int, 0)
	for rows.Next() {
		var row MonitorSession
		if err := rows.Scan(&row.SessionID, &row.UserID, &row.FullName, &row.Username, &row.Class,
			&row.StartTime, &row.Status, &row.Score, &row.Violations, &row.IPAddress, &row.Terminated); err != nil {
			return nil, err
		}
		out = append(out, row)
		ids = append(ids, row.SessionID)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	counts, err := s.AnswerCounts(ctx, ids)
	if err != nil {
		return nil, err
	}
	for i := range out {
		out[i].Answered = counts[out[i].SessionID]
	}
	return out, nil
}

func (s *Store) AnswerCounts(ctx context.Context, sessionIDs []int) (map[int]int, error) {
	out := map[int]int{}
	if !s.HasPool() || len(sessionIDs) == 0 {
		return out, nil
	}
	rows, err := s.pool.Query(ctx, `
SELECT session_id, COUNT(*) FROM answers WHERE session_id = ANY($1) GROUP BY session_id`, sessionIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var id, n int
		if err := rows.Scan(&id, &n); err != nil {
			return nil, err
		}
		out[id] = n
	}
	return out, rows.Err()
}

func (s *Store) ListActiveExams(ctx context.Context, creatorID int) ([]ActiveExamStat, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	q := `
SELECT e.id, e.title, e.start_time, e.end_time, e.duration_minutes,
       COALESCE(st.total_sessions, 0), COALESCE(st.in_progress_count, 0),
       COALESCE(st.completed_count, 0), COALESCE(st.total_violations, 0)
  FROM exams e
  LEFT JOIN (
    SELECT exam_id,
           COUNT(*) AS total_sessions,
           COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress_count,
           COUNT(*) FILTER (WHERE status IN ('submitted', 'completed')) AS completed_count,
           COALESCE(SUM(violation_count), 0) AS total_violations
      FROM exam_sessions
     GROUP BY exam_id
  ) st ON st.exam_id = e.id
 WHERE COALESCE(e.is_deleted, false) = false
   AND COALESCE(e.is_published, false) = true
   AND e.start_time <= NOW() AND e.end_time >= NOW()`
	args := []any{}
	if creatorID > 0 {
		q += ` AND e.creator_id = $1`
		args = append(args, creatorID)
	}
	q += ` ORDER BY e.start_time DESC`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ActiveExamStat
	for rows.Next() {
		var row ActiveExamStat
		if err := rows.Scan(&row.ExamID, &row.Title, &row.StartTime, &row.EndTime, &row.DurationMinutes,
			&row.TotalSessions, &row.InProgress, &row.Completed, &row.Violations); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) SetExamPaused(ctx context.Context, examID, userID int, paused bool) (affected int, pausedAt *time.Time, duration int, err error) {
	if !s.HasPool() {
		return 0, nil, 0, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, nil, 0, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var current bool
	var at *time.Time
	err = tx.QueryRow(ctx, `
SELECT COALESCE(is_globally_paused, false), globally_paused_at
  FROM exams WHERE id=$1 AND COALESCE(is_deleted,false)=false`, examID).Scan(&current, &at)
	if err == pgx.ErrNoRows {
		return 0, nil, 0, pgx.ErrNoRows
	}
	if err != nil {
		return 0, nil, 0, err
	}
	if paused && current {
		return 0, at, 0, ErrAlreadyPaused
	}
	if !paused && !current {
		return 0, nil, 0, ErrNotPaused
	}
	now := time.Now().UTC()
	if paused {
		_, err = tx.Exec(ctx, `
UPDATE exams SET is_globally_paused=true, globally_paused_at=$2, globally_paused_by=$3, updated_at=NOW()
 WHERE id=$1`, examID, now, userID)
		if err != nil {
			return 0, nil, 0, err
		}
		tag, err := tx.Exec(ctx, `
UPDATE exam_sessions SET is_paused=true, paused_at=$2
 WHERE exam_id=$1 AND status='in_progress'`, examID, now)
		if err != nil {
			return 0, nil, 0, err
		}
		if err := tx.Commit(ctx); err != nil {
			return 0, nil, 0, err
		}
		return int(tag.RowsAffected()), &now, 0, nil
	}
	if at != nil {
		duration = int(now.Sub(*at).Seconds())
		if duration < 0 {
			duration = 0
		}
	}
	_, err = tx.Exec(ctx, `
UPDATE exams SET is_globally_paused=false, globally_paused_at=NULL, updated_at=NOW()
 WHERE id=$1`, examID)
	if err != nil {
		return 0, nil, 0, err
	}
	tag, err := tx.Exec(ctx, `
UPDATE exam_sessions SET
  is_paused=false,
  total_paused_seconds = COALESCE(total_paused_seconds, 0) + $2,
  paused_at=NULL
 WHERE exam_id=$1 AND COALESCE(is_paused, false)=true`, examID, duration)
	if err != nil {
		return 0, nil, 0, err
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, nil, 0, err
	}
	return int(tag.RowsAffected()), nil, duration, nil
}

var (
	ErrAlreadyPaused = fmt.Errorf("already paused")
	ErrNotPaused     = fmt.Errorf("not paused")
)
