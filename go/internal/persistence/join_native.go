package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type JoinUserRow struct {
	ID           int
	Role         string
	StudentClass *string
	IsActive     bool
}

func (s *Store) LookupJoinUser(ctx context.Context, userID int) (*JoinUserRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row JoinUserRow
	err := s.pool.QueryRow(ctx, `
SELECT id, role, student_class, COALESCE(is_active, false)
  FROM users WHERE id = $1`, userID).Scan(&row.ID, &row.Role, &row.StudentClass, &row.IsActive)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

type JoinExamRow struct {
	ID              int
	Title           string
	Description     *string
	DurationMinutes int
	StartTime       time.Time
	EndTime         time.Time
	Published       bool
	MaxAttempts     int
	AllowedClasses  *string
	AllowedStudents *string
	CreatorRole     *string
}

func (e *JoinExamRow) AccessRow() *ExamRow {
	if e == nil {
		return nil
	}
	return &ExamRow{
		ID:              e.ID,
		AllowedClasses:  e.AllowedClasses,
		AllowedStudents: e.AllowedStudents,
		CreatorRole:     e.CreatorRole,
	}
}

func (s *Store) LookupJoinExamByToken(ctx context.Context, token string) (*JoinExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row JoinExamRow
	err := s.pool.QueryRow(ctx, `
SELECT e.id, e.title, e.description, e.duration_minutes, e.start_time, e.end_time,
       COALESCE(e.is_published, false), COALESCE(e.max_attempts, 1),
       e.allowed_classes, e.allowed_students, u.role
  FROM exams e
  JOIN users u ON u.id = e.creator_id
 WHERE e.access_token = $1`, token).Scan(
		&row.ID, &row.Title, &row.Description, &row.DurationMinutes, &row.StartTime, &row.EndTime,
		&row.Published, &row.MaxAttempts, &row.AllowedClasses, &row.AllowedStudents, &row.CreatorRole,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) CountJoinQuestions(ctx context.Context, examID int) (int, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM questions WHERE exam_id = $1`, examID).Scan(&n)
	return n, err
}
