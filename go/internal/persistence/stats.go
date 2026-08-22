package persistence

import (
	"context"
	"fmt"
	"time"
)

type DashboardCounts struct {
	TotalUsers     int
	TotalExams     int
	PublishedExams int
	DraftExams     int
	UpcomingExams  int
	ActiveSessions int
	CompletedToday int
}

type RecentExam struct {
	ID              int
	Title           string
	DurationMinutes int
	StartTime       time.Time
	EndTime         time.Time
	Published       bool
}

func examScopeSQL(role string, userID int, args []any) (string, []any) {
	q := `COALESCE(e.is_deleted, false) = false`
	switch role {
	case "teacher":
		args = append(args, userID)
		q += fmt.Sprintf(` AND e.creator_id = $%d`, len(args))
	case "admin":
		q += ` AND COALESCE(cu.role, '') <> 'developer'`
	case "student", "guruplus":
		q += ` AND COALESCE(e.is_published, false) = true`
	}
	return q, args
}

func (s *Store) CountAllUsers(ctx context.Context) (int, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM users`).Scan(&n)
	return n, err
}

func (s *Store) DashboardCounts(ctx context.Context, userID int, role string) (DashboardCounts, error) {
	var out DashboardCounts
	if !s.HasPool() {
		return out, fmt.Errorf("no pgx pool")
	}
	where, args := examScopeSQL(role, userID, nil)
	join := ``
	if role == "admin" {
		join = ` JOIN users cu ON cu.id = e.creator_id`
	}
	err := s.pool.QueryRow(ctx, `
SELECT COUNT(*)::int,
       COUNT(*) FILTER (WHERE COALESCE(e.is_published, false) = true)::int,
       COUNT(*) FILTER (WHERE COALESCE(e.is_published, false) = false)::int,
       COUNT(*) FILTER (WHERE COALESCE(e.is_published, false) = true AND e.start_time > NOW())::int
  FROM exams e`+join+` WHERE `+where, args...).Scan(
		&out.TotalExams, &out.PublishedExams, &out.DraftExams, &out.UpcomingExams)
	if err != nil {
		return out, err
	}
	err = s.pool.QueryRow(ctx, `
SELECT COUNT(*)::int FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id`+join+`
 WHERE `+where+` AND es.status = 'in_progress' AND COALESCE(e.is_published, false) = true`, args...).Scan(&out.ActiveSessions)
	if err != nil {
		return out, err
	}
	err = s.pool.QueryRow(ctx, `
SELECT COUNT(*)::int FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id`+join+`
 WHERE `+where+` AND es.status = 'submitted'
   AND es.end_time >= date_trunc('day', NOW())
   AND es.end_time < date_trunc('day', NOW()) + interval '1 day'`, args...).Scan(&out.CompletedToday)
	return out, err
}

func (s *Store) RecentExams(ctx context.Context, userID int, role string, limit int) ([]RecentExam, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if limit <= 0 {
		limit = 5
	}
	where, args := examScopeSQL(role, userID, nil)
	join := ``
	if role == "admin" {
		join = ` JOIN users cu ON cu.id = e.creator_id`
	}
	args = append(args, limit)
	rows, err := s.pool.Query(ctx, `
SELECT e.id, e.title, e.duration_minutes, e.start_time, e.end_time, COALESCE(e.is_published, false)
  FROM exams e`+join+` WHERE `+where+`
 ORDER BY e.created_at DESC LIMIT $`+fmt.Sprint(len(args)), args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []RecentExam
	for rows.Next() {
		var row RecentExam
		if err := rows.Scan(&row.ID, &row.Title, &row.DurationMinutes, &row.StartTime, &row.EndTime, &row.Published); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}
