package httpserver_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"siab1/internal/config"
	"siab1/internal/httpserver"
)

func TestSXBExamWithoutSEB(t *testing.T) {
	t.Setenv("ENFORCE_SXB", "true")
	h := httpserver.New(config.Config{EnforceSXB: true, DisableRateLimit: true}, nil)
	req := httptest.NewRequest(http.MethodGet, "/student/exam.html", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusSeeOther && rec.Code != http.StatusForbidden {
		t.Fatalf("status=%d want 303 or 403", rec.Code)
	}
}

func TestSXBExamWithExambro(t *testing.T) {
	t.Setenv("ENFORCE_SXB", "true")
	h := httpserver.New(config.Config{EnforceSXB: true, DisableRateLimit: true}, nil)
	req := httptest.NewRequest(http.MethodGet, "/student/exam.html", nil)
	req.Header.Set("User-Agent", "Exambro")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code == http.StatusForbidden {
		t.Fatalf("SXB blocked Exambro UA")
	}
}
