package exam

import (
	"context"
	"crypto/rand"
	"encoding/hex"
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

type autosaveHTTPError struct {
	Status int
	Detail any
}

func (e *autosaveHTTPError) Error() string { return "autosave http error" }

func autosaveError(status int, detail any) *autosaveHTTPError {
	return &autosaveHTTPError{Status: status, Detail: detail}
}

func (d deps) autoSave(w http.ResponseWriter, r *http.Request) {
	if d.store == nil || !d.store.HasPool() {
		writeDetail(w, http.StatusServiceUnavailable, "Database tidak tersedia")
		return
	}
	response, err := d.acceptLegacyAutosave(r)
	if err != nil {
		if errors.Is(r.Context().Err(), context.Canceled) {
			return
		}
		if err.Status == http.StatusUnauthorized {
			w.Header().Set("WWW-Authenticate", "Bearer")
		}
		writeJSON(w, err.Status, map[string]any{"detail": err.Detail})
		return
	}
	writeJSON(w, http.StatusOK, response)
}

func (d deps) autoSaveBatch(w http.ResponseWriter, r *http.Request) {
	if d.store == nil || !d.store.HasPool() {
		writeDetail(w, http.StatusServiceUnavailable, "Database tidak tersedia")
		return
	}
	response, err := d.acceptAutosaveBatch(r)
	if err != nil {
		if errors.Is(r.Context().Err(), context.Canceled) {
			return
		}
		if err.Status == http.StatusUnauthorized {
			w.Header().Set("WWW-Authenticate", "Bearer")
		}
		writeJSON(w, err.Status, map[string]any{"detail": err.Detail})
		return
	}
	writeJSON(w, http.StatusOK, response)
}

func (d deps) acceptLegacyAutosave(r *http.Request) (map[string]any, *autosaveHTTPError) {
	userID, active, err := authenticateAutosave(d.secret, r)
	if err != nil {
		return nil, err
	}
	if !active {
		return nil, autosaveError(http.StatusForbidden, "Akun tidak aktif")
	}
	var body map[string]any
	if readErr := readJSON(r, &body); readErr != nil {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	sessionID, ok := coerceSubmitInt(body["session_id"])
	if !ok {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	if _, hasTS := body["timestamp"]; !hasTS {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	rawAnswers, exists := body["answers"]
	if !exists {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	answers, ok := rawAnswers.(map[string]any)
	if !ok {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	normalized := map[string]any{}
	for key, value := range answers {
		id, convErr := strconv.Atoi(strings.TrimSpace(key))
		if convErr != nil {
			return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
		normalized[strconv.Itoa(id)] = value
	}
	probe, probeErr := d.store.ProbeAnswerSession(r.Context(), sessionID, userID)
	if probeErr != nil {
		if persistence.IsTransientDB(probeErr) {
			return nil, autosaveError(http.StatusServiceUnavailable, "Server sedang sibuk, silakan ulangi kirim jawaban.")
		}
		return nil, autosaveError(http.StatusInternalServerError, "Gagal memuat sesi")
	}
	if probe == nil || strings.ToLower(strings.TrimSpace(probe.Status)) != "in_progress" {
		return nil, autosaveError(http.StatusNotFound, "Sesi ujian tidak ditemukan atau sudah berakhir")
	}
	if cacheErr := d.store.ReplaceSessionAnswerCache(r.Context(), sessionID, normalized); cacheErr != nil {
		log.Printf("go_autosave redis failed session=%d err=%v", sessionID, cacheErr)
		return nil, autosaveError(http.StatusInternalServerError, "Internal Server Error")
	}
	ids := make([]int, 0, len(normalized))
	for key := range normalized {
		if id, convErr := strconv.Atoi(key); convErr == nil {
			ids = append(ids, id)
		}
	}
	if count, ok, runtimeErr := d.store.AddAnsweredQuestions(r.Context(), sessionID, ids); runtimeErr == nil && ok {
		_ = d.store.PatchSessionAnsweredCount(r.Context(), sessionID, userID, count)
	}
	return map[string]any{
		"status":      "success",
		"saved_count": len(normalized),
		"timestamp":   time.Now().UTC().Format("2006-01-02T15:04:05.000000+00:00"),
	}, nil
}

func (d deps) acceptAutosaveBatch(r *http.Request) (map[string]any, *autosaveHTTPError) {
	userID, active, err := authenticateAutosave(d.secret, r)
	if err != nil {
		return nil, err
	}
	if !active {
		return nil, autosaveError(http.StatusForbidden, "Akun tidak aktif")
	}
	var body map[string]any
	if readErr := readJSON(r, &body); readErr != nil {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	sessionID, ok := coerceSubmitInt(body["session_id"])
	if !ok {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	rawAnswers, exists := body["answers"]
	if !exists {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	list, ok := rawAnswers.([]any)
	if !ok {
		return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	probe, probeErr := d.store.ProbeAnswerSession(r.Context(), sessionID, userID)
	if probeErr != nil {
		if persistence.IsTransientDB(probeErr) {
			return nil, autosaveError(http.StatusServiceUnavailable, "Server sedang sibuk, silakan ulangi kirim jawaban.")
		}
		return nil, autosaveError(http.StatusInternalServerError, "Gagal memuat sesi")
	}
	if probe == nil || strings.ToLower(strings.TrimSpace(probe.Status)) != "in_progress" {
		return nil, autosaveError(http.StatusNotFound, "Sesi ujian tidak ditemukan atau sudah berakhir")
	}
	if len(list) == 0 {
		return map[string]any{
			"status":       "no_changes",
			"queued_count": 0,
			"queue_id":     "empty",
			"timestamp":    time.Now().UTC().Format("2006-01-02T15:04:05.000000+00:00"),
		}, nil
	}
	deduped := map[int]map[string]any{}
	order := make([]int, 0)
	for _, raw := range list {
		item, ok := raw.(map[string]any)
		if !ok {
			return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
		qid, ok := coerceSubmitInt(item["question_id"])
		if !ok {
			return nil, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
		if _, seen := deduped[qid]; !seen {
			order = append(order, qid)
		}
		deduped[qid] = item
	}
	questionIDs := make([]int, 0, len(order))
	questionIDs = append(questionIDs, order...)
	validIDs, validErr := d.store.ValidQuestionIDs(r.Context(), probe.ExamID, questionIDs)
	if validErr != nil {
		if persistence.IsTransientDB(validErr) {
			return nil, autosaveError(http.StatusServiceUnavailable, "Server sedang sibuk, silakan ulangi kirim jawaban.")
		}
		return nil, autosaveError(http.StatusInternalServerError, "Gagal memuat soal")
	}
	writes := make([]persistence.BatchAnswerWrite, 0)
	validQuestionIDs := make([]int, 0)
	cacheFlags := map[string]bool{}
	for _, qid := range order {
		if _, ok := validIDs[qid]; !ok {
			continue
		}
		item := deduped[qid]
		write, parseErr := parseBatchWrite(item, qid)
		if parseErr != nil {
			return nil, parseErr
		}
		writes = append(writes, write)
		validQuestionIDs = append(validQuestionIDs, qid)
		cacheFlags[strconv.Itoa(qid)] = true
	}
	now := time.Now().UTC()
	outcome, writeErr := d.store.WriteBatchAutosave(r.Context(), probe.ID, userID, writes, now)
	if writeErr != nil {
		if persistence.IsTransientDB(writeErr) {
			return nil, autosaveError(http.StatusServiceUnavailable, "Server sedang sibuk, silakan ulangi kirim jawaban.")
		}
		log.Printf("go_autosave_batch write failed session=%d err=%v", probe.ID, writeErr)
		return nil, autosaveError(http.StatusConflict, "Konflik penyimpanan jawaban, silakan coba lagi")
	}
	if outcome.Status == "not_found" {
		return nil, autosaveError(http.StatusNotFound, "Sesi ujian tidak ditemukan")
	}
	if outcome.Status == "ended" {
		return nil, autosaveError(http.StatusBadRequest, "Sesi ujian sudah berakhir")
	}
	if cacheErr := d.store.ReplaceSessionAnswerCache(r.Context(), probe.ID, cacheFlags); cacheErr != nil {
		log.Printf("go_autosave_batch redis failed session=%d err=%v", probe.ID, cacheErr)
		return nil, autosaveError(http.StatusInternalServerError, "Internal Server Error")
	}
	if count, ok, runtimeErr := d.store.AddAnsweredQuestions(r.Context(), probe.ID, validQuestionIDs); runtimeErr == nil && ok {
		_ = d.store.PatchSessionAnsweredCount(r.Context(), probe.ID, userID, count)
	}
	status := "no_changes"
	if outcome.Changed > 0 {
		status = "saved_to_db"
	}
	return map[string]any{
		"status":       status,
		"queued_count": len(writes),
		"queue_id":     shortQueueID(),
		"timestamp":    now.Format("2006-01-02T15:04:05.000000+00:00"),
	}, nil
}

func parseBatchWrite(item map[string]any, qid int) (persistence.BatchAnswerWrite, *autosaveHTTPError) {
	out := persistence.BatchAnswerWrite{QuestionID: qid}
	if value, exists := item["selected_option_id"]; exists {
		if value == nil || value == "" || value == "null" || value == "undefined" {
			out.SelectedOptionID = nil
		} else if id, ok := coerceSubmitInt(value); ok {
			out.SelectedOptionID = &id
		} else {
			return out, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
	}
	if value, exists := item["selected_option_ids"]; exists {
		out.HasOptionIDs = true
		if value != nil && value != "" && value != "null" {
			list, ok := value.([]any)
			if !ok {
				return out, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
			}
			for _, raw := range list {
				if raw == nil {
					continue
				}
				id, ok := coerceSubmitInt(raw)
				if !ok {
					return out, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
				}
				out.SelectedOptionIDs = append(out.SelectedOptionIDs, int32(id))
			}
			if out.SelectedOptionIDs == nil {
				out.SelectedOptionIDs = []int32{}
			}
		}
	}
	if value, exists := item["answer_text"]; exists && value != nil {
		text := stringify(value)
		out.AnswerText = &text
	}
	if value, exists := item["answer_metadata"]; exists && value != nil {
		obj, ok := value.(map[string]any)
		if !ok {
			return out, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
		out.IncomingMetadata = obj
	}
	if value, exists := item["statement_answers"]; exists && value != nil {
		obj, ok := value.(map[string]any)
		if !ok {
			return out, autosaveError(http.StatusUnprocessableEntity, "Payload tidak valid")
		}
		out.HasStatements = true
		out.StatementAnswers = map[string]bool{}
		for key, raw := range obj {
			flag, _ := coerceBool(raw)
			out.StatementAnswers[key] = flag
		}
	}
	return out, nil
}

func authenticateAutosave(secret string, r *http.Request) (int, bool, *autosaveHTTPError) {
	raw := auth.Bearer(r.Header.Get("Authorization"))
	if raw == "" {
		return 0, false, autosaveError(http.StatusUnauthorized, "Not authenticated")
	}
	claims, err := auth.Parse(secret, raw)
	if err != nil {
		return 0, false, autosaveError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	userID, err := claims.UserID()
	if err != nil {
		return 0, false, autosaveError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	return userID, claims.Active(), nil
}

func pythonBool(v any) bool {
	switch typed := v.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case float64:
		return typed != 0
	case int:
		return typed != 0
	case json.Number:
		n, _ := typed.Float64()
		return n != 0
	case map[string]any:
		return len(typed) > 0
	case []any:
		return len(typed) > 0
	default:
		return true
	}
}

func shortQueueID() string {
	buf := make([]byte, 4)
	if _, err := rand.Read(buf); err != nil {
		return strconv.FormatInt(time.Now().UnixNano(), 16)[:8]
	}
	return hex.EncodeToString(buf)
}
