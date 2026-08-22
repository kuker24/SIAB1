package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

var (
	ErrQuestionTypeLocked = errors.New("question type locked by answers")
	ErrOptionsProtected   = errors.New("options protected by answers")
)

type OptionWrite struct {
	Text        string
	IsCorrect   bool
	OrderIndex  int
	OptionGroup string
	PairID      *string
}

type QuestionWrite struct {
	Text       string
	Stimulus   *string
	Type       string
	Subtype    *string
	PgkType    *string
	Difficulty string
	CategoryID *int
	TagIDs     []int
	Settings   []byte
	Points     float64
	OrderIndex int
	ImageURL   *string
	VideoURL   *string
	AudioURL   *string
	Options    []OptionWrite
}

type CategoryRow struct {
	ID          int
	Name        string
	Description *string
	ParentID    *int
	CreatedAt   *time.Time
}

type TagRow struct {
	ID    int
	Name  string
	Color string
}

func (s *Store) GetQuestion(ctx context.Context, questionID int) (*QuestionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var q QuestionRow
	err := s.pool.QueryRow(ctx, `
SELECT id, exam_id, question_text, stimulus, question_type, pgk_type,
       COALESCE(difficulty_level, 'medium'), COALESCE(question_settings, '{}'::jsonb),
       COALESCE(points, 1), order_index, image_url, video_url, audio_url, category_id
  FROM questions WHERE id = $1`, questionID).Scan(
		&q.ID, &q.ExamID, &q.Text, &q.Stimulus, &q.Type, &q.PgkType, &q.Difficulty,
		&q.Settings, &q.Points, &q.OrderIndex, &q.ImageURL, &q.VideoURL, &q.AudioURL, &q.CategoryID,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	opts, err := s.loadOptions(ctx, []int{q.ID}, true)
	if err != nil {
		return nil, err
	}
	q.Options = opts[q.ID]
	return &q, nil
}

func (s *Store) CreateQuestion(ctx context.Context, examID int, in QuestionWrite) (*QuestionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if len(in.Settings) == 0 {
		in.Settings = []byte("{}")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var id int
	err = tx.QueryRow(ctx, `
INSERT INTO questions (
  exam_id, question_text, stimulus, question_type, question_subtype, pgk_type,
  difficulty_level, category_id, question_settings, points, order_index,
  image_url, video_url, audio_url, created_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14,NOW())
RETURNING id`,
		examID, in.Text, in.Stimulus, in.Type, in.Subtype, in.PgkType,
		in.Difficulty, in.CategoryID, string(in.Settings), in.Points, in.OrderIndex,
		in.ImageURL, in.VideoURL, in.AudioURL,
	).Scan(&id)
	if err != nil {
		return nil, err
	}
	if err := replaceTags(ctx, tx, id, in.TagIDs); err != nil {
		return nil, err
	}
	for _, opt := range in.Options {
		if _, err := tx.Exec(ctx, `
INSERT INTO question_options (
  question_id, option_text, is_correct, order_index, option_group, pair_id
) VALUES ($1,$2,$3,$4,$5,$6)`,
			id, opt.Text, opt.IsCorrect, opt.OrderIndex, opt.OptionGroup, opt.PairID); err != nil {
			return nil, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.GetQuestion(ctx, id)
}

func (s *Store) UpdateQuestion(ctx context.Context, q *QuestionRow, in QuestionWrite) (*QuestionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if len(in.Settings) == 0 {
		in.Settings = []byte("{}")
	}
	existing := append([]OptionRow(nil), q.Options...)
	typeChanged := in.Type != q.Type
	shrinking := len(in.Options) < len(existing)
	var referenced map[int]struct{}
	if typeChanged || shrinking {
		removable := existing[min(len(existing), len(in.Options)):]
		ids := make([]int, 0, len(removable))
		for _, opt := range removable {
			ids = append(ids, opt.ID)
		}
		if len(ids) > 0 {
			var err error
			referenced, err = s.referencedOptionIDs(ctx, q.ID, ids)
			if err != nil {
				return nil, err
			}
		} else {
			has, err := s.HasAnswersForQuestion(ctx, q.ID)
			if err != nil {
				return nil, err
			}
			if has && typeChanged {
				return nil, ErrQuestionTypeLocked
			}
		}
		if len(referenced) > 0 && typeChanged {
			return nil, ErrQuestionTypeLocked
		}
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	_, err = tx.Exec(ctx, `
UPDATE questions SET
  question_text=$2, stimulus=$3, question_type=$4, question_subtype=$5, pgk_type=$6,
  difficulty_level=$7, category_id=$8, question_settings=$9::jsonb, points=$10,
  order_index=$11, image_url=$12, video_url=$13, audio_url=$14
 WHERE id=$1`,
		q.ID, in.Text, in.Stimulus, in.Type, in.Subtype, in.PgkType,
		in.Difficulty, in.CategoryID, string(in.Settings), in.Points,
		in.OrderIndex, in.ImageURL, in.VideoURL, in.AudioURL,
	)
	if err != nil {
		return nil, err
	}
	if err := replaceTags(ctx, tx, q.ID, in.TagIDs); err != nil {
		return nil, err
	}
	common := min(len(existing), len(in.Options))
	for i := 0; i < common; i++ {
		opt := in.Options[i]
		if _, err := tx.Exec(ctx, `
UPDATE question_options SET
  option_text=$2, is_correct=$3, order_index=$4, option_group=$5, pair_id=$6
 WHERE id=$1`,
			existing[i].ID, opt.Text, opt.IsCorrect, opt.OrderIndex, opt.OptionGroup, opt.PairID); err != nil {
			return nil, err
		}
	}
	for _, opt := range in.Options[common:] {
		if _, err := tx.Exec(ctx, `
INSERT INTO question_options (
  question_id, option_text, is_correct, order_index, option_group, pair_id
) VALUES ($1,$2,$3,$4,$5,$6)`,
			q.ID, opt.Text, opt.IsCorrect, opt.OrderIndex, opt.OptionGroup, opt.PairID); err != nil {
			return nil, err
		}
	}
	for _, opt := range existing[common:] {
		if _, ok := referenced[opt.ID]; ok {
			return nil, ErrOptionsProtected
		}
		if _, err := tx.Exec(ctx, `DELETE FROM question_options WHERE id=$1`, opt.ID); err != nil {
			return nil, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.GetQuestion(ctx, q.ID)
}

func (s *Store) DeleteQuestion(ctx context.Context, questionID int) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	tag, err := s.pool.Exec(ctx, `DELETE FROM questions WHERE id=$1`, questionID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

func (s *Store) HasAnswersForQuestion(ctx context.Context, questionID int) (bool, error) {
	if !s.HasPool() {
		return false, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `SELECT 1 FROM answers WHERE question_id=$1 LIMIT 1`, questionID).Scan(&n)
	if err == pgx.ErrNoRows {
		return false, nil
	}
	return err == nil, err
}

func (s *Store) LoadCategory(ctx context.Context, id int) (*CategoryRow, error) {
	if !s.HasPool() || id <= 0 {
		return nil, nil
	}
	var row CategoryRow
	err := s.pool.QueryRow(ctx, `
SELECT id, name, description, parent_id, created_at
  FROM question_categories WHERE id=$1`, id).Scan(
		&row.ID, &row.Name, &row.Description, &row.ParentID, &row.CreatedAt,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) LoadTags(ctx context.Context, ids []int) ([]TagRow, error) {
	if !s.HasPool() || len(ids) == 0 {
		return nil, nil
	}
	rows, err := s.pool.Query(ctx, `
SELECT id, name, COALESCE(color, '#6c757d')
  FROM question_tags WHERE id = ANY($1)`, ids)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	byID := map[int]TagRow{}
	for rows.Next() {
		var row TagRow
		if err := rows.Scan(&row.ID, &row.Name, &row.Color); err != nil {
			return nil, err
		}
		byID[row.ID] = row
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	out := make([]TagRow, 0, len(ids))
	for _, id := range ids {
		if row, ok := byID[id]; ok {
			out = append(out, row)
		}
	}
	return out, nil
}

func (s *Store) referencedOptionIDs(ctx context.Context, questionID int, optionIDs []int) (map[int]struct{}, error) {
	out := map[int]struct{}{}
	if len(optionIDs) == 0 {
		return out, nil
	}
	rows, err := s.pool.Query(ctx, `
SELECT selected_option_id, selected_option_ids
  FROM answers
 WHERE question_id = $1
   AND (selected_option_id = ANY($2) OR selected_option_ids && $2::int[])`, questionID, optionIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	want := map[int]struct{}{}
	for _, id := range optionIDs {
		want[id] = struct{}{}
	}
	for rows.Next() {
		var one *int
		var many []int32
		if err := rows.Scan(&one, &many); err != nil {
			return nil, err
		}
		if one != nil {
			if _, ok := want[*one]; ok {
				out[*one] = struct{}{}
			}
		}
		for _, id := range many {
			if _, ok := want[int(id)]; ok {
				out[int(id)] = struct{}{}
			}
		}
	}
	return out, rows.Err()
}

func (s *Store) loadOptions(ctx context.Context, ids []int, withKeys bool) (map[int][]OptionRow, error) {
	out := map[int][]OptionRow{}
	if len(ids) == 0 {
		return out, nil
	}
	sql := `
SELECT id, question_id, option_text, order_index,
       COALESCE(option_group, 'standard'), pair_id, false
  FROM question_options WHERE question_id = ANY($1) ORDER BY order_index, id`
	if withKeys {
		sql = `
SELECT id, question_id, option_text, order_index,
       COALESCE(option_group, 'standard'), pair_id, COALESCE(is_correct, false)
  FROM question_options WHERE question_id = ANY($1) ORDER BY order_index, id`
	}
	rows, err := s.pool.Query(ctx, sql, ids)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var o OptionRow
		if err := rows.Scan(&o.ID, &o.QuestionID, &o.Text, &o.OrderIndex, &o.OptionGroup, &o.PairID, &o.IsCorrect); err != nil {
			return nil, err
		}
		out[o.QuestionID] = append(out[o.QuestionID], o)
	}
	return out, rows.Err()
}

func replaceTags(ctx context.Context, tx pgx.Tx, questionID int, tagIDs []int) error {
	if _, err := tx.Exec(ctx, `DELETE FROM question_tags_map WHERE question_id=$1`, questionID); err != nil {
		return err
	}
	for _, id := range tagIDs {
		if id <= 0 {
			continue
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO question_tags_map (question_id, tag_id)
SELECT $1, $2 WHERE EXISTS (SELECT 1 FROM question_tags WHERE id=$2)
ON CONFLICT DO NOTHING`, questionID, id); err != nil {
			return err
		}
	}
	return nil
}
