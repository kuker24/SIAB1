package exam

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

const sessionPollTokenExpiresMinutes = 15

type startRepository interface {
	startSecurityRepository
	BeginStart(context.Context) (persistence.StartTransaction, error)
	CanonicalActiveStartSession(context.Context, int, int) (*persistence.StartSessionRow, error)
	LoadQuestions(context.Context, int) ([]persistence.QuestionRow, error)
	RedisSetNX(context.Context, string, string, time.Duration) (bool, error)
	RedisDelete(context.Context, string) error
	RedisPublish(context.Context, string, string) error
	RedisXAdd(context.Context, string, string, int, int) error
}

type startHTTPError struct {
	Status       int
	Detail       any
	RedirectHTML string
}

func (e *startHTTPError) Error() string {
	return fmt.Sprint(e.Detail)
}

func startError(status int, detail any) *startHTTPError {
	return &startHTTPError{Status: status, Detail: detail}
}

type startService struct {
	repo                  startRepository
	gate                  *startAdmission
	jwtSecret             string
	appSecret             string
	enforceSXB            bool
	defaultSEBKey         string
	challengeEnabled      bool
	challengePrefix       string
	monitoringDelta       bool
	monitoringDeltaMaxLen int
	monitoringDeltaTTL    int
}

type nativeStartResponse struct {
	SessionID                      int                     `json:"session_id"`
	ExamID                         int                     `json:"exam_id"`
	ExamTitle                      string                  `json:"exam_title"`
	DurationMinutes                int                     `json:"duration_minutes"`
	QuestionCount                  int                     `json:"question_count"`
	StartTime                      string                  `json:"start_time"`
	EndTime                        string                  `json:"end_time"`
	ServerTime                     string                  `json:"server_time"`
	ShowResults                    bool                    `json:"show_results"`
	ShowTeacherName                bool                    `json:"show_teacher_name"`
	TeacherName                    *string                 `json:"teacher_name"`
	Subject                        *string                 `json:"subject"`
	ExamType                       *string                 `json:"exam_type"`
	ShuffleQuestions               bool                    `json:"shuffle_questions"`
	ShuffleOptions                 bool                    `json:"shuffle_options"`
	SessionPollToken               string                  `json:"session_poll_token"`
	SessionPollTokenExpiresMinutes int                     `json:"session_poll_token_expires_minutes"`
	Questions                      []startQuestionResponse `json:"questions"`
}

func (d deps) startExam(w http.ResponseWriter, r *http.Request) {
	if d.store == nil || !d.store.HasPool() {
		writeDetail(w, http.StatusServiceUnavailable, "Database tidak tersedia")
		return
	}
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
		return
	}
	service := startService{
		repo:                  d.store,
		gate:                  d.startGate,
		jwtSecret:             d.secret,
		appSecret:             d.appSecret,
		enforceSXB:            d.enforceSXB,
		defaultSEBKey:         d.sebKey,
		challengeEnabled:      d.sebChallenge,
		challengePrefix:       d.sebChallengePrefix,
		monitoringDelta:       d.monitoringDelta,
		monitoringDeltaMaxLen: d.monitoringDeltaMaxLen,
		monitoringDeltaTTL:    d.monitoringDeltaTTL,
	}
	response, startErr := service.start(r, examID)
	if startErr != nil {
		log.Printf("go_start outcome=failure exam_id=%d status=%d", examID, startErr.Status)
		if errors.Is(r.Context().Err(), context.Canceled) {
			return
		}
		if startErr.RedirectHTML != "" && strings.Contains(r.Header.Get("Accept"), "text/html") {
			http.Redirect(w, r, startErr.RedirectHTML, http.StatusSeeOther)
			return
		}
		if startErr.Status == http.StatusUnauthorized {
			w.Header().Set("WWW-Authenticate", "Bearer")
		}
		writeJSON(w, startErr.Status, map[string]any{"detail": startErr.Detail})
		return
	}
	log.Printf("go_start outcome=success exam_id=%d session_id=%d", examID, response.SessionID)
	writeJSON(w, http.StatusOK, response)
}

func (s startService) start(r *http.Request, examID int) (*nativeStartResponse, *startHTTPError) {
	ctx := r.Context()
	securitySettings := s.loadSecuritySettings(ctx)
	if err := validateStartSXB(r, securitySettings, s.enforceSXB); err != nil {
		return nil, err
	}
	token := auth.Bearer(r.Header.Get("Authorization"))
	if token == "" {
		return nil, startError(http.StatusForbidden, "Not authenticated")
	}
	claims, err := auth.Parse(s.jwtSecret, token)
	if err != nil {
		return nil, startError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	if !claims.Active() {
		return nil, startError(http.StatusForbidden, "Akun tidak aktif")
	}
	role := strings.ToLower(strings.TrimSpace(claims.Role))
	if role != "student" && role != "guruplus" {
		return nil, startError(http.StatusForbidden, "Hanya peserta ujian yang dapat mengikuti ujian")
	}
	userID, err := claims.UserID()
	if err != nil {
		return nil, startError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}

	securityRelease, acquireErr := s.gate.acquire(ctx)
	if acquireErr != nil {
		return nil, startError(http.StatusInternalServerError, "Internal Server Error")
	}
	sebErr := validateStartSEB(
		ctx, s.repo, r, examID, securitySettings, s.defaultSEBKey,
		s.challengeEnabled, s.challengePrefix,
	)
	securityRelease()
	if sebErr != nil {
		return nil, sebErr
	}

	mainRelease, acquireErr := s.gate.acquire(ctx)
	if acquireErr != nil {
		return nil, startError(http.StatusInternalServerError, "Internal Server Error")
	}
	exam, session, resumed, now, txErr := s.startTransaction(ctx, r, examID, userID, claims)
	mainRelease()
	if txErr != nil {
		return nil, txErr
	}

	existingSnapshot := map[string]any(nil)
	if resumed {
		raw, found, err := s.repo.RedisGet(ctx, "exam_session:"+strconv.Itoa(session.ID))
		if err != nil {
			return nil, startError(http.StatusInternalServerError, "Internal Server Error")
		}
		if found {
			if json.Unmarshal([]byte(raw), &existingSnapshot) != nil || existingSnapshot == nil {
				return nil, startError(http.StatusInternalServerError, "Internal Server Error")
			}
		}
	}
	snapshot := buildSessionSnapshot(session, exam, userID, existingSnapshot)
	if err := s.storeSessionSnapshot(ctx, session.ID, snapshot); err != nil {
		return nil, startError(http.StatusInternalServerError, "Internal Server Error")
	}
	monitorEvent := map[string]any{
		"type":       "student_started",
		"user_id":    userID,
		"username":   claims.Username,
		"session_id": session.ID,
		"timestamp":  pythonISOTime(now),
	}
	monitorJSON, _ := json.Marshal(monitorEvent)
	if err := s.repo.RedisPublish(ctx, "exam_monitor_"+strconv.Itoa(examID), string(monitorJSON)); err != nil {
		return nil, startError(http.StatusInternalServerError, "Internal Server Error")
	}
	s.publishMonitoringDelta(ctx, examID, monitorEvent)

	questionRows, questionErr := s.loadStartQuestions(ctx, examID)
	if questionErr != nil {
		return nil, questionErr
	}
	if len(questionRows) == 0 {
		return nil, startError(http.StatusNotFound, "Soal ujian tidak ditemukan")
	}
	if jsonInt(snapshot["total_questions"]) != len(questionRows) {
		snapshot["total_questions"] = len(questionRows)
		if err := s.storeSessionSnapshot(ctx, session.ID, snapshot); err != nil {
			return nil, startError(http.StatusInternalServerError, "Internal Server Error")
		}
	}
	questions, buildErr := buildStartQuestions(
		questionRows, exam.ID, userID, exam.ShuffleQuestions,
		exam.ShuffleOptions, s.appSecret,
	)
	if buildErr != nil {
		return nil, buildErr
	}
	pollToken, err := auth.SessionPollToken(s.jwtSecret, session.ID, userID)
	if err != nil {
		return nil, startError(http.StatusInternalServerError, "Internal Server Error")
	}
	var teacherName *string
	if exam.TeacherVisible() {
		teacherName = exam.TeacherName
	}
	serverTime := time.Now().UTC().Truncate(time.Microsecond)
	return &nativeStartResponse{
		SessionID:                      session.ID,
		ExamID:                         exam.ID,
		ExamTitle:                      exam.Title,
		DurationMinutes:                exam.DurationMinutes,
		QuestionCount:                  len(questions),
		StartTime:                      pythonTime(session.StartTime),
		EndTime:                        pythonTime(session.StartTime.Add(time.Duration(exam.DurationMinutes) * time.Minute)),
		ServerTime:                     pythonTime(serverTime),
		ShowResults:                    exam.ShowResults,
		ShowTeacherName:                exam.ShowTeacher(),
		TeacherName:                    teacherName,
		Subject:                        exam.Subject,
		ExamType:                       exam.ExamType,
		ShuffleQuestions:               exam.ShuffleQuestions,
		ShuffleOptions:                 exam.ShuffleOptions,
		SessionPollToken:               pollToken,
		SessionPollTokenExpiresMinutes: sessionPollTokenExpiresMinutes,
		Questions:                      questions,
	}, nil
}

func (s startService) loadSecuritySettings(ctx context.Context) persistence.StartSecuritySettings {
	settings, err := s.repo.LoadStartSecuritySettings(ctx)
	if err != nil {
		return persistence.StartSecuritySettings{AllowMobileApps: true}
	}
	return settings
}

func (s startService) publishMonitoringDelta(ctx context.Context, examID int, payload map[string]any) {
	if !s.monitoringDelta {
		return
	}
	event, err := json.Marshal(map[string]any{
		"event_type": payload["type"],
		"payload":    payload,
		"ts":         pythonISOTime(time.Now().UTC()),
	})
	if err != nil {
		return
	}
	_ = s.repo.RedisXAdd(
		ctx,
		"monitoring:delta:exam:"+strconv.Itoa(examID),
		string(event),
		s.monitoringDeltaMaxLen,
		s.monitoringDeltaTTL,
	)
}

func (s startService) startTransaction(
	ctx context.Context,
	r *http.Request,
	examID int,
	userID int,
	claims *auth.Claims,
) (*persistence.StartExamRow, *persistence.StartSessionRow, bool, time.Time, *startHTTPError) {
	tx, err := s.repo.BeginStart(ctx)
	if err != nil {
		return nil, nil, false, time.Time{}, startError(500, "Internal Server Error")
	}
	finished := false
	defer func() {
		if !finished {
			rollbackStartTransaction(ctx, tx)
		}
	}()
	exam, err := tx.Exam(ctx, examID)
	if err != nil {
		return nil, nil, false, time.Time{}, startError(500, "Internal Server Error")
	}
	if exam == nil {
		return nil, nil, false, time.Time{}, startError(404, "Ujian tidak ditemukan")
	}
	if integrityErr := s.ensureOptionIntegrity(ctx, tx, examID); integrityErr != nil {
		return nil, nil, false, time.Time{}, integrityErr
	}
	if !exam.Published {
		return nil, nil, false, time.Time{}, startError(400, "Ujian belum dipublikasikan")
	}
	now := time.Now().UTC().Truncate(time.Microsecond)
	if now.Before(exam.StartTime) {
		return nil, nil, false, time.Time{}, startError(400, "Ujian belum dimulai")
	}
	if now.After(exam.EndTime) {
		return nil, nil, false, time.Time{}, startError(400, "Ujian sudah berakhir")
	}
	accessView := &persistence.ExamRow{
		AllowedClasses:  exam.AllowedClasses,
		AllowedStudents: exam.AllowedStudents,
		CreatorRole:     exam.CreatorRole,
	}
	if ok, detail := participantAccess(accessView, userID, claims.Role, claims.StudentClass); !ok {
		return nil, nil, false, time.Time{}, startError(403, detail)
	}
	state, err := tx.SessionState(ctx, userID, examID)
	if err != nil {
		return nil, nil, false, time.Time{}, startError(500, "Internal Server Error")
	}
	if state.AttemptCount >= exam.MaxAttempts {
		return nil, nil, false, time.Time{}, startError(400, "Batas percobaan sudah tercapai")
	}
	answerCounts := map[int]int{}
	if len(state.Sessions) > 1 {
		ids := make([]int, 0, len(state.Sessions))
		for _, candidate := range state.Sessions {
			ids = append(ids, candidate.ID)
		}
		answerCounts, err = tx.AnswerCounts(ctx, ids)
		if err != nil {
			return nil, nil, false, time.Time{}, startError(500, "Internal Server Error")
		}
	}
	sortStartSessions(state.Sessions, answerCounts)
	var selected *persistence.StartSessionRow
	resumed := false
	for index := range state.Sessions {
		if state.Sessions[index].Status == "in_progress" || state.Sessions[index].Status == "active" {
			copy := state.Sessions[index]
			selected = &copy
			resumed = true
			break
		}
	}
	if selected == nil {
		type recoveryCandidate struct {
			session persistence.StartSessionRow
			result  recoveryResult
		}
		candidates := make([]recoveryCandidate, 0, len(state.Sessions))
		for index := range state.Sessions {
			candidate := state.Sessions[index]
			if candidate.Status != "terminated" && candidate.Status != "kicked" {
				continue
			}
			logs, err := tx.SessionLogs(ctx, candidate.ID, 30)
			if err != nil {
				return nil, nil, false, time.Time{}, startError(500, "Internal Server Error")
			}
			recovery := evaluateSessionRecovery(
				candidate.Status, candidate.TerminatedByAdmin,
				candidate.ViolationCount, logs,
			)
			if recovery.Category == "admin_decision" {
				return nil, nil, false, time.Time{}, startError(
					409,
					"Sesi dihentikan oleh pengawas/admin. Hubungi pengawas untuk membuka kembali sesi.",
				)
			}
			candidates = append(candidates, recoveryCandidate{session: candidate, result: recovery})
		}
		for _, candidate := range candidates {
			if !candidate.result.AllowContinue {
				continue
			}
			selected, err = tx.RecoverSession(
				ctx, candidate.session, candidate.result.Category, candidate.result.Message,
			)
			if err != nil {
				return nil, nil, false, time.Time{}, startError(500, "Internal Server Error")
			}
			resumed = true
			break
		}
	}
	if selected == nil {
		userAgent := r.Header.Get("User-Agent")
		if userAgent == "" {
			userAgent = "unknown"
		}
		client := persistence.StartClientInfo{
			IPAddress:   clientIP(r),
			UserAgent:   userAgent,
			SEBDetected: r.Header.Get("X-SafeExamBrowser-ConfigKeyHash") != "",
			StartTime:   now,
		}
		selected, err = tx.CreateSessionWithLog(ctx, userID, examID, client, persistence.SessionStartLog{
			IP:              client.IPAddress,
			SEBDetected:     client.SEBDetected,
			Title:           exam.Title,
			Subject:         exam.Subject,
			ExamType:        exam.ExamType,
			AllowedClasses:  exam.AllowedClasses,
			AllowedStudents: exam.AllowedStudents,
			ExamStartTime:   exam.StartTime,
			ExamEndTime:     exam.EndTime,
			DurationMinutes: exam.DurationMinutes,
		})
		if err != nil {
			if persistence.IsIntegrityError(err) {
				rollbackStartTransaction(ctx, tx)
				finished = true
				raced, lookupErr := s.repo.CanonicalActiveStartSession(ctx, userID, examID)
				if lookupErr != nil || raced == nil {
					return nil, nil, false, time.Time{}, startError(
						409, "Konflik saat memulai sesi ujian, silakan coba lagi.",
					)
				}
				return exam, raced, true, now, nil
			}
			return nil, nil, false, time.Time{}, startError(500, "Internal Server Error")
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, nil, false, time.Time{}, startError(500, "Internal Server Error")
	}
	finished = true
	return exam, selected, resumed, now, nil
}

func sortStartSessions(sessions []persistence.StartSessionRow, answerCounts map[int]int) {
	sort.SliceStable(sessions, func(i, j int) bool {
		left, right := sessions[i], sessions[j]
		if answerCounts[left.ID] != answerCounts[right.ID] {
			return answerCounts[left.ID] > answerCounts[right.ID]
		}
		if !left.StartTime.Equal(right.StartTime) {
			return left.StartTime.After(right.StartTime)
		}
		return left.ID > right.ID
	})
}

func rollbackStartTransaction(ctx context.Context, tx persistence.StartTransaction) {
	rollbackCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 3*time.Second)
	defer cancel()
	_ = tx.Rollback(rollbackCtx)
}

func (s startService) ensureOptionIntegrity(
	ctx context.Context,
	tx persistence.StartTransaction,
	examID int,
) *startHTTPError {
	cacheKey := "cache:exam-start-validation:v1:" + strconv.Itoa(examID)
	if cached, found, err := s.repo.RedisGet(ctx, cacheKey); err == nil && found && cached == "1" {
		return nil
	}
	tokenBytes := make([]byte, 16)
	_, _ = rand.Read(tokenBytes)
	token := hex.EncodeToString(tokenBytes)
	lockKey := cacheKey + ":lock"
	locked, redisErr := s.repo.RedisSetNX(ctx, lockKey, token, 15*time.Second)
	if redisErr == nil && !locked {
		deadline := time.NewTimer(12 * time.Second)
		ticker := time.NewTicker(50 * time.Millisecond)
		defer deadline.Stop()
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return startError(500, "Internal Server Error")
			case <-deadline.C:
				return nil
			case <-ticker.C:
				if cached, found, err := s.repo.RedisGet(ctx, cacheKey); err == nil && found && cached == "1" {
					return nil
				}
			}
		}
	}
	orphans, err := tx.ValidateOptionIntegrity(ctx, examID)
	if err != nil {
		return startError(500, "Internal Server Error")
	}
	if len(orphans) > 0 {
		return startError(500, fmt.Sprintf(
			"Ujian memiliki %d soal pilihan ganda tanpa pilihan jawaban. Tidak bisa dimulai. Silakan hubungi pengawas atau administrator.",
			len(orphans),
		))
	}
	_ = s.repo.RedisSet(ctx, cacheKey, "1", 120*time.Second)
	if redisErr == nil && locked {
		if current, found, err := s.repo.RedisGet(ctx, lockKey); err == nil && found && current == token {
			_ = s.repo.RedisDelete(ctx, lockKey)
		}
	}
	return nil
}

func buildSessionSnapshot(
	session *persistence.StartSessionRow,
	exam *persistence.StartExamRow,
	userID int,
	existing map[string]any,
) map[string]any {
	startedAt := pythonISOTime(session.StartTime)
	if value, ok := existing["started_at"].(string); ok && value != "" {
		startedAt = value
	}
	snapshot := map[string]any{
		"session_id":           session.ID,
		"user_id":              userID,
		"exam_id":              exam.ID,
		"start_time":           pythonISOTime(session.StartTime),
		"end_time":             nil,
		"started_at":           startedAt,
		"duration_seconds":     exam.DurationMinutes * 60,
		"elapsed_seconds":      jsonInt(existing["elapsed_seconds"]),
		"paused":               false,
		"duration_minutes":     exam.DurationMinutes,
		"status":               "in_progress",
		"answered_count":       jsonInt(existing["answered_count"]),
		"answered_count_stale": false,
		"total_questions":      jsonInt(existing["total_questions"]),
		"violation_count":      session.ViolationCount,
	}
	if session.EndTime != nil {
		snapshot["end_time"] = pythonISOTime(*session.EndTime)
	}
	paused := session.TotalPausedSeconds
	if cached := jsonInt(existing["total_paused_seconds"]); cached > paused {
		paused = cached
	}
	if paused > 0 {
		snapshot["total_paused_seconds"] = paused
	}
	return snapshot
}

func (s startService) storeSessionSnapshot(ctx context.Context, sessionID int, snapshot map[string]any) error {
	encoded, err := json.Marshal(snapshot)
	if err != nil {
		return err
	}
	return s.repo.RedisSet(ctx, "exam_session:"+strconv.Itoa(sessionID), string(encoded), 2*time.Hour)
}

type cachedStartQuestion struct {
	ID               int             `json:"id"`
	QuestionText     string          `json:"question_text"`
	Stimulus         *string         `json:"stimulus"`
	QuestionType     string          `json:"question_type"`
	PgkType          *string         `json:"pgk_type"`
	Points           json.RawMessage `json:"points"`
	OrderIndex       int             `json:"order_index"`
	ImageURL         *string         `json:"image_url"`
	VideoURL         *string         `json:"video_url"`
	AudioURL         *string         `json:"audio_url"`
	QuestionSettings json.RawMessage `json:"question_settings"`
	Options          []struct {
		ID          int     `json:"id"`
		OptionText  string  `json:"option_text"`
		OrderIndex  int     `json:"order_index"`
		OptionGroup string  `json:"option_group"`
		PairID      *string `json:"pair_id"`
	} `json:"options"`
}

func (s startService) loadStartQuestions(ctx context.Context, examID int) ([]persistence.QuestionRow, *startHTTPError) {
	cacheKey := "exam:" + strconv.Itoa(examID) + ":questions:payload:v1"
	if raw, found, err := s.repo.RedisGet(ctx, cacheKey); err == nil && found {
		if rows, ok := decodeCachedStartQuestions(raw, examID); ok {
			return rows, nil
		}
		return nil, startError(500, "Internal Server Error")
	}
	release, err := s.gate.acquire(ctx)
	if err != nil {
		return nil, startError(500, "Internal Server Error")
	}
	rows, loadErr := s.repo.LoadQuestions(ctx, examID)
	release()
	if loadErr != nil {
		return nil, startError(500, "Internal Server Error")
	}
	for index := range rows {
		// FastAPI's v1 question cache omits difficulty_level.
		rows[index].Difficulty = ""
	}
	if encoded, err := encodeCachedStartQuestions(rows); err == nil {
		_ = s.repo.RedisSet(ctx, cacheKey, encoded, 30*time.Minute)
	}
	return rows, nil
}

func decodeCachedStartQuestions(raw string, examID int) ([]persistence.QuestionRow, bool) {
	var cached []cachedStartQuestion
	if json.Unmarshal([]byte(raw), &cached) != nil {
		return nil, false
	}
	rows := make([]persistence.QuestionRow, 0, len(cached))
	for _, item := range cached {
		pointsText := strings.Trim(string(item.Points), "\"")
		points, err := strconv.ParseFloat(pointsText, 64)
		if err != nil {
			points = 0
		}
		row := persistence.QuestionRow{
			ID: item.ID, ExamID: examID, Text: item.QuestionText,
			Stimulus: item.Stimulus, Type: item.QuestionType, PgkType: item.PgkType,
			Settings: append([]byte(nil), item.QuestionSettings...), Points: points,
			PointsText: pointsText, OrderIndex: item.OrderIndex,
			ImageURL: item.ImageURL, VideoURL: item.VideoURL, AudioURL: item.AudioURL,
		}
		for _, option := range item.Options {
			row.Options = append(row.Options, persistence.OptionRow{
				ID: option.ID, QuestionID: item.ID, Text: option.OptionText,
				OrderIndex: option.OrderIndex, OptionGroup: option.OptionGroup,
				PairID: option.PairID,
			})
		}
		rows = append(rows, row)
	}
	return rows, true
}

func encodeCachedStartQuestions(rows []persistence.QuestionRow) (string, error) {
	payload := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		settings := decodeQuestionSettings(row.Settings)
		options := make([]map[string]any, 0, len(row.Options))
		for _, option := range row.Options {
			group := option.OptionGroup
			if group == "" {
				group = "standard"
			}
			options = append(options, map[string]any{
				"id":           option.ID,
				"option_text":  option.Text,
				"order_index":  option.OrderIndex,
				"option_group": group,
				"pair_id":      option.PairID,
			})
		}
		points := row.PointsText
		if points == "" {
			points = pythonDecimalFromFloat(row.Points)
		}
		payload = append(payload, map[string]any{
			"id":                row.ID,
			"question_text":     row.Text,
			"stimulus":          row.Stimulus,
			"question_type":     row.Type,
			"pgk_type":          row.PgkType,
			"points":            points,
			"order_index":       row.OrderIndex,
			"image_url":         row.ImageURL,
			"video_url":         row.VideoURL,
			"audio_url":         row.AudioURL,
			"question_settings": settings,
			"options":           options,
		})
	}
	encoded, err := json.Marshal(payload)
	return string(encoded), err
}

func jsonInt(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case float64:
		return int(typed)
	case json.Number:
		parsed, _ := typed.Int64()
		return int(parsed)
	case string:
		parsed, _ := strconv.Atoi(typed)
		return parsed
	default:
		return 0
	}
}

func pythonTime(value time.Time) string {
	value = value.UTC().Truncate(time.Microsecond)
	base := value.Format("2006-01-02T15:04:05")
	if micros := value.Nanosecond() / 1000; micros > 0 {
		base += fmt.Sprintf(".%06d", micros)
	}
	return base + "Z"
}

func pythonISOTime(value time.Time) string {
	value = value.UTC().Truncate(time.Microsecond)
	base := value.Format("2006-01-02T15:04:05")
	if micros := value.Nanosecond() / 1000; micros > 0 {
		base += fmt.Sprintf(".%06d", micros)
	}
	return base + "+00:00"
}
