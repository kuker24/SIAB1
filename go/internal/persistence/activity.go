package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type ActivityFilter struct {
	UserID    int
	EventType string
	DateFrom  *time.Time
	DateTo    *time.Time
	Limit     int
	Offset    int
}

type ActivityRow struct {
	ID        int
	UserID    *int
	UserName  string
	UserRole  *string
	EventType string
	EventData []byte
	IPAddress *string
	CreatedAt time.Time
}

type ActivityCount struct {
	Name  string
	Count int
}

type ActivityStatsRow struct {
	Total    int
	ByType   []ActivityCount
	ByDay    []ActivityCount
	TopUsers []ActivityUserCount
}

type ActivityUserCount struct {
	UserID   int
	UserName string
	Count    int
}

func (s *Store) ListActivity(ctx context.Context, f ActivityFilter) ([]ActivityRow, int, error) {
	if !s.HasPool() {
		return nil, 0, fmt.Errorf("no pgx pool")
	}
	where, args := []string{}, []any{}
	add := func(sql string, value any) {
		args = append(args, value)
		where = append(where, fmt.Sprintf(sql, len(args)))
	}
	if f.UserID > 0 {
		add("l.user_id = $%d", f.UserID)
	}
	if f.EventType != "" {
		add("l.event_type = $%d", f.EventType)
	}
	if f.DateFrom != nil {
		add("l.created_at >= $%d", *f.DateFrom)
	}
	if f.DateTo != nil {
		add("l.created_at <= $%d", *f.DateTo)
	}
	clause := ""
	if len(where) > 0 {
		clause = " WHERE " + strings.Join(where, " AND ")
	}
	var total int
	if err := s.pool.QueryRow(ctx, "SELECT COUNT(*) FROM user_activity_logs l"+clause, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	args = append(args, f.Limit, f.Offset)
	rows, err := s.pool.Query(ctx, `
SELECT l.id, l.user_id, COALESCE(u.full_name, 'Unknown'), u.role,
       l.event_type, COALESCE(l.event_data, '{}'::jsonb), l.ip_address, l.created_at
  FROM user_activity_logs l LEFT JOIN users u ON u.id = l.user_id`+clause+fmt.Sprintf(`
 ORDER BY l.created_at DESC, l.id DESC LIMIT $%d OFFSET $%d`, len(args)-1, len(args)), args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	out := []ActivityRow{}
	for rows.Next() {
		var row ActivityRow
		if err := rows.Scan(&row.ID, &row.UserID, &row.UserName, &row.UserRole, &row.EventType,
			&row.EventData, &row.IPAddress, &row.CreatedAt); err != nil {
			return nil, 0, err
		}
		out = append(out, row)
	}
	return out, total, rows.Err()
}

func (s *Store) ActivityStats(ctx context.Context, since time.Time) (*ActivityStatsRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var out ActivityStatsRow
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM user_activity_logs WHERE created_at >= $1`, since).Scan(&out.Total); err != nil {
		return nil, err
	}
	rows, err := s.pool.Query(ctx, `
SELECT event_type, COUNT(*) FROM user_activity_logs
 WHERE created_at >= $1 GROUP BY event_type`, since)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var row ActivityCount
		if err := rows.Scan(&row.Name, &row.Count); err != nil {
			rows.Close()
			return nil, err
		}
		out.ByType = append(out.ByType, row)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}
	rows, err = s.pool.Query(ctx, `
SELECT TO_CHAR(timezone('Asia/Jakarta', created_at), 'YYYY-MM-DD'), COUNT(*)
  FROM user_activity_logs WHERE created_at >= $1
 GROUP BY 1 ORDER BY 1`, since)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var row ActivityCount
		if err := rows.Scan(&row.Name, &row.Count); err != nil {
			rows.Close()
			return nil, err
		}
		out.ByDay = append(out.ByDay, row)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}
	rows, err = s.pool.Query(ctx, `
SELECT u.id, COALESCE(u.full_name, u.username, ''), COUNT(l.id)
  FROM users u JOIN user_activity_logs l ON l.user_id = u.id
 WHERE l.created_at >= $1 GROUP BY u.id, u.full_name, u.username
 ORDER BY COUNT(l.id) DESC LIMIT 10`, since)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var row ActivityUserCount
		if err := rows.Scan(&row.UserID, &row.UserName, &row.Count); err != nil {
			return nil, err
		}
		out.TopUsers = append(out.TopUsers, row)
	}
	return &out, rows.Err()
}

func (s *Store) ResetActivity(ctx context.Context, mode string, retentionDays, maxRows int) (before, deleted, remaining int, err error) {
	if !s.HasPool() {
		return 0, 0, 0, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, 0, 0, err
	}
	defer tx.Rollback(ctx)
	if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM user_activity_logs`).Scan(&before); err != nil {
		return 0, 0, 0, err
	}
	if mode == "all" {
		if _, err := tx.Exec(ctx, `TRUNCATE TABLE user_activity_logs RESTART IDENTITY`); err != nil {
			return 0, 0, 0, err
		}
	} else {
		cutoff := time.Now().UTC().AddDate(0, 0, -retentionDays)
		if _, err := tx.Exec(ctx, `DELETE FROM user_activity_logs WHERE created_at < $1`, cutoff); err != nil {
			return 0, 0, 0, err
		}
		var current int
		if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM user_activity_logs`).Scan(&current); err != nil {
			return 0, 0, 0, err
		}
		if overflow := current - maxRows; overflow > 0 {
			if _, err := tx.Exec(ctx, `
DELETE FROM user_activity_logs WHERE id IN (
  SELECT id FROM user_activity_logs ORDER BY created_at, id LIMIT $1
)`, overflow); err != nil {
				return 0, 0, 0, err
			}
		}
	}
	if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM user_activity_logs`).Scan(&remaining); err != nil {
		return 0, 0, 0, err
	}
	deleted = before - remaining
	if err := tx.Commit(ctx); err != nil {
		return 0, 0, 0, err
	}
	return before, deleted, remaining, nil
}
