package exam

import (
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

var (
	joinMu    sync.Mutex
	joinHits  = map[string][]time.Time{}
	joinLimit = 10
)

func (d deps) myResults(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	claims, err := auth.Parse(d.secret, auth.Bearer(r.Header.Get("Authorization")))
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, auth.FormatDetail(err))
		return
	}
	if claims.Role != "student" && claims.Role != "guruplus" {
		writeDetail(w, http.StatusForbidden, "Hanya peserta ujian yang dapat melihat riwayat ujian sendiri")
		return
	}
	exams, err := d.store.ListMyResults(r.Context(), userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat hasil")
		return
	}
	out := make([]map[string]any, 0, len(exams))
	for i := range exams {
		out = append(out, examJSON(&exams[i]))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) listExams(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	claims, err := auth.Parse(d.secret, auth.Bearer(r.Header.Get("Authorization")))
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, auth.FormatDetail(err))
		return
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	skip, _ := strconv.Atoi(r.URL.Query().Get("skip"))
	publishedOnly := true
	if v := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("published_only"))); v == "false" || v == "0" {
		publishedOnly = false
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		exams, err := d.store.ListPublishedExams(r.Context(), limit, skip)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian")
			return
		}
		out := make([]map[string]any, 0, len(exams))
		for i := range exams {
			ex := &exams[i]
			if ok, _ := participantAccess(ex, userID, claims.Role, claims.StudentClass); !ok {
				continue
			}
			out = append(out, examJSON(ex))
		}
		writeJSON(w, http.StatusOK, map[string]any{"exams": out, "total": len(out)})
		return
	}
	filter := persistence.ExamListFilter{Limit: limit, Offset: skip, PublishedOnly: publishedOnly}
	switch claims.Role {
	case "developer":
	case "admin":
		filter.HideDeveloper = true
	case "teacher":
		filter.HideDeveloper = true
		if isPengawas(claims.Role, claims.JobTitle) {
			filter.PublishedOnly = true
		} else {
			filter.CreatorID = userID
		}
	default:
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses ke daftar ujian")
		return
	}
	exams, total, err := d.store.ListExamsFiltered(r.Context(), filter)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian")
		return
	}
	out := make([]map[string]any, 0, len(exams))
	for i := range exams {
		out = append(out, examJSON(&exams[i]))
	}
	writeJSON(w, http.StatusOK, map[string]any{"exams": out, "total": total})
}

func (d deps) getExam(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	claims, err := auth.Parse(d.secret, auth.Bearer(r.Header.Get("Authorization")))
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, auth.FormatDetail(err))
		return
	}
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		d.tryFallback(w, r)
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
	if claims.Role == "student" || claims.Role == "guruplus" {
		if !ex.Published {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return
		}
		if ok, detail := participantAccess(ex, userID, claims.Role, claims.StudentClass); !ok {
			writeDetail(w, http.StatusForbidden, detail)
			return
		}
		writeJSON(w, http.StatusOK, examJSON(ex))
		return
	}
	if ok, hidden := staffCanViewExam(ex, userID, claims.Role, claims.JobTitle); !ok {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return
		}
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses ke ujian ini")
		return
	}
	writeJSON(w, http.StatusOK, examJSON(ex))
}

func (d deps) pauseStatus(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	claims, err := auth.Parse(d.secret, auth.Bearer(r.Header.Get("Authorization")))
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, auth.FormatDetail(err))
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
	if claims.Role == "student" || claims.Role == "guruplus" {
		if !ex.Published {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return
		}
		if ok, detail := participantAccess(ex, userID, claims.Role, claims.StudentClass); !ok {
			writeDetail(w, http.StatusForbidden, detail)
			return
		}
	} else if ok, hidden := staffCanViewExam(ex, userID, claims.Role, claims.JobTitle); !ok {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return
		}
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses ke ujian ini")
		return
	}
	paused, pausedAt, found, err := d.store.ExamPauseStatus(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat status jeda")
		return
	}
	if !found {
		writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
		return
	}
	var at any
	dur := 0
	if paused && pausedAt != nil {
		at = pausedAt.UTC().Format(time.RFC3339)
		dur = int(time.Since(pausedAt.UTC()).Seconds())
		if dur < 0 {
			dur = 0
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"exam_id":                examID,
		"is_paused":              paused,
		"paused_at":              at,
		"current_pause_duration": dur,
	})
}

func (d deps) refreshToken(w http.ResponseWriter, r *http.Request) {
	if d.store == nil || !d.store.HasPool() {
		d.tryFallback(w, r)
		return
	}
	claims, err := auth.ParseAllowExpired(d.secret, auth.Bearer(r.Header.Get("Authorization")))
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, "Token tidak valid")
		return
	}
	if !auth.WithinRefreshGrace(claims, 15) {
		writeDetail(w, http.StatusUnauthorized, "Sesi telah berakhir. Silakan login ulang.")
		return
	}
	userID, err := claims.UserID()
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, "Token tidak valid")
		return
	}
	u, err := d.store.GetUser(r.Context(), userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat profil")
		return
	}
	if u == nil || !u.IsActive {
		writeDetail(w, http.StatusUnauthorized, "Pengguna tidak ditemukan")
		return
	}
	className := ""
	if u.StudentClass != nil {
		className = *u.StudentClass
	}
	job := ""
	if u.JobTitle != nil {
		job = *u.JobTitle
	}
	tok, err := auth.Sign(d.secret, auth.Claims{
		Sub:          itoa(u.ID),
		Username:     u.Username,
		Role:         u.Role,
		FullName:     u.FullName,
		StudentClass: className,
		JobTitle:     job,
		IsActive:     u.IsActive,
	})
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat token")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"access_token": tok,
		"token_type":   "bearer",
		"expires_in":   auth.TokenTTLSeconds(),
		"user":         userJSON(u),
	})
}

func examJSON(ex *persistence.ExamRow) map[string]any {
	teacher := any(nil)
	if ex.ShowTeacherName && ex.TeacherName != nil {
		teacher = *ex.TeacherName
	}
	return map[string]any{
		"id":                ex.ID,
		"title":             ex.Title,
		"description":       ex.Description,
		"creator_id":        ex.CreatorID,
		"duration_minutes":  ex.DurationMinutes,
		"start_time":        ex.StartTime.UTC().Format(time.RFC3339),
		"end_time":          ex.EndTime.UTC().Format(time.RFC3339),
		"start_time_wib":    formatWIB(ex.StartTime),
		"end_time_wib":      formatWIB(ex.EndTime),
		"passing_score":     ex.PassingScore,
		"max_attempts":      ex.MaxAttempts,
		"shuffle_questions": ex.ShuffleQuestions,
		"shuffle_options":   ex.ShuffleOptions,
		"show_results":      ex.ShowResults,
		"allow_review":      ex.AllowReview,
		"is_published":      ex.Published,
		"access_token":      ex.AccessToken,
		"subject":           ex.Subject,
		"exam_type":         ex.ExamType,
		"academic_year":     ex.AcademicYear,
		"show_teacher_name": ex.ShowTeacherName,
		"builder_settings":  map[string]any{},
		"teacher_name":      teacher,
		"allowed_classes":   ex.AllowedClasses,
		"allowed_students":  ex.AllowedStudents,
		"question_count":    ex.QuestionCount,
		"created_at":        ex.CreatedAt.UTC().Format(time.RFC3339),
	}
}

func formatWIB(t time.Time) string {
	loc, err := time.LoadLocation("Asia/Jakarta")
	if err != nil {
		return t.UTC().Format("02 January 2006 15:04") + " WIB"
	}
	return t.In(loc).Format("02 January 2006 15:04") + " WIB"
}

func allowJoin(key string) bool {
	now := time.Now()
	joinMu.Lock()
	defer joinMu.Unlock()
	buf := joinHits[key]
	cut := now.Add(-time.Minute)
	i := 0
	for i < len(buf) && !buf[i].After(cut) {
		i++
	}
	buf = buf[i:]
	if len(buf) >= joinLimit {
		joinHits[key] = buf
		return false
	}
	joinHits[key] = append(buf, now)
	return true
}
