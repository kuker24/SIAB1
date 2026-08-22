package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type AnswerRow struct {
	QuestionID        int
	SelectedOptionID  *int
	SelectedOptionIDs []int32
	AnswerText        *string
	Metadata          []byte
	IsCorrect         *bool
	Points            *float64
	AnsweredAt        *time.Time
}

func (s *Store) HasPool() bool {
	return s != nil && s.pool != nil
}

func (s *Store) SessionOwned(ctx context.Context, sessionID, userID int) (status string, ok bool, err error) {
	if !s.HasPool() {
		return "", false, fmt.Errorf("no pgx pool")
	}
	err = s.pool.QueryRow(ctx, `
SELECT status FROM exam_sessions
 WHERE id = $1 AND user_id = $2`, sessionID, userID).Scan(&status)
	if err == pgx.ErrNoRows {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	return status, true, nil
}

func (s *Store) UpsertAnswer(ctx context.Context, sessionID int, row AnswerRow) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	meta := row.Metadata
	if len(meta) == 0 {
		meta = []byte("{}")
	}
	_, err := s.pool.Exec(ctx, `
INSERT INTO answers (
  session_id, question_id, selected_option_id, selected_option_ids,
  answer_text, answer_metadata, answered_at
) VALUES ($1,$2,$3,$4,$5,$6::jsonb,NOW())
ON CONFLICT (session_id, question_id) DO UPDATE SET
  selected_option_id = EXCLUDED.selected_option_id,
  selected_option_ids = EXCLUDED.selected_option_ids,
  answer_text = EXCLUDED.answer_text,
  answer_metadata = EXCLUDED.answer_metadata,
  answered_at = NOW()`,
		sessionID, row.QuestionID, row.SelectedOptionID, row.SelectedOptionIDs,
		row.AnswerText, string(meta))
	return err
}

func (s *Store) ListAnswers(ctx context.Context, sessionID int) ([]AnswerRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT question_id, selected_option_id, selected_option_ids, answer_text, answer_metadata,
       is_correct, points_earned, answered_at
  FROM answers WHERE session_id = $1`, sessionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []AnswerRow
	for rows.Next() {
		var row AnswerRow
		var meta []byte
		if err := rows.Scan(
			&row.QuestionID, &row.SelectedOptionID, &row.SelectedOptionIDs,
			&row.AnswerText, &meta, &row.IsCorrect, &row.Points, &row.AnsweredAt,
		); err != nil {
			return nil, err
		}
		row.Metadata = meta
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) CountAnswers(ctx context.Context, sessionID int) (int, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM answers WHERE session_id = $1`, sessionID).Scan(&n)
	return n, err
}

func (s *Store) CountQuestions(ctx context.Context, examID int) (int, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM questions WHERE exam_id = $1`, examID).Scan(&n)
	return n, err
}

func (s *Store) LogViolation(ctx context.Context, sessionID int, eventType string, data []byte) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	if len(data) == 0 {
		data = []byte("{}")
	}
	_, err := s.pool.Exec(ctx, `
INSERT INTO exam_logs (session_id, event_type, event_data, created_at)
VALUES ($1, $2, $3::jsonb, NOW())`, sessionID, eventType, string(data))
	return err
}

func (s *Store) AddViolation(ctx context.Context, sessionID, userID, delta int) (count int, examID int, status string, err error) {
	if !s.HasPool() {
		return 0, 0, "", fmt.Errorf("no pgx pool")
	}
	err = s.pool.QueryRow(ctx, `
UPDATE exam_sessions
   SET violation_count = COALESCE(violation_count, 0) + $1
 WHERE id = $2 AND user_id = $3
   AND status IN ('in_progress', 'active', 'paused')
RETURNING violation_count, exam_id, status`, delta, sessionID, userID).Scan(&count, &examID, &status)
	if err == pgx.ErrNoRows {
		return 0, 0, "", nil
	}
	return count, examID, status, err
}

func MetadataJSON(v any) []byte {
	if v == nil {
		return []byte("{}")
	}
	b, err := json.Marshal(v)
	if err != nil {
		return []byte("{}")
	}
	return b
}

func IntPtr(v int) *int { return &v }

func StrPtr(v string) *string { return &v }
