package exam

import (
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/persistence"
)

func (d deps) createSchedule(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadResultsExam(w, r, userID, claims)
	if !ok {
		return
	}
	var body struct {
		PublishAt   string  `json:"publish_at"`
		UnpublishAt *string `json:"unpublish_at"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	publishAt, err := parseFlexTime(body.PublishAt)
	if err != nil || !publishAt.After(time.Now()) {
		writeDetail(w, http.StatusUnprocessableEntity, "Publish time must be in the future")
		return
	}
	var unpublishAt *time.Time
	if body.UnpublishAt != nil && strings.TrimSpace(*body.UnpublishAt) != "" {
		parsed, err := parseFlexTime(*body.UnpublishAt)
		if err != nil || !parsed.After(publishAt) {
			writeDetail(w, http.StatusUnprocessableEntity, "Unpublish time must be after publish time")
			return
		}
		unpublishAt = &parsed
	}
	row, err := d.store.CreateSchedule(r.Context(), ex.ID, userID, publishAt, unpublishAt)
	if errors.Is(err, persistence.ErrPendingSchedule) {
		writeDetail(w, http.StatusBadRequest, "Ujian sudah memiliki jadwal pending. Batalkan terlebih dahulu.")
		return
	}
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menyimpan jadwal")
		return
	}
	writeJSON(w, http.StatusCreated, scheduleJSON(row))
}

func (d deps) listSchedules(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadResultsExam(w, r, userID, claims)
	if !ok {
		return
	}
	rows, err := d.store.ListExamSchedules(r.Context(), ex.ID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat jadwal")
		return
	}
	out := make([]map[string]any, 0, len(rows))
	for i := range rows {
		out = append(out, scheduleJSON(&rows[i]))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) cancelSchedule(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	id, err := strconv.Atoi(r.PathValue("schedule_id"))
	if err != nil || id <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "schedule_id tidak valid")
		return
	}
	row, err := d.store.GetSchedule(r.Context(), id)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat jadwal")
		return
	}
	if row == nil {
		writeDetail(w, http.StatusNotFound, "Jadwal tidak ditemukan")
		return
	}
	if row.CreatorRole != nil && developerExamHidden(claims.Role, *row.CreatorRole) {
		writeDetail(w, http.StatusNotFound, "Jadwal tidak ditemukan")
		return
	}
	if row.CreatedBy == nil || (*row.CreatedBy != userID && !isAdminScope(claims.Role)) {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses untuk membatalkan jadwal ini")
		return
	}
	if row.Status != "pending" {
		writeDetail(w, http.StatusBadRequest, "Tidak dapat membatalkan jadwal dengan status: "+row.Status)
		return
	}
	if err := d.store.CancelSchedule(r.Context(), id); errors.Is(err, persistence.ErrScheduleState) {
		writeDetail(w, http.StatusConflict, "Jadwal tidak lagi pending")
		return
	} else if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membatalkan jadwal")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"message": "Jadwal berhasil dibatalkan"})
}

func (d deps) upcomingSchedules(w http.ResponseWriter, r *http.Request) {
	if !d.activityAdmin(w, r) {
		return
	}
	limit, ok := boundedQueryInt(w, r, "limit", 20, 1, 100)
	if !ok {
		return
	}
	rows, err := d.store.ListUpcomingSchedules(r.Context(), limit)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat jadwal")
		return
	}
	out := make([]map[string]any, 0, len(rows))
	for i := range rows {
		out = append(out, scheduleJSON(&rows[i]))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) scheduleStats(w http.ResponseWriter, r *http.Request) {
	if !d.activityAdmin(w, r) {
		return
	}
	stats, err := d.store.ScheduleStats(r.Context())
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat statistik jadwal")
		return
	}
	total := 0
	for _, count := range stats {
		total += count
	}
	writeJSON(w, http.StatusOK, map[string]any{"total": total, "by_status": stats})
}

func scheduleJSON(row *persistence.ScheduleRow) map[string]any {
	return map[string]any{
		"id": row.ID, "exam_id": row.ExamID, "publish_at": row.PublishAt.UTC().Format(time.RFC3339),
		"unpublish_at": persistence.FormatTimePtr(row.UnpublishAt), "status": row.Status,
		"created_by": row.CreatedBy, "created_at": row.CreatedAt.UTC().Format(time.RFC3339),
		"executed_at": persistence.FormatTimePtr(row.ExecutedAt), "error_message": row.ErrorMessage,
	}
}
