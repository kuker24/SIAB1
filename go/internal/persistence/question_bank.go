package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

func (s *Store) ListCategories(ctx context.Context) ([]CategoryRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT id, name, description, parent_id, created_at
  FROM question_categories ORDER BY name, id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []CategoryRow
	for rows.Next() {
		var row CategoryRow
		if err := rows.Scan(&row.ID, &row.Name, &row.Description, &row.ParentID, &row.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) CreateCategory(ctx context.Context, name string, description *string, parentID *int) (*CategoryRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row CategoryRow
	err := s.pool.QueryRow(ctx, `
INSERT INTO question_categories (name, description, parent_id, created_at)
VALUES ($1,$2,$3,NOW())
RETURNING id, name, description, parent_id, created_at`, name, description, parentID).Scan(
		&row.ID, &row.Name, &row.Description, &row.ParentID, &row.CreatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) ListTags(ctx context.Context) ([]TagRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT id, name, COALESCE(color, '#6c757d') FROM question_tags ORDER BY name, id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []TagRow
	for rows.Next() {
		var row TagRow
		if err := rows.Scan(&row.ID, &row.Name, &row.Color); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) CreateTag(ctx context.Context, name, color string) (*TagRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var exists int
	err := s.pool.QueryRow(ctx, `SELECT 1 FROM question_tags WHERE lower(name)=lower($1) LIMIT 1`, name).Scan(&exists)
	if err == nil {
		return nil, ErrTagExists
	}
	if err != pgx.ErrNoRows {
		return nil, err
	}
	if strings.TrimSpace(color) == "" {
		color = "#6c757d"
	}
	var row TagRow
	err = s.pool.QueryRow(ctx, `
INSERT INTO question_tags (name, color, created_at)
VALUES ($1,$2,NOW())
RETURNING id, name, COALESCE(color, '#6c757d')`, name, color).Scan(&row.ID, &row.Name, &row.Color)
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "unique") {
			return nil, ErrTagExists
		}
		return nil, err
	}
	return &row, nil
}

var ErrTagExists = fmt.Errorf("tag exists")

func FormatTimePtr(t *time.Time) any {
	if t == nil {
		return nil
	}
	return t.UTC().Format(time.RFC3339)
}

type QuestionSearchFilter struct {
	Query         string
	CategoryID    *int
	TagIDs        []int
	Difficulty    string
	QuestionType  string
	CreatorID     int
	HideDeveloper bool
	Limit         int
	Offset        int
}

func (s *Store) SearchQuestionIDs(ctx context.Context, f QuestionSearchFilter) ([]int, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if f.Limit <= 0 {
		f.Limit = 20
	}
	if f.Limit > 100 {
		f.Limit = 100
	}
	if f.Offset < 0 {
		f.Offset = 0
	}
	q := `SELECT DISTINCT q.id FROM questions q JOIN exams e ON e.id = q.exam_id`
	if f.HideDeveloper {
		q += ` JOIN users creator ON creator.id = e.creator_id`
	}
	args := []any{}
	q += ` WHERE COALESCE(e.is_deleted, false) = false`
	if f.CreatorID > 0 {
		args = append(args, f.CreatorID)
		q += fmt.Sprintf(` AND e.creator_id = $%d`, len(args))
	}
	if f.HideDeveloper {
		q += ` AND COALESCE(creator.role, '') <> 'developer'`
	}
	if strings.TrimSpace(f.Query) != "" {
		args = append(args, "%"+strings.TrimSpace(f.Query)+"%")
		q += fmt.Sprintf(` AND q.question_text ILIKE $%d`, len(args))
	}
	if f.CategoryID != nil {
		args = append(args, *f.CategoryID)
		q += fmt.Sprintf(` AND q.category_id = $%d`, len(args))
	}
	if strings.TrimSpace(f.Difficulty) != "" {
		args = append(args, strings.TrimSpace(f.Difficulty))
		q += fmt.Sprintf(` AND q.difficulty_level = $%d`, len(args))
	}
	if strings.TrimSpace(f.QuestionType) != "" {
		args = append(args, strings.TrimSpace(f.QuestionType))
		q += fmt.Sprintf(` AND q.question_type = $%d`, len(args))
	}
	if len(f.TagIDs) > 0 {
		args = append(args, f.TagIDs)
		q += fmt.Sprintf(` AND EXISTS (
			SELECT 1 FROM question_tags_map qtm
			WHERE qtm.question_id = q.id AND qtm.tag_id = ANY($%d)
		)`, len(args))
	}
	args = append(args, f.Limit, f.Offset)
	q += fmt.Sprintf(` ORDER BY q.id DESC LIMIT $%d OFFSET $%d`, len(args)-1, len(args))
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ids []int
	for rows.Next() {
		var id int
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func (s *Store) QuestionTagIDs(ctx context.Context, questionID int) ([]int, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT tag_id FROM question_tags_map WHERE question_id = $1 ORDER BY tag_id`, questionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ids []int
	for rows.Next() {
		var id int
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}
