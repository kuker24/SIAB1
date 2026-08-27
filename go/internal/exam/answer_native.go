package exam

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

type answerRepository interface {
	startSecurityRepository
	HasPool() bool
	HasRedis() bool
	ProbeAnswerSession(context.Context, int, int) (*persistence.AnswerSessionProbe, error)
	LoadAnswerQuestion(context.Context, int, int) (*persistence.AnswerQuestionPayload, error)
	WriteSingleAnswerDirect(context.Context, int, int, int, persistence.AnswerWriteFields) (string, error)
	AllowSlidingRate(context.Context, string, string, int, int) (bool, int)
	AddAnsweredQuestions(context.Context, int, []int) (int, bool, error)
	PatchSessionAnsweredCount(context.Context, int, int, int) error
	ReplaceSessionAnswerCache(context.Context, int, any) error
}

type answerHTTPError struct {
	Status  int
	Detail  any
	Headers map[string]string
}

func (e *answerHTTPError) Error() string { return "answer http error" }

func answerError(status int, detail any) *answerHTTPError {
	return &answerHTTPError{Status: status, Detail: detail}
}

type answerService struct {
	repo             answerRepository
	secret           string
	defaultSEBKey    string
	challengeEnabled bool
	challengePrefix  string
	disableRateLimit bool
	examPeak         bool
}

type nativeAnswerResponse struct {
	Status     string `json:"status"`
	QuestionID int    `json:"question_id"`
	Message    string `json:"message"`
}

type answerSubmit struct {
	SessionID         int
	QuestionID        int
	SelectedOptionID  *int
	SelectedOptionIDs []int
	AnswerText        *string
	StatementAnswers  map[string]bool
	Metadata          map[string]any
}

func (d deps) submitAnswer(w http.ResponseWriter, r *http.Request) {
	if d.store == nil || !d.store.HasPool() {
		writeDetail(w, http.StatusServiceUnavailable, "Database tidak tersedia")
		return
	}
	response, err := answerService{
		repo:             d.store,
		secret:           d.secret,
		defaultSEBKey:    d.sebKey,
		challengeEnabled: d.sebChallenge,
		challengePrefix:  d.sebChallengePrefix,
		disableRateLimit: d.disableRateLimit,
		examPeak:         d.examPeak,
	}.accept(r)
	if err != nil {
		log.Printf("go_answer outcome=failure status=%d", err.Status)
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
	log.Printf("go_answer outcome=success question_id=%d", response.QuestionID)
	writeJSON(w, http.StatusOK, response)
}

func alreadySubmittedAnswer(questionID int) *nativeAnswerResponse {
	return &nativeAnswerResponse{
		Status:     "saved",
		QuestionID: questionID,
		Message:    "Sesi ujian sudah dikumpulkan. Jawaban tambahan diabaikan.",
	}
}

func (s answerService) accept(r *http.Request) (*nativeAnswerResponse, *answerHTTPError) {
	userID, active, err := s.authenticate(r)
	if err != nil {
		return nil, err
	}
	if !active {
		return nil, answerError(http.StatusForbidden, "Akun tidak aktif")
	}
	body, err := readAnswerSubmit(r)
	if err != nil {
		return nil, err
	}
	if !s.disableRateLimit {
		key := strconv.Itoa(userID) + ":" + strconv.Itoa(body.SessionID)
		allowed, remaining := s.repo.AllowSlidingRate(r.Context(), "answer_submit", key, 60, 60)
		if !allowed {
			return nil, &answerHTTPError{
				Status: http.StatusTooManyRequests,
				Detail: "Terlalu banyak request. Tunggu beberapa saat.",
				Headers: map[string]string{
					"Retry-After":           "5",
					"X-RateLimit-Remaining": strconv.Itoa(remaining),
				},
			}
		}
	}
	probe, probeErr := s.repo.ProbeAnswerSession(r.Context(), body.SessionID, userID)
	if probeErr != nil {
		if persistence.IsTransientDB(probeErr) {
			return nil, busyAnswer()
		}
		return nil, answerError(http.StatusInternalServerError, "Gagal memuat sesi")
	}
	if probe == nil {
		return nil, answerError(http.StatusNotFound, "Sesi ujian tidak ditemukan")
	}
	status := strings.ToLower(strings.TrimSpace(probe.Status))
	if status == "submitted" || status == "completed" {
		return alreadySubmittedAnswer(body.QuestionID), nil
	}
	if status != "in_progress" {
		return nil, answerError(http.StatusBadRequest, "Sesi ujian sudah berakhir")
	}
	settings, settingsErr := s.repo.LoadStartSecuritySettings(r.Context())
	if settingsErr != nil {
		return nil, answerError(http.StatusInternalServerError, "Internal Server Error")
	}
	if sebErr := validateStartSEB(
		r.Context(), s.repo, r, probe.ExamID, settings, s.defaultSEBKey, s.challengeEnabled, s.challengePrefix,
	); sebErr != nil {
		return nil, answerError(sebErr.Status, sebErr.Detail)
	}
	question, questionErr := s.repo.LoadAnswerQuestion(r.Context(), probe.ExamID, body.QuestionID)
	if questionErr != nil {
		if persistence.IsTransientDB(questionErr) {
			return nil, busyAnswer()
		}
		return nil, answerError(http.StatusInternalServerError, "Gagal memuat soal")
	}
	if question == nil {
		return nil, answerError(http.StatusNotFound, "Soal tidak ditemukan")
	}
	metadata := mergeAnswerMetadata(body.Metadata, body.StatementAnswers)
	isCorrect, points := validateAnswerPayload(question, body)
	writeAt := time.Now().UTC()
	outcome, writeErr := s.repo.WriteSingleAnswerDirect(r.Context(), probe.ID, userID, question.ID, persistence.AnswerWriteFields{
		SelectedOptionID:  body.SelectedOptionID,
		SelectedOptionIDs: int32s(body.SelectedOptionIDs),
		AnswerText:        body.AnswerText,
		Metadata:          persistence.MetadataJSON(metadata),
		IsCorrect:         isCorrect,
		PointsEarned:      points,
		AnsweredAt:        writeAt,
	})
	if writeErr != nil {
		if persistence.IsAnswerNotFound(writeErr) {
			return nil, answerError(http.StatusNotFound, "Sesi ujian tidak ditemukan")
		}
		if persistence.IsAnswerEnded(writeErr) {
			return nil, answerError(http.StatusBadRequest, "Sesi ujian sudah berakhir")
		}
		if persistence.IsTransientDB(writeErr) {
			return nil, busyAnswer()
		}
		log.Printf("go_answer upsert failed question=%d err=%v", question.ID, writeErr)
		return nil, answerError(http.StatusConflict, "Konflik penyimpanan jawaban, silakan coba lagi")
	}
	if outcome == "submitted" {
		return alreadySubmittedAnswer(question.ID), nil
	}
	s.afterWrite(r.Context(), probe.ID, userID, question.ID)
	return &nativeAnswerResponse{
		Status:     "saved",
		QuestionID: question.ID,
		Message:    "Jawaban berhasil disimpan",
	}, nil
}

func (s answerService) afterWrite(ctx context.Context, sessionID, userID, questionID int) {
	if count, ok, err := s.repo.AddAnsweredQuestions(ctx, sessionID, []int{questionID}); err == nil && ok {
		_ = s.repo.PatchSessionAnsweredCount(ctx, sessionID, userID, count)
	}
	_ = s.repo.ReplaceSessionAnswerCache(ctx, sessionID, map[string]bool{strconv.Itoa(questionID): true})
}

func (s answerService) authenticate(r *http.Request) (int, bool, *answerHTTPError) {
	raw := auth.Bearer(r.Header.Get("Authorization"))
	if raw == "" {
		return 0, false, answerError(http.StatusUnauthorized, "Not authenticated")
	}
	claims, err := auth.Parse(s.secret, raw)
	if err != nil {
		return 0, false, answerError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	userID, err := claims.UserID()
	if err != nil {
		return 0, false, answerError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	return userID, claims.Active(), nil
}

func busyAnswer() *answerHTTPError {
	return &answerHTTPError{
		Status:  http.StatusServiceUnavailable,
		Detail:  "Server sedang sibuk, silakan ulangi kirim jawaban.",
		Headers: map[string]string{"Retry-After": "1"},
	}
}

func readAnswerSubmit(r *http.Request) (*answerSubmit, *answerHTTPError) {
	var raw map[string]any
	if err := readJSON(r, &raw); err != nil {
		return nil, answerError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	sessionID, ok := coerceSubmitInt(raw["session_id"])
	if !ok {
		return nil, answerError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	questionID, ok := coerceSubmitInt(raw["question_id"])
	if !ok {
		return nil, answerError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	out := &answerSubmit{SessionID: sessionID, QuestionID: questionID, Metadata: map[string]any{}}
	if value, exists := raw["selected_option_id"]; exists {
		if value == nil || value == "" || value == "null" || value == "undefined" {
			out.SelectedOptionID = nil
		} else if id, ok := coerceSubmitInt(value); ok {
			out.SelectedOptionID = &id
		} else {
			return nil, answerError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
	}
	if value, exists := raw["selected_option_ids"]; exists && value != nil && value != "" && value != "null" {
		list, ok := value.([]any)
		if !ok {
			return nil, answerError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
		for _, item := range list {
			if item == nil {
				continue
			}
			id, ok := coerceSubmitInt(item)
			if !ok {
				return nil, answerError(http.StatusUnprocessableEntity, "Payload tidak valid")
			}
			out.SelectedOptionIDs = append(out.SelectedOptionIDs, id)
		}
	}
	if value, exists := raw["answer_text"]; exists && value != nil {
		text := strings.TrimSpace(stringify(value))
		out.AnswerText = &text
	}
	if value, exists := raw["statement_answers"]; exists && value != nil {
		obj, ok := value.(map[string]any)
		if !ok {
			return nil, answerError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
		out.StatementAnswers = map[string]bool{}
		for key, item := range obj {
			flag, _ := coerceBool(item)
			out.StatementAnswers[key] = flag
		}
	}
	if value, exists := raw["answer_metadata"]; exists && value != nil {
		obj, ok := value.(map[string]any)
		if !ok {
			return nil, answerError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
		out.Metadata = obj
	}
	return out, nil
}

func coerceSubmitInt(v any) (int, bool) {
	switch typed := v.(type) {
	case json.Number:
		n, err := typed.Int64()
		return int(n), err == nil
	case float64:
		return int(typed), true
	case int:
		return typed, true
	case string:
		n, err := strconv.Atoi(strings.TrimSpace(typed))
		return n, err == nil
	default:
		return 0, false
	}
}

func stringify(v any) string {
	switch typed := v.(type) {
	case string:
		return typed
	default:
		b, _ := json.Marshal(typed)
		return string(b)
	}
}

func mergeAnswerMetadata(incoming map[string]any, statements map[string]bool) map[string]any {
	final := map[string]any{}
	for key, value := range incoming {
		final[key] = value
	}
	delete(final, "replace_statement_answers")
	delete(final, "delete_statement_answers")
	replace, _ := coerceBool(incoming["replace_statement_answers"])
	deleteStmts, _ := coerceBool(incoming["delete_statement_answers"])
	var merged map[string]bool
	if deleteStmts {
		merged = map[string]bool{}
	} else if statements == nil {
		if replace {
			merged = map[string]bool{}
		}
	} else if replace {
		merged = statements
	} else {
		merged = statements
	}
	if merged != nil {
		if len(merged) > 0 {
			final["statement_answers"] = merged
		} else {
			delete(final, "statement_answers")
		}
	}
	return final
}

func validateAnswerPayload(question *persistence.AnswerQuestionPayload, body *answerSubmit) (*bool, *float64) {
	settings := map[string]any{}
	_ = json.Unmarshal(question.QuestionSettings, &settings)
	correctIDs := map[int]struct{}{}
	for _, opt := range question.Options {
		if opt.IsCorrect {
			correctIDs[opt.ID] = struct{}{}
		}
	}
	points := question.Points
	switch question.QuestionType {
	case "multiple_choice", "true_false":
		if body.SelectedOptionID == nil {
			return boolPtr(false), floatPtr(0)
		}
		if _, ok := correctIDs[*body.SelectedOptionID]; ok {
			return boolPtr(true), floatPtr(points)
		}
		return boolPtr(false), floatPtr(0)
	case "multiple_choice_complex":
		pgk := "checkbox"
		if question.PGKType != nil && strings.TrimSpace(*question.PGKType) != "" {
			pgk = strings.TrimSpace(*question.PGKType)
		} else if raw, ok := settings["pgk_type"].(string); ok && strings.TrimSpace(raw) != "" {
			pgk = strings.TrimSpace(raw)
		}
		if pgk == "table_validation" {
			return validateTable(settings, body.StatementAnswers, points)
		}
		selected := map[int]struct{}{}
		for _, id := range body.SelectedOptionIDs {
			selected[id] = struct{}{}
		}
		if len(selected) == 0 || len(correctIDs) == 0 {
			return boolPtr(false), floatPtr(0)
		}
		if ok, _ := coerceBool(settings["partial_scoring"]); ok {
			correctCount := 0
			incorrectCount := 0
			for id := range selected {
				if _, ok := correctIDs[id]; ok {
					correctCount++
				} else {
					incorrectCount++
				}
			}
			ratio := float64(correctCount-incorrectCount) / float64(len(correctIDs))
			if ratio < 0 {
				ratio = 0
			}
			return boolPtr(ratio >= 0.5), floatPtr(points * ratio)
		}
		if len(selected) != len(correctIDs) {
			return boolPtr(false), floatPtr(0)
		}
		for id := range selected {
			if _, ok := correctIDs[id]; !ok {
				return boolPtr(false), floatPtr(0)
			}
		}
		return boolPtr(true), floatPtr(points)
	case "essay":
		return nil, nil
	case "short_answer":
		text := ""
		if body.AnswerText != nil {
			text = strings.TrimSpace(*body.AnswerText)
		}
		if manual, _ := coerceBool(settings["require_manual_grading"]); text == "" || manual {
			return nil, nil
		}
		rawAcceptable, _ := settings["acceptable_answers"].([]any)
		if len(rawAcceptable) == 0 {
			return nil, nil
		}
		caseSensitive, _ := coerceBool(settings["case_sensitive"])
		if !caseSensitive {
			text = strings.ToLower(text)
		}
		for _, item := range rawAcceptable {
			candidate := strings.TrimSpace(stringify(item))
			if !caseSensitive {
				candidate = strings.ToLower(candidate)
			}
			if text == candidate {
				return boolPtr(true), floatPtr(points)
			}
		}
		return boolPtr(false), floatPtr(0)
	default:
		return boolPtr(false), floatPtr(0)
	}
}

func validateTable(settings map[string]any, statements map[string]bool, points float64) (*bool, *float64) {
	correct := map[string]*bool{}
	if list, ok := settings["statement_answers"].([]any); ok && len(list) > 0 {
		for idx, value := range list {
			v, _ := coerceBool(value)
			correct[strconv.Itoa(idx)] = &v
		}
	} else if obj, ok := settings["correct_statements"].(map[string]any); ok && len(obj) > 0 {
		for key, value := range obj {
			v, _ := coerceBool(value)
			correct[key] = &v
		}
	}
	if len(correct) == 0 {
		return boolPtr(false), floatPtr(0)
	}
	correctCount := 0
	for key, expected := range correct {
		if expected == nil {
			continue
		}
		got, ok := statements[key]
		if ok && got == *expected {
			correctCount++
		}
	}
	ratio := float64(correctCount) / float64(len(correct))
	return boolPtr(ratio == 1.0), floatPtr(points * ratio)
}

func int32s(ids []int) []int32 {
	if len(ids) == 0 {
		return nil
	}
	out := make([]int32, 0, len(ids))
	for _, id := range ids {
		out = append(out, int32(id))
	}
	return out
}
