package auth

import (
	"sync"
	"time"
)

const (
	MaxLoginAttempts   = 5
	LoginRateLimit     = 120
	LoginRateWindow    = time.Minute
	LoginLockoutWindow = 15 * time.Minute
)

type loginGate struct {
	mu       sync.Mutex
	attempts map[string][]time.Time
	failures map[string][]time.Time
	lockouts map[string]time.Time
}

var gate = &loginGate{
	attempts: map[string][]time.Time{},
	failures: map[string][]time.Time{},
	lockouts: map[string]time.Time{},
}

func prune(buf []time.Time, window time.Duration, now time.Time) []time.Time {
	cut := now.Add(-window)
	i := 0
	for i < len(buf) && !buf[i].After(cut) {
		i++
	}
	if i == 0 {
		return buf
	}
	return buf[i:]
}

func AllowLoginAttempt(key string) (ok bool, remaining int) {
	now := time.Now()
	gate.mu.Lock()
	defer gate.mu.Unlock()
	buf := prune(gate.attempts[key], LoginRateWindow, now)
	if len(buf) >= LoginRateLimit {
		gate.attempts[key] = buf
		return false, 0
	}
	buf = append(buf, now)
	gate.attempts[key] = buf
	return true, LoginRateLimit - len(buf)
}

func LockoutRemainingMinutes(key string) int {
	now := time.Now()
	gate.mu.Lock()
	defer gate.mu.Unlock()
	until, found := gate.lockouts[key]
	if !found {
		return 0
	}
	if !until.After(now) {
		delete(gate.lockouts, key)
		delete(gate.failures, key)
		return 0
	}
	mins := int(until.Sub(now).Minutes()) + 1
	if mins < 1 {
		return 1
	}
	return mins
}

func RecordLoginFailure(key string) (attempts int, warning string) {
	now := time.Now()
	gate.mu.Lock()
	defer gate.mu.Unlock()
	buf := prune(gate.failures[key], LoginLockoutWindow, now)
	buf = append(buf, now)
	gate.failures[key] = buf
	attempts = len(buf)
	if attempts >= MaxLoginAttempts {
		gate.lockouts[key] = now.Add(LoginLockoutWindow)
		return attempts, "Terlalu banyak percobaan gagal. Akun dikunci sementara."
	}
	if attempts >= MaxLoginAttempts-1 {
		return attempts, "Sisa 1 percobaan sebelum akun dikunci sementara."
	}
	return attempts, ""
}

func ClearLoginFailures(key string) {
	gate.mu.Lock()
	defer gate.mu.Unlock()
	delete(gate.failures, key)
	delete(gate.lockouts, key)
}
