package persistence

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

var ErrTemplateAccessToken = errors.New("failed to create unique exam access token")

type TemplateRow struct {
	ID          int
	Name        string
	Description *string
	CreatorID   *int
	CreatorRole *string
	Data        []byte
	Public      bool
	CreatedAt   time.Time
}

type TemplateListFilter struct {
	ViewerID   int
	ViewerRole string
	PublicOnly bool
	Limit      int
	Offset     int
}

type TemplateWrite struct {
	Name        string
	Description *string
	Data        []byte
	Public      bool
}

type TemplateUpdate struct {
	Name         *string
	Description  *string
	Data         []byte
	UpdateData   bool
	Public       *bool
	CanSetPublic bool
}

type TemplateQuestion struct {
	Text       string
	Type       string
	Subtype    *string
	Difficulty string
	CategoryID *int
	Settings   []byte
	Points     float64
	OrderIndex int
	ImageURL   *string
	PgkType    *string
	Stimulus   *string
	VideoURL   *string
	AudioURL   *string
	Options    []TemplateOption
}

type TemplateOption struct {
	Text       string
	Correct    bool
	OrderIndex int
	Group      string
	PairID     *string
	Metadata   []byte
}

type TemplateExamWrite struct {
	Exam      ExamWrite
	Questions []TemplateQuestion
}

const templateSelect = `
SELECT t.id, t.name, t.description, t.creator_id, u.role,
       COALESCE(t.template_data, '{}'::jsonb), COALESCE(t.is_public, false),
       COALESCE(t.created_at, NOW())
  FROM exam_templates t
  LEFT JOIN users u ON u.id = t.creator_id`

func templateScan(row *TemplateRow) []any {
	return []any{
		&row.ID, &row.Name, &row.Description, &row.CreatorID, &row.CreatorRole,
		&row.Data, &row.Public, &row.CreatedAt,
	}
}

func (s *Store) ListTemplates(ctx context.Context, f TemplateListFilter) ([]TemplateRow, int, error) {
	if !s.HasPool() {
		return nil, 0, fmt.Errorf("no pgx pool")
	}
	if f.Limit <= 0 {
		f.Limit = 20
	}
	if f.Offset < 0 {
		f.Offset = 0
	}
	role := strings.ToLower(strings.TrimSpace(f.ViewerRole))
	where := []string{}
	args := []any{}
	if role == "teacher" {
		where = append(where, "(COALESCE(t.is_public, false) = true OR t.creator_id = $1)")
		args = append(args, f.ViewerID)
		where = append(where, "COALESCE(lower(u.role), '') <> 'developer'")
	} else if f.PublicOnly {
		where = append(where, "COALESCE(t.is_public, false) = true")
		if role != "developer" {
			where = append(where, "COALESCE(lower(u.role), '') <> 'developer'")
		}
	} else if role == "admin" {
		where = append(where, "COALESCE(lower(u.role), '') <> 'developer'")
	} else if role != "developer" {
		args = append(args, f.ViewerID)
		where = append(where, fmt.Sprintf("t.creator_id = $%d", len(args)))
	}
	clause := ""
	if len(where) > 0 {
		clause = " WHERE " + strings.Join(where, " AND ")
	}
	var total int
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM exam_templates t LEFT JOIN users u ON u.id = t.creator_id`+clause, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	args = append(args, f.Limit, f.Offset)
	rows, err := s.pool.Query(ctx, templateSelect+clause+fmt.Sprintf(`
 ORDER BY t.created_at DESC, t.id DESC
 LIMIT $%d OFFSET $%d`, len(args)-1, len(args)), args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	out := make([]TemplateRow, 0)
	for rows.Next() {
		var row TemplateRow
		if err := rows.Scan(templateScan(&row)...); err != nil {
			return nil, 0, err
		}
		out = append(out, row)
	}
	return out, total, rows.Err()
}

func (s *Store) GetTemplate(ctx context.Context, templateID int) (*TemplateRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row TemplateRow
	err := s.pool.QueryRow(ctx, templateSelect+" WHERE t.id = $1", templateID).Scan(templateScan(&row)...)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) CreateTemplate(ctx context.Context, creatorID int, in TemplateWrite) (*TemplateRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var id int
	err := s.pool.QueryRow(ctx, `
INSERT INTO exam_templates (name, description, creator_id, template_data, is_public, created_at)
VALUES ($1,$2,$3,$4::jsonb,$5,NOW()) RETURNING id`,
		in.Name, in.Description, creatorID, string(in.Data), in.Public,
	).Scan(&id)
	if err != nil {
		return nil, err
	}
	return s.GetTemplate(ctx, id)
}

func (s *Store) UpdateTemplate(ctx context.Context, templateID int, in TemplateUpdate) (*TemplateRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var data any
	if in.UpdateData {
		data = string(in.Data)
	}
	var public any
	if in.CanSetPublic && in.Public != nil {
		public = *in.Public
	}
	tag, err := s.pool.Exec(ctx, `
UPDATE exam_templates SET
  name=COALESCE($2, name), description=COALESCE($3, description),
  template_data=CASE WHEN $4 THEN $5::jsonb ELSE template_data END,
  is_public=COALESCE($6, is_public)
WHERE id=$1`, templateID, in.Name, in.Description, in.UpdateData, data, public)
	if err != nil {
		return nil, err
	}
	if tag.RowsAffected() == 0 {
		return nil, pgx.ErrNoRows
	}
	return s.GetTemplate(ctx, templateID)
}

func (s *Store) DeleteTemplate(ctx context.Context, templateID int) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	tag, err := s.pool.Exec(ctx, `DELETE FROM exam_templates WHERE id=$1`, templateID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

func (s *Store) CreateExamFromTemplate(ctx context.Context, creatorID int, in TemplateExamWrite) (*ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var examID int
	for i := 0; i < 10; i++ {
		token, err := randomExamToken(6)
		if err != nil {
			return nil, err
		}
		err = tx.QueryRow(ctx, `
INSERT INTO exams (
  title, description, creator_id, duration_minutes, start_time, end_time,
  passing_score, max_attempts, shuffle_questions, shuffle_options,
  show_results, allow_review, is_published, show_teacher_name, builder_settings,
  allowed_classes, access_token, seb_config_key, seb_browser_exam_key, created_at, updated_at
) VALUES (
  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,false,true,'{}'::jsonb,$13,$14,$15,$16,NOW(),NOW()
) ON CONFLICT DO NOTHING RETURNING id`,
			in.Exam.Title, in.Exam.Description, creatorID, in.Exam.DurationMinutes,
			in.Exam.StartTime, in.Exam.EndTime, in.Exam.PassingScore, in.Exam.MaxAttempts,
			in.Exam.ShuffleQuestions, in.Exam.ShuffleOptions, in.Exam.ShowResults,
			in.Exam.AllowReview, in.Exam.AllowedClasses, token, randomURL(32), randomURL(32),
		).Scan(&examID)
		if err == pgx.ErrNoRows {
			continue
		}
		if err != nil {
			return nil, err
		}
		break
	}
	if examID == 0 {
		return nil, ErrTemplateAccessToken
	}
	for _, question := range in.Questions {
		var questionID int
		err := tx.QueryRow(ctx, `
INSERT INTO questions (
  exam_id, question_text, question_type, question_subtype, difficulty_level,
  category_id, question_settings, points, order_index, image_url, pgk_type,
  stimulus, video_url, audio_url, created_at
) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12,$13,$14,NOW())
RETURNING id`, examID, question.Text, question.Type, question.Subtype, question.Difficulty,
			question.CategoryID, string(question.Settings), question.Points, question.OrderIndex,
			question.ImageURL, question.PgkType, question.Stimulus, question.VideoURL, question.AudioURL,
		).Scan(&questionID)
		if err != nil {
			return nil, err
		}
		for _, option := range question.Options {
			_, err := tx.Exec(ctx, `
INSERT INTO question_options (
  question_id, option_text, is_correct, order_index, option_group, pair_id, option_metadata
) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)`, questionID, option.Text, option.Correct,
				option.OrderIndex, option.Group, option.PairID, string(option.Metadata))
			if err != nil {
				return nil, err
			}
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.GetExam(ctx, examID)
}

func randomExamToken(length int) (string, error) {
	const chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
	raw := make([]byte, length)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	for i := range raw {
		raw[i] = chars[int(raw[i])%len(chars)]
	}
	return string(raw), nil
}
