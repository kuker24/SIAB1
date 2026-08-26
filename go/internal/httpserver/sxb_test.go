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

func TestSXBAnswerWritesWithoutSecureClient(t *testing.T) {
	t.Setenv("ENFORCE_SXB", "true")
	h := httpserver.New(config.Config{EnforceSXB: true, DisableRateLimit: true}, nil)
	paths := []string{
		"/api/exams/auto-save",
		"/api/exams/auto-save-batch",
		"/api/exams/answer-journal/sync",
	}

	for _, path := range paths {
		t.Run(path, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, path, nil)
			req.Header.Set("User-Agent", "Mozilla/5.0")
			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, req)
			if rec.Code != http.StatusForbidden {
				t.Fatalf("status=%d want %d", rec.Code, http.StatusForbidden)
			}
		})
	}
}
