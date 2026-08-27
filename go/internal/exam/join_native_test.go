package exam

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

const joinSecret = "join-test-secret"

type fakeJoinRepo struct {
	mu        sync.Mutex
	users     map[int]*persistence.JoinUserRow
	exam      *persistence.JoinExamRow
	attempts  map[int]int
	questions int
	lookups   int
	counts    int
	usersGets int
}

func (f *fakeJoinRepo) LookupJoinUser(_ context.Context, id int) (*persistence.JoinUserRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.usersGets++
	if f.users == nil {
		return nil, nil
	}
	user := f.users[id]
	if user == nil {
		return nil, nil
	}
	copyUser := *user
	return &copyUser, nil
}

func (f *fakeJoinRepo) LookupJoinExamByToken(_ context.Context, token string) (*persistence.JoinExamRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.lookups++
	if f.exam == nil || token != "ABC123" {
		return nil, nil
	}
	copyExam := *f.exam
	return &copyExam, nil
}

func (f *fakeJoinRepo) CompletedAttemptCount(_ context.Context, userID, _ int) (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.attempts == nil {
		return 0, nil
	}
	return f.attempts[userID], nil
}

func (f *fakeJoinRepo) CountJoinQuestions(context.Context, int) (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.counts++
	return f.questions, nil
}

func activeExam() *persistence.JoinExamRow {
	now := time.Now().UTC()
	desc := "Join desc"
	role := "teacher"
	return &persistence.JoinExamRow{
		ID:              7,
		Title:           "Ujian Join",
		Description:     &desc,
		DurationMinutes: 90,
		StartTime:       now.Add(-time.Hour),
		EndTime:         now.Add(2 * time.Hour),
		Published:       true,
		MaxAttempts:     3,
		CreatorRole:     &role,
	}
}

func studentUser(id int, class string, active bool) *persistence.JoinUserRow {
	cls := class
	return &persistence.JoinUserRow{
		ID:           id,
		Role:         "student",
		StudentClass: &cls,
		IsActive:     active,
	}
}

func joinToken(user *persistence.JoinUserRow) string {
	className := ""
	if user.StudentClass != nil {
		className = *user.StudentClass
	}
	tok, err := auth.SignUser(joinSecret, user.ID, "s"+itoa(user.ID), user.Role, "Student", className, user.IsActive)
	if err != nil {
		panic(err)
	}
	return tok
}

func doJoin(t *testing.T, repo *fakeJoinRepo, user *persistence.JoinUserRow, body string, authHeader string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/api/exams/join", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	if authHeader != "" {
		req.Header.Set("Authorization", authHeader)
	} else if user != nil {
		req.Header.Set("Authorization", "Bearer "+joinToken(user))
	}
	req.RemoteAddr = "10.0.0." + itoa(userIDOr(user)) + ":1234"
	rec := httptest.NewRecorder()
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		response, joinErr := joinService{repo: repo, secret: joinSecret}.join(r)
		if joinErr != nil {
			if joinErr.Status == http.StatusUnauthorized {
				w.Header().Set("WWW-Authenticate", "Bearer")
			}
			if joinErr.Status == http.StatusTooManyRequests {
				w.Header().Set("Retry-After", "60")
			}
			writeJSON(w, joinErr.Status, map[string]any{"detail": joinErr.Detail})
			return
		}
		writeJSON(w, http.StatusOK, response)
	})
	handler.ServeHTTP(rec, req)
	return rec
}

func userIDOr(user *persistence.JoinUserRow) int {
	if user == nil {
		return 1
	}
	return user.ID
}

func decodeJoin(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var payload map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("json: %v body=%s", err, rec.Body.String())
	}
	return payload
}

func TestJoinValid(t *testing.T) {
	user := studentUser(11, "XII A", true)
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{11: user}, exam: activeExam(), questions: 4}
	rec := doJoin(t, repo, user, `{"token":"abc123"}`, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	payload := decodeJoin(t, rec)
	if payload["exam_id"] != float64(7) || payload["allowed"] != true || payload["question_count"] != float64(4) {
		t.Fatalf("payload=%v", payload)
	}
	if payload["message"] != "Token valid. Anda dapat memulai ujian." {
		t.Fatalf("message=%v", payload["message"])
	}
	if repo.lookups != 1 || repo.counts != 1 || repo.usersGets != 1 {
		t.Fatalf("sql lookups=%d counts=%d users=%d", repo.lookups, repo.counts, repo.usersGets)
	}
}

func TestJoinInvalidToken(t *testing.T) {
	user := studentUser(12, "XII A", true)
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{12: user}, exam: activeExam()}
	rec := doJoin(t, repo, user, `{"token":"ZZZZZZ"}`, "")
	if rec.Code != http.StatusNotFound || decodeJoin(t, rec)["detail"] != "Token ujian tidak valid" {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestJoinUnpublished(t *testing.T) {
	user := studentUser(13, "XII A", true)
	exam := activeExam()
	exam.Published = false
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{13: user}, exam: exam}
	rec := doJoin(t, repo, user, `{"token":"ABC123"}`, "")
	if rec.Code != http.StatusForbidden || decodeJoin(t, rec)["detail"] != "Ujian belum dipublikasikan" {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestJoinBeforeStart(t *testing.T) {
	user := studentUser(14, "XII A", true)
	exam := activeExam()
	exam.StartTime = time.Now().UTC().Add(time.Hour)
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{14: user}, exam: exam}
	rec := doJoin(t, repo, user, `{"token":"ABC123"}`, "")
	if rec.Code != http.StatusForbidden || decodeJoin(t, rec)["detail"] != "Ujian belum dimulai" {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestJoinEnded(t *testing.T) {
	user := studentUser(15, "XII A", true)
	exam := activeExam()
	exam.EndTime = time.Now().UTC().Add(-time.Minute)
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{15: user}, exam: exam}
	rec := doJoin(t, repo, user, `{"token":"ABC123"}`, "")
	if rec.Code != http.StatusForbidden || decodeJoin(t, rec)["detail"] != "Ujian sudah berakhir" {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestJoinInactiveUser(t *testing.T) {
	user := studentUser(16, "XII A", false)
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{16: user}, exam: activeExam()}
	rec := doJoin(t, repo, user, `{"token":"ABC123"}`, "")
	if rec.Code != http.StatusForbidden || decodeJoin(t, rec)["detail"] != "Akun tidak aktif" {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestJoinMissingAndInvalidAuth(t *testing.T) {
	user := studentUser(17, "XII A", true)
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{17: user}, exam: activeExam()}
	missing := doJoin(t, repo, user, `{"token":"ABC123"}`, " ")
	if missing.Code != http.StatusUnauthorized || decodeJoin(t, missing)["detail"] != "Not authenticated" {
		t.Fatalf("missing status=%d body=%s", missing.Code, missing.Body.String())
	}
	bad := doJoin(t, repo, user, `{"token":"ABC123"}`, "Bearer not-a-jwt")
	if bad.Code != http.StatusUnauthorized || decodeJoin(t, bad)["detail"] != "Token tidak valid atau sudah kadaluarsa" {
		t.Fatalf("bad status=%d body=%s", bad.Code, bad.Body.String())
	}
	if bad.Header().Get("WWW-Authenticate") != "Bearer" {
		t.Fatal("missing www-authenticate")
	}
}

func TestJoinAllowedAndForbiddenClass(t *testing.T) {
	allowed := studentUser(18, "XII A", true)
	denied := studentUser(19, "XII B", true)
	exam := activeExam()
	classes := "XII A"
	exam.AllowedClasses = &classes
	repo := &fakeJoinRepo{
		users: map[int]*persistence.JoinUserRow{18: allowed, 19: denied},
		exam:  exam,
	}
	ok := doJoin(t, repo, allowed, `{"token":"ABC123"}`, "")
	if ok.Code != http.StatusOK {
		t.Fatalf("allowed status=%d body=%s", ok.Code, ok.Body.String())
	}
	no := doJoin(t, repo, denied, `{"token":"ABC123"}`, "")
	if no.Code != http.StatusForbidden {
		t.Fatalf("denied status=%d body=%s", no.Code, no.Body.String())
	}
	detail, _ := decodeJoin(t, no)["detail"].(string)
	if detail == "" || !bytes.Contains([]byte(detail), []byte("Kelas Anda")) {
		t.Fatalf("detail=%q", detail)
	}
}

func TestJoinAllowedAndForbiddenStudent(t *testing.T) {
	listed := studentUser(20, "XII A", true)
	other := studentUser(21, "XII A", true)
	exam := activeExam()
	students := "20"
	exam.AllowedStudents = &students
	repo := &fakeJoinRepo{
		users: map[int]*persistence.JoinUserRow{20: listed, 21: other},
		exam:  exam,
	}
	ok := doJoin(t, repo, listed, `{"token":"ABC123"}`, "")
	if ok.Code != http.StatusOK {
		t.Fatalf("listed status=%d", ok.Code)
	}
	no := doJoin(t, repo, other, `{"token":"ABC123"}`, "")
	if no.Code != http.StatusForbidden || decodeJoin(t, no)["detail"] != "Anda tidak termasuk peserta yang diizinkan untuk ujian ini" {
		t.Fatalf("unlisted status=%d body=%s", no.Code, no.Body.String())
	}
}

func TestJoinStaffAndGuruPlus(t *testing.T) {
	teacher := &persistence.JoinUserRow{ID: 30, Role: "teacher", IsActive: true}
	admin := &persistence.JoinUserRow{ID: 31, Role: "admin", IsActive: true}
	guru := &persistence.JoinUserRow{ID: 32, Role: "guruplus", StudentClass: strp("GuruPlus"), IsActive: true}
	exam := activeExam()
	exam.AllowedClasses = strp("GuruPlus")
	teacherCreator := "teacher"
	exam.CreatorRole = &teacherCreator
	repo := &fakeJoinRepo{
		users: map[int]*persistence.JoinUserRow{30: teacher, 31: admin, 32: guru},
		exam:  exam,
	}
	if rec := doJoin(t, repo, teacher, `{"token":"ABC123"}`, ""); rec.Code != http.StatusForbidden {
		t.Fatalf("teacher=%d", rec.Code)
	}
	if rec := doJoin(t, repo, admin, `{"token":"ABC123"}`, ""); rec.Code != http.StatusForbidden {
		t.Fatalf("admin=%d", rec.Code)
	}
	if rec := doJoin(t, repo, guru, `{"token":"ABC123"}`, ""); rec.Code != http.StatusForbidden {
		t.Fatalf("guruplus teacher-exam=%d body=%s", rec.Code, rec.Body.String())
	}
	dev := "developer"
	exam.CreatorRole = &dev
	if rec := doJoin(t, repo, guru, `{"token":"ABC123"}`, ""); rec.Code != http.StatusOK {
		t.Fatalf("guruplus developer-exam=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestJoinExistingAndRepeated(t *testing.T) {
	user := studentUser(22, "XII A", true)
	repo := &fakeJoinRepo{
		users:     map[int]*persistence.JoinUserRow{22: user},
		exam:      activeExam(),
		attempts:  map[int]int{22: 0},
		questions: 2,
	}
	first := doJoin(t, repo, user, `{"token":"ABC123"}`, "")
	second := doJoin(t, repo, user, `{"token":"ABC123"}`, "")
	if first.Code != http.StatusOK || second.Code != http.StatusOK {
		t.Fatalf("repeat %d %d", first.Code, second.Code)
	}
	if decodeJoin(t, first)["exam_id"] != decodeJoin(t, second)["exam_id"] {
		t.Fatal("repeat changed exam")
	}
}

func TestJoinMaxAttempts(t *testing.T) {
	user := studentUser(23, "XII A", true)
	exam := activeExam()
	exam.MaxAttempts = 1
	repo := &fakeJoinRepo{
		users:    map[int]*persistence.JoinUserRow{23: user},
		exam:     exam,
		attempts: map[int]int{23: 1},
	}
	rec := doJoin(t, repo, user, `{"token":"ABC123"}`, "")
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestJoinConcurrent(t *testing.T) {
	user := studentUser(24, "XII A", true)
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{24: user}, exam: activeExam(), questions: 1}
	var wg sync.WaitGroup
	codes := make([]int, 8)
	wg.Add(8)
	for i := 0; i < 8; i++ {
		go func(i int) {
			defer wg.Done()
			rec := doJoin(t, repo, user, `{"token":"ABC123"}`, "")
			codes[i] = rec.Code
		}(i)
	}
	wg.Wait()
	for i, code := range codes {
		if code != http.StatusOK {
			t.Fatalf("i=%d status=%d", i, code)
		}
	}
}

func TestJoinMalformed(t *testing.T) {
	user := studentUser(25, "XII A", true)
	repo := &fakeJoinRepo{users: map[int]*persistence.JoinUserRow{25: user}, exam: activeExam()}
	missing := doJoin(t, repo, user, `{}`, "")
	if missing.Code != http.StatusUnprocessableEntity {
		t.Fatalf("missing token status=%d", missing.Code)
	}
	bad := doJoin(t, repo, user, `{`, "")
	if bad.Code != http.StatusUnprocessableEntity {
		t.Fatalf("bad json status=%d", bad.Code)
	}
}

func TestJoinNoPoolDoesNotProxy(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/api/exams/join", bytes.NewBufferString(`{"token":"ABC123"}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+joinToken(studentUser(26, "XII A", true)))
	rec := httptest.NewRecorder()
	deps{}.joinExam(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if decodeJoin(t, rec)["detail"] != "Database tidak tersedia" {
		t.Fatalf("body=%s", rec.Body.String())
	}
}
