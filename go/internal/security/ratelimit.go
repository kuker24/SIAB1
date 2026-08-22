package security

import (
	"encoding/json"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
)

type rateLimiter struct {
	mu       sync.Mutex
	window   time.Duration
	maxRead  int
	maxWrite int
	maxLogin int
	hits     map[string][]time.Time
}

func RateLimit(next http.Handler) http.Handler {
	rl := &rateLimiter{
		window:   time.Minute,
		maxRead:  1000,
		maxWrite: 300,
		maxLogin: 2000,
		hits:     make(map[string][]time.Time),
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key, limit := rl.keyAndLimit(r)
		if !rl.allow(key, limit) {
			w.Header().Set("Retry-After", "60")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"detail":      "Terlalu banyak request. Coba lagi dalam beberapa menit.",
				"retry_after": 60,
			})
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (rl *rateLimiter) keyAndLimit(r *http.Request) (string, int) {
	ip := clientIP(r)
	path := r.URL.Path
	limit := rl.maxRead
	if r.Method == http.MethodPost || r.Method == http.MethodPut || r.Method == http.MethodPatch || r.Method == http.MethodDelete {
		limit = rl.maxWrite
		if strings.HasPrefix(path, "/api/auth/login") || strings.HasPrefix(path, "/api/auth/signin") {
			limit = rl.maxLogin
		}
	}
	return ip + ":" + r.Method, limit
}

func (rl *rateLimiter) allow(key string, limit int) bool {
	now := time.Now()
	cutoff := now.Add(-rl.window)
	rl.mu.Lock()
	defer rl.mu.Unlock()
	q := rl.hits[key]
	i := 0
	for i < len(q) && q[i].Before(cutoff) {
		i++
	}
	if i > 0 {
		q = q[i:]
	}
	if len(q) >= limit {
		rl.hits[key] = q
		return false
	}
	rl.hits[key] = append(q, now)
	return true
}

func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		if i := len(xff); i > 0 {
			for _, p := range []string{xff} {
				if comma := indexByte(p, ','); comma >= 0 {
					p = p[:comma]
				}
				return trim(p)
			}
		}
	}
	if realIP := r.Header.Get("X-Real-IP"); realIP != "" {
		return realIP
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func indexByte(s string, c byte) int {
	for i := 0; i < len(s); i++ {
		if s[i] == c {
			return i
		}
	}
	return -1
}

func trim(s string) string {
	for len(s) > 0 && (s[0] == ' ' || s[0] == '\t') {
		s = s[1:]
	}
	for len(s) > 0 && (s[len(s)-1] == ' ' || s[len(s)-1] == '\t') {
		s = s[:len(s)-1]
	}
	return s
}
