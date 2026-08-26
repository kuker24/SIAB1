package exam

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	"siab1/internal/auth"
	"siab1/internal/config"
	"siab1/internal/persistence"
)

type deps struct {
	store     *persistence.Store
	secret    string
	appSecret string
	examPeak  bool
	fallback  http.Handler
	sebLegacy bool
	sebStrict bool
	sebKey    string
	sebBEK    string
	baseURL   string
}

func Register(mux *http.ServeMux, store *persistence.Store, cfg config.Config, fallback http.Handler) {
	d := deps{
		store:     store,
		secret:    cfg.JWTSecretKey,
		appSecret: cfg.SecretKey,
		examPeak:  cfg.ExamPeakMode,
		fallback:  fallback,
		sebLegacy: cfg.SEBDesktopLegacy,
		sebStrict: cfg.SEBStrictMode,
		sebKey:    cfg.SEBDefaultConfigKey,
		sebBEK:    cfg.SEBDefaultBrowserExamKey,
		baseURL:   cfg.BaseURL,
	}
	mux.HandleFunc("POST /api/exams/auto-save", d.autoSave)
	mux.HandleFunc("POST /api/exams/submit-answer", d.submitAnswer)
	mux.HandleFunc("GET /api/exams/session/{session_id}/answers", d.getAnswers)
	mux.HandleFunc("POST /api/exams/{exam_id}/start", d.startExam)
	mux.HandleFunc("GET /api/exams/session/{session_id}/remaining-time", d.remainingTime)
	mux.HandleFunc("GET /api/auth/me", d.me)
	mux.HandleFunc("GET /api/runtime/policy", d.runtimePolicy)
	mux.HandleFunc("POST /api/auth/login", d.loginAny)
	mux.HandleFunc("POST /api/auth/signin", d.loginAny)
	registerLoginLane(mux, "student", d.loginStudent)
	registerLoginLane(mux, "control", d.loginControl)
	registerLoginLane(mux, "admin", d.loginAdmin)
	registerLoginLane(mux, "teacher", d.loginTeacher)
	registerLoginLane(mux, "pengawas", d.loginPengawas)
	mux.HandleFunc("POST /api/exams/submit", d.submitExam)
	mux.HandleFunc("POST /api/exams/auto-save-batch", d.autoSaveBatch)
	mux.HandleFunc("POST /api/exams/answer-journal/sync", d.journalSync)
	mux.HandleFunc("POST /api/exams/log-violation", d.logViolation)
	mux.HandleFunc("GET /api/exams/session/{session_id}/status", d.sessionStatus)
	mux.HandleFunc("GET /api/exams/session/{session_id}/resume", d.resumeSession)
	mux.HandleFunc("POST /api/exams/join", d.joinExam)
	mux.HandleFunc("GET /api/templates", d.listTemplates)
	mux.HandleFunc("GET /api/templates/{$}", d.listTemplates)
	mux.HandleFunc("POST /api/templates", d.createTemplate)
	mux.HandleFunc("POST /api/templates/{$}", d.createTemplate)
	mux.HandleFunc("GET /api/templates/{template_id}", d.getTemplate)
	mux.HandleFunc("PUT /api/templates/{template_id}", d.updateTemplate)
	mux.HandleFunc("DELETE /api/templates/{template_id}", d.deleteTemplate)
	mux.HandleFunc("POST /api/templates/{template_id}/create-exam", d.createExamFromTemplate)
	mux.HandleFunc("GET /api/activity/logs", d.activityLogs)
	mux.HandleFunc("GET /api/activity/stats", d.activityStats)
	mux.HandleFunc("DELETE /api/activity/logs/reset", d.resetActivityLogs)
	mux.HandleFunc("POST /api/scheduled/exams/{exam_id}/schedule", d.createSchedule)
	mux.HandleFunc("GET /api/scheduled/exams/{exam_id}/schedules", d.listSchedules)
	mux.HandleFunc("DELETE /api/scheduled/schedules/{schedule_id}", d.cancelSchedule)
	mux.HandleFunc("GET /api/scheduled/schedules/upcoming", d.upcomingSchedules)
	mux.HandleFunc("GET /api/scheduled/schedules/stats", d.scheduleStats)
	mux.HandleFunc("GET /api/v1/settings/timezone", d.systemTimezone)
	mux.HandleFunc("POST /api/exams", d.createExam)
	mux.HandleFunc("PUT /api/exams/{exam_id}", d.updateExam)
	mux.HandleFunc("DELETE /api/exams/{exam_id}", d.deleteExam)
	mux.HandleFunc("POST /api/exams/{exam_id}/publish", d.publishExam)
	mux.HandleFunc("PATCH /api/exams/{exam_id}/publish", d.togglePublish)
	mux.HandleFunc("GET /api/exams", d.listExams)
	mux.HandleFunc("GET /api/exams/results/all", d.examsWithResults)
	mux.HandleFunc("GET /api/exams/my-results", d.myResults)
	mux.HandleFunc("GET /api/exams/{exam_id}/results", d.examResults)
	mux.HandleFunc("GET /api/exams/{exam_id}/participation-summary", d.participationSummary)
	mux.HandleFunc("GET /api/exams/{exam_id}/analytics", d.examAnalytics)
	mux.HandleFunc("GET /api/analytics/exam/{exam_id}/classes", d.examClasses)
	mux.HandleFunc("GET /api/analytics/exam/{exam_id}/question-difficulty", d.questionDifficulty)
	mux.HandleFunc("GET /api/analytics/dashboard", d.analyticsDashboard)
	mux.HandleFunc("GET /api/analytics/class", d.classPerformance)
	mux.HandleFunc("GET /api/analytics/class/{class_name}", d.classPerformance)
	mux.HandleFunc("GET /api/analytics/exam/{exam_id}/assessment", d.assessmentAnalysis)
	mux.HandleFunc("GET /api/exams/{exam_id}/sessions/{session_id}/review", d.sessionReview)
	mux.HandleFunc("GET /api/stats/dashboard", d.dashboardStats)
	mux.HandleFunc("GET /api/grading/pending-essays", d.pendingGrades)
	mux.HandleFunc("GET /api/grading/stats", d.gradingStats)
	mux.HandleFunc("POST /api/grading/grade-essay", d.gradeEssay)
	mux.HandleFunc("POST /api/grading/batch-grade", d.batchGrade)
	mux.HandleFunc("GET /api/grading/answer/{answer_id}", d.gradingAnswerDetail)
	mux.HandleFunc("GET /api/questions/categories", d.listCategories)
	mux.HandleFunc("POST /api/questions/categories", d.createCategory)
	mux.HandleFunc("GET /api/questions/tags", d.listTags)
	mux.HandleFunc("POST /api/questions/tags", d.createTag)
	mux.HandleFunc("POST /api/questions/search", d.searchQuestions)
	mux.HandleFunc("GET /api/questions/{exam_id}/all", d.listQuestions)
	mux.HandleFunc("POST /api/questions/{exam_id}", d.createQuestion)
	mux.HandleFunc("PUT /api/questions/{question_id}", d.updateQuestion)
	mux.HandleFunc("DELETE /api/questions/{question_id}", d.deleteQuestion)
	mux.HandleFunc("GET /api/exams/{exam_id}/preview", d.previewExam)
	mux.HandleFunc("POST /api/exams/{exam_id}/duplicate", d.duplicateExam)
	mux.HandleFunc("POST /api/exams/{exam_id}/regenerate-token", d.regenerateToken)
	mux.HandleFunc("GET /api/users/student-classes", d.studentClasses)
	mux.HandleFunc("GET /api/users/students-by-class", d.studentsByClass)
	mux.HandleFunc("GET /api/users/advanced-search", d.searchUsers)
	mux.HandleFunc("GET /api/users/template/csv", d.userTemplateCSV)
	mux.HandleFunc("POST /api/users/batch-create", d.batchCreateUsers)
	mux.HandleFunc("PATCH /api/users/batch-update", d.batchUpdateUsers)
	mux.HandleFunc("DELETE /api/users/batch-delete", d.batchDeleteUsers)
	mux.HandleFunc("POST /api/users/export", d.exportUsers)
	mux.HandleFunc("GET /api/users", d.listUsers)
	mux.HandleFunc("POST /api/users", d.createUser)
	mux.HandleFunc("GET /api/users/{user_id}", d.getUser)
	mux.HandleFunc("PUT /api/users/{user_id}", d.updateUser)
	mux.HandleFunc("DELETE /api/users/{user_id}", d.deleteUser)
	mux.HandleFunc("GET /api/subjects", d.listSubjects)
	mux.HandleFunc("POST /api/subjects", d.createSubject)
	mux.HandleFunc("DELETE /api/subjects/{subject_id}", d.deleteSubject)
	mux.HandleFunc("GET /api/exams/{exam_id}/pause-status", d.pauseStatus)
	mux.HandleFunc("POST /api/exams/{exam_id}/pause-all", d.pauseAll)
	mux.HandleFunc("POST /api/exams/{exam_id}/resume-all", d.resumeAll)
	mux.HandleFunc("POST /api/exams/{exam_id}/cleanup-sessions", d.cleanupSessions)
	mux.HandleFunc("GET /api/monitoring/exam/{exam_id}/live-stats", d.liveStats)
	mux.HandleFunc("GET /api/monitoring/exam/{exam_id}/sessions", d.monitorSessions)
	mux.HandleFunc("GET /api/monitoring/active-exams", d.activeExams)
	mux.HandleFunc("GET /api/monitoring/violation-types", d.violationTypes)
	mux.HandleFunc("GET /api/monitoring/violations", d.violationsDashboard)
	mux.HandleFunc("GET /api/monitoring/exam/{exam_id}/recovery-candidates", d.recoveryCandidates)
	mux.HandleFunc("POST /api/monitoring/sessions/{session_id}/kick", d.kickSession)
	mux.HandleFunc("GET /api/monitoring/sessions/{session_id}/recovery-status", d.recoveryStatus)
	mux.HandleFunc("POST /api/monitoring/sessions/{session_id}/reset", d.resetSession)
	mux.HandleFunc("POST /api/monitoring/sessions/{session_id}/reopen-override", d.reopenOverride)
	mux.HandleFunc("POST /api/exams/sessions/{session_id}/force-submit", d.forceSubmit)
	mux.HandleFunc("POST /api/exams/sessions/{session_id}/emergency-exit", d.emergencyExit)
	mux.HandleFunc("POST /api/exams/sessions/{session_id}/revoke-emergency-exit", d.revokeEmergencyExit)
	mux.HandleFunc("GET /api/exams/default-seb-config.seb", d.defaultSEBConfig)
	mux.HandleFunc("GET /api/seb/download-config", d.defaultSEBConfig)
	mux.HandleFunc("GET /api/exams/{exam_id}/seb-config.seb", d.examSEBConfig)
	mux.HandleFunc("GET /api/exams/{exam_id}", d.getExam)
	mux.HandleFunc("GET /ws/exam/{exam_id}/{user_id}", d.examWebSocket)
	mux.HandleFunc("POST /api/auth/refresh", d.refreshToken)
}

func registerLoginLane(mux *http.ServeMux, lane string, h http.HandlerFunc) {
	mux.HandleFunc("POST /api/auth/"+lane+"/login", h)
	mux.HandleFunc("POST /api/auth/"+lane+"/signin", h)
	mux.HandleFunc("POST /api/"+lane+"/auth/login", h)
	mux.HandleFunc("POST /api/"+lane+"/auth/signin", h)
}

func (d deps) autoSave(w http.ResponseWriter, r *http.Request) {
	d.proxyExamWrite(w, r)
}

func (d deps) submitAnswer(w http.ResponseWriter, r *http.Request) {
	d.proxyExamWrite(w, r)
}

func (d deps) getAnswers(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	sessionID, err := strconv.Atoi(r.PathValue("session_id"))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id must be a valid integer")
		return
	}
	status, found, err := d.store.SessionOwned(r.Context(), sessionID, userID)
	if err != nil {
		d.tryFallback(w, r)
		return
	}
	if !found {
		writeDetail(w, http.StatusNotFound, "Session not found")
		return
	}
	if status != "in_progress" && status != "active" {
		writeJSON(w, http.StatusOK, map[string]any{"answers": map[string]any{}, "session_status": status})
		return
	}
	rows, err := d.store.ListAnswers(r.Context(), sessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat jawaban")
		return
	}
	answers := map[string]any{}
	for _, row := range rows {
		answers[strconv.Itoa(row.QuestionID)] = exportAnswer(row)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"answers":        answers,
		"session_status": status,
		"answered_count": len(answers),
	})
}

func (d deps) userOrFallback(w http.ResponseWriter, r *http.Request) (int, bool) {
	if d.store == nil || !d.store.HasPool() {
		return 0, d.tryFallback(w, r)
	}
	claims, err := auth.Parse(d.secret, auth.Bearer(r.Header.Get("Authorization")))
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, auth.FormatDetail(err))
		return 0, false
	}
	id, err := claims.UserID()
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, "Not authenticated")
		return 0, false
	}
	return id, true
}

func (d deps) tryFallback(w http.ResponseWriter, r *http.Request) bool {
	if d.fallback == nil {
		writeDetail(w, http.StatusServiceUnavailable, "Database tidak tersedia")
		return false
	}
	d.fallback.ServeHTTP(w, r)
	return false
}

func (d deps) proxyExamWrite(w http.ResponseWriter, r *http.Request) {
	_ = d.tryFallback(w, r)
}

func exportAnswer(row persistence.AnswerRow) any {
	if len(row.Metadata) > 0 {
		var meta map[string]any
		if json.Unmarshal(row.Metadata, &meta) == nil {
			if stmts, ok := meta["statement_answers"]; ok && stmts != nil {
				return stmts
			}
		}
	}
	if len(row.SelectedOptionIDs) > 0 {
		return row.SelectedOptionIDs
	}
	if row.AnswerText != nil && strings.TrimSpace(*row.AnswerText) != "" {
		return *row.AnswerText
	}
	if row.SelectedOptionID != nil {
		return *row.SelectedOptionID
	}
	return nil
}

func readJSON(r *http.Request, dest any) error {
	defer r.Body.Close()
	dec := json.NewDecoder(io.LimitReader(r.Body, 1<<20))
	dec.UseNumber()
	return dec.Decode(dest)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func writeDetail(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]string{"detail": msg})
}
