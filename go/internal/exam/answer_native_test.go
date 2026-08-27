package exam

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

const answerSecret = "answer-test-secret"

type fakeAnswerRepo struct {
	mu        sync.Mutex
	sessions  map[int]persistence.AnswerSessionProbe
	owners    map[int]int
	questions map[int]*persistence.AnswerQuestionPayload
	writes    []persistence.AnswerWriteFields
	writeN    int
	writeErr  error
	redisErr  error
	failDB    bool
}

func (f *fakeAnswerRepo) HasPool() bool  { return true }
func (f *fakeAnswerRepo) HasRedis() bool { return true }

func (f *fakeAnswerRepo) ProbeAnswerSession(_ context.Context, sessionID, userID int) (*persistence.AnswerSessionProbe, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failDB {
		return nil, errors.New("timeout")
	}
	row, ok := f.sessions[sessionID]
	if !ok || f.owners[sessionID] != userID {
		return nil, nil
	}
	copyRow := row
	return &copyRow, nil
}

func (f *fakeAnswerRepo) LoadAnswerQuestion(_ context.Context, examID, questionID int) (*persistence.AnswerQuestionPayload, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	q := f.questions[questionID]
	if q == nil || q.ExamID != examID {
		return nil, nil
	}
	copyQ := *q
	return &copyQ, nil
}

func (f *fakeAnswerRepo) WriteSingleAnswerDirect(_ context.Context, sessionID, userID, _ int, fields persistence.AnswerWriteFields) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.writeErr != nil {
		return "", f.writeErr
	}
	row, ok := f.sessions[sessionID]
	if !ok || f.owners[sessionID] != userID {
		return "", errors.New("answer session not found")
	}
	status := row.Status
	if status == "submitted" || status == "completed" {
		return "submitted", nil
	}
	if status != "in_progress" {
		return status, errors.New("answer session ended")
	}
	f.writes = append(f.writes, fields)
	f.writeN++
	return "in_progress", nil
}

func (f *fakeAnswerRepo) AllowSlidingRate(context.Context, string, string, int, int) (bool, int) {
	return true, 60
}

func (f *fakeAnswerRepo) AddAnsweredQuestions(context.Context, int, []int) (int, bool, error) {
	if f.redisErr != nil {
		return 0, false, f.redisErr
	}
	return 1, true, nil
}

func (f *fakeAnswerRepo) PatchSessionAnsweredCount(context.Context, int, int, int) error {
	return f.redisErr
}

func (f *fakeAnswerRepo) ReplaceSessionAnswerCache(context.Context, int, any) error {
	return f.redisErr
}

func (f *fakeAnswerRepo) LoadStartSecuritySettings(context.Context) (persistence.StartSecuritySettings, error) {
	return persistence.StartSecuritySettings{DeveloperMode: true, AllowMobileApps: true}, nil
}

func (f *fakeAnswerRepo) StartSEBKeys(context.Context, int) (string, string, bool, error) {
	return "seb", "", true, nil
}

func (f *fakeAnswerRepo) RedisGet(context.Context, string) (string, bool, error) {
	return "", false, nil
}

func (f *fakeAnswerRepo) RedisSet(context.Context, string, string, time.Duration) error {
	return nil
}

func (f *fakeAnswerRepo) RedisDelete(context.Context, string) error { return nil }

func mcQuestion() *persistence.AnswerQuestionPayload {
	return &persistence.AnswerQuestionPayload{
		ID: 11, ExamID: 5, QuestionType: "multiple_choice", Points: 1,
		QuestionSettings: []byte("{}"),
		Options:          []persistence.AnswerQuestionOption{{ID: 21, IsCorrect: true}, {ID: 22, IsCorrect: false}},
	}
}

func answerToken(t *testing.T, userID int, active bool) string {
	t.Helper()
	tok, err := auth.SignUser(answerSecret, userID, "s", "student", "S", "XII", active)
	if err != nil {
		t.Fatal(err)
	}
	return tok
}

func doAnswer(t *testing.T, repo *fakeAnswerRepo, token, body string) *httptest.ResponseRecorder {
	t.Helper()
	svc := answerService{repo: repo, secret: answerSecret, disableRateLimit: true, examPeak: true}
	req := httptest.NewRequest(http.MethodPost, "/api/exams/submit-answer", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	rec := httptest.NewRecorder()
	handler := deps{store: &persistence.Store{}}.submitAnswer
	_ = handler
	response, err := svc.accept(req)
	if err != nil {
		rec.WriteHeader(err.Status)
		_ = json.NewEncoder(rec).Encode(map[string]any{"detail": err.Detail})
		return rec
	}
	rec.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(rec).Encode(response)
	return rec
}

func liveRepo() *fakeAnswerRepo {
	return &fakeAnswerRepo{
		sessions:  map[int]persistence.AnswerSessionProbe{9: {ID: 9, ExamID: 5, Status: "in_progress"}},
		owners:    map[int]int{9: 3},
		questions: map[int]*persistence.AnswerQuestionPayload{11: mcQuestion()},
	}
}

func TestAnswerFirstAndUpdate(t *testing.T) {
	repo := liveRepo()
	tok := answerToken(t, 3, true)
	first := doAnswer(t, repo, tok, `{"session_id":9,"question_id":11,"selected_option_id":21}`)
	if first.Code != 200 {
		t.Fatalf("first %s", first.Body.String())
	}
	second := doAnswer(t, repo, tok, `{"session_id":9,"question_id":11,"selected_option_id":22}`)
	if second.Code != 200 || repo.writeN != 2 {
		t.Fatalf("update writes=%d body=%s", repo.writeN, second.Body.String())
	}
}

func TestAnswerIdempotentAndInvalid(t *testing.T) {
	repo := liveRepo()
	tok := answerToken(t, 3, true)
	body := `{"session_id":9,"question_id":11,"selected_option_id":21}`
	if doAnswer(t, repo, tok, body).Code != 200 || doAnswer(t, repo, tok, body).Code != 200 {
		t.Fatal("idempotent")
	}
	if doAnswer(t, repo, tok, `{"session_id":9,"question_id":99,"selected_option_id":21}`).Code != 404 {
		t.Fatal("invalid question")
	}
	if doAnswer(t, repo, tok, `{"session_id":8,"question_id":11,"selected_option_id":21}`).Code != 404 {
		t.Fatal("invalid session")
	}
}

func TestAnswerOwnershipSubmittedExpired(t *testing.T) {
	repo := liveRepo()
	repo.sessions[10] = persistence.AnswerSessionProbe{ID: 10, ExamID: 5, Status: "in_progress"}
	repo.owners[10] = 4
	repo.sessions[11] = persistence.AnswerSessionProbe{ID: 11, ExamID: 5, Status: "submitted"}
	repo.owners[11] = 3
	repo.sessions[12] = persistence.AnswerSessionProbe{ID: 12, ExamID: 5, Status: "paused"}
	repo.owners[12] = 3
	tok := answerToken(t, 3, true)
	if doAnswer(t, repo, tok, `{"session_id":10,"question_id":11,"selected_option_id":21}`).Code != 404 {
		t.Fatal("ownership")
	}
	submitted := doAnswer(t, repo, tok, `{"session_id":11,"question_id":11,"selected_option_id":21}`)
	if submitted.Code != 200 || !bytes.Contains(submitted.Body.Bytes(), []byte("sudah dikumpulkan")) {
		t.Fatalf("submitted %s", submitted.Body.String())
	}
	if doAnswer(t, repo, tok, `{"session_id":12,"question_id":11,"selected_option_id":21}`).Code != 400 {
		t.Fatal("expired")
	}
}

func TestAnswerTypesConcurrentAndFailures(t *testing.T) {
	repo := liveRepo()
	settings, _ := json.Marshal(map[string]any{
		"pgk_type": "table_validation", "statement_answers": []any{true, false},
	})
	pgk := "table_validation"
	repo.questions[12] = &persistence.AnswerQuestionPayload{
		ID: 12, ExamID: 5, QuestionType: "multiple_choice_complex", PGKType: &pgk, Points: 2, QuestionSettings: settings,
	}
	repo.questions[13] = &persistence.AnswerQuestionPayload{
		ID: 13, ExamID: 5, QuestionType: "essay", Points: 5, QuestionSettings: []byte("{}"),
	}
	tok := answerToken(t, 3, true)
	table := doAnswer(t, repo, tok, `{"session_id":9,"question_id":12,"statement_answers":{"0":true,"1":false}}`)
	essay := doAnswer(t, repo, tok, `{"session_id":9,"question_id":13,"answer_text":"jawaban"}`)
	if table.Code != 200 || essay.Code != 200 {
		t.Fatalf("types %s %s", table.Body.String(), essay.Body.String())
	}
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			doAnswer(t, repo, tok, `{"session_id":9,"question_id":11,"selected_option_id":21}`)
		}()
	}
	wg.Wait()
	repo.writeErr = errors.New("deadlock")
	conflict := doAnswer(t, repo, tok, `{"session_id":9,"question_id":11,"selected_option_id":21}`)
	if conflict.Code != 409 {
		t.Fatalf("db fail %d", conflict.Code)
	}
	repo.writeErr = nil
	repo.redisErr = errors.New("redis down")
	if doAnswer(t, repo, tok, `{"session_id":9,"question_id":11,"selected_option_id":21}`).Code != 200 {
		t.Fatal("redis fail should not lose answer")
	}
	repo.failDB = true
	busy := doAnswer(t, repo, tok, `{"session_id":9,"question_id":11,"selected_option_id":21}`)
	if busy.Code != 503 {
		t.Fatalf("busy %d", busy.Code)
	}
}

func TestAnswerAuthMalformed(t *testing.T) {
	repo := liveRepo()
	if doAnswer(t, repo, "", `{"session_id":9,"question_id":11,"selected_option_id":21}`).Code != 401 {
		t.Fatal("missing auth")
	}
	if doAnswer(t, repo, "bad", `{"session_id":9,"question_id":11}`).Code != 401 {
		t.Fatal("invalid auth")
	}
	tok := answerToken(t, 3, true)
	if doAnswer(t, repo, tok, `{`).Code != 422 {
		t.Fatal("malformed")
	}
	inactive := answerToken(t, 3, false)
	if doAnswer(t, repo, inactive, `{"session_id":9,"question_id":11,"selected_option_id":21}`).Code != 403 {
		t.Fatal("inactive")
	}
}
