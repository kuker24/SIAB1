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

type examPayload struct {
	Title            string          `json:"title"`
	Description      *string         `json:"description"`
	DurationMinutes  int             `json:"duration_minutes"`
	StartTime        string          `json:"start_time"`
	EndTime          string          `json:"end_time"`
	PassingScore     *float64        `json:"passing_score"`
	MaxAttempts      int             `json:"max_attempts"`
	ShuffleQuestions bool            `json:"shuffle_questions"`
	ShuffleOptions   bool            `json:"shuffle_options"`
	ShowResults      bool            `json:"show_results"`
	AllowReview      bool            `json:"allow_review"`
	Published        bool            `json:"is_published"`
	Subject          *string         `json:"subject"`
	ExamType         *string         `json:"exam_type"`
	AcademicYear     *string         `json:"academic_year"`
	ShowTeacherName  *bool           `json:"show_teacher_name"`
	BuilderSettings  json.RawMessage `json:"builder_settings"`
	AllowedClasses   *string         `json:"allowed_classes"`
	AllowedStudents  *string         `json:"allowed_students"`
}

func (d deps) createExam(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Hanya guru atau admin yang dapat membuat ujian")
		return
	}
	in, errMsg := readExamWrite(r)
	if errMsg != "" {
		writeDetail(w, http.StatusBadRequest, errMsg)
		return
	}
	ex, err := d.store.CreateExam(r.Context(), userID, in)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal generate token ujian yang unik. Silakan coba lagi.")
		return
	}
	writeJSON(w, http.StatusCreated, examJSON(ex))
}

func (d deps) updateExam(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadStaffExam(w, r, userID, claims, false)
	if !ok {
		return
	}
	in, errMsg := readExamWrite(r)
	if errMsg != "" {
		writeDetail(w, http.StatusBadRequest, errMsg)
		return
	}
	if criticalScheduleChange(ex, in) {
		n, err := d.store.CountSessions(r.Context(), ex.ID)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa sesi")
			return
		}
		if n > 0 {
			writeDetail(w, http.StatusConflict, "Ujian sudah memiliki sesi peserta. Perubahan jadwal atau target peserta dikunci agar hasil historis tidak berubah konteks. Buat ujian/susulan baru atau hubungi developer untuk recovery terkontrol.")
			return
		}
	}
	updated, err := d.store.UpdateExam(r.Context(), ex.ID, in)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memperbarui ujian")
		return
	}
	writeJSON(w, http.StatusOK, examJSON(updated))
}

func (d deps) deleteExam(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadStaffExam(w, r, userID, claims, false)
	if !ok {
		return
	}
	if err := d.store.SoftDeleteExam(r.Context(), ex.ID); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menghapus ujian")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (d deps) publishExam(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if isPengawas(claims.Role, claims.JobTitle) {
		writeDetail(w, http.StatusForbidden, "Pengawas tidak diizinkan publish ujian. Hanya guru pembuat atau admin.")
		return
	}
	ex, ok := d.loadStaffExam(w, r, userID, claims, false)
	if !ok {
		return
	}
	if err := d.requireQuestions(r, ex.ID); err != "" {
		writeDetail(w, http.StatusBadRequest, err)
		return
	}
	if err := d.store.SetExamPublished(r.Context(), ex.ID, true); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mempublikasikan ujian")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"message": "Ujian berhasil dipublikasikan", "is_published": true})
}

func (d deps) togglePublish(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	pengawas := isPengawas(claims.Role, claims.JobTitle)
	ex, ok := d.loadStaffExam(w, r, userID, claims, pengawas)
	if !ok {
		return
	}
	if pengawas && !ex.Published {
		writeDetail(w, http.StatusForbidden, "Pengawas hanya dapat menarik ujian (unpublish), tidak dapat publish.")
		return
	}
	next := !ex.Published
	if next {
		if err := d.requireQuestions(r, ex.ID); err != "" {
			writeDetail(w, http.StatusBadRequest, err)
			return
		}
	}
	if err := d.store.SetExamPublished(r.Context(), ex.ID, next); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mengubah status publikasi")
		return
	}
	msg := "Ujian berhasil dipublikasikan"
	if !next {
		msg = "Ujian dibatalkan publikasinya"
	}
	writeJSON(w, http.StatusOK, map[string]any{"message": msg, "is_published": next})
}

func (d deps) requireQuestions(r *http.Request, examID int) string {
	n, err := d.store.CountQuestions(r.Context(), examID)
	if err != nil {
		return "Gagal memeriksa soal"
	}
	if n < 1 {
		return "Ujian belum memiliki soal"
	}
	return ""
}

func (d deps) staffOrFallback(w http.ResponseWriter, r *http.Request) (int, *auth.Claims, bool) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return 0, nil, false
	}
	claims, err := auth.Parse(d.secret, auth.Bearer(r.Header.Get("Authorization")))
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, auth.FormatDetail(err))
		return 0, nil, false
	}
	return userID, claims, true
}

func (d deps) loadStaffExam(w http.ResponseWriter, r *http.Request, userID int, claims *auth.Claims, pengawasUnpublish bool) (*persistence.ExamRow, bool) {
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
		writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
		return nil, false
	}
	ok, hidden, detail := staffCanMutateExam(ex, userID, claims.Role, claims.JobTitle, pengawasUnpublish)
	if !ok {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return nil, false
		}
		writeDetail(w, http.StatusForbidden, detail)
		return nil, false
	}
	return ex, true
}

func readExamWrite(r *http.Request) (persistence.ExamWrite, string) {
	var body examPayload
	if err := readJSON(r, &body); err != nil {
		return persistence.ExamWrite{}, "Payload tidak valid"
	}
	title := strings.TrimSpace(body.Title)
	if title == "" || len(title) > 255 {
		return persistence.ExamWrite{}, "Judul ujian tidak valid"
	}
	if body.DurationMinutes <= 0 {
		return persistence.ExamWrite{}, "Durasi ujian harus lebih dari 0"
	}
	start, err := parseFlexTime(body.StartTime)
	if err != nil {
		return persistence.ExamWrite{}, "Waktu mulai tidak valid"
	}
	end, err := parseFlexTime(body.EndTime)
	if err != nil {
		return persistence.ExamWrite{}, "Waktu selesai tidak valid"
	}
	if !end.After(start) {
		return persistence.ExamWrite{}, "Waktu selesai harus setelah waktu mulai"
	}
	showTeacher := true
	if body.ShowTeacherName != nil {
		showTeacher = *body.ShowTeacherName
	}
	settings := []byte("{}")
	if len(body.BuilderSettings) > 0 && string(body.BuilderSettings) != "null" {
		settings = body.BuilderSettings
	}
	return persistence.ExamWrite{
		Title:            title,
		Description:      body.Description,
		DurationMinutes:  body.DurationMinutes,
		StartTime:        start,
		EndTime:          end,
		PassingScore:     body.PassingScore,
		MaxAttempts:      body.MaxAttempts,
		ShuffleQuestions: body.ShuffleQuestions,
		ShuffleOptions:   body.ShuffleOptions,
		ShowResults:      body.ShowResults,
		AllowReview:      body.AllowReview,
		Published:        body.Published,
		Subject:          body.Subject,
		ExamType:         body.ExamType,
		AcademicYear:     body.AcademicYear,
		ShowTeacherName:  showTeacher,
		BuilderSettings:  settings,
		AllowedClasses:   body.AllowedClasses,
		AllowedStudents:  body.AllowedStudents,
	}, ""
}

func parseFlexTime(raw string) (time.Time, error) {
	raw = strings.TrimSpace(raw)
	layouts := []string{
		time.RFC3339Nano,
		time.RFC3339,
		"2006-01-02T15:04:05.000Z07:00",
		"2006-01-02T15:04:05Z07:00",
		"2006-01-02T15:04:05",
		"2006-01-02 15:04:05",
	}
	var err error
	for _, layout := range layouts {
		var t time.Time
		t, err = time.Parse(layout, raw)
		if err == nil {
			if t.Location() == time.UTC && !strings.ContainsAny(raw, "Z+-") {
				return t.UTC(), nil
			}
			return t.UTC(), nil
		}
	}
	return time.Time{}, err
}

func criticalScheduleChange(ex *persistence.ExamRow, in persistence.ExamWrite) bool {
	if !sameInstant(ex.StartTime, in.StartTime) || !sameInstant(ex.EndTime, in.EndTime) {
		return true
	}
	return csvKey(ex.AllowedClasses) != csvKey(in.AllowedClasses) ||
		csvKey(ex.AllowedStudents) != csvKey(in.AllowedStudents)
}

func sameInstant(a, b time.Time) bool {
	return a.UTC().Truncate(time.Second).Equal(b.UTC().Truncate(time.Second))
}

func csvKey(raw *string) string {
	if raw == nil {
		return ""
	}
	parts := strings.Split(*raw, ",")
	out := make([]string, 0, len(parts))
	seen := map[string]struct{}{}
	for _, p := range parts {
		p = strings.ToUpper(strings.TrimSpace(p))
		if p == "" {
			continue
		}
		if _, ok := seen[p]; ok {
			continue
		}
		seen[p] = struct{}{}
		out = append(out, p)
	}
	return strings.Join(out, ",")
}
