package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

type SubmitSessionRow struct {
	ID             int
	ExamID         int
	Status         string
	Score          *float64
	ViolationCount int
	EndTime        *time.Time
	ShowResults    bool
	PassingScore   *float64
}

type SubmitAnswerGrade struct {
	ID                int
	QuestionID        int
	SelectedOptionID  *int
	SelectedOptionIDs []int32
	AnswerText        *string
	Metadata          []byte
	IsCorrect         *bool
	Points            *float64
	AnsweredAt        *time.Time
}

type SubmitAnswerScore struct {
	QuestionID int
	IsCorrect  *bool
	Points     *float64
}

type SubmitGradeOutput struct {
	Percentage   float64
	TotalPoints  float64
	PointsEarned float64
	Breakdown    []map[string]any
	Scores       []SubmitAnswerScore
}

type SubmitGradeFunc func([]QuestionRow, []SubmitAnswerGrade) SubmitGradeOutput

type SubmitFinalizeResult struct {
	Status       string
	Row          SubmitSessionRow
	TotalPoints  float64
	PointsEarned float64
	Percentage   float64
	Breakdown    []map[string]any
}

func (s *Store) LoadSubmitSession(ctx context.Context, sessionID, userID int) (*SubmitSessionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row SubmitSessionRow
	err := s.pool.QueryRow(ctx, `
SELECT es.id, es.exam_id, es.status, es.score, COALESCE(es.violation_count, 0), es.end_time,
       COALESCE(e.show_results, true), e.passing_score
  FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id
 WHERE es.id = $1 AND es.user_id = $2`, sessionID, userID).Scan(
		&row.ID, &row.ExamID, &row.Status, &row.Score, &row.ViolationCount, &row.EndTime,
		&row.ShowResults, &row.PassingScore,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) FinalizeNativeSubmit(
	ctx context.Context,
	sessionID, userID int,
	forceSubmit bool,
	submittedAt time.Time,
	grade SubmitGradeFunc,
) (SubmitFinalizeResult, error) {
	result := SubmitFinalizeResult{}
	if !s.HasPool() {
		return result, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return result, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1, $2)`, sessionWriteLockNS, sessionID); err != nil {
		return result, err
	}
	var row SubmitSessionRow
	err = tx.QueryRow(ctx, `
SELECT es.id, es.exam_id, es.status, es.score, COALESCE(es.violation_count, 0), es.end_time,
       COALESCE(e.show_results, true), e.passing_score
  FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id
 WHERE es.id = $1 AND es.user_id = $2
 FOR UPDATE OF es`, sessionID, userID).Scan(
		&row.ID, &row.ExamID, &row.Status, &row.Score, &row.ViolationCount, &row.EndTime,
		&row.ShowResults, &row.PassingScore,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return SubmitFinalizeResult{Status: "not_found"}, nil
	}
	if err != nil {
		return result, err
	}
	status := strings.ToLower(strings.TrimSpace(row.Status))
	if status == "submitted" || status == "completed" {
		if err := tx.Commit(ctx); err != nil {
			return result, err
		}
		return SubmitFinalizeResult{Status: "already", Row: row}, nil
	}
	if status != "in_progress" {
		return SubmitFinalizeResult{Status: "ended", Row: row}, nil
	}
	questions, err := loadQuestionsTx(ctx, tx, row.ExamID)
	if err != nil {
		return result, err
	}
	answers, err := listSubmitAnswersTx(ctx, tx, sessionID)
	if err != nil {
		return result, err
	}
	graded := grade(questions, answers)
	for _, score := range graded.Scores {
		if _, err := tx.Exec(ctx, `
UPDATE answers SET is_correct = $1, points_earned = $2
 WHERE session_id = $3 AND question_id = $4`,
			score.IsCorrect, score.Points, sessionID, score.QuestionID,
		); err != nil {
			return result, err
		}
	}
	if _, err := tx.Exec(ctx, `
UPDATE exam_sessions
   SET status = 'submitted', end_time = $1, score = $2
 WHERE id = $3`, submittedAt, graded.Percentage, sessionID); err != nil {
		return result, err
	}
	if _, err := tx.Exec(ctx, `
UPDATE exams SET has_ever_had_results = true
 WHERE id = $1 AND COALESCE(has_ever_had_results, false) = false`, row.ExamID); err != nil {
		return result, err
	}
	recovery := "session_submitted"
	if forceSubmit {
		recovery = "cheating_detected"
	}
	submittedPayload, _ := json.Marshal(map[string]any{
		"force_submit":       forceSubmit,
		"recovery_category":  recovery,
		"score":              graded.Percentage,
		"violation_count":    row.ViolationCount,
	})
	breakdownPayload, _ := json.Marshal(map[string]any{"score_breakdown": graded.Breakdown})
	if _, err := tx.Exec(ctx, `
INSERT INTO exam_logs (session_id, event_type, event_data, created_at)
VALUES ($1, 'EXAM_SUBMITTED', $2::jsonb, $3)`, sessionID, string(submittedPayload), submittedAt); err != nil {
		return result, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO exam_logs (session_id, event_type, event_data, created_at)
VALUES ($1, 'SCORE_BREAKDOWN', $2::jsonb, $3)`, sessionID, string(breakdownPayload), submittedAt); err != nil {
		return result, err
	}
	if err := tx.Commit(ctx); err != nil {
		return result, err
	}
	row.Status = "submitted"
	score := graded.Percentage
	row.Score = &score
	row.EndTime = &submittedAt
	return SubmitFinalizeResult{
		Status:       "submitted",
		Row:          row,
		TotalPoints:  graded.TotalPoints,
		PointsEarned: graded.PointsEarned,
		Percentage:   graded.Percentage,
		Breakdown:    graded.Breakdown,
	}, nil
}

func loadQuestionsTx(ctx context.Context, tx pgx.Tx, examID int) ([]QuestionRow, error) {
	qrows, err := tx.Query(ctx, `
SELECT id, question_text, stimulus, question_type, pgk_type,
       COALESCE(difficulty_level, 'medium'), COALESCE(question_settings, '{}'::jsonb),
       COALESCE(points, 1)::text, order_index, image_url, video_url, audio_url
  FROM questions WHERE exam_id = $1 ORDER BY order_index, id`, examID)
	if err != nil {
		return nil, err
	}
	defer qrows.Close()
	var questions []QuestionRow
	ids := make([]int, 0)
	for qrows.Next() {
		var q QuestionRow
		if err := qrows.Scan(
			&q.ID, &q.Text, &q.Stimulus, &q.Type, &q.PgkType, &q.Difficulty,
			&q.Settings, &q.PointsText, &q.OrderIndex, &q.ImageURL, &q.VideoURL, &q.AudioURL,
		); err != nil {
			return nil, err
		}
		q.Points, _ = strconv.ParseFloat(q.PointsText, 64)
		questions = append(questions, q)
		ids = append(ids, q.ID)
	}
	if err := qrows.Err(); err != nil {
		return nil, err
	}
	if len(ids) == 0 {
		return questions, nil
	}
	orows, err := tx.Query(ctx, `
SELECT id, question_id, option_text, order_index,
       COALESCE(option_group, 'standard'), pair_id, COALESCE(is_correct, false)
  FROM question_options
 WHERE question_id = ANY($1)
 ORDER BY order_index, id`, ids)
	if err != nil {
		return nil, err
	}
	defer orows.Close()
	byQ := map[int][]OptionRow{}
	for orows.Next() {
		var o OptionRow
		if err := orows.Scan(&o.ID, &o.QuestionID, &o.Text, &o.OrderIndex, &o.OptionGroup, &o.PairID, &o.IsCorrect); err != nil {
			return nil, err
		}
		byQ[o.QuestionID] = append(byQ[o.QuestionID], o)
	}
	if err := orows.Err(); err != nil {
		return nil, err
	}
	for i := range questions {
		questions[i].Options = byQ[questions[i].ID]
	}
	return questions, nil
}

func listSubmitAnswersTx(ctx context.Context, tx pgx.Tx, sessionID int) ([]SubmitAnswerGrade, error) {
	rows, err := tx.Query(ctx, `
SELECT id, question_id, selected_option_id, selected_option_ids, answer_text,
       COALESCE(answer_metadata, '{}'::jsonb), is_correct, points_earned, answered_at
  FROM answers WHERE session_id = $1`, sessionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []SubmitAnswerGrade
	for rows.Next() {
		var row SubmitAnswerGrade
		if err := rows.Scan(
			&row.ID, &row.QuestionID, &row.SelectedOptionID, &row.SelectedOptionIDs,
			&row.AnswerText, &row.Metadata, &row.IsCorrect, &row.Points, &row.AnsweredAt,
		); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) PatchSubmittedSnapshot(ctx context.Context, sessionID, userID, examID, violationCount int, endTime *time.Time) error {
	if !s.HasRedis() {
		return fmt.Errorf("no redis client")
	}
	key := fmt.Sprintf("exam_session:%d", sessionID)
	raw, ok, err := s.RedisGet(ctx, key)
	if err != nil || !ok {
		return err
	}
	var snapshot map[string]any
	if json.Unmarshal([]byte(raw), &snapshot) != nil {
		return nil
	}
	if snapshotUser, ok := asInt(snapshot["user_id"]); ok && snapshotUser != userID {
		return nil
	}
	snapshot["session_id"] = sessionID
	snapshot["exam_id"] = examID
	snapshot["status"] = "submitted"
	if endTime != nil {
		snapshot["end_time"] = endTime.UTC().Format("2006-01-02T15:04:05.000000+00:00")
	} else {
		snapshot["end_time"] = nil
	}
	snapshot["answered_count_stale"] = false
	snapshot["violation_count"] = violationCount
	encoded, err := json.Marshal(snapshot)
	if err != nil {
		return err
	}
	return s.RedisSet(ctx, key, string(encoded), 7200*time.Second)
}
