package exam

import (
	"math"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

func (d deps) kickSession(w http.ResponseWriter, r *http.Request) {
	userID, claims, sess, ok := d.loadControlSession(w, r)
	if !ok {
		return
	}
	reason := "Dikeluarkan oleh pengawas"
	var body struct {
		Reason string `json:"reason"`
	}
	if err := readJSON(r, &body); err == nil && strings.TrimSpace(body.Reason) != "" {
		reason = strings.TrimSpace(body.Reason)
	}
	if err := d.store.KickSession(r.Context(), sess.SessionID); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mengeluarkan siswa")
		return
	}
	_ = d.store.LogViolation(r.Context(), sess.SessionID, "SESSION_FORCE_KICK", persistence.MustJSON(map[string]any{
		"category": "admin_decision", "allow_continue": false, "reason": reason,
		"message": "Sesi dihentikan oleh pengawas/admin.", "actor_id": userID, "actor_username": claims.Username,
	}))
	name := sess.UserName
	if name == "" {
		name = "Siswa"
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true, "message": "Student " + name + " telah dikeluarkan dari ujian",
		"session_id": sess.SessionID, "user_id": sess.UserID, "reason": reason,
	})
}

func (d deps) emergencyExit(w http.ResponseWriter, r *http.Request) {
	userID, claims, sess, ok := d.loadControlSession(w, r)
	if !ok {
		return
	}
	st := strings.ToLower(sess.Status)
	if st != "in_progress" && st != "created" && st != "active" {
		writeDetail(w, http.StatusBadRequest, "Sesi sudah selesai atau tidak aktif")
		return
	}
	if err := d.store.SetEmergencyExit(r.Context(), sess.SessionID, true); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mengaktifkan emergency exit")
		return
	}
	_ = d.store.LogViolation(r.Context(), sess.SessionID, "EMERGENCY_EXIT_ENABLED", persistence.MustJSON(map[string]any{
		"admin_id": userID, "admin_username": claims.Username,
	}))
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true, "message": "🚨 Emergency exit diaktifkan untuk sesi ini",
		"session_id": sess.SessionID, "emergency_exit_allowed": true,
	})
}

func (d deps) revokeEmergencyExit(w http.ResponseWriter, r *http.Request) {
	userID, claims, sess, ok := d.loadControlSession(w, r)
	if !ok {
		return
	}
	if err := d.store.SetEmergencyExit(r.Context(), sess.SessionID, false); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mencabut emergency exit")
		return
	}
	_ = d.store.LogViolation(r.Context(), sess.SessionID, "EMERGENCY_EXIT_REVOKED", persistence.MustJSON(map[string]any{
		"admin_id": userID, "admin_username": claims.Username,
	}))
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true, "message": "Emergency exit dicabut untuk sesi ini",
		"session_id": sess.SessionID, "emergency_exit_allowed": false,
	})
}

func (d deps) recoveryStatus(w http.ResponseWriter, r *http.Request) {
	_, _, sess, ok := d.loadControlSession(w, r)
	if !ok {
		return
	}
	logs, err := d.store.ListSessionLogs(r.Context(), sess.SessionID, 30)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat log sesi")
		return
	}
	rec := evaluateSessionRecovery(sess.Status, sess.Terminated, sess.Violations, logs)
	action := "block_relogin"
	if rec.AllowContinue {
		action = "allow_continue"
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id": sess.SessionID, "exam_id": sess.ExamID, "user_id": sess.UserID,
		"status": sess.Status, "terminated_by_admin": sess.Terminated,
		"recovery_category": rec.Category, "allow_continue": rec.AllowContinue,
		"message": rec.Message, "recommended_action": action,
	})
}

func (d deps) resetSession(w http.ResponseWriter, r *http.Request) {
	userID, claims, sess, ok := d.loadControlSession(w, r)
	if !ok {
		return
	}
	reason := "Manual reset for disconnection recovery"
	var body struct {
		Reason string `json:"reason"`
	}
	if err := readJSON(r, &body); err == nil && strings.TrimSpace(body.Reason) != "" {
		reason = strings.TrimSpace(body.Reason)
	}
	logs, err := d.store.ListSessionLogs(r.Context(), sess.SessionID, 30)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat log sesi")
		return
	}
	rec := evaluateSessionRecovery(sess.Status, sess.Terminated, sess.Violations, logs)
	if !rec.AllowContinue {
		_ = d.store.LogViolation(r.Context(), sess.SessionID, "SESSION_RESET_BLOCKED", persistence.MustJSON(map[string]any{
			"category": rec.Category, "allow_continue": false, "reason": reason,
			"message": rec.Message, "actor_id": userID, "actor_username": claims.Username,
		}))
		writeJSON(w, http.StatusConflict, map[string]any{"detail": map[string]any{
			"error": "SESSION_RESET_BLOCKED", "category": rec.Category,
			"allow_continue": false, "message": rec.Message,
		}})
		return
	}
	if err := d.store.ResetSession(r.Context(), sess.SessionID, false); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mereset sesi")
		return
	}
	_ = d.store.LogViolation(r.Context(), sess.SessionID, "SESSION_MANUAL_RESET", persistence.MustJSON(map[string]any{
		"category": rec.Category, "allow_continue": true, "reason": reason,
		"message": rec.Message, "actor_id": userID, "actor_username": claims.Username,
		"previous_status": sess.Status,
	}))
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true, "session_id": sess.SessionID, "user_id": sess.UserID, "exam_id": sess.ExamID,
		"status": "in_progress", "recovery_category": rec.Category, "allow_continue": true,
		"message": "Sesi berhasil di-reset. Siswa dapat login kembali dan melanjutkan ujian.",
	})
}

func (d deps) reopenOverride(w http.ResponseWriter, r *http.Request) {
	userID, claims, sess, ok := d.loadControlSession(w, r)
	if !ok {
		return
	}
	if sess.Deleted || !sess.Published {
		writeDetail(w, http.StatusConflict, "Ujian tidak aktif untuk reopen override")
		return
	}
	if time.Now().UTC().After(sess.ExamEnd.UTC()) {
		writeDetail(w, http.StatusConflict, "Ujian sudah berakhir, override reopen ditolak")
		return
	}
	reason := "Override pengawas"
	resetVio := true
	var body struct {
		Reason              string `json:"reason"`
		ResetViolationCount *bool  `json:"reset_violation_count"`
	}
	if err := readJSON(r, &body); err == nil {
		if strings.TrimSpace(body.Reason) != "" {
			reason = strings.TrimSpace(body.Reason)
		}
		if body.ResetViolationCount != nil {
			resetVio = *body.ResetViolationCount
		}
	}
	logs, _ := d.store.ListSessionLogs(r.Context(), sess.SessionID, 30)
	rec := evaluateSessionRecovery(sess.Status, sess.Terminated, sess.Violations, logs)
	if err := d.store.ResetSession(r.Context(), sess.SessionID, resetVio); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuka ulang sesi")
		return
	}
	_ = d.store.LogViolation(r.Context(), sess.SessionID, "SESSION_ADMIN_OVERRIDE_REOPEN", persistence.MustJSON(map[string]any{
		"category": rec.Category, "allow_continue_before_override": rec.AllowContinue,
		"reason": reason, "actor_id": userID, "actor_username": claims.Username,
		"actor_role": claims.Role, "previous_status": sess.Status,
		"previous_violation_count": sess.Violations, "reset_violation_count": resetVio,
	}))
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true, "session_id": sess.SessionID, "user_id": sess.UserID, "exam_id": sess.ExamID,
		"status": "in_progress", "message": "Sesi berhasil dibuka ulang dengan override pengawas.",
	})
}

func (d deps) cleanupSessions(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
		return
	}
	ex, err := d.store.GetExam(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian")
		return
	}
	if ex == nil || ex.Deleted || developerExamHidden(claims.Role, creatorRole(ex)) {
		writeDetail(w, http.StatusNotFound, "Exam not found")
		return
	}
	if allowed, _ := staffCanPauseExam(ex, userID, claims.Role, claims.JobTitle); !allowed {
		writeDetail(w, http.StatusForbidden, "Not authorized to clean up this exam")
		return
	}
	cleaned, saved, err := d.store.CleanupExamSessions(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal cleanup sesi")
		return
	}
	_ = d.store.LogUserActivity(r.Context(), userID, "EXAM_SESSIONS_CLEANUP", persistence.MustJSON(map[string]any{
		"exam_id": examID, "cleaned_count": cleaned, "saved_count": saved,
	}))
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true, "exam_id": examID, "cleaned_count": cleaned,
		"saved_count": saved, "message": "Cleanup sesi sementara selesai",
	})
}

func (d deps) recoveryCandidates(w http.ResponseWriter, r *http.Request) {
	ex, ok := d.loadMonitorExam(w, r)
	if !ok {
		return
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit == 0 {
		limit = 400
	}
	rows, err := d.store.ListRecoverySessions(r.Context(), ex.ID, limit)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat kandidat recovery")
		return
	}
	ids := make([]int, 0, len(rows))
	for _, row := range rows {
		ids = append(ids, row.SessionID)
	}
	logsBy, err := d.store.ListSessionLogsBulk(r.Context(), ids)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat log recovery")
		return
	}
	summary := map[string]int{
		"network_issue": 0, "cheating_detected": 0, "admin_decision": 0,
		"user_submit": 0, "unknown": 0, "allow_continue": 0, "blocked": 0,
	}
	_, claims, _ := d.staffOrFallback(w, r)
	canOverrideRole := claims != nil && (claims.Role == "admin" || claims.Role == "teacher")
	cands := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		logs := logsBy[row.SessionID]
		rec := evaluateSessionRecovery(row.Status, row.Terminated, row.Violations, logs)
		mode := deriveSubmitMode(logs)
		bucket := deriveReasonBucket(row.Status, rec.Category, mode)
		summary[bucket]++
		if rec.AllowContinue {
			summary["allow_continue"]++
		} else {
			summary["blocked"]++
		}
		name := row.UserName
		if name == "" {
			name = "User #" + strconv.Itoa(row.UserID)
		}
		var lastType any
		var lastAt any
		if len(logs) > 0 {
			lastType = logs[0].EventType
			lastAt = logs[0].CreatedAt.UTC().Format(time.RFC3339)
		}
		var started, ended any
		if row.StartTime != nil {
			started = row.StartTime.UTC().Format(time.RFC3339)
		}
		if row.EndTime != nil {
			ended = row.EndTime.UTC().Format(time.RFC3339)
		}
		cands = append(cands, map[string]any{
			"session_id": row.SessionID, "user_id": row.UserID, "user_name": name,
			"user_class": row.Class, "status": row.Status, "violation_count": row.Violations,
			"started_at": started, "ended_at": ended,
			"recovery_category": rec.Category, "recovery_message": rec.Message,
			"submit_mode": mode, "reason_bucket": bucket,
			"reason_label":    recoveryReasonLabels[bucket],
			"allow_continue":  rec.AllowContinue,
			"can_override":    canOverrideRole && !rec.AllowContinue,
			"last_event_type": lastType, "last_event_at": lastAt,
		})
	}
	sort.SliceStable(cands, func(i, j int) bool {
		ai, _ := cands[i]["allow_continue"].(bool)
		aj, _ := cands[j]["allow_continue"].(bool)
		if ai != aj {
			return ai
		}
		bi, _ := cands[i]["reason_bucket"].(string)
		bj, _ := cands[j]["reason_bucket"].(string)
		si, sj := recoveryReasonSort[bi], recoveryReasonSort[bj]
		if si != sj {
			return si < sj
		}
		vi, _ := cands[i]["violation_count"].(int)
		vj, _ := cands[j]["violation_count"].(int)
		if vi != vj {
			return vi > vj
		}
		ni, _ := cands[i]["user_name"].(string)
		nj, _ := cands[j]["user_name"].(string)
		return ni < nj
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"exam_id": ex.ID, "exam_title": ex.Title, "total_candidates": len(cands),
		"summary": summary, "candidates": cands,
	})
}

func (d deps) forceSubmit(w http.ResponseWriter, r *http.Request) {
	_, _, sess, ok := d.loadControlSession(w, r)
	if !ok {
		return
	}
	probe, err := d.store.ProbeSubmitAny(r.Context(), sess.SessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa sesi")
		return
	}
	if probe == nil {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	if probe.Status == "submitted" || probe.Status == "completed" {
		writeJSON(w, http.StatusOK, staffSubmitted(probe, sess.SessionID, "Sesi sudah pernah dikumpulkan."))
		return
	}
	if probe.Status != "in_progress" && probe.Status != "active" {
		writeDetail(w, http.StatusBadRequest, "Sesi tidak dalam status in_progress")
		return
	}
	tx, err := d.store.BeginSubmit(r.Context(), sess.SessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mengunci sesi")
		return
	}
	defer func() { _ = tx.Rollback(r.Context()) }()
	questions, err := d.store.LoadQuestionsForGrade(r.Context(), probe.ExamID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat soal")
		return
	}
	answers, err := d.store.ListAnswers(r.Context(), sess.SessionID)
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
		if err := persistence.UpdateAnswerScore(r.Context(), tx, sess.SessionID, ans.QuestionID, correct, pts); err != nil {
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
	if err := persistence.MarkSessionSubmitted(r.Context(), tx, sess.SessionID, probe.ExamID, pct); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menyelesaikan sesi")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menyimpan pengumpulan")
		return
	}
	_ = d.store.LogViolation(r.Context(), sess.SessionID, "FORCE_SUBMIT_BY_TEACHER", persistence.MustJSON(map[string]any{
		"category": "admin_decision", "allow_continue": false, "score": pct,
		"reason": "Teacher forced submission via admin panel",
	}))
	var passed any
	if probe.PassingScore != nil {
		passed = pct >= *probe.PassingScore
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id": sess.SessionID, "status": "submitted", "score": pct,
		"total_points": total, "points_earned": earned, "percentage": pct,
		"passed": passed, "message": "Sesi berhasil diselesaikan secara paksa.",
	})
}

func staffSubmitted(p *persistence.SubmitProbe, sessionID int, msg string) map[string]any {
	score := 0.0
	if p.Score != nil {
		score = *p.Score
	}
	var passed any
	if p.PassingScore != nil {
		passed = score >= *p.PassingScore
	}
	return map[string]any{
		"session_id": sessionID, "status": "submitted", "score": score,
		"total_points": nil, "points_earned": nil, "percentage": score,
		"passed": passed, "message": msg,
	}
}

func (d deps) loadControlSession(w http.ResponseWriter, r *http.Request) (int, *auth.Claims, *persistence.ControlSession, bool) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return 0, nil, nil, false
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return 0, nil, nil, false
	}
	sessionID, err := strconv.Atoi(r.PathValue("session_id"))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id tidak valid")
		return 0, nil, nil, false
	}
	sess, err := d.store.GetControlSession(r.Context(), sessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat sesi")
		return 0, nil, nil, false
	}
	if sess == nil {
		writeDetail(w, http.StatusNotFound, "Session not found")
		return 0, nil, nil, false
	}
	ex := &persistence.ExamRow{ID: sess.ExamID, CreatorID: sess.CreatorID}
	if !staffCanMonitor(ex, userID, claims.Role, claims.JobTitle) {
		writeDetail(w, http.StatusForbidden, "Not authorized to control this exam")
		return 0, nil, nil, false
	}
	return userID, claims, sess, true
}
