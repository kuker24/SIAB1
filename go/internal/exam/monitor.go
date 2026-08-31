package exam

import (
	"errors"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/persistence"
)

func (d deps) liveStats(w http.ResponseWriter, r *http.Request) {
	ex, ok := d.loadMonitorExam(w, r)
	if !ok {
		return
	}
	rows, err := d.store.ListMonitorSessions(r.Context(), ex.ID, "")
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat statistik")
		return
	}
	totalQ := ex.QuestionCount
	if totalQ < 1 {
		totalQ = 1
	}
	active, completed := 0, 0
	violations := 0
	var scoreSum float64
	scoreN := 0
	var progSum float64
	progN := 0
	for _, row := range rows {
		violations += row.Violations
		st := strings.ToLower(row.Status)
		if st == "in_progress" {
			active++
			progSum += (float64(row.Answered) / float64(totalQ)) * 100
			progN++
		}
		if st == "submitted" || st == "completed" {
			completed++
			if row.Score != nil {
				scoreSum += *row.Score
				scoreN++
			}
		}
	}
	avgScore := 0.0
	if scoreN > 0 {
		avgScore = math.Round((scoreSum/float64(scoreN))*100) / 100
	}
	avgProg := 0.0
	if progN > 0 {
		avgProg = math.Round((progSum/float64(progN))*100) / 100
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"exam_id":                ex.ID,
		"exam_title":             ex.Title,
		"active_participants":    active,
		"completed_participants": completed,
		"total_violations":       violations,
		"average_score":          avgScore,
		"average_progress":       avgProg,
		"timestamp":              time.Now().UTC().Format(time.RFC3339),
	})
}

func (d deps) monitorSessions(w http.ResponseWriter, r *http.Request) {
	ex, ok := d.loadMonitorExam(w, r)
	if !ok {
		return
	}
	status := strings.TrimSpace(r.URL.Query().Get("status"))
	rows, err := d.store.ListMonitorSessions(r.Context(), ex.ID, status)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat sesi")
		return
	}
	totalQ := ex.QuestionCount
	if totalQ < 1 {
		totalQ = 1
	}
	sessions := make([]map[string]any, 0, len(rows))
	inProg, done := 0, 0
	for _, row := range rows {
		st := strings.ToLower(row.Status)
		if st == "in_progress" {
			inProg++
		}
		if st == "submitted" || st == "completed" {
			done++
		}
		name := row.FullName
		if name == "" {
			name = row.Username
		}
		if name == "" {
			name = "User #" + strconv.Itoa(row.UserID)
		}
		start := ""
		if row.StartTime != nil {
			start = row.StartTime.UTC().Format(time.RFC3339)
		}
		progress := math.Round((float64(row.Answered)/float64(totalQ))*10000) / 100
		var ip any
		if row.IPAddress != nil {
			ip = *row.IPAddress
		}
		sessions = append(sessions, map[string]any{
			"session_id":          row.SessionID,
			"user_id":             row.UserID,
			"user_name":           name,
			"user_class":          row.Class,
			"progress":            progress,
			"violation_count":     row.Violations,
			"start_time":          start,
			"status":              row.Status,
			"ip_address":          ip,
			"is_online":           false,
			"last_active":         nil,
			"terminated_by_admin": row.Terminated,
			"recovery_category":   nil,
			"recovery_message":    nil,
			"allow_continue":      !row.Terminated,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"exam_id":         ex.ID,
		"exam_title":      ex.Title,
		"total_questions": ex.QuestionCount,
		"sessions":        sessions,
		"summary":         map[string]any{"total": len(rows), "in_progress": inProg, "completed": done},
	})
}

func (d deps) activeExams(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	creatorID := 0
	if claims.Role == "teacher" {
		creatorID = userID
	}
	rows, err := d.store.ListActiveExams(r.Context(), creatorID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian aktif")
		return
	}
	items := make([]map[string]any, 0, len(rows))
	totalSess, totalActive, totalDone, totalVio := 0, 0, 0, 0
	for _, row := range rows {
		items = append(items, map[string]any{
			"id":                     row.ExamID,
			"title":                  row.Title,
			"start_time":             row.StartTime.UTC().Format(time.RFC3339),
			"end_time":               row.EndTime.UTC().Format(time.RFC3339),
			"duration_minutes":       row.DurationMinutes,
			"total_sessions":         row.TotalSessions,
			"active_participants":    row.InProgress,
			"in_progress_count":      row.InProgress,
			"completed_count":        row.Completed,
			"completed_participants": row.Completed,
			"total_violations":       row.Violations,
		})
		totalSess += row.TotalSessions
		totalActive += row.InProgress
		totalDone += row.Completed
		totalVio += row.Violations
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"active_exams":                 items,
		"total":                        len(items),
		"total_sessions":               totalSess,
		"total_active_participants":    totalActive,
		"total_completed_participants": totalDone,
		"total_violations":             totalVio,
		"timestamp":                    time.Now().UTC().Format(time.RFC3339),
	})
}

func (d deps) pauseAll(w http.ResponseWriter, r *http.Request) {
	d.setPaused(w, r, true)
}

func (d deps) resumeAll(w http.ResponseWriter, r *http.Request) {
	d.setPaused(w, r, false)
}

func (d deps) setPaused(w http.ResponseWriter, r *http.Request, paused bool) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
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
	if ex == nil || ex.Deleted {
		writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
		return
	}
	if ok, hidden := staffCanPauseExam(ex, userID, claims.Role, claims.JobTitle); !ok {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return
		}
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	n, at, dur, err := d.store.SetExamPaused(r.Context(), examID, userID, paused)
	if errors.Is(err, persistence.ErrAlreadyPaused) {
		writeDetail(w, http.StatusBadRequest, "Ujian sudah dalam status pause")
		return
	}
	if errors.Is(err, persistence.ErrNotPaused) {
		writeDetail(w, http.StatusBadRequest, "Ujian tidak dalam status pause")
		return
	}
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mengubah status jeda")
		return
	}
	msg := "Ujian berhasil di-pause. " + strconv.Itoa(n) + " sesi terpengaruh."
	var pausedAt any
	if paused && at != nil {
		pausedAt = at.UTC().Format(time.RFC3339)
	}
	if !paused {
		msg = "Ujian dilanjutkan. " + strconv.Itoa(n) + " sesi resumed. Pause duration: " + strconv.Itoa(dur) + "s"
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"exam_id":           examID,
		"is_paused":         paused,
		"paused_at":         pausedAt,
		"affected_sessions": n,
		"message":           msg,
	})
}

func (d deps) loadMonitorExam(w http.ResponseWriter, r *http.Request) (*persistence.ExamRow, bool) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return nil, false
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return nil, false
	}
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
		return nil, false
	}
	ex, err := d.store.GetExam(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian")
		return nil, false
	}
	if ex == nil || ex.Deleted {
		writeDetail(w, http.StatusNotFound, "Exam not found")
		return nil, false
	}
	if !staffCanMonitor(ex, userID, claims.Role, claims.JobTitle) {
		writeDetail(w, http.StatusForbidden, "Not authorized to monitor this exam")
		return nil, false
	}
	return ex, true
}
