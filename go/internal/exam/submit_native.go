package exam

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

type submitHTTPError struct {
	Status  int
	Detail  any
	Headers map[string]string
}

func (e *submitHTTPError) Error() string { return "submit http error" }

func submitError(status int, detail any) *submitHTTPError {
	return &submitHTTPError{Status: status, Detail: detail}
}

type submitResponse struct {
	SessionID    int      `json:"session_id"`
	Status       string   `json:"status"`
	Score        *float64 `json:"score"`
	TotalPoints  *float64 `json:"total_points"`
	PointsEarned *float64 `json:"points_earned"`
	Percentage   *float64 `json:"percentage"`
	Passed       *bool    `json:"passed"`
	Message      string   `json:"message"`
}

func (d deps) submitExam(w http.ResponseWriter, r *http.Request) {
	if d.store == nil || !d.store.HasPool() {
		writeDetail(w, http.StatusServiceUnavailable, "Database tidak tersedia")
		return
	}
	response, err := d.acceptSubmit(r)
	if err != nil {
		if errors.Is(r.Context().Err(), context.Canceled) {
			return
		}
		if err.Status == http.StatusUnauthorized {
			w.Header().Set("WWW-Authenticate", "Bearer")
		}
		for key, value := range err.Headers {
			w.Header().Set(key, value)
		}
		writeJSON(w, err.Status, map[string]any{"detail": err.Detail})
		return
	}
	writeJSON(w, http.StatusOK, response)
}

func (d deps) acceptSubmit(r *http.Request) (*submitResponse, *submitHTTPError) {
	raw := auth.Bearer(r.Header.Get("Authorization"))
	if raw == "" {
		return nil, submitError(http.StatusUnauthorized, "Not authenticated")
	}
	claims, err := auth.Parse(d.secret, raw)
	if err != nil {
		return nil, submitError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	userID, err := claims.UserID()
	if err != nil {
		return nil, submitError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	if !claims.Active() {
		return nil, submitError(http.StatusForbidden, "Akun tidak aktif")
	}
	var body map[string]any
	if readErr := readJSON(r, &body); readErr != nil {
		return nil, submitError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	sessionID, ok := coerceSubmitInt(body["session_id"])
	if !ok {
		return nil, submitError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	forceSubmit := pythonBool(body["force_submit"])
	if !d.disableRateLimit {
		allowed, remaining := d.store.AllowSlidingRate(r.Context(), "exam_submit", strconv.Itoa(userID), 10, 60)
		if !allowed {
			return nil, &submitHTTPError{
				Status: http.StatusTooManyRequests,
				Detail: "Terlalu banyak percobaan submit. Tunggu beberapa saat.",
				Headers: map[string]string{
					"Retry-After":           "20",
					"X-RateLimit-Remaining": strconv.Itoa(remaining),
				},
			}
		}
	}
	probe, probeErr := d.store.LoadSubmitSession(r.Context(), sessionID, userID)
	if probeErr != nil {
		if persistence.IsTransientDB(probeErr) {
			return nil, busySubmit()
		}
		return nil, submitError(http.StatusInternalServerError, "Gagal memuat sesi")
	}
	if probe == nil {
		return nil, submitError(http.StatusNotFound, "Sesi ujian tidak ditemukan")
	}
	status := strings.ToLower(strings.TrimSpace(probe.Status))
	if status == "submitted" || status == "completed" {
		return alreadySubmittedResponse(*probe), nil
	}
	if status != "in_progress" {
		return nil, submitError(http.StatusBadRequest, "Sesi ujian sudah berakhir")
	}
	settings, settingsErr := d.store.LoadStartSecuritySettings(r.Context())
	if settingsErr != nil {
		return nil, submitError(http.StatusInternalServerError, "Internal Server Error")
	}
	if sebErr := validateStartSEB(
		r.Context(), d.store, r, probe.ExamID, settings, d.sebKey, d.sebChallenge, d.sebChallengePrefix,
	); sebErr != nil {
		return nil, submitError(sebErr.Status, sebErr.Detail)
	}
	submittedAt := time.Now().UTC()
	result, finErr := d.store.FinalizeNativeSubmit(r.Context(), sessionID, userID, forceSubmit, submittedAt, gradeSubmitSession)
	if finErr != nil {
		if persistence.IsTransientDB(finErr) {
			return nil, busySubmit()
		}
		log.Printf("go_submit finalize failed session=%d err=%v", sessionID, finErr)
		return nil, submitError(http.StatusInternalServerError, "Gagal mengumpulkan ujian")
	}
	if result.Status == "not_found" {
		return nil, submitError(http.StatusNotFound, "Sesi ujian tidak ditemukan")
	}
	if result.Status == "already" {
		return alreadySubmittedResponse(result.Row), nil
	}
	if result.Status == "ended" {
		return nil, submitError(http.StatusBadRequest, "Sesi ujian sudah berakhir")
	}
	_ = d.store.PatchSubmittedSnapshot(
		r.Context(), result.Row.ID, userID, result.Row.ExamID, result.Row.ViolationCount, result.Row.EndTime,
	)
	monitor, _ := json.Marshal(map[string]any{
		"type":       "student_submitted",
		"user_id":    userID,
		"username":   claims.Username,
		"session_id": result.Row.ID,
		"score":      result.Percentage,
		"timestamp":  time.Now().UTC().Format(time.RFC3339Nano),
	})
	_ = d.store.RedisPublish(r.Context(), "exam_monitor_"+strconv.Itoa(result.Row.ExamID), string(monitor))
	if d.monitoringDelta {
		_ = d.store.RedisXAdd(r.Context(), "exam_monitor_delta:"+strconv.Itoa(result.Row.ExamID), string(monitor), d.monitoringDeltaMaxLen, d.monitoringDeltaTTL)
	}
	show := result.Row.ShowResults
	resp := &submitResponse{
		SessionID: result.Row.ID,
		Status:    "submitted",
		Message:   "Ujian berhasil dikumpulkan",
	}
	if forceSubmit {
		resp.Message = "Ujian dikumpulkan otomatis karena pelanggaran"
	}
	if show {
		score := result.Percentage
		total := result.TotalPoints
		earned := result.PointsEarned
		resp.Score = &score
		resp.TotalPoints = &total
		resp.PointsEarned = &earned
		resp.Percentage = &score
		if result.Row.PassingScore != nil && *result.Row.PassingScore != 0 {
			passed := result.Percentage >= *result.Row.PassingScore
			resp.Passed = &passed
		}
	}
	return resp, nil
}

func alreadySubmittedResponse(row persistence.SubmitSessionRow) *submitResponse {
	resp := &submitResponse{
		SessionID: row.ID,
		Status:    "submitted",
		Message:   "Sesi sudah pernah dikumpulkan.",
	}
	if row.ShowResults && row.Score != nil {
		score := *row.Score
		resp.Score = &score
		resp.Percentage = &score
		if row.PassingScore != nil && *row.PassingScore != 0 {
			passed := score >= *row.PassingScore
			resp.Passed = &passed
		}
	}
	return resp
}

func busySubmit() *submitHTTPError {
	return &submitHTTPError{
		Status:  http.StatusServiceUnavailable,
		Detail:  "Server sedang sibuk, silakan ulangi submit.",
		Headers: map[string]string{"Retry-After": "1"},
	}
}

func gradeSubmitSession(questions []persistence.QuestionRow, answers []persistence.SubmitAnswerGrade) persistence.SubmitGradeOutput {
	latest := map[int]persistence.SubmitAnswerGrade{}
	for _, answer := range answers {
		cur, ok := latest[answer.QuestionID]
		if !ok {
			latest[answer.QuestionID] = answer
			continue
		}
		if submitAnswerNewer(answer, cur) {
			latest[answer.QuestionID] = answer
		}
	}
	qmap := map[int]persistence.QuestionRow{}
	total := 0.0
	for _, question := range questions {
		qmap[question.ID] = question
		total += question.Points
	}
	out := persistence.SubmitGradeOutput{TotalPoints: total, Breakdown: []map[string]any{}}
	earned := 0.0
	for _, answer := range latest {
		question, ok := qmap[answer.QuestionID]
		if !ok {
			continue
		}
		isCorrect, points := scoreSubmitAnswer(question, answer)
		out.Scores = append(out.Scores, persistence.SubmitAnswerScore{
			QuestionID: question.ID,
			IsCorrect:  isCorrect,
			Points:     points,
		})
		var earnedVal any
		if points != nil {
			earned += *points
			earnedVal = *points
		}
		partial := settingBool(question.Settings, "partial_scoring")
		out.Breakdown = append(out.Breakdown, map[string]any{
			"question_id":     strconv.Itoa(question.ID),
			"question_type":   question.Type,
			"points_earned":   earnedVal,
			"max_points":      question.Points,
			"is_correct":      isCorrect,
			"partial_scoring": partial,
		})
	}
	out.PointsEarned = earned
	percentage := 0.0
	if total > 0 {
		percentage = earned / total * 100
	}
	out.Percentage = round2(percentage)
	return out
}

func scoreSubmitAnswer(question persistence.QuestionRow, answer persistence.SubmitAnswerGrade) (*bool, *float64) {
	if canReuseSubmitScore(question, answer) {
		return answer.IsCorrect, answer.Points
	}
	row := persistence.AnswerRow{
		QuestionID:        answer.QuestionID,
		SelectedOptionID:  answer.SelectedOptionID,
		SelectedOptionIDs: answer.SelectedOptionIDs,
		AnswerText:        answer.AnswerText,
		Metadata:          answer.Metadata,
		IsCorrect:         answer.IsCorrect,
		Points:            answer.Points,
		AnsweredAt:        answer.AnsweredAt,
	}
	isCorrect, points := gradeAnswer(question, row)
	if question.Type == "essay" || question.Type == "short_answer" {
		manual := settingBool(question.Settings, "require_manual_grading")
		acceptable := settingStringSlice(question.Settings, "acceptable_answers")
		if manual || question.Type == "essay" || len(acceptable) == 0 {
			return nil, nil
		}
	}
	return isCorrect, points
}

func canReuseSubmitScore(question persistence.QuestionRow, answer persistence.SubmitAnswerGrade) bool {
	if answer.Points == nil {
		return false
	}
	switch question.Type {
	case "multiple_choice", "true_false", "multiple_choice_complex":
		return answer.IsCorrect != nil
	case "short_answer":
		manual := settingBool(question.Settings, "require_manual_grading")
		acceptable := settingStringSlice(question.Settings, "acceptable_answers")
		return !manual && len(acceptable) > 0 && answer.IsCorrect != nil
	default:
		return false
	}
}

func submitAnswerNewer(a, b persistence.SubmitAnswerGrade) bool {
	at := time.Time{}
	bt := time.Time{}
	if a.AnsweredAt != nil {
		at = a.AnsweredAt.UTC()
	}
	if b.AnsweredAt != nil {
		bt = b.AnsweredAt.UTC()
	}
	if at.After(bt) {
		return true
	}
	if at.Equal(bt) {
		return a.ID >= b.ID
	}
	return false
}

func round2(v float64) float64 {
	return math.Round(v*100) / 100
}
