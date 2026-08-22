package persistence

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
)

const sessionWriteLockNS = 48102

func (s *Store) ProbeSubmit(ctx context.Context, sessionID, userID int) (*SubmitProbe, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var p SubmitProbe
	err := s.pool.QueryRow(ctx, `
SELECT es.id, es.exam_id, es.status, es.score,
       COALESCE(e.show_results, true), e.passing_score
  FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id
 WHERE es.id = $1 AND es.user_id = $2`, sessionID, userID).Scan(
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

func (s *Store) BeginSubmit(ctx context.Context, sessionID int) (pgx.Tx, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1, $2)`, sessionWriteLockNS, sessionID); err != nil {
		_ = tx.Rollback(ctx)
		return nil, err
	}
	return tx, nil
}

func ProbeSubmitTx(ctx context.Context, tx pgx.Tx, sessionID, userID int) (*SubmitProbe, error) {
	var p SubmitProbe
	err := tx.QueryRow(ctx, `
SELECT es.id, es.exam_id, es.status, es.score,
       COALESCE(e.show_results, true), e.passing_score
  FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id
 WHERE es.id = $1 AND es.user_id = $2`, sessionID, userID).Scan(
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

func UpdateAnswerScore(ctx context.Context, tx pgx.Tx, sessionID, questionID int, correct *bool, points *float64) error {
	_, err := tx.Exec(ctx, `
UPDATE answers SET is_correct = $1, points_earned = $2
 WHERE session_id = $3 AND question_id = $4`,
		correct, points, sessionID, questionID)
	return err
}

func MarkSessionSubmitted(ctx context.Context, tx pgx.Tx, sessionID, examID int, score float64) error {
	if _, err := tx.Exec(ctx, `
UPDATE exam_sessions
   SET status = 'submitted', end_time = NOW(), score = $1
 WHERE id = $2`, score, sessionID); err != nil {
		return err
	}
	_, err := tx.Exec(ctx, `
UPDATE exams SET has_ever_had_results = true
 WHERE id = $1 AND COALESCE(has_ever_had_results, false) = false`, examID)
	return err
}
