package persistence

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

type BatchAnswerWrite struct {
	QuestionID         int
	SelectedOptionID   *int
	SelectedOptionIDs  []int32
	HasOptionIDs       bool
	AnswerText         *string
	IncomingMetadata   map[string]any
	StatementAnswers   map[string]bool
	HasStatements      bool
}

type BatchWriteOutcome struct {
	Changed    int
	ValidCount int
	Status     string
}

func (s *Store) ValidQuestionIDs(ctx context.Context, examID int, questionIDs []int) (map[int]struct{}, error) {
	out := map[int]struct{}{}
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if len(questionIDs) == 0 {
		return out, nil
	}
	rows, err := s.pool.Query(ctx, `SELECT id FROM questions WHERE exam_id = $1 AND id = ANY($2)`, examID, questionIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var id int
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out[id] = struct{}{}
	}
	return out, rows.Err()
}

func (s *Store) WriteBatchAutosave(
	ctx context.Context,
	sessionID, userID int,
	items []BatchAnswerWrite,
	now time.Time,
) (BatchWriteOutcome, error) {
	out := BatchWriteOutcome{ValidCount: len(items), Status: "no_changes"}
	if !s.HasPool() {
		return out, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return out, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1, $2)`, sessionWriteLockNS, sessionID); err != nil {
		return out, err
	}
	var status string
	err = tx.QueryRow(ctx, `
SELECT status FROM exam_sessions
 WHERE id = $1 AND user_id = $2
 FOR UPDATE`, sessionID, userID).Scan(&status)
	if errors.Is(err, pgx.ErrNoRows) {
		return BatchWriteOutcome{Status: "not_found"}, nil
	}
	if err != nil {
		return out, err
	}
	if strings.ToLower(strings.TrimSpace(status)) != "in_progress" {
		return BatchWriteOutcome{Status: "ended"}, nil
	}
	ids := make([]int, 0, len(items))
	for _, item := range items {
		ids = append(ids, item.QuestionID)
	}
	existing := map[int]existingBatchAnswer{}
	if len(ids) > 0 {
		rows, qerr := tx.Query(ctx, `
SELECT question_id, selected_option_id, selected_option_ids, answer_text, COALESCE(answer_metadata, '{}'::jsonb)
  FROM answers
 WHERE session_id = $1 AND question_id = ANY($2)`, sessionID, ids)
		if qerr != nil {
			return out, qerr
		}
		for rows.Next() {
			var row existingBatchAnswer
			if scanErr := rows.Scan(&row.QuestionID, &row.SelectedOptionID, &row.SelectedOptionIDs, &row.AnswerText, &row.Metadata); scanErr != nil {
				rows.Close()
				return out, scanErr
			}
			existing[row.QuestionID] = row
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return out, err
		}
	}
	changed := 0
	for _, item := range items {
		cur, ok := existing[item.QuestionID]
		existingMeta := map[string]any{}
		if ok && len(cur.Metadata) > 0 {
			_ = json.Unmarshal(cur.Metadata, &existingMeta)
		}
		var statements map[string]bool
		if item.HasStatements {
			statements = item.StatementAnswers
			if statements == nil {
				statements = map[string]bool{}
			}
		}
		finalMeta := MergeStatementMetadata(existingMeta, item.IncomingMetadata, statements)
		meta := MetadataJSON(finalMeta)
		if ok && !batchAnswerChanged(cur, item, meta) {
			continue
		}
		var optionIDs any
		if item.HasOptionIDs {
			optionIDs = item.SelectedOptionIDs
		}
		if ok {
			if _, err := tx.Exec(ctx, `
UPDATE answers SET
  selected_option_id = $3,
  selected_option_ids = $4,
  answer_text = $5,
  answer_metadata = $6::jsonb,
  answered_at = $7,
  is_correct = NULL,
  points_earned = NULL
 WHERE session_id = $1 AND question_id = $2`,
				sessionID, item.QuestionID, item.SelectedOptionID, optionIDs, item.AnswerText, string(meta), now,
			); err != nil {
				return out, err
			}
		} else {
			if _, err := tx.Exec(ctx, `
INSERT INTO answers (
  session_id, question_id, selected_option_id, selected_option_ids,
  answer_text, answer_metadata, answered_at, is_correct, points_earned
) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,NULL,NULL)`,
				sessionID, item.QuestionID, item.SelectedOptionID, optionIDs, item.AnswerText, string(meta), now,
			); err != nil {
				return out, err
			}
		}
		changed++
	}
	if err := tx.Commit(ctx); err != nil {
		return out, err
	}
	out.Changed = changed
	if changed > 0 {
		out.Status = "saved_to_db"
	}
	return out, nil
}

type existingBatchAnswer struct {
	QuestionID        int
	SelectedOptionID  *int
	SelectedOptionIDs []int32
	AnswerText        *string
	Metadata          []byte
}

func batchAnswerChanged(cur existingBatchAnswer, item BatchAnswerWrite, meta []byte) bool {
	if (cur.SelectedOptionID == nil) != (item.SelectedOptionID == nil) {
		return true
	}
	if cur.SelectedOptionID != nil && item.SelectedOptionID != nil && *cur.SelectedOptionID != *item.SelectedOptionID {
		return true
	}
	if !pyInt32Equal(cur.SelectedOptionIDs, item.SelectedOptionIDs, cur.SelectedOptionIDs != nil, item.HasOptionIDs) {
		return true
	}
	if (cur.AnswerText == nil) != (item.AnswerText == nil) {
		return true
	}
	if cur.AnswerText != nil && item.AnswerText != nil && *cur.AnswerText != *item.AnswerText {
		return true
	}
	return !jsonBytesEqual(cur.Metadata, meta)
}

func pyInt32Equal(a, b []int32, aSet, bSet bool) bool {
	if !aSet && !bSet {
		return true
	}
	if !aSet || !bSet {
		return false
	}
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func MergeStatementMetadata(existing, incoming map[string]any, statements map[string]bool) map[string]any {
	previous := map[string]any{}
	for key, value := range existing {
		previous[key] = value
	}
	normalized := map[string]any{}
	for key, value := range incoming {
		normalized[key] = value
	}
	var prevStatements map[string]bool
	switch raw := previous["statement_answers"].(type) {
	case map[string]any:
		prevStatements = map[string]bool{}
		for key, value := range raw {
			prevStatements[key] = asBool(value)
		}
	case map[string]bool:
		prevStatements = raw
	}
	replace := pyBool(normalized["replace_statement_answers"])
	deleteStmts := pyBool(normalized["delete_statement_answers"])
	var merged map[string]bool
	if deleteStmts {
		merged = map[string]bool{}
	} else if statements == nil {
		if replace {
			merged = map[string]bool{}
		} else if prevStatements != nil {
			merged = prevStatements
		}
	} else if replace {
		merged = statements
	} else if prevStatements != nil {
		merged = map[string]bool{}
		for key, value := range prevStatements {
			merged[key] = value
		}
		for key, value := range statements {
			merged[key] = value
		}
	} else {
		merged = statements
	}
	final := map[string]any{}
	for key, value := range previous {
		final[key] = value
	}
	for key, value := range normalized {
		final[key] = value
	}
	delete(final, "replace_statement_answers")
	delete(final, "delete_statement_answers")
	if merged != nil {
		if len(merged) > 0 {
			final["statement_answers"] = merged
		} else {
			delete(final, "statement_answers")
		}
	}
	return final
}

func pyBool(v any) bool {
	switch typed := v.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case float64:
		return typed != 0
	case int:
		return typed != 0
	case json.Number:
		n, _ := typed.Float64()
		return n != 0
	case map[string]any:
		return len(typed) > 0
	case []any:
		return len(typed) > 0
	default:
		return true
	}
}

func asBool(v any) bool {
	switch typed := v.(type) {
	case bool:
		return typed
	case string:
		lower := strings.ToLower(strings.TrimSpace(typed))
		return lower == "true" || lower == "1" || lower == "yes"
	case float64:
		return typed != 0
	case int:
		return typed != 0
	case json.Number:
		n, _ := typed.Float64()
		return n != 0
	default:
		return pyBool(v)
	}
}

func jsonBytesEqual(a, b []byte) bool {
	if len(a) == 0 {
		a = []byte("{}")
	}
	if len(b) == 0 {
		b = []byte("{}")
	}
	var am, bm any
	if json.Unmarshal(a, &am) != nil || json.Unmarshal(b, &bm) != nil {
		return bytes.Equal(a, b)
	}
	ab, _ := json.Marshal(am)
	bb, _ := json.Marshal(bm)
	return bytes.Equal(ab, bb)
}
