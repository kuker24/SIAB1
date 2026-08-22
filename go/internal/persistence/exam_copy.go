package persistence

import (
	"context"
	"crypto/rand"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
)

const accessTokenChars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

func (s *Store) DuplicateExam(ctx context.Context, examID, creatorID int, includeQuestions bool) (*ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var last error
	for i := 0; i < 5; i++ {
		id, err := s.duplicateExamOnce(ctx, examID, creatorID, includeQuestions)
		if err != nil {
			last = err
			if strings.Contains(strings.ToLower(err.Error()), "unique") {
				continue
			}
			return nil, err
		}
		return s.GetExam(ctx, id)
	}
	if last == nil {
		last = fmt.Errorf("token collision")
	}
	return nil, last
}

func (s *Store) duplicateExamOnce(ctx context.Context, examID, creatorID int, includeQuestions bool) (int, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var newID int
	err = tx.QueryRow(ctx, `
INSERT INTO exams (
  title, description, creator_id, duration_minutes, start_time, end_time,
  passing_score, max_attempts, shuffle_questions, shuffle_options,
  show_results, allow_review, is_published, subject, exam_type, academic_year,
  show_teacher_name, builder_settings, allowed_classes, allowed_students,
  access_token, seb_config_key, seb_browser_exam_key, created_at, updated_at
)
SELECT
  title || ' (Copy)', description, $2, duration_minutes, start_time, end_time,
  passing_score, max_attempts, shuffle_questions, shuffle_options,
  show_results, allow_review, false, subject, exam_type, academic_year,
  show_teacher_name, COALESCE(builder_settings, '{}'::jsonb), allowed_classes, allowed_students,
  $3, $4, $5, NOW(), NOW()
  FROM exams
 WHERE id = $1 AND COALESCE(is_deleted, false) = false
RETURNING id`,
		examID, creatorID, randomHex(3), randomURL(32), randomURL(32),
	).Scan(&newID)
	if err == pgx.ErrNoRows {
		return 0, pgx.ErrNoRows
	}
	if err != nil {
		return 0, err
	}
	if includeQuestions {
		qrows, err := tx.Query(ctx, `SELECT id FROM questions WHERE exam_id=$1 ORDER BY order_index, id`, examID)
		if err != nil {
			return 0, err
		}
		var oldIDs []int
		for qrows.Next() {
			var id int
			if err := qrows.Scan(&id); err != nil {
				qrows.Close()
				return 0, err
			}
			oldIDs = append(oldIDs, id)
		}
		qrows.Close()
		if err := qrows.Err(); err != nil {
			return 0, err
		}
		for _, oldID := range oldIDs {
			var newQ int
			err = tx.QueryRow(ctx, `
INSERT INTO questions (
  exam_id, question_text, stimulus, question_type, question_subtype, pgk_type,
  difficulty_level, category_id, question_settings, points, order_index,
  image_url, video_url, audio_url, created_at
)
SELECT $2, question_text, stimulus, question_type, question_subtype, pgk_type,
       difficulty_level, category_id, question_settings, points, order_index,
       image_url, video_url, audio_url, NOW()
  FROM questions WHERE id=$1
RETURNING id`, oldID, newID).Scan(&newQ)
			if err != nil {
				return 0, err
			}
			if _, err := tx.Exec(ctx, `
INSERT INTO question_options (
  question_id, option_text, is_correct, order_index, option_group, pair_id, option_metadata
)
SELECT $2, option_text, is_correct, order_index, option_group, pair_id, COALESCE(option_metadata, '{}'::jsonb)
  FROM question_options WHERE question_id=$1`, oldID, newQ); err != nil {
				return 0, err
			}
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return newID, nil
}

func (s *Store) RegenerateAccessToken(ctx context.Context, examID int) (*ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var last error
	for i := 0; i < 10; i++ {
		token := randomAccessToken(6)
		tag, err := s.pool.Exec(ctx, `
UPDATE exams SET access_token=$2, updated_at=NOW()
 WHERE id=$1 AND COALESCE(is_deleted,false)=false`, examID, token)
		if err != nil {
			last = err
			if strings.Contains(strings.ToLower(err.Error()), "unique") {
				continue
			}
			return nil, err
		}
		if tag.RowsAffected() == 0 {
			return nil, pgx.ErrNoRows
		}
		return s.GetExam(ctx, examID)
	}
	if last == nil {
		last = fmt.Errorf("token collision")
	}
	return nil, last
}

func randomAccessToken(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	out := make([]byte, n)
	for i := range out {
		out[i] = accessTokenChars[int(b[i])%len(accessTokenChars)]
	}
	return string(out)
}
