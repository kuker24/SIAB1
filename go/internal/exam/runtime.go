package exam

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

const autoSubmitViolations = 8

func (d deps) autoSaveBatch(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	var body struct {
		SessionID json.Number `json:"session_id"`
		Answers   []any       `json:"answers"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	sessionID, err := strconv.Atoi(strings.TrimSpace(body.SessionID.String()))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id must be a valid integer")
		return
	}
	status, found, err := d.store.SessionOwned(r.Context(), sessionID, userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa sesi")
		return
	}
	if !found || (status != "in_progress" && status != "active") {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan atau sudah berakhir")
		return
	}
	if len(body.Answers) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":       "no_changes",
			"queued_count": 0,
			"queue_id":     "empty",
			"timestamp":    time.Now().UTC().Format(time.RFC3339),
		})
		return
	}
	saved := 0
	seen := map[int]struct{}{}
	for i := len(body.Answers) - 1; i >= 0; i-- {
		item, ok := body.Answers[i].(map[string]any)
		if !ok {
			continue
		}
		qid := asInt(item["question_id"])
		if qid <= 0 {
			continue
		}
		if _, dup := seen[qid]; dup {
			continue
		}
		seen[qid] = struct{}{}
		if err := d.store.UpsertAnswer(r.Context(), sessionID, decodeAnswer(qid, item)); err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal menyimpan jawaban")
			return
		}
		saved++
	}
	statusName := "saved_to_db"
	if saved == 0 {
		statusName = "no_changes"
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"status":       statusName,
		"queued_count": saved,
		"queue_id":     shortID(),
		"timestamp":    time.Now().UTC().Format(time.RFC3339),
	})
}

func (d deps) journalSync(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	var body struct {
		SessionID json.Number      `json:"session_id"`
		Events    []map[string]any `json:"events"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	sessionID, err := strconv.Atoi(strings.TrimSpace(body.SessionID.String()))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id must be a valid integer")
		return
	}
	if !d.sessionWritable(w, r, sessionID, userID) {
		return
	}
	acks := make([]map[string]any, 0, len(body.Events))
	accepted := 0
	invalid := 0
	applied := map[int]struct{}{}
	for _, ev := range body.Events {
		eventID := strings.ToLower(strings.TrimSpace(asString(ev["event_id"])))
		qid := asInt(ev["question_id"])
		if len(eventID) < 10 || qid <= 0 {
			invalid++
			acks = append(acks, map[string]any{
				"event_id":    eventID,
				"question_id": qid,
				"status":      "invalid",
				"reason":      "event_id or question_id",
			})
			continue
		}
		if err := d.store.UpsertAnswer(r.Context(), sessionID, decodeAnswer(qid, ev)); err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal menyimpan jurnal")
			return
		}
		accepted++
		applied[qid] = struct{}{}
		acks = append(acks, map[string]any{
			"event_id":    eventID,
			"question_id": qid,
			"status":      "applied",
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"status":                 "ok",
		"accepted":               accepted,
		"duplicates":             0,
		"invalid":                invalid,
		"applied_question_count": len(applied),
		"acks":                   acks,
		"server_time":            time.Now().UTC().Format(time.RFC3339),
	})
}

func (d deps) logViolation(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	var body struct {
		SessionID        json.Number    `json:"session_id"`
		ExamID           any            `json:"exam_id"`
		EventType        string         `json:"event_type"`
		EventData        map[string]any `json:"event_data"`
		Timestamp        any            `json:"timestamp"`
		UserAgent        string         `json:"user_agent"`
		ScreenResolution string         `json:"screen_resolution"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	sessionID, err := strconv.Atoi(strings.TrimSpace(body.SessionID.String()))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id must be a valid integer")
		return
	}
	eventType := canonicalViolation(body.EventType)
	if eventType == "" {
		writeDetail(w, http.StatusBadRequest, "Jenis pelanggaran tidak valid")
		return
	}
	row, err := d.store.TimerSession(r.Context(), sessionID, userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa sesi")
		return
	}
	if row == nil {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	if isTerminal(row.Status) {
		writeJSON(w, http.StatusAccepted, map[string]any{
			"status":          "ignored",
			"violation_count": row.ViolationCount,
			"warning":         nil,
		})
		return
	}
	payload := body.EventData
	if payload == nil {
		payload = map[string]any{}
	}
	payload["raw_event_type"] = body.EventType
	payload["user_agent"] = body.UserAgent
	payload["screen_resolution"] = body.ScreenResolution
	payload["counted_for_score"] = true
	if err := d.store.LogViolation(r.Context(), sessionID, eventType, persistence.MetadataJSON(payload)); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mencatat pelanggaran")
		return
	}
	count, _, _, err := d.store.AddViolation(r.Context(), sessionID, userID, 1)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memperbarui pelanggaran")
		return
	}
	if count == 0 {
		count = row.ViolationCount + 1
	}
	writeJSON(w, http.StatusAccepted, map[string]any{
		"status":          "logged",
		"violation_count": count,
		"warning":         violationWarning(count),
	})
}

func (d deps) sessionStatus(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	sessionID, err := strconv.Atoi(r.PathValue("session_id"))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id tidak valid")
		return
	}
	row, err := d.store.TimerSession(r.Context(), sessionID, userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat sesi")
		return
	}
	if row == nil {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	_, remaining, _, _ := timerParts(row)
	answered, _ := d.store.CountAnswers(r.Context(), sessionID)
	totalQ, _ := d.store.CountQuestions(r.Context(), row.ExamID)
	reported := row.Status
	var kick any
	if row.Status == "kicked" || (row.Status == "terminated" && row.TerminatedByAdmin && !row.EmergencyExit) {
		reported = "kicked"
		kick = "Dikeluarkan oleh pengawas"
	}
	var pauseMsg any
	if row.IsPaused {
		pauseMsg = "Ujian sedang di-pause oleh pengawas"
	}
	poll, _ := auth.SessionPollToken(d.secret, sessionID, userID)
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id":                         sessionID,
		"status":                             reported,
		"time_remaining_seconds":             remaining,
		"answered_count":                     answered,
		"total_questions":                    totalQ,
		"violation_count":                    row.ViolationCount,
		"server_time":                        time.Now().UTC().Format(time.RFC3339),
		"is_paused":                          row.IsPaused,
		"paused_by":                          nil,
		"pause_message":                      pauseMsg,
		"kick_reason":                        kick,
		"emergency_exit_allowed":             row.EmergencyExit,
		"terminated_by_admin":                row.TerminatedByAdmin,
		"session_poll_token":                 poll,
		"session_poll_token_expires_minutes": 15,
	})
}

func (d deps) resumeSession(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	sessionID, err := strconv.Atoi(r.PathValue("session_id"))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id tidak valid")
		return
	}
	row, err := d.store.TimerSession(r.Context(), sessionID, userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat sesi")
		return
	}
	if row == nil {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	elapsed, remaining, total, expired := timerParts(row)
	totalQ, _ := d.store.CountQuestions(r.Context(), row.ExamID)
	poll, _ := auth.SessionPollToken(d.secret, sessionID, userID)
	if row.Status == "completed" || row.Status == "submitted" {
		writeJSON(w, http.StatusOK, map[string]any{
			"session_id":                         sessionID,
			"exam_id":                            row.ExamID,
			"exam_title":                         row.ExamTitle,
			"remaining_seconds":                  0,
			"elapsed_seconds":                    total,
			"total_seconds":                      total,
			"is_expired":                         true,
			"saved_answers":                      map[string]any{},
			"answered_count":                     0,
			"total_questions":                    totalQ,
			"last_question_id":                   nil,
			"can_resume":                         false,
			"message":                            "Ujian sudah selesai dikumpulkan",
			"session_poll_token":                 poll,
			"session_poll_token_expires_minutes": 15,
		})
		return
	}
	answers, err := d.store.ListAnswers(r.Context(), sessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat jawaban")
		return
	}
	saved := map[string]any{}
	var lastQ any
	for _, ans := range answers {
		saved[strconv.Itoa(ans.QuestionID)] = resumeAnswer(ans)
		lastQ = ans.QuestionID
	}
	can := !expired && (row.Status == "in_progress" || row.Status == "active" || row.Status == "paused")
	msg := "Lanjutkan ujian. " + strconv.Itoa(len(saved)) + " jawaban tersimpan."
	if expired {
		msg = "Waktu ujian sudah habis. Jawaban tersimpan otomatis."
		can = false
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id":                         sessionID,
		"exam_id":                            row.ExamID,
		"exam_title":                         row.ExamTitle,
		"remaining_seconds":                  remaining,
		"elapsed_seconds":                    elapsed,
		"total_seconds":                      total,
		"is_expired":                         expired,
		"saved_answers":                      saved,
		"answered_count":                     len(saved),
		"total_questions":                    totalQ,
		"last_question_id":                   lastQ,
		"can_resume":                         can,
		"message":                            msg,
		"session_poll_token":                 poll,
		"session_poll_token_expires_minutes": 15,
	})
}

func timerParts(row *persistence.SessionRow) (elapsed, remaining, total int, expired bool) {
	total = row.DurationMinutes * 60
	elapsed = int(time.Now().UTC().Sub(row.StartTime.UTC()).Seconds()) - row.TotalPausedSeconds
	if elapsed < 0 {
		elapsed = 0
	}
	remaining = total - elapsed
	if remaining < 0 {
		remaining = 0
	}
	expired = remaining <= 0 && !row.IsPaused
	return
}

func resumeAnswer(row persistence.AnswerRow) map[string]any {
	out := map[string]any{}
	if row.SelectedOptionID != nil {
		out["selected_option_id"] = *row.SelectedOptionID
	}
	if len(row.SelectedOptionIDs) > 0 {
		out["selected_option_ids"] = row.SelectedOptionIDs
	}
	if row.AnswerText != nil && strings.TrimSpace(*row.AnswerText) != "" {
		out["answer_text"] = *row.AnswerText
	}
	if len(row.Metadata) > 0 {
		var meta map[string]any
		if json.Unmarshal(row.Metadata, &meta) == nil {
			if stmts, ok := meta["statement_answers"]; ok && stmts != nil {
				out["statement_answers"] = stmts
			}
		}
	}
	return out
}

func canonicalViolation(raw string) string {
	v := strings.ToLower(strings.TrimSpace(raw))
	v = strings.ReplaceAll(v, " ", "_")
	if v == "" {
		return ""
	}
	return v
}

func isTerminal(status string) bool {
	switch status {
	case "submitted", "completed", "abandoned", "terminated", "kicked":
		return true
	default:
		return false
	}
}

func violationWarning(count int) any {
	if count >= autoSubmitViolations {
		return "Batas pelanggaran tercapai. Ujian akan dikumpulkan otomatis."
	}
	if count == autoSubmitViolations-1 {
		return "PERINGATAN TERAKHIR! Ujian akan dikumpulkan otomatis pada pelanggaran berikutnya."
	}
	if count >= 3 {
		return "Peringatan: Anda sudah melakukan " + strconv.Itoa(count) + " pelanggaran."
	}
	return nil
}

func shortID() string {
	var b [4]byte
	if _, err := rand.Read(b[:]); err != nil {
		return strconv.FormatInt(time.Now().UnixNano()%1e8, 16)
	}
	return hex.EncodeToString(b[:])
}

func asString(v any) string {
	switch t := v.(type) {
	case string:
		return t
	case json.Number:
		return t.String()
	default:
		return ""
	}
}
