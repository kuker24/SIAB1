package exam

import (
	"math"
	"net/http"

	"siab1/internal/persistence"
)

func (d deps) submitExam(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	var body struct {
		SessionID   any  `json:"session_id"`
		ForceSubmit bool `json:"force_submit"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	sessionID := asInt(body.SessionID)
	if sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id must be a valid integer")
		return
	}
	probe, err := d.store.ProbeSubmit(r.Context(), sessionID, userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa sesi")
		return
	}
	if probe == nil {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	if probe.Status == "submitted" || probe.Status == "completed" {
		writeJSON(w, http.StatusOK, alreadySubmitted(probe))
		return
	}
	if probe.Status != "in_progress" && probe.Status != "active" {
		writeDetail(w, http.StatusBadRequest, "Sesi ujian sudah berakhir")
		return
	}
	tx, err := d.store.BeginSubmit(r.Context(), sessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mengunci sesi")
		return
	}
	defer func() { _ = tx.Rollback(r.Context()) }()
	probe, err = persistence.ProbeSubmitTx(r.Context(), tx, sessionID, userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa sesi")
		return
	}
	if probe == nil {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	if probe.Status == "submitted" || probe.Status == "completed" {
		writeJSON(w, http.StatusOK, alreadySubmitted(probe))
		return
	}
	if probe.Status != "in_progress" && probe.Status != "active" {
		writeDetail(w, http.StatusBadRequest, "Sesi ujian sudah berakhir")
		return
	}
	questions, err := d.store.LoadQuestionsForGrade(r.Context(), probe.ExamID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat soal")
		return
	}
	answers, err := d.store.ListAnswers(r.Context(), sessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat jawaban")
		return
	}
	byQ := map[int]persistence.QuestionRow{}
	total := 0.0
	for _, q := range questions {
		byQ[q.ID] = q
		total += q.Points
	}
	earned := 0.0
	for _, ans := range answers {
		q, ok := byQ[ans.QuestionID]
		if !ok {
			continue
		}
		correct, pts := gradeAnswer(q, ans)
		if err := persistence.UpdateAnswerScore(r.Context(), tx, sessionID, ans.QuestionID, correct, pts); err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal menilai jawaban")
			return
		}
		if pts != nil {
			earned += *pts
		}
	}
	pct := 0.0
	if total > 0 {
		pct = math.Round((earned/total*100)*100) / 100
	}
	if err := persistence.MarkSessionSubmitted(r.Context(), tx, sessionID, probe.ExamID, pct); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menyelesaikan sesi")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menyimpan pengumpulan")
		return
	}
	msg := "Ujian berhasil dikumpulkan"
	if body.ForceSubmit {
		msg = "Ujian dikumpulkan otomatis karena pelanggaran"
	}
	var score any
	var totalOut any
	var earnedOut any
	var pctOut any
	var passed any
	if probe.ShowResults {
		score = pct
		totalOut = total
		earnedOut = earned
		pctOut = pct
		if probe.PassingScore != nil {
			passed = pct >= *probe.PassingScore
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id":    sessionID,
		"status":        "submitted",
		"score":         score,
		"total_points":  totalOut,
		"points_earned": earnedOut,
		"percentage":    pctOut,
		"passed":        passed,
		"message":       msg,
	})
}

func alreadySubmitted(p *persistence.SubmitProbe) map[string]any {
	var score any
	var passed any
	if p.ShowResults && p.Score != nil {
		score = *p.Score
		if p.PassingScore != nil {
			passed = *p.Score >= *p.PassingScore
		}
	}
	return map[string]any{
		"session_id":    p.SessionID,
		"status":        "submitted",
		"score":         score,
		"total_points":  nil,
		"points_earned": nil,
		"percentage":    score,
		"passed":        passed,
		"message":       "Sesi sudah pernah dikumpulkan.",
	}
}
