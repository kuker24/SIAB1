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
	"github.com/redis/go-redis/v9"
)



type AnswerSessionProbe struct {
	ID     int
	ExamID int
	Status string
}

type AnswerQuestionPayload struct {
	ID               int
	ExamID           int
	QuestionType     string
	PGKType          *string
	Points           float64
	QuestionSettings []byte
	Options          []AnswerQuestionOption
}

type AnswerQuestionOption struct {
	ID        int
	IsCorrect bool
}

type AnswerWriteFields struct {
	SelectedOptionID  *int
	SelectedOptionIDs []int32
	AnswerText        *string
	Metadata          []byte
	IsCorrect         *bool
	PointsEarned      *float64
	AnsweredAt        time.Time
}

func (s *Store) HasRedis() bool {
	return s != nil && s.redis != nil
}

func (s *Store) ProbeAnswerSession(ctx context.Context, sessionID, userID int) (*AnswerSessionProbe, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row AnswerSessionProbe
	err := s.pool.QueryRow(ctx, `
SELECT id, exam_id, status
  FROM exam_sessions
 WHERE id = $1 AND user_id = $2`, sessionID, userID).Scan(&row.ID, &row.ExamID, &row.Status)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) LoadAnswerQuestion(ctx context.Context, examID, questionID int) (*AnswerQuestionPayload, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row AnswerQuestionPayload
	err := s.pool.QueryRow(ctx, `
SELECT id, exam_id, question_type, pgk_type, COALESCE(points, 0), COALESCE(question_settings, '{}'::jsonb)
  FROM questions
 WHERE id = $1 AND exam_id = $2`, questionID, examID).Scan(
		&row.ID, &row.ExamID, &row.QuestionType, &row.PGKType, &row.Points, &row.QuestionSettings,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	settings := map[string]any{}
	_ = json.Unmarshal(row.QuestionSettings, &settings)
	pgk := ""
	if row.PGKType != nil {
		pgk = strings.TrimSpace(*row.PGKType)
	}
	if pgk == "" {
		if raw, ok := settings["pgk_type"].(string); ok {
			pgk = strings.TrimSpace(raw)
		}
	}
	if pgk == "" {
		pgk = "checkbox"
	}
	needsOptions := row.QuestionType == "multiple_choice" || row.QuestionType == "true_false" ||
		(row.QuestionType == "multiple_choice_complex" && pgk != "table_validation")
	if needsOptions {
		optRows, optErr := s.pool.Query(ctx, `
SELECT id, COALESCE(is_correct, false)
  FROM question_options
 WHERE question_id = $1`, row.ID)
		if optErr != nil {
			return nil, optErr
		}
		defer optRows.Close()
		for optRows.Next() {
			var opt AnswerQuestionOption
			if scanErr := optRows.Scan(&opt.ID, &opt.IsCorrect); scanErr != nil {
				return nil, scanErr
			}
			row.Options = append(row.Options, opt)
		}
		if err := optRows.Err(); err != nil {
			return nil, err
		}
	}
	return &row, nil
}

func (s *Store) WriteSingleAnswerDirect(
	ctx context.Context,
	sessionID, userID, questionID int,
	fields AnswerWriteFields,
) (string, error) {
	if !s.HasPool() {
		return "", fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1, $2)`, sessionWriteLockNS, sessionID); err != nil {
		return "", err
	}
	var status string
	err = tx.QueryRow(ctx, `
SELECT status FROM exam_sessions
 WHERE id = $1 AND user_id = $2
 FOR UPDATE`, sessionID, userID).Scan(&status)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", errAnswerNotFound
	}
	if err != nil {
		return "", err
	}
	normalized := strings.ToLower(strings.TrimSpace(status))
	if normalized == "submitted" || normalized == "completed" {
		if err := tx.Commit(ctx); err != nil {
			return "", err
		}
		return "submitted", nil
	}
	if normalized != "in_progress" {
		return normalized, errAnswerEnded
	}
	if len(fields.Metadata) == 0 {
		fields.Metadata = []byte("{}")
	}
	_, err = tx.Exec(ctx, `
INSERT INTO answers (
  session_id, question_id, selected_option_id, selected_option_ids,
  answer_text, answer_metadata, is_correct, points_earned, answered_at
) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9)
ON CONFLICT (session_id, question_id) DO UPDATE SET
  selected_option_id = EXCLUDED.selected_option_id,
  selected_option_ids = EXCLUDED.selected_option_ids,
  answer_text = EXCLUDED.answer_text,
  answer_metadata = EXCLUDED.answer_metadata,
  is_correct = EXCLUDED.is_correct,
  points_earned = EXCLUDED.points_earned,
  answered_at = EXCLUDED.answered_at
WHERE answers.selected_option_id IS DISTINCT FROM EXCLUDED.selected_option_id
   OR answers.selected_option_ids IS DISTINCT FROM EXCLUDED.selected_option_ids
   OR answers.answer_text IS DISTINCT FROM EXCLUDED.answer_text
   OR answers.answer_metadata IS DISTINCT FROM EXCLUDED.answer_metadata
   OR answers.is_correct IS DISTINCT FROM EXCLUDED.is_correct
   OR answers.points_earned IS DISTINCT FROM EXCLUDED.points_earned`,
		sessionID, questionID, fields.SelectedOptionID, fields.SelectedOptionIDs,
		fields.AnswerText, string(fields.Metadata), fields.IsCorrect, fields.PointsEarned, fields.AnsweredAt,
	)
	if err != nil && strings.Contains(strings.ToLower(err.Error()), "no unique or exclusion constraint") {
		if _, lockErr := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1, $2)`, sessionID, questionID); lockErr != nil {
			return "", lockErr
		}
		tag, updErr := tx.Exec(ctx, `
UPDATE answers SET
  selected_option_id = $3,
  selected_option_ids = $4,
  answer_text = $5,
  answer_metadata = $6::jsonb,
  is_correct = $7,
  points_earned = $8,
  answered_at = $9
 WHERE session_id = $1 AND question_id = $2`,
			sessionID, questionID, fields.SelectedOptionID, fields.SelectedOptionIDs,
			fields.AnswerText, string(fields.Metadata), fields.IsCorrect, fields.PointsEarned, fields.AnsweredAt,
		)
		if updErr != nil {
			return "", updErr
		}
		if tag.RowsAffected() == 0 {
			_, err = tx.Exec(ctx, `
INSERT INTO answers (
  session_id, question_id, selected_option_id, selected_option_ids,
  answer_text, answer_metadata, is_correct, points_earned, answered_at
) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9)`,
				sessionID, questionID, fields.SelectedOptionID, fields.SelectedOptionIDs,
				fields.AnswerText, string(fields.Metadata), fields.IsCorrect, fields.PointsEarned, fields.AnsweredAt,
			)
		} else {
			err = nil
		}
	}
	if err != nil {
		return "", err
	}
	if err := tx.Commit(ctx); err != nil {
		return "", err
	}
	return "in_progress", nil
}

var (
	errAnswerNotFound = errors.New("answer session not found")
	errAnswerEnded    = errors.New("answer session ended")
)

func IsAnswerNotFound(err error) bool { return errors.Is(err, errAnswerNotFound) }
func IsAnswerEnded(err error) bool    { return errors.Is(err, errAnswerEnded) }

func (s *Store) AllowSlidingRate(ctx context.Context, prefix, identifier string, limit, window int) (bool, int) {
	if !s.HasRedis() {
		return true, limit
	}
	key := "ratelimit:" + prefix + ":" + identifier
	now := float64(time.Now().UnixNano()) / 1e9
	windowStart := now - float64(window)
	pipe := s.redis.Pipeline()
	pipe.ZRemRangeByScore(ctx, key, "0", strconv.FormatFloat(windowStart, 'f', -1, 64))
	countCmd := pipe.ZCard(ctx, key)
	member := fmt.Sprintf("%.6f:%d", now, time.Now().UnixNano())
	pipe.ZAdd(ctx, key, redis.Z{Score: now, Member: member})
	pipe.Expire(ctx, key, time.Duration(window+1)*time.Second)
	_, err := pipe.Exec(ctx)
	if err != nil {
		return true, limit
	}
	current := int(countCmd.Val())
	remaining := limit - current - 1
	if remaining < 0 {
		remaining = 0
	}
	return current < limit, remaining
}

func (s *Store) AddAnsweredQuestions(ctx context.Context, sessionID int, questionIDs []int) (int, bool, error) {
	if !s.HasRedis() {
		return 0, false, fmt.Errorf("no redis client")
	}
	members := make([]any, 0, len(questionIDs))
	seen := map[int]struct{}{}
	for _, id := range questionIDs {
		if id <= 0 {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		members = append(members, strconv.Itoa(id))
	}
	if len(members) == 0 {
		return 0, false, nil
	}
	key := fmt.Sprintf("exam_answered_questions:%d", sessionID)
	pipe := s.redis.Pipeline()
	pipe.SAdd(ctx, key, members...)
	pipe.Expire(ctx, key, 7200*time.Second)
	card := pipe.SCard(ctx, key)
	if _, err := pipe.Exec(ctx); err != nil {
		return 0, false, err
	}
	return int(card.Val()), true, nil
}

func (s *Store) PatchSessionAnsweredCount(ctx context.Context, sessionID, userID, count int) error {
	if !s.HasRedis() {
		return fmt.Errorf("no redis client")
	}
	key := fmt.Sprintf("exam_session:%d", sessionID)
	raw, err := s.redis.Get(ctx, key).Result()
	if errors.Is(err, redis.Nil) {
		return nil
	}
	if err != nil {
		return err
	}
	var snapshot map[string]any
	if json.Unmarshal([]byte(raw), &snapshot) != nil {
		return nil
	}
	if snapshotUser, ok := asInt(snapshot["user_id"]); ok && snapshotUser != userID {
		return nil
	}
	if count < 0 {
		count = 0
	}
	snapshot["answered_count"] = count
	snapshot["answered_count_stale"] = false
	snapshot["status"] = "in_progress"
	encoded, err := json.Marshal(snapshot)
	if err != nil {
		return err
	}
	return s.redis.Set(ctx, key, encoded, 7200*time.Second).Err()
}

func (s *Store) ReplaceSessionAnswerCache(ctx context.Context, sessionID int, payload any) error {
	if !s.HasRedis() {
		return fmt.Errorf("no redis client")
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	return s.redis.Set(ctx, fmt.Sprintf("exam_answers:%d", sessionID), encoded, 7200*time.Second).Err()
}

func asInt(v any) (int, bool) {
	switch typed := v.(type) {
	case float64:
		return int(typed), true
	case json.Number:
		n, err := typed.Int64()
		return int(n), err == nil
	case int:
		return typed, true
	case string:
		n, err := strconv.Atoi(typed)
		return n, err == nil
	default:
		return 0, false
	}
}

func IsTransientDB(err error) bool {
	if err == nil {
		return false
	}
	message := strings.ToLower(err.Error())
	markers := []string{
		"timeout",
		"queuepool limit",
		"connection was closed",
		"too many clients already",
		"canceling statement due to statement timeout",
		"could not serialize access due to concurrent update",
	}
	for _, marker := range markers {
		if strings.Contains(message, marker) {
			return true
		}
	}
	return false
}
