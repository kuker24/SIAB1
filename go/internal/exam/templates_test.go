package exam

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"siab1/internal/config"
	"siab1/internal/persistence"
)

func TestTemplateRoutesAreNativeWithBothCollectionForms(t *testing.T) {
	mux := http.NewServeMux()
	Register(mux, nil, config.Config{}, nil)
	tests := []struct {
		method string
		path   string
	}{
		{http.MethodGet, "/api/templates"},
		{http.MethodGet, "/api/templates/"},
		{http.MethodPost, "/api/templates"},
		{http.MethodPost, "/api/templates/"},
		{http.MethodGet, "/api/templates/7"},
		{http.MethodPut, "/api/templates/7"},
		{http.MethodDelete, "/api/templates/7"},
		{http.MethodPost, "/api/templates/7/create-exam"},
	}
	for _, tc := range tests {
		req := httptest.NewRequest(tc.method, tc.path, bytes.NewBufferString(`{}`))
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)
		if rec.Code != http.StatusServiceUnavailable {
			t.Errorf("%s %s status=%d body=%s", tc.method, tc.path, rec.Code, rec.Body.String())
		}
	}
}

func TestTemplateCanAccessHonorsOwnershipAdminAndDeveloperHiding(t *testing.T) {
	ownerID := 9
	teacher := "teacher"
	developer := "developer"
	private := &persistence.TemplateRow{CreatorID: &ownerID, CreatorRole: &teacher}
	if ok, hidden := templateCanAccess(private, ownerID, "teacher", false); !ok || hidden {
		t.Fatal("owner should read private template")
	}
	if ok, hidden := templateCanAccess(private, 10, "teacher", false); ok || hidden {
		t.Fatal("other teacher should receive forbidden, not hidden")
	}
	if ok, hidden := templateCanAccess(private, 10, "admin", true); !ok || hidden {
		t.Fatal("admin should mutate non-developer template")
	}
	private.CreatorRole = &developer
	if ok, hidden := templateCanAccess(private, ownerID, "admin", false); ok || !hidden {
		t.Fatal("developer template should be hidden from admin even when ids coincide")
	}
	if ok, hidden := templateCanAccess(private, ownerID, "developer", true); !ok || hidden {
		t.Fatal("developer owner should mutate developer template")
	}
}

func TestBuildTemplateExamMergesOverridesAndCopiesQuestions(t *testing.T) {
	start := time.Date(2026, time.August, 22, 1, 0, 0, 0, time.UTC)
	end := start.Add(time.Hour)
	duration := 90
	raw := []byte(`{
  "duration_minutes": 45,
  "passing_score": 75,
  "max_attempts": 2,
  "shuffle_questions": true,
  "show_results": false,
  "questions": [{
    "question_text": "Dua tambah dua?",
    "options": [{"option_text": "4", "is_correct": true}]
  }]
}`)
	write, err := buildTemplateExam(raw, templateExamPayload{
		Title: "Ujian Matematika", DurationMinutes: &duration,
	}, start, end)
	if err != nil {
		t.Fatal(err)
	}
	if write.Exam.DurationMinutes != 90 || write.Exam.PassingScore == nil || *write.Exam.PassingScore != 75 {
		t.Fatalf("merged numeric defaults: %+v", write.Exam)
	}
	if write.Exam.MaxAttempts != 2 || !write.Exam.ShuffleQuestions || write.Exam.ShowResults {
		t.Fatalf("merged flags: %+v", write.Exam)
	}
	if write.Exam.Published {
		t.Fatal("template exam must be created as draft")
	}
	if len(write.Questions) != 1 || write.Questions[0].Type != "multiple_choice" || write.Questions[0].Difficulty != "medium" {
		t.Fatalf("question defaults: %+v", write.Questions)
	}
	question := write.Questions[0]
	if question.Points != 1 || len(question.Options) != 1 || question.Options[0].Group != "standard" || !question.Options[0].Correct {
		t.Fatalf("option defaults: %+v", question)
	}
}

func TestBuildTemplateExamUsesPythonDefaultsAndFalsyScoreFallback(t *testing.T) {
	zero := 0.0
	write, err := buildTemplateExam(
		[]byte(`{"passing_score": 80}`),
		templateExamPayload{Title: "Ujian", PassingScore: &zero},
		time.Time{}, time.Time{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if write.Exam.DurationMinutes != 60 || write.Exam.PassingScore == nil || *write.Exam.PassingScore != 80 || write.Exam.MaxAttempts != 1 {
		t.Fatalf("numeric defaults: %+v", write.Exam)
	}
	if !write.Exam.ShowResults || write.Exam.ShuffleQuestions || write.Exam.ShuffleOptions || write.Exam.AllowReview {
		t.Fatalf("boolean defaults: %+v", write.Exam)
	}
}
