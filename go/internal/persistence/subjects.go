package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
)

var ErrSubjectExists = errors.New("subject exists")

type SubjectRow struct {
	ID          int
	Name        string
	Description *string
	CreatorID   *int
}

func (s *Store) ListSubjects(ctx context.Context) ([]SubjectRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT id, name, description FROM subjects ORDER BY name, id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []SubjectRow
	for rows.Next() {
		var row SubjectRow
		if err := rows.Scan(&row.ID, &row.Name, &row.Description); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) CreateSubject(ctx context.Context, name string, description *string, creatorID int) (*SubjectRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var exists int
	err := s.pool.QueryRow(ctx, `SELECT 1 FROM subjects WHERE lower(name)=lower($1) LIMIT 1`, name).Scan(&exists)
	if err == nil {
		return nil, ErrSubjectExists
	}
	if err != pgx.ErrNoRows {
		return nil, err
	}
	var row SubjectRow
	err = s.pool.QueryRow(ctx, `
INSERT INTO subjects (name, description, creator_id, created_at)
VALUES ($1,$2,$3,NOW())
RETURNING id, name, description, creator_id`, name, description, creatorID).Scan(
		&row.ID, &row.Name, &row.Description, &row.CreatorID,
	)
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "unique") {
			return nil, ErrSubjectExists
		}
		return nil, err
	}
	return &row, nil
}

func (s *Store) GetSubject(ctx context.Context, id int) (*SubjectRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row SubjectRow
	err := s.pool.QueryRow(ctx, `
SELECT id, name, description, creator_id FROM subjects WHERE id=$1`, id).Scan(
		&row.ID, &row.Name, &row.Description, &row.CreatorID,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) DeleteSubject(ctx context.Context, id int) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	tag, err := s.pool.Exec(ctx, `DELETE FROM subjects WHERE id=$1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}
