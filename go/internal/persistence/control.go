package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type ControlSession struct {
	SessionID  int
	UserID     int
	ExamID     int
	CreatorID  int
	Status     string
	Terminated bool
	Violations int
	UserName   string
	Username   string
	Class      *string
	ExamTitle  string
	Published  bool
	Deleted    bool
	ExamEnd    time.Time
	StartTime  *time.Time
	EndTime    *time.Time
	Score      *float64
}

type SessionLog struct {
	EventType string
	Data      []byte
	CreatedAt time.Time
}

func (s *Store) GetControlSession(ctx context.Context, sessionID int) (*ControlSession, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row ControlSession
	err := s.pool.QueryRow(ctx, `
SELECT es.id, es.user_id, es.exam_id, e.creator_id, COALESCE(es.status, ''),
       COALESCE(es.terminated_by_admin, false), COALESCE(es.violation_count, 0),
       COALESCE(u.full_name, u.username, ''), COALESCE(u.username, ''), u.student_class,
       e.title, COALESCE(e.is_published, false), COALESCE(e.is_deleted, false),
       e.end_time, es.start_time, es.end_time, es.score
  FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id
  JOIN users u ON u.id = es.user_id
 WHERE es.id = $1`, sessionID).Scan(
		&row.SessionID, &row.UserID, &row.ExamID, &row.CreatorID, &row.Status,
		&row.Terminated, &row.Violations, &row.UserName, &row.Username, &row.Class,
		&row.ExamTitle, &row.Published, &row.Deleted, &row.ExamEnd, &row.StartTime, &row.EndTime, &row.Score,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) ProbeSubmitAny(ctx context.Context, sessionID int) (*SubmitProbe, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var p SubmitProbe
	err := s.pool.QueryRow(ctx, `
SELECT es.id, es.exam_id, es.status, es.score,
       COALESCE(e.show_results, true), e.passing_score
  FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id
 WHERE es.id = $1`, sessionID).Scan(
		&p.SessionID, &p.ExamID, &p.Status, &p.Score, &p.ShowResults, &p.PassingScore,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &p, nil
}

func (s *Store) SetEmergencyExit(ctx context.Context, sessionID int, allowed bool) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	_, err := s.pool.Exec(ctx, `
UPDATE exam_sessions SET emergency_exit_allowed = $2 WHERE id = $1`, sessionID, allowed)
	return err
}

func (s *Store) KickSession(ctx context.Context, sessionID int) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	_, err := s.pool.Exec(ctx, `
UPDATE exam_sessions SET
  status = 'terminated',
  terminated_by_admin = true,
  end_time = COALESCE(end_time, NOW()),
  violation_count = COALESCE(violation_count, 0) + 1
 WHERE id = $1`, sessionID)
	return err
}

func (s *Store) ResetSession(ctx context.Context, sessionID int, resetViolations bool) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	q := `
UPDATE exam_sessions SET
  status = 'in_progress',
  end_time = NULL,
  score = NULL,
  terminated_by_admin = false,
  emergency_exit_allowed = false,
  is_paused = false,
  paused_at = NULL`
	if resetViolations {
		q += `,
  violation_count = 0,
  total_paused_seconds = 0`
	}
	q += ` WHERE id = $1`
	_, err := s.pool.Exec(ctx, q, sessionID)
	return err
}

func (s *Store) CleanupExamSessions(ctx context.Context, examID int) (cleaned, saved int, err error) {
	if !s.HasPool() {
		return 0, 0, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, 0, err
	}
	defer tx.Rollback(ctx)
	if err := tx.QueryRow(ctx, `
SELECT COUNT(*) FROM exam_sessions
 WHERE exam_id = $1 AND status IN ('submitted', 'completed')`, examID).Scan(&saved); err != nil {
		return 0, 0, err
	}
	rows, err := tx.Query(ctx, `
SELECT id FROM exam_sessions
 WHERE exam_id = $1 AND status = 'in_progress'
 FOR UPDATE`, examID)
	if err != nil {
		return 0, 0, err
	}
	var sessionIDs []int
	for rows.Next() {
		var sessionID int
		if err := rows.Scan(&sessionID); err != nil {
			rows.Close()
			return 0, 0, err
		}
		sessionIDs = append(sessionIDs, sessionID)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, 0, err
	}
	if len(sessionIDs) == 0 {
		if err := tx.Commit(ctx); err != nil {
			return 0, 0, err
		}
		return 0, saved, nil
	}
	// Preserve security audit rows while allowing their temporary session to be removed.
	if _, err := tx.Exec(ctx, `
UPDATE security_events SET session_id = NULL
 WHERE session_id = ANY($1)`, sessionIDs); err != nil {
		return 0, 0, err
	}
	result, err := tx.Exec(ctx, `
DELETE FROM exam_sessions WHERE id = ANY($1)`, sessionIDs)
	if err != nil {
		return 0, 0, err
	}
	cleaned = int(result.RowsAffected())
	if err := tx.Commit(ctx); err != nil {
		return 0, 0, err
	}
	return cleaned, saved, nil
}

func (s *Store) ListSessionLogs(ctx context.Context, sessionID, limit int) ([]SessionLog, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if limit <= 0 {
		limit = 30
	}
	rows, err := s.pool.Query(ctx, `
SELECT event_type, COALESCE(event_data, '{}'::jsonb), created_at
  FROM exam_logs WHERE session_id = $1
 ORDER BY created_at DESC, id DESC LIMIT $2`, sessionID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []SessionLog
	for rows.Next() {
		var row SessionLog
		if err := rows.Scan(&row.EventType, &row.Data, &row.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) ListRecoverySessions(ctx context.Context, examID, limit int) ([]ControlSession, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if limit < 50 {
		limit = 50
	}
	if limit > 1000 {
		limit = 1000
	}
	rows, err := s.pool.Query(ctx, `
SELECT es.id, es.user_id, es.exam_id, e.creator_id, COALESCE(es.status, ''),
       COALESCE(es.terminated_by_admin, false), COALESCE(es.violation_count, 0),
       COALESCE(u.full_name, u.username, ''), COALESCE(u.username, ''), u.student_class,
       e.title, COALESCE(e.is_published, false), COALESCE(e.is_deleted, false),
       e.end_time, es.start_time, es.end_time, es.score
  FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id
  JOIN users u ON u.id = es.user_id
 WHERE es.exam_id = $1
   AND es.status IN ('submitted', 'completed', 'terminated', 'kicked', 'abandoned')
 ORDER BY es.start_time DESC NULLS LAST, es.id DESC
 LIMIT $2`, examID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ControlSession
	for rows.Next() {
		var row ControlSession
		if err := rows.Scan(&row.SessionID, &row.UserID, &row.ExamID, &row.CreatorID, &row.Status,
			&row.Terminated, &row.Violations, &row.UserName, &row.Username, &row.Class,
			&row.ExamTitle, &row.Published, &row.Deleted, &row.ExamEnd, &row.StartTime, &row.EndTime, &row.Score); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) ListSessionLogsBulk(ctx context.Context, sessionIDs []int) (map[int][]SessionLog, error) {
	out := map[int][]SessionLog{}
	if !s.HasPool() || len(sessionIDs) == 0 {
		return out, nil
	}
	rows, err := s.pool.Query(ctx, `
SELECT session_id, event_type, COALESCE(event_data, '{}'::jsonb), created_at
  FROM exam_logs
 WHERE session_id = ANY($1)
   AND event_type IN (
     'EXAM_SUBMIT','EXAM_SUBMITTED','AUTO_SUBMIT_VIOLATION','FORCE_SUBMIT_BY_TEACHER',
     'SESSION_TERMINATED','SESSION_FORCE_KICK','ADMIN_KICK_STUDENT','SESSION_MANUAL_RESET',
     'SESSION_RESET_BLOCKED','SESSION_REOPENED_BY_ADMIN','SESSION_ADMIN_OVERRIDE_REOPEN'
   )
 ORDER BY created_at DESC, id DESC`, sessionIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	seen := map[int]int{}
	for rows.Next() {
		var sid int
		var row SessionLog
		if err := rows.Scan(&sid, &row.EventType, &row.Data, &row.CreatedAt); err != nil {
			return nil, err
		}
		if seen[sid] >= 20 {
			continue
		}
		out[sid] = append(out[sid], row)
		seen[sid]++
	}
	return out, rows.Err()
}
