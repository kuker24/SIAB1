package auth

import (
	"testing"

	"golang.org/x/crypto/bcrypt"
)

func TestVerifyPassword(t *testing.T) {
	hash, err := bcrypt.GenerateFromPassword([]byte("rahasia"), bcrypt.DefaultCost)
	if err != nil {
		t.Fatal(err)
	}
	if !VerifyPassword("rahasia", string(hash)) {
		t.Fatal("expected match")
	}
	if VerifyPassword("salah", string(hash)) {
		t.Fatal("expected mismatch")
	}
}

func TestLockoutAfterFiveFailures(t *testing.T) {
	key := "lockout-test:127.0.0.1"
	ClearLoginFailures(key)
	for i := 0; i < MaxLoginAttempts; i++ {
		RecordLoginFailure(key)
	}
	if mins := LockoutRemainingMinutes(key); mins <= 0 {
		t.Fatalf("expected lockout, remaining=%d", mins)
	}
	ClearLoginFailures(key)
	if mins := LockoutRemainingMinutes(key); mins != 0 {
		t.Fatalf("cleared remaining=%d", mins)
	}
}
