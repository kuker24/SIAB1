package httpserver_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"siab1/internal/auth"
	"siab1/internal/config"
	"siab1/internal/httpserver"
)

func TestAutoSaveRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams/auto-save", bytes.NewBufferString(`{"session_id":1,"answers":{}}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestAutoSaveRejectsBadToken(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams/auto-save", bytes.NewBufferString(`{"session_id":1,"answers":{}}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer not-a-jwt")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestJWTRoundTrip120Minutes(t *testing.T) {
	if auth.ExamJWTExpiryMinutes != 120 {
		t.Fatalf("jwt minutes=%d", auth.ExamJWTExpiryMinutes)
	}
	tok, err := auth.SignUser("test-secret", 9, "siswa", "student", "Nama", "XII", true)
	if err != nil {
		t.Fatal(err)
	}
	claims, err := auth.Parse("test-secret", tok)
	if err != nil {
		t.Fatal(err)
	}
	if claims.Username != "siswa" || claims.Role != "student" {
		t.Fatalf("claims=%+v", claims)
	}
	id, err := claims.UserID()
	if err != nil || id != 9 {
		t.Fatalf("id=%d err=%v", id, err)
	}
}

func TestRuntimePolicyNoAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, ExamPeakMode: true}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/runtime/policy", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["mode"] != "exam_peak" {
		t.Fatalf("mode=%v", body["mode"])
	}
	if body["final_submit_priority"] != true {
		t.Fatalf("priority=%v", body["final_submit_priority"])
	}
}

func TestStartExamRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams/1/start", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestMeRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/auth/me", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestLoginWithoutPoolFallsClosed(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/auth/student/login", bytes.NewBufferString(`{"username":"a","password":"b"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable && rec.Code != http.StatusUnauthorized {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestSubmitExamRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams/submit", bytes.NewBufferString(`{"session_id":1}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestBatchAutoSaveRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams/auto-save-batch", bytes.NewBufferString(`{"session_id":1,"answers":[]}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestLogViolationRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams/log-violation", bytes.NewBufferString(`{"session_id":1,"event_type":"tab_switch"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestSessionStatusRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/exams/session/1/status", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestJoinExamRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams/join", bytes.NewBufferString(`{"token":"ABC123"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestListExamsRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/exams?published_only=true", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestRefreshRequiresToken(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/auth/refresh", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestStudentNamespaceRewritesRuntimePolicy(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, ExamPeakMode: true}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/student/runtime/policy", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestMyResultsRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/exams/my-results", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestValidateAPKTokenNoPool(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/validate-apk-token", bytes.NewBufferString(`{"token":"BUILD-20260125120000-ABC123"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestWSHealth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true}, nil)
	req := httptest.NewRequest(http.MethodGet, "/ws/health", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestAdminLoginLaneWithoutPool(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/control/auth/login", bytes.NewBufferString(`{"username":"a","password":"b"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable && rec.Code != http.StatusUnauthorized {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestAdminNamespaceRewritesMe(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/admin/auth/me", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestExamResultsRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/exams/3/results", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestQuestionsAllRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/questions/3/all", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestUsersRequireAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	for _, req := range []*http.Request{
		httptest.NewRequest(http.MethodGet, "/api/users", nil),
		httptest.NewRequest(http.MethodGet, "/api/users/advanced-search", nil),
		httptest.NewRequest(http.MethodPost, "/api/users", bytes.NewBufferString(`{"username":"abc","password":"secret1","full_name":"A"}`)),
		httptest.NewRequest(http.MethodGet, "/api/users/3", nil),
		httptest.NewRequest(http.MethodPut, "/api/users/3", bytes.NewBufferString(`{"full_name":"B"}`)),
		httptest.NewRequest(http.MethodDelete, "/api/users/3", nil),
		httptest.NewRequest(http.MethodPost, "/api/users/batch-create", bytes.NewBufferString(`[]`)),
		httptest.NewRequest(http.MethodGet, "/api/stats/dashboard", nil),
		httptest.NewRequest(http.MethodGet, "/api/exams/1/sessions/2/review", nil),
		httptest.NewRequest(http.MethodGet, "/api/exams/1/analytics", nil),
		httptest.NewRequest(http.MethodGet, "/api/analytics/exam/1/classes", nil),
		httptest.NewRequest(http.MethodGet, "/api/analytics/exam/1/question-difficulty", nil),
		httptest.NewRequest(http.MethodGet, "/api/analytics/dashboard", nil),
		httptest.NewRequest(http.MethodGet, "/api/analytics/class?class_name=X", nil),
		httptest.NewRequest(http.MethodGet, "/api/analytics/exam/1/assessment?class_name=X", nil),
		httptest.NewRequest(http.MethodGet, "/api/monitoring/violations", nil),
		httptest.NewRequest(http.MethodGet, "/api/activity/logs", nil),
		httptest.NewRequest(http.MethodGet, "/api/activity/stats", nil),
		httptest.NewRequest(http.MethodDelete, "/api/activity/logs/reset?mode=all", nil),
		httptest.NewRequest(http.MethodPost, "/api/scheduled/exams/1/schedule", bytes.NewBufferString(`{}`)),
		httptest.NewRequest(http.MethodGet, "/api/scheduled/exams/1/schedules", nil),
		httptest.NewRequest(http.MethodDelete, "/api/scheduled/schedules/1", nil),
		httptest.NewRequest(http.MethodGet, "/api/scheduled/schedules/upcoming", nil),
		httptest.NewRequest(http.MethodGet, "/api/scheduled/schedules/stats", nil),
		httptest.NewRequest(http.MethodGet, "/api/v1/settings/timezone", nil),
		httptest.NewRequest(http.MethodPost, "/api/questions/search", bytes.NewBufferString(`{}`)),
		httptest.NewRequest(http.MethodGet, "/api/grading/pending-essays", nil),
		httptest.NewRequest(http.MethodGet, "/api/grading/stats", nil),
		httptest.NewRequest(http.MethodPost, "/api/grading/grade-essay", bytes.NewBufferString(`{"answer_id":1,"points_earned":1}`)),
		httptest.NewRequest(http.MethodPost, "/api/grading/batch-grade", bytes.NewBufferString(`{"grades":[]}`)),
		httptest.NewRequest(http.MethodGet, "/api/grading/answer/1", nil),
		httptest.NewRequest(http.MethodPost, "/api/exams/sessions/3/emergency-exit", nil),
		httptest.NewRequest(http.MethodPost, "/api/exams/1/cleanup-sessions", nil),
	} {
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("%s %s status=%d", req.Method, req.URL.Path, rec.Code)
		}
	}
}

func TestSessionControlRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	for _, req := range []*http.Request{
		httptest.NewRequest(http.MethodPost, "/api/monitoring/sessions/3/kick", bytes.NewBufferString(`{}`)),
		httptest.NewRequest(http.MethodGet, "/api/monitoring/sessions/3/recovery-status", nil),
		httptest.NewRequest(http.MethodPost, "/api/monitoring/sessions/3/reset", bytes.NewBufferString(`{}`)),
		httptest.NewRequest(http.MethodPost, "/api/exams/sessions/3/force-submit", nil),
	} {
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("%s %s status=%d", req.Method, req.URL.Path, rec.Code)
		}
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/monitoring/violation-types", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("violation-types status=%d", rec.Code)
	}
}

func TestMonitoringRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	for _, req := range []*http.Request{
		httptest.NewRequest(http.MethodGet, "/api/monitoring/active-exams", nil),
		httptest.NewRequest(http.MethodGet, "/api/monitoring/exam/3/live-stats", nil),
		httptest.NewRequest(http.MethodGet, "/api/monitoring/exam/3/sessions", nil),
		httptest.NewRequest(http.MethodPost, "/api/exams/3/pause-all", nil),
		httptest.NewRequest(http.MethodPost, "/api/exams/3/resume-all", nil),
	} {
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("%s %s status=%d", req.Method, req.URL.Path, rec.Code)
		}
	}
}

func TestSubjectsAndClassesRequireAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	for _, req := range []*http.Request{
		httptest.NewRequest(http.MethodGet, "/api/subjects", nil),
		httptest.NewRequest(http.MethodPost, "/api/subjects", bytes.NewBufferString(`{"name":"Kimia"}`)),
		httptest.NewRequest(http.MethodGet, "/api/users/student-classes", nil),
		httptest.NewRequest(http.MethodGet, "/api/users/students-by-class?student_class=XII", nil),
	} {
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("%s %s status=%d", req.Method, req.URL.Path, rec.Code)
		}
	}
}

func TestPreviewAndBankRequireAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	for _, req := range []*http.Request{
		httptest.NewRequest(http.MethodGet, "/api/exams/3/preview", nil),
		httptest.NewRequest(http.MethodPost, "/api/exams/3/duplicate", nil),
		httptest.NewRequest(http.MethodPost, "/api/exams/3/regenerate-token", nil),
		httptest.NewRequest(http.MethodGet, "/api/questions/categories", nil),
		httptest.NewRequest(http.MethodGet, "/api/questions/tags", nil),
	} {
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("%s %s status=%d", req.Method, req.URL.Path, rec.Code)
		}
	}
}

func TestQuestionWriteRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	for _, req := range []*http.Request{
		httptest.NewRequest(http.MethodPost, "/api/questions/3", bytes.NewBufferString(`{}`)),
		httptest.NewRequest(http.MethodPut, "/api/questions/3", bytes.NewBufferString(`{}`)),
		httptest.NewRequest(http.MethodDelete, "/api/questions/3", nil),
	} {
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
			t.Fatalf("%s %s status=%d", req.Method, req.URL.Path, rec.Code)
		}
	}
}

func TestCreateExamRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams", bytes.NewBufferString(`{"title":"x","duration_minutes":60,"start_time":"2026-01-01T00:00:00Z","end_time":"2026-01-01T01:00:00Z"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestPauseStatusRequiresAuth(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/exams/3/pause-status", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestAPKVersion(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/apk/version", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestDefaultSEBConfigDisabled(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/exams/default-seb-config.seb", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestDefaultSEBConfigEnabled(t *testing.T) {
	h := httpserver.New(config.Config{
		DisableRateLimit:         true,
		SEBDesktopLegacy:         true,
		SEBDefaultConfigKey:      "k",
		SEBDefaultBrowserExamKey: "b",
		BaseURL:                  "https://exam.example",
	}, nil)
	req := httptest.NewRequest(http.MethodGet, "/api/seb/download-config", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/seb" {
		t.Fatalf("content-type=%s", ct)
	}
	if !bytes.Contains(rec.Body.Bytes(), []byte("startURL")) {
		t.Fatal("missing startURL")
	}
}

func TestExamWebSocketRequiresUpgrade(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodGet, "/ws/exam/1/1", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestSubmitAnswerJSONDetail(t *testing.T) {
	h := httpserver.New(config.Config{DisableRateLimit: true, JWTSecretKey: "test-secret"}, nil)
	req := httptest.NewRequest(http.MethodPost, "/api/exams/submit-answer", bytes.NewBufferString(`{}`))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	var body map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if _, ok := body["detail"]; !ok && rec.Code >= 400 {
		if rec.Code != http.StatusServiceUnavailable && rec.Code != http.StatusUnauthorized {
			t.Fatalf("missing detail status=%d body=%s", rec.Code, rec.Body.String())
		}
	}
}
