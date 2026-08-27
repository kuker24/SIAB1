package exam

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"reflect"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgconn"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

type fakeStartRepo struct {
	tx          *fakeStartTx
	txQueue     []*fakeStartTx
	security    persistence.StartSecuritySettings
	securityErr error
	sebConfig   string
	sebBrowser  string
	sebFound    bool
	questions   []persistence.QuestionRow
	questionErr error
	raced       *persistence.StartSessionRow
	raceErr     error
	redis       map[string]string
	redisSetErr map[string]error
	redisGetErr map[string]error
	publishErr  error
	published   []string
	xaddErr     error
	xaddKeys    []string
	xaddEvents  []string
	mu          sync.Mutex
}

func newFakeStartRepo(tx *fakeStartTx) *fakeStartRepo {
	return &fakeStartRepo{
		tx:          tx,
		security:    persistence.StartSecuritySettings{DeveloperMode: true, AllowMobileApps: true},
		sebConfig:   "config-key",
		sebFound:    true,
		redis:       map[string]string{},
		redisSetErr: map[string]error{},
		redisGetErr: map[string]error{},
	}
}

func (f *fakeStartRepo) BeginStart(context.Context) (persistence.StartTransaction, error) {
	f.mu.Lock()
	if len(f.txQueue) > 0 {
		tx := f.txQueue[0]
		f.txQueue = f.txQueue[1:]
		f.mu.Unlock()
		return tx, tx.beginErr
	}
	f.mu.Unlock()
	if f.tx.beginErr != nil {
		return nil, f.tx.beginErr
	}
	return f.tx, nil
}

func (f *fakeStartRepo) LoadStartSecuritySettings(context.Context) (persistence.StartSecuritySettings, error) {
	return f.security, f.securityErr
}

func (f *fakeStartRepo) StartSEBKeys(context.Context, int) (string, string, bool, error) {
	return f.sebConfig, f.sebBrowser, f.sebFound, nil
}

func (f *fakeStartRepo) CanonicalActiveStartSession(context.Context, int, int) (*persistence.StartSessionRow, error) {
	return f.raced, f.raceErr
}

func (f *fakeStartRepo) LoadQuestions(context.Context, int) ([]persistence.QuestionRow, error) {
	return append([]persistence.QuestionRow(nil), f.questions...), f.questionErr
}

func (f *fakeStartRepo) RedisGet(_ context.Context, key string) (string, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if err := f.redisGetErr[key]; err != nil {
		return "", false, err
	}
	value, ok := f.redis[key]
	return value, ok, nil
}

func (f *fakeStartRepo) RedisSet(_ context.Context, key, value string, _ time.Duration) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if err := f.redisSetErr[key]; err != nil {
		return err
	}
	f.redis[key] = value
	return nil
}

func (f *fakeStartRepo) RedisSetNX(_ context.Context, key, value string, _ time.Duration) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if _, exists := f.redis[key]; exists {
		return false, nil
	}
	f.redis[key] = value
	return true, nil
}

func (f *fakeStartRepo) RedisDelete(_ context.Context, key string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	delete(f.redis, key)
	return nil
}

func (f *fakeStartRepo) RedisPublish(_ context.Context, channel, value string) error {
	if f.publishErr != nil {
		return f.publishErr
	}
	f.published = append(f.published, channel+":"+value)
	return nil
}

func (f *fakeStartRepo) RedisXAdd(_ context.Context, key, event string, _, _ int) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.xaddErr != nil {
		return f.xaddErr
	}
	f.xaddKeys = append(f.xaddKeys, key)
	f.xaddEvents = append(f.xaddEvents, event)
	return nil
}

type fakeStartTx struct {
	exam             *persistence.StartExamRow
	state            persistence.StartSessionState
	answerCounts     map[int]int
	logs             map[int][]persistence.SessionLog
	orphans          []int
	createdSession   *persistence.StartSessionRow
	recovered        *persistence.StartSessionRow
	beginErr         error
	examErr          error
	stateErr         error
	createErr        error
	recoverErr       error
	commitErr        error
	createCalled     int
	logAdded         int
	recoverCalled    int
	commits          int
	rollbacks        int
	rollbackCanceled bool
}

func (f *fakeStartTx) Exam(context.Context, int) (*persistence.StartExamRow, error) {
	return f.exam, f.examErr
}

func (f *fakeStartTx) ValidateOptionIntegrity(context.Context, int) ([]int, error) {
	return f.orphans, nil
}

func (f *fakeStartTx) SessionState(context.Context, int, int) (persistence.StartSessionState, error) {
	return f.state, f.stateErr
}

func (f *fakeStartTx) AnswerCounts(context.Context, []int) (map[int]int, error) {
	return f.answerCounts, nil
}

func (f *fakeStartTx) SessionLogs(_ context.Context, sessionID, _ int) ([]persistence.SessionLog, error) {
	return f.logs[sessionID], nil
}

func (f *fakeStartTx) RecoverSession(
	_ context.Context,
	session persistence.StartSessionRow,
	_, _ string,
) (*persistence.StartSessionRow, error) {
	f.recoverCalled++
	if f.recoverErr != nil {
		return nil, f.recoverErr
	}
	if f.recovered != nil {
		return f.recovered, nil
	}
	session.Status = "in_progress"
	session.EndTime = nil
	return &session, nil
}

func (f *fakeStartTx) CreateSessionWithLog(
	context.Context,
	int,
	int,
	persistence.StartClientInfo,
	persistence.SessionStartLog,
) (*persistence.StartSessionRow, error) {
	f.createCalled++
	if f.createErr != nil {
		return nil, f.createErr
	}
	f.logAdded++
	return f.createdSession, nil
}

func (f *fakeStartTx) Commit(context.Context) error {
	if f.commitErr != nil {
		return f.commitErr
	}
	f.commits++
	return nil
}

func (f *fakeStartTx) Rollback(ctx context.Context) error {
	f.rollbacks++
	f.rollbackCanceled = ctx.Err() != nil
	return nil
}

func validStartExam() *persistence.StartExamRow {
	now := time.Now().UTC()
	showTeacher := true
	teacher := "Guru"
	role := "teacher"
	return &persistence.StartExamRow{
		ID: 7, CreatorID: 11, Published: true,
		StartTime: now.Add(-time.Hour), EndTime: now.Add(time.Hour),
		MaxAttempts: 2, DurationMinutes: 60,
		Title: "Ujian", Subject: stringPointer("MTK"), ExamType: stringPointer("UH"),
		ShowTeacherName: &showTeacher, TeacherName: &teacher, CreatorRole: &role,
	}
}

func validQuestion() persistence.QuestionRow {
	return persistence.QuestionRow{
		ID: 1, ExamID: 7, Text: "Soal", Type: "multiple_choice",
		Points: 1, PointsText: "1.00", OrderIndex: 0, Settings: []byte(`{}`),
		Options: []persistence.OptionRow{
			{ID: 11, QuestionID: 1, Text: "A", OrderIndex: 0, OptionGroup: "standard"},
			{ID: 12, QuestionID: 1, Text: "B", OrderIndex: 1, OptionGroup: "standard"},
		},
	}
}

func validStartTx() *fakeStartTx {
	return &fakeStartTx{
		exam:         validStartExam(),
		answerCounts: map[int]int{},
		logs:         map[int][]persistence.SessionLog{},
		createdSession: &persistence.StartSessionRow{
			ID: 99, UserID: 5, ExamID: 7, Status: "in_progress",
			StartTime: time.Now().UTC().Truncate(time.Microsecond),
		},
	}
}

func validService(repo *fakeStartRepo) startService {
	return startService{
		repo:                  repo,
		gate:                  newStartAdmission(4),
		jwtSecret:             "jwt-secret",
		appSecret:             "app-secret",
		defaultSEBKey:         "default-seb-config-key",
		challengeEnabled:      true,
		challengePrefix:       "seb:challenge:",
		monitoringDelta:       true,
		monitoringDeltaMaxLen: 5000,
		monitoringDeltaTTL:    7200,
	}
}

func validStartRequest(t *testing.T, active bool) *http.Request {
	t.Helper()
	token, err := auth.SignUser("jwt-secret", 5, "student", "student", "Student", "XII", active)
	if err != nil {
		t.Fatal(err)
	}
	r := httptest.NewRequest(http.MethodPost, "https://example.test/api/exams/7/start", nil)
	r.Header.Set("Authorization", "Bearer "+token)
	r.Header.Set("User-Agent", "test")
	return r
}

func TestNativeStartNormalCreatesAtomicSessionAndSnapshot(t *testing.T) {
	tx := validStartTx()
	repo := newFakeStartRepo(tx)
	repo.questions = []persistence.QuestionRow{validQuestion()}
	response, startErr := validService(repo).start(validStartRequest(t, true), 7)
	if startErr != nil {
		t.Fatal(startErr)
	}
	if response.SessionID != 99 || response.QuestionCount != 1 {
		t.Fatalf("response=%+v", response)
	}
	if tx.createCalled != 1 || tx.logAdded != 1 || tx.commits != 1 || tx.rollbacks != 0 {
		t.Fatalf("transaction create=%d log=%d commit=%d rollback=%d", tx.createCalled, tx.logAdded, tx.commits, tx.rollbacks)
	}
	raw, ok := repo.redis["exam_session:99"]
	if !ok {
		t.Fatal("missing Redis session snapshot")
	}
	var snapshot map[string]any
	if err := json.Unmarshal([]byte(raw), &snapshot); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{
		"session_id", "user_id", "exam_id", "start_time", "started_at",
		"duration_seconds", "elapsed_seconds", "paused", "duration_minutes",
		"status", "answered_count", "answered_count_stale", "total_questions",
		"violation_count",
	} {
		if _, exists := snapshot[key]; !exists {
			t.Fatalf("missing snapshot field %s", key)
		}
	}
	if snapshot["status"] != "in_progress" || jsonInt(snapshot["session_id"]) != 99 {
		t.Fatalf("snapshot=%v", snapshot)
	}
	if len(repo.published) != 1 {
		t.Fatalf("published=%v", repo.published)
	}
	if len(repo.xaddKeys) != 1 || repo.xaddKeys[0] != "monitoring:delta:exam:7" {
		t.Fatalf("delta=%v", repo.xaddKeys)
	}
	var delta map[string]any
	if err := json.Unmarshal([]byte(repo.xaddEvents[0]), &delta); err != nil {
		t.Fatal(err)
	}
	if delta["event_type"] != "student_started" {
		t.Fatalf("delta=%v", delta)
	}
	payload, _ := delta["payload"].(map[string]any)
	if payload["type"] != "student_started" || jsonInt(payload["user_id"]) != 5 || jsonInt(payload["session_id"]) != 99 {
		t.Fatalf("payload=%v", payload)
	}
	if _, ok := delta["ts"].(string); !ok {
		t.Fatalf("missing delta ts: %v", delta)
	}
	if response.Questions[0].DifficultyLevel != "medium" || response.Questions[0].Points != "1.0" {
		t.Fatalf("question=%+v", response.Questions[0])
	}
	rawResponse, err := json.Marshal(response)
	if err != nil {
		t.Fatal(err)
	}
	var encoded map[string]any
	if err := json.Unmarshal(rawResponse, &encoded); err != nil {
		t.Fatal(err)
	}
	fixture := loadStartParityFixture(t)
	for _, key := range fixture.ResponseKeys {
		if _, exists := encoded[key]; !exists {
			t.Fatalf("missing response field %s", key)
		}
	}
	if extra := extraJSONKeys(encoded, fixture.ResponseKeys); len(extra) > 0 {
		t.Fatalf("extra response fields %v", extra)
	}
}

func TestNativeStartMissingAuthMatchesFastAPI(t *testing.T) {
	repo := newFakeStartRepo(validStartTx())
	req := httptest.NewRequest(http.MethodPost, "https://example.test/api/exams/7/start", nil)
	_, startErr := validService(repo).start(req, 7)
	if startErr == nil || startErr.Status != http.StatusForbidden || startErr.Detail != "Not authenticated" {
		t.Fatalf("error=%v", startErr)
	}
}

func TestNativeStartMonitoringXAddFailOpen(t *testing.T) {
	tx := validStartTx()
	repo := newFakeStartRepo(tx)
	repo.questions = []persistence.QuestionRow{validQuestion()}
	repo.xaddErr = errors.New("xadd down")
	response, startErr := validService(repo).start(validStartRequest(t, true), 7)
	if startErr != nil || response == nil || response.SessionID != 99 {
		t.Fatalf("error=%v response=%v", startErr, response)
	}
	if tx.commits != 1 || tx.rollbacks != 0 {
		t.Fatalf("commit=%d rollback=%d", tx.commits, tx.rollbacks)
	}
	if _, ok := repo.redis["exam_session:99"]; !ok {
		t.Fatal("missing Redis session snapshot after XADD failure")
	}
	if len(repo.published) != 1 {
		t.Fatalf("published=%v", repo.published)
	}
	if len(repo.xaddKeys) != 0 {
		t.Fatalf("xaddKeys=%v", repo.xaddKeys)
	}
}

func TestNativeStartDifficultyAndPointsMatchFastAPI(t *testing.T) {
	tx := validStartTx()
	repo := newFakeStartRepo(tx)
	hard := validQuestion()
	hard.Difficulty = "hard"
	hard.Points = 1
	hard.PointsText = "1.00"
	repo.questions = []persistence.QuestionRow{hard}
	response, startErr := validService(repo).start(validStartRequest(t, true), 7)
	if startErr != nil {
		t.Fatal(startErr)
	}
	fixture := loadStartParityFixture(t)
	if response.Questions[0].DifficultyLevel != fixture.DifficultyDefault {
		t.Fatalf("difficulty=%q", response.Questions[0].DifficultyLevel)
	}
	if response.Questions[0].Points != fixture.Points.From100 {
		t.Fatalf("points=%q", response.Questions[0].Points)
	}

	cases := []struct {
		points float64
		want   string
	}{
		{1, fixture.Points.IntLike},
		{1.25, fixture.Points.Fractional},
		{0, fixture.Points.Zero},
	}
	for _, tc := range cases {
		questions, err := buildStartQuestions(
			[]persistence.QuestionRow{{
				ID: 1, Text: "Soal", Type: "essay", Points: tc.points, OrderIndex: 0, Settings: []byte(`{}`),
			}},
			7, 5, false, false, "app-secret",
		)
		if err != nil {
			t.Fatal(err)
		}
		if questions[0].Points != tc.want {
			t.Fatalf("points(%v)=%q want %q", tc.points, questions[0].Points, tc.want)
		}
	}

	questions, err := buildStartQuestions(
		[]persistence.QuestionRow{validQuestion()},
		7, 5, false, false, "app-secret",
	)
	if err != nil {
		t.Fatal(err)
	}
	raw, marshalErr := json.Marshal(questions[0])
	if marshalErr != nil {
		t.Fatal(marshalErr)
	}
	var encoded map[string]any
	if json.Unmarshal(raw, &encoded) != nil {
		t.Fatal("question json")
	}
	for _, key := range fixture.QuestionKeys {
		if _, exists := encoded[key]; !exists {
			t.Fatalf("missing question field %s", key)
		}
	}
	if extra := extraJSONKeys(encoded, fixture.QuestionKeys); len(extra) > 0 {
		t.Fatalf("extra question fields %v", extra)
	}
	option, _ := encoded["options"].([]any)[0].(map[string]any)
	for _, key := range fixture.OptionKeys {
		if _, exists := option[key]; !exists {
			t.Fatalf("missing option field %s", key)
		}
	}
	if extra := extraJSONKeys(option, fixture.OptionKeys); len(extra) > 0 {
		t.Fatalf("extra option fields %v", extra)
	}
	if encoded["difficulty_level"] != "medium" || encoded["points"] != "1.0" || encoded["category"] != nil {
		t.Fatalf("question json=%s", raw)
	}
}

func TestNativeStartInvalidTokenMatchesFastAPI(t *testing.T) {
	repo := newFakeStartRepo(validStartTx())
	req := httptest.NewRequest(http.MethodPost, "https://example.test/api/exams/7/start", nil)
	req.Header.Set("Authorization", "Bearer not-a-jwt")
	_, startErr := validService(repo).start(req, 7)
	if startErr == nil || startErr.Status != http.StatusUnauthorized || startErr.Detail != "Token tidak valid atau sudah kadaluarsa" {
		t.Fatalf("error=%v", startErr)
	}
}

func TestNativeStartSEBRequired(t *testing.T) {
	repo := newFakeStartRepo(validStartTx())
	repo.security = persistence.StartSecuritySettings{AllowMobileApps: true}
	req := validStartRequest(t, true)
	_, startErr := validService(repo).start(req, 7)
	if startErr == nil || startErr.Status != http.StatusForbidden {
		t.Fatalf("error=%v", startErr)
	}
	detail, _ := startErr.Detail.(map[string]any)
	if detail["error"] != "SEB_REQUIRED" {
		t.Fatalf("detail=%v", startErr.Detail)
	}
}

func TestNativeStartRejectsInactiveJWT(t *testing.T) {
	tx := validStartTx()
	repo := newFakeStartRepo(tx)
	_, startErr := validService(repo).start(validStartRequest(t, false), 7)
	if startErr == nil || startErr.Status != http.StatusForbidden || startErr.Detail != "Akun tidak aktif" {
		t.Fatalf("error=%v", startErr)
	}
	if tx.createCalled != 0 {
		t.Fatal("inactive account reached transaction")
	}
}

func TestNativeStartMaxAttempts(t *testing.T) {
	tx := validStartTx()
	tx.state.AttemptCount = tx.exam.MaxAttempts
	repo := newFakeStartRepo(tx)
	_, _, _, _, startErr := validService(repo).startTransaction(
		context.Background(), validStartRequest(t, true), 7, 5,
		&auth.Claims{Role: "student", StudentClass: "XII"},
	)
	if startErr == nil || startErr.Status != 400 || startErr.Detail != "Batas percobaan sudah tercapai" {
		t.Fatalf("error=%v", startErr)
	}
	if tx.createCalled != 0 || tx.rollbacks != 1 {
		t.Fatalf("create=%d rollback=%d", tx.createCalled, tx.rollbacks)
	}
}

func TestNativeStartInvalidAccess(t *testing.T) {
	tx := validStartTx()
	allowed := "XI"
	tx.exam.AllowedClasses = &allowed
	repo := newFakeStartRepo(tx)
	_, _, _, _, startErr := validService(repo).startTransaction(
		context.Background(), validStartRequest(t, true), 7, 5,
		&auth.Claims{Role: "student", StudentClass: "XII"},
	)
	if startErr == nil || startErr.Status != 403 {
		t.Fatalf("error=%v", startErr)
	}
}

func TestNativeStartResumesCanonicalSession(t *testing.T) {
	tx := validStartTx()
	tx.state.Sessions = []persistence.StartSessionRow{
		{ID: 40, Status: "active", StartTime: time.Now().Add(-time.Minute)},
		{ID: 41, Status: "in_progress", StartTime: time.Now()},
	}
	tx.answerCounts = map[int]int{40: 5, 41: 2}
	repo := newFakeStartRepo(tx)
	exam, session, resumed, _, startErr := validService(repo).startTransaction(
		context.Background(), validStartRequest(t, true), 7, 5,
		&auth.Claims{Role: "student", StudentClass: "XII"},
	)
	if startErr != nil || exam == nil || !resumed || session.ID != 40 {
		t.Fatalf("session=%+v resumed=%v error=%v", session, resumed, startErr)
	}
	if tx.createCalled != 0 || tx.commits != 1 {
		t.Fatalf("create=%d commit=%d", tx.createCalled, tx.commits)
	}
}

func TestNativeStartRecoversNetworkTermination(t *testing.T) {
	tx := validStartTx()
	tx.state.Sessions = []persistence.StartSessionRow{
		{ID: 41, Status: "terminated", StartTime: time.Now(), TerminatedByAdmin: false},
	}
	repo := newFakeStartRepo(tx)
	_, session, resumed, _, startErr := validService(repo).startTransaction(
		context.Background(), validStartRequest(t, true), 7, 5,
		&auth.Claims{Role: "student", StudentClass: "XII"},
	)
	if startErr != nil || !resumed || session.ID != 41 || session.Status != "in_progress" {
		t.Fatalf("session=%+v resumed=%v error=%v", session, resumed, startErr)
	}
	if tx.recoverCalled != 1 || tx.commits != 1 {
		t.Fatalf("recover=%d commit=%d", tx.recoverCalled, tx.commits)
	}
}

func TestNativeStartBlocksAnyAdminTerminationBeforeRecovery(t *testing.T) {
	tx := validStartTx()
	tx.state.Sessions = []persistence.StartSessionRow{
		{ID: 42, Status: "terminated", StartTime: time.Now()},
		{ID: 41, Status: "kicked", StartTime: time.Now().Add(-time.Minute), TerminatedByAdmin: true},
	}
	repo := newFakeStartRepo(tx)
	_, _, _, _, startErr := validService(repo).startTransaction(
		context.Background(), validStartRequest(t, true), 7, 5,
		&auth.Claims{Role: "student", StudentClass: "XII"},
	)
	if startErr == nil || startErr.Status != 409 || tx.recoverCalled != 0 {
		t.Fatalf("error=%v recover=%d", startErr, tx.recoverCalled)
	}
}

func TestNativeStartDuplicateRaceReturnsCanonicalSession(t *testing.T) {
	tx := validStartTx()
	tx.createErr = &pgconn.PgError{Code: "23505"}
	repo := newFakeStartRepo(tx)
	repo.raced = &persistence.StartSessionRow{
		ID: 77, UserID: 5, ExamID: 7, Status: "in_progress", StartTime: time.Now(),
	}
	_, session, resumed, _, startErr := validService(repo).startTransaction(
		context.Background(), validStartRequest(t, true), 7, 5,
		&auth.Claims{Role: "student", StudentClass: "XII"},
	)
	if startErr != nil || !resumed || session.ID != 77 {
		t.Fatalf("session=%+v resumed=%v error=%v", session, resumed, startErr)
	}
	if tx.rollbacks != 1 || tx.commits != 0 {
		t.Fatalf("rollback=%d commit=%d", tx.rollbacks, tx.commits)
	}
}

func TestNativeStartSimultaneousDuplicateRequestsConverge(t *testing.T) {
	first := validStartTx()
	second := validStartTx()
	second.createErr = &pgconn.PgError{Code: "23505"}
	repo := newFakeStartRepo(first)
	repo.txQueue = []*fakeStartTx{first, second}
	repo.raced = first.createdSession
	service := validService(repo)
	claims := &auth.Claims{Role: "student", StudentClass: "XII"}
	request := validStartRequest(t, true)
	type result struct {
		session *persistence.StartSessionRow
		err     *startHTTPError
	}
	results := make(chan result, 2)
	for i := 0; i < 2; i++ {
		go func() {
			_, session, _, _, startErr := service.startTransaction(
				context.Background(), request, 7, 5, claims,
			)
			results <- result{session: session, err: startErr}
		}()
	}
	for i := 0; i < 2; i++ {
		result := <-results
		if result.err != nil || result.session == nil || result.session.ID != 99 {
			t.Fatalf("session=%+v error=%v", result.session, result.err)
		}
	}
	if first.commits != 1 || second.rollbacks != 1 {
		t.Fatalf("first commits=%d second rollbacks=%d", first.commits, second.rollbacks)
	}
}

func TestNativeStartFailurePathsRollback(t *testing.T) {
	tests := []struct {
		name      string
		configure func(*fakeStartTx)
	}{
		{"db", func(tx *fakeStartTx) { tx.examErr = errors.New("db") }},
		{"log", func(tx *fakeStartTx) { tx.createErr = errors.New("log") }},
		{"commit", func(tx *fakeStartTx) { tx.commitErr = errors.New("commit") }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			tx := validStartTx()
			test.configure(tx)
			repo := newFakeStartRepo(tx)
			_, _, _, _, startErr := validService(repo).startTransaction(
				context.Background(), validStartRequest(t, true), 7, 5,
				&auth.Claims{Role: "student", StudentClass: "XII"},
			)
			if startErr == nil || startErr.Status != 500 || tx.commits != 0 || tx.rollbacks != 1 {
				t.Fatalf("error=%v commit=%d rollback=%d", startErr, tx.commits, tx.rollbacks)
			}
		})
	}
}

func TestNativeStartRedisFailureOccursAfterCommit(t *testing.T) {
	tx := validStartTx()
	repo := newFakeStartRepo(tx)
	repo.questions = []persistence.QuestionRow{validQuestion()}
	repo.redisSetErr["exam_session:99"] = errors.New("redis down")
	_, startErr := validService(repo).start(validStartRequest(t, true), 7)
	if startErr == nil || startErr.Status != 500 {
		t.Fatalf("error=%v", startErr)
	}
	if tx.commits != 1 || tx.rollbacks != 0 {
		t.Fatalf("commit=%d rollback=%d", tx.commits, tx.rollbacks)
	}
}

func TestStartSecurityParity(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "https://example.test/api/exams/7/start", nil)
	settings := persistence.StartSecuritySettings{}
	if err := validateStartSXB(request, settings, true); err == nil || err.Status != 403 {
		t.Fatalf("missing SXB should fail: %v", err)
	}
	settings.DeveloperMode = true
	if err := validateStartSXB(request, settings, true); err != nil {
		t.Fatalf("developer mode should bypass: %v", err)
	}
	settings = persistence.StartSecuritySettings{
		AllowMobileApps: true,
		MinimumAPKToken: "BUILD-20260125120000-ABC123",
	}
	request.Header.Set("User-Agent", "SXB-Client")
	request.Header.Set("X-Build-Token", "BUILD-20260125120000-ABC123")
	repo := newFakeStartRepo(validStartTx())
	if err := validateStartSEB(
		context.Background(), repo, request, 7, settings,
		"default-seb-config-key", true, "seb:challenge:",
	); err != nil {
		t.Fatalf("trusted mobile should bypass SEB: %v", err)
	}
	request.Header.Del("X-Build-Token")
	configHash := sha256.Sum256([]byte(repo.sebConfig))
	request.Header.Set("X-SafeExamBrowser-ConfigKeyHash", hex.EncodeToString(configHash[:]))
	if err := validateStartSEB(
		context.Background(), repo, request, 7, settings,
		"default-seb-config-key", true, "seb:challenge:",
	); err != nil {
		t.Fatalf("valid SEB hash should pass: %v", err)
	}
	request.Header.Set("X-SafeExamBrowser-ConfigKeyHash", "deadbeef")
	invalid := validateStartSEB(
		context.Background(), repo, request, 7, settings,
		"default-seb-config-key", true, "seb:challenge:",
	)
	if invalid == nil || invalid.Status != http.StatusForbidden {
		t.Fatalf("invalid SEB hash should fail: %v", invalid)
	}
	detail, _ := invalid.Detail.(map[string]any)
	if detail["error"] != "INVALID_SEB_CONFIG" {
		t.Fatalf("detail=%v", invalid.Detail)
	}
}

func TestStartAdmissionLimitAndCancellation(t *testing.T) {
	gate := newStartAdmission(4)
	var current atomic.Int32
	var peak atomic.Int32
	releaseAll := make(chan struct{})
	started := make(chan struct{}, 8)
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			release, err := gate.acquire(context.Background())
			if err != nil {
				return
			}
			value := current.Add(1)
			for value > peak.Load() && !peak.CompareAndSwap(peak.Load(), value) {
			}
			started <- struct{}{}
			<-releaseAll
			current.Add(-1)
			release()
		}()
	}
	for i := 0; i < 4; i++ {
		<-started
	}
	deadline := time.Now().Add(time.Second)
	for gate.snapshot().Waiters != 4 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if snapshot := gate.snapshot(); snapshot.Holders != 4 || snapshot.Waiters != 4 {
		t.Fatalf("snapshot=%+v", snapshot)
	}
	close(releaseAll)
	wg.Wait()
	if peak.Load() > 4 || gate.snapshot().Holders != 0 {
		t.Fatalf("peak=%d snapshot=%+v", peak.Load(), gate.snapshot())
	}

	holderReleases := make([]func(), 0, 4)
	for i := 0; i < 4; i++ {
		release, err := gate.acquire(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		holderReleases = append(holderReleases, release)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if release, err := gate.acquire(ctx); !errors.Is(err, context.Canceled) || release != nil {
		t.Fatalf("release_nil=%v error=%v", release == nil, err)
	}
	for _, release := range holderReleases {
		release()
	}
}

func TestCancellationRollbackUsesLiveContext(t *testing.T) {
	tx := validStartTx()
	tx.examErr = context.Canceled
	repo := newFakeStartRepo(tx)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, _, _, _, startErr := validService(repo).startTransaction(
		ctx, validStartRequest(t, true), 7, 5,
		&auth.Claims{Role: "student", StudentClass: "XII"},
	)
	if startErr == nil || tx.rollbacks != 1 || tx.rollbackCanceled {
		t.Fatalf("error=%v rollback=%d canceled=%v", startErr, tx.rollbacks, tx.rollbackCanceled)
	}
}

func TestBuildStartQuestionParityFixtures(t *testing.T) {
	fixture := loadStartParityFixture(t)
	rows := []persistence.QuestionRow{
		{ID: 11, Text: "Q11", Type: "multiple_choice", Points: 1, OrderIndex: 0, Settings: []byte(`{}`), Options: parityOptions()},
		{ID: 12, Text: "Q12", Type: "multiple_choice", Points: 1, OrderIndex: 1, Settings: []byte(`{}`), Options: parityOptions()},
		{ID: 13, Text: "Q13", Type: "multiple_choice", Points: 1, OrderIndex: 2, Settings: []byte(`{}`), Options: parityOptions()},
		{ID: 14, Text: "Q14", Type: "multiple_choice", Points: 1, OrderIndex: 3, Settings: []byte(`{}`), Options: parityOptions()},
	}
	questions, startErr := buildStartQuestions(rows, 9, 42, true, true, "test-secret")
	if startErr != nil {
		t.Fatal(startErr)
	}
	ids := make([]int, 0, len(questions))
	for _, question := range questions {
		ids = append(ids, question.ID)
	}
	if !reflect.DeepEqual(ids, fixture.QuestionOrder) {
		t.Fatalf("question order=%v", ids)
	}
	var options []int
	for _, question := range questions {
		if question.ID == 11 {
			for _, option := range question.Options {
				options = append(options, option.ID)
			}
		}
	}
	if !reflect.DeepEqual(options, fixture.OptionOrderQuestion11) {
		t.Fatalf("option order=%v", options)
	}
}

func TestBuildStartTableAndImageParity(t *testing.T) {
	fixture := loadStartParityFixture(t)
	pgk := "table_validation"
	image := "/static/q.png"
	rows := []persistence.QuestionRow{
		{
			ID: 21, Text: "Tabel", Type: "multiple_choice_complex", PgkType: &pgk,
			Points: 1, Settings: []byte(`{"allow_table_statement_shuffle":true,"statements":["A","B","C"]}`),
		},
		{
			ID: 22, Text: "", Type: "multiple_choice", Points: 1, ImageURL: &image,
			Settings: []byte(`{"is_placeholder":true,"placeholder_source":"image","allow_placeholder_shuffle":true}`),
			Options:  parityOptions(),
		},
	}
	questions, startErr := buildStartQuestions(rows, 3, 7, false, true, "test-secret")
	if startErr != nil {
		t.Fatal(startErr)
	}
	statements := questions[0].QuestionSettings["statements"].([]any)
	indexes := make([]int, 0, len(statements))
	for _, raw := range statements {
		indexes = append(indexes, raw.(map[string]any)["original_index"].(int))
	}
	if !reflect.DeepEqual(indexes, fixture.TableStatementOrder) {
		t.Fatalf("statement order=%v", indexes)
	}
	if questions[1].QuestionText != fixture.ImagePlaceholderText {
		t.Fatalf("image fallback=%q", questions[1].QuestionText)
	}
	optionIDs := []int{}
	for _, option := range questions[1].Options {
		optionIDs = append(optionIDs, option.ID)
	}
	if !reflect.DeepEqual(optionIDs, fixture.ImagePlaceholderOptionOrder) {
		t.Fatalf("image placeholder options shuffled: %v", optionIDs)
	}
}

func parityOptions() []persistence.OptionRow {
	return []persistence.OptionRow{
		{ID: 1, Text: "A", OrderIndex: 0, OptionGroup: "standard"},
		{ID: 2, Text: "B", OrderIndex: 1, OptionGroup: "standard"},
		{ID: 3, Text: "C", OrderIndex: 2, OptionGroup: "standard"},
		{ID: 4, Text: "D", OrderIndex: 3, OptionGroup: "standard"},
	}
}

func stringPointer(value string) *string {
	return &value
}

type startParityFixture struct {
	StableShuffle               []int    `json:"stable_shuffle"`
	QuestionOrder               []int    `json:"question_order"`
	OptionOrderQuestion11       []int    `json:"option_order_question_11"`
	TableStatementOrder         []int    `json:"table_statement_order"`
	ImagePlaceholderText        string   `json:"image_placeholder_text"`
	ImagePlaceholderOptionOrder []int    `json:"image_placeholder_option_order"`
	QuestionKeys                []string `json:"question_keys"`
	OptionKeys                  []string `json:"option_keys"`
	ResponseKeys                []string `json:"response_keys"`
	DifficultyDefault           string   `json:"difficulty_default"`
	Points                      struct {
		IntLike    string `json:"int_like"`
		From100    string `json:"from_1_00"`
		Fractional string `json:"fractional"`
		Zero       string `json:"zero"`
	} `json:"points"`
}

func extraJSONKeys(encoded map[string]any, allowed []string) []string {
	permitted := map[string]struct{}{}
	for _, key := range allowed {
		permitted[key] = struct{}{}
	}
	extra := make([]string, 0)
	for key := range encoded {
		if _, ok := permitted[key]; !ok {
			extra = append(extra, key)
		}
	}
	return extra
}

func loadStartParityFixture(t *testing.T) startParityFixture {
	t.Helper()
	raw, err := os.ReadFile("testdata/fastapi_start_parity.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture startParityFixture
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	return fixture
}
