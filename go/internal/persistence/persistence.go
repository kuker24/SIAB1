package persistence

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/url"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

const closeExpiredSQL = `
UPDATE exam_sessions es
SET status = 'submitted',
    end_time = COALESCE(es.end_time, NOW())
FROM exams e
WHERE es.exam_id = e.id
  AND es.status = 'in_progress'
  AND es.start_time IS NOT NULL
  AND e.duration_minutes IS NOT NULL
  AND (es.start_time + make_interval(mins => e.duration_minutes) + interval '5 minutes') < NOW()
`

type Store struct {
	pgAddr    string
	redisAddr string
	pgDSN     string
	pool      *pgxpool.Pool
}

func Connect(databaseURL, redisURL string) *Store {
	s := &Store{}
	if databaseURL != "" {
		s.pgDSN = StripAsyncPG(databaseURL)
		s.pgAddr = hostPortFromURL(s.pgDSN, 5432)
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		pool, err := pgxpool.New(ctx, s.pgDSN)
		if err == nil {
			if err := pool.Ping(ctx); err == nil {
				s.pool = pool
			} else {
				pool.Close()
			}
		}
	}
	if redisURL != "" {
		s.redisAddr = hostPortFromURL(redisURL, 6379)
	}
	return s
}

func StripAsyncPG(raw string) string {
	return strings.ReplaceAll(raw, "+asyncpg", "")
}

func (s *Store) HasDatabase() bool {
	return s != nil && s.pgAddr != ""
}

func (s *Store) PingDB(ctx context.Context) bool {
	if !s.HasDatabase() {
		return false
	}
	if s.pool != nil {
		if err := s.pool.Ping(ctx); err == nil {
			return true
		}
	}
	return dialOK(ctx, s.pgAddr)
}

func (s *Store) PingRedis(ctx context.Context) bool {
	if s == nil || s.redisAddr == "" {
		return false
	}
	d := net.Dialer{}
	conn, err := d.DialContext(ctx, "tcp", s.redisAddr)
	if err != nil {
		return false
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(2 * time.Second))
	_, _ = conn.Write([]byte("*1\r\n$4\r\nPING\r\n"))
	buf := make([]byte, 64)
	n, err := conn.Read(buf)
	if err != nil && err != io.EOF {
		return false
	}
	return n > 0
}

func (s *Store) CloseExpiredSessions(ctx context.Context) (int64, error) {
	if s == nil || s.pool == nil {
		return 0, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `
SELECT COUNT(*) FROM information_schema.columns
WHERE table_schema = 'public'
  AND (
    (table_name = 'exam_sessions' AND column_name IN ('id','status','start_time','end_time','exam_id'))
    OR (table_name = 'exams' AND column_name IN ('id','duration_minutes'))
  )`).Scan(&n)
	if err != nil || n < 7 {
		return 0, fmt.Errorf("simple columns missing")
	}
	tag, err := s.pool.Exec(ctx, closeExpiredSQL)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

func (s *Store) Close() {
	if s != nil && s.pool != nil {
		s.pool.Close()
		s.pool = nil
	}
}

func hostPortFromURL(raw string, defaultPort int) string {
	if !strings.Contains(raw, "://") {
		raw = "tcp://" + raw
	}
	u, err := url.Parse(raw)
	if err != nil {
		return ""
	}
	host := u.Hostname()
	if host == "" {
		return ""
	}
	port := u.Port()
	if port == "" {
		port = fmt.Sprintf("%d", defaultPort)
	}
	return net.JoinHostPort(host, port)
}

func dialOK(ctx context.Context, addr string) bool {
	d := net.Dialer{}
	c, err := d.DialContext(ctx, "tcp", addr)
	if err != nil {
		return false
	}
	_ = c.Close()
	return true
}
