package httpserver_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"siab1/internal/config"
	"siab1/internal/httpserver"
)

func TestHealth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true}, nil)
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["status"] != "healthy" {
		t.Fatalf("status=%v", body["status"])
	}
	if body["app"] != "SIAB1" {
		t.Fatalf("app=%v", body["app"])
	}
	if body["version"] != "1.0.0" {
		t.Fatalf("version=%v", body["version"])
	}
	if body["runtime"] != "go" {
		t.Fatalf("runtime=%v", body["runtime"])
	}
}
