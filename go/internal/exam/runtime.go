package exam

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)



func (d deps) journalSync(w http.ResponseWriter, r *http.Request) {
	d.proxyExamWrite(w, r)
}

func (d deps) logViolation(w http.ResponseWriter, r *http.Request) {
	d.proxyExamWrite(w, r)
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
