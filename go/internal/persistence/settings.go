package persistence

import (
	"context"
	"fmt"
)

func (s *Store) SystemTimezone(ctx context.Context) (string, error) {
	if !s.HasPool() {
		return "", fmt.Errorf("no pgx pool")
	}
	var timezone string
	if err := s.pool.QueryRow(ctx, `
SELECT COALESCE((SELECT timezone FROM system_settings ORDER BY id LIMIT 1), 'Asia/Jakarta')`).Scan(&timezone); err != nil {
		return "", err
	}
	return timezone, nil
}
