package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

var (
	ErrPendingSchedule = errors.New("pending schedule exists")
	ErrScheduleState   = errors.New("schedule is not pending")
)

type ScheduleRow struct {
	ID           int
	ExamID       int
	PublishAt    time.Time
	UnpublishAt  *time.Time
	Status       string
	CreatedBy    *int
	CreatorRole  *string
	CreatedAt    time.Time
	ExecutedAt   *time.Time
	ErrorMessage *string
}

const scheduleSelect = `
SELECT s.id, s.exam_id, s.publish_at, s.unpublish_at, s.status, s.created_by,
       u.role, s.created_at, s.executed_at, s.error_message
  FROM scheduled_publications s LEFT JOIN users u ON u.id = s.created_by`

func scheduleScan(row *ScheduleRow) []any {
	return []any{&row.ID, &row.ExamID, &row.PublishAt, &row.UnpublishAt, &row.Status,
		&row.CreatedBy, &row.CreatorRole, &row.CreatedAt, &row.ExecutedAt, &row.ErrorMessage}
}

func (s *Store) CreateSchedule(ctx context.Context, examID, creatorID int, publishAt time.Time, unpublishAt *time.Time) (*ScheduleRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, examID); err != nil {
		return nil, err
	}
	var exists bool
	if err := tx.QueryRow(ctx, `
SELECT EXISTS(SELECT 1 FROM scheduled_publications WHERE exam_id=$1 AND status='pending')`, examID).Scan(&exists); err != nil {
		return nil, err
	}
	if exists {
		return nil, ErrPendingSchedule
	}
	var id int
	if err := tx.QueryRow(ctx, `
INSERT INTO scheduled_publications (exam_id,publish_at,unpublish_at,status,created_by,created_at)
VALUES ($1,$2,$3,'pending',$4,NOW()) RETURNING id`, examID, publishAt, unpublishAt, creatorID).Scan(&id); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.GetSchedule(ctx, id)
}

func (s *Store) GetSchedule(ctx context.Context, scheduleID int) (*ScheduleRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row ScheduleRow
	err := s.pool.QueryRow(ctx, scheduleSelect+" WHERE s.id=$1", scheduleID).Scan(scheduleScan(&row)...)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) ListExamSchedules(ctx context.Context, examID int) ([]ScheduleRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, scheduleSelect+` WHERE s.exam_id=$1 ORDER BY s.created_at DESC, s.id DESC`, examID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []ScheduleRow{}
	for rows.Next() {
		var row ScheduleRow
		if err := rows.Scan(scheduleScan(&row)...); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) ListUpcomingSchedules(ctx context.Context, limit int) ([]ScheduleRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, scheduleSelect+` WHERE s.status='pending' ORDER BY s.publish_at LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []ScheduleRow{}
	for rows.Next() {
		var row ScheduleRow
		if err := rows.Scan(scheduleScan(&row)...); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func (s *Store) ScheduleStats(ctx context.Context) (map[string]int, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	out := map[string]int{"pending": 0, "published": 0, "unpublished": 0, "cancelled": 0}
	rows, err := s.pool.Query(ctx, `SELECT status,COUNT(*) FROM scheduled_publications GROUP BY status`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var status string
		var count int
		if err := rows.Scan(&status, &count); err != nil {
			return nil, err
		}
		if _, ok := out[status]; ok {
			out[status] = count
		}
	}
	return out, rows.Err()
}

func (s *Store) CancelSchedule(ctx context.Context, scheduleID int) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	tag, err := s.pool.Exec(ctx, `
UPDATE scheduled_publications SET status='cancelled'
 WHERE id=$1 AND status='pending'`, scheduleID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrScheduleState
	}
	return nil
}

func (s *Store) ProcessScheduledPublications(ctx context.Context, now time.Time) (published, unpublished int, err error) {
	if !s.HasPool() {
		return 0, 0, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, 0, err
	}
	defer tx.Rollback(ctx)
	rows, err := tx.Query(ctx, `
SELECT id, exam_id FROM scheduled_publications
 WHERE status='pending' AND publish_at <= $1
 ORDER BY publish_at FOR UPDATE SKIP LOCKED LIMIT 200`, now)
	if err != nil {
		return 0, 0, err
	}
	type due struct{ scheduleID, examID int }
	var publishDue []due
	for rows.Next() {
		var item due
		if err := rows.Scan(&item.scheduleID, &item.examID); err != nil {
			rows.Close()
			return 0, 0, err
		}
		publishDue = append(publishDue, item)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, 0, err
	}
	for _, item := range publishDue {
		tag, err := tx.Exec(ctx, `UPDATE exams SET is_published=true,updated_at=$2 WHERE id=$1`, item.examID, now)
		if err != nil {
			return 0, 0, err
		}
		if tag.RowsAffected() == 0 {
			if _, err := tx.Exec(ctx, `UPDATE scheduled_publications SET status='cancelled',error_message='Exam not found' WHERE id=$1`, item.scheduleID); err != nil {
				return 0, 0, err
			}
			continue
		}
		if _, err := tx.Exec(ctx, `UPDATE scheduled_publications SET status='published',executed_at=$2,error_message=NULL WHERE id=$1`, item.scheduleID, now); err != nil {
			return 0, 0, err
		}
		published++
	}
	rows, err = tx.Query(ctx, `
SELECT id, exam_id FROM scheduled_publications
 WHERE status='published' AND unpublish_at IS NOT NULL AND unpublish_at <= $1
 ORDER BY unpublish_at FOR UPDATE SKIP LOCKED LIMIT 200`, now)
	if err != nil {
		return 0, 0, err
	}
	var unpublishDue []due
	for rows.Next() {
		var item due
		if err := rows.Scan(&item.scheduleID, &item.examID); err != nil {
			rows.Close()
			return 0, 0, err
		}
		unpublishDue = append(unpublishDue, item)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, 0, err
	}
	for _, item := range unpublishDue {
		if _, err := tx.Exec(ctx, `UPDATE exams SET is_published=false,updated_at=$2 WHERE id=$1`, item.examID, now); err != nil {
			return 0, 0, err
		}
		if _, err := tx.Exec(ctx, `UPDATE scheduled_publications SET status='unpublished',executed_at=$2 WHERE id=$1`, item.scheduleID, now); err != nil {
			return 0, 0, err
		}
		unpublished++
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, 0, err
	}
	return published, unpublished, nil
}
