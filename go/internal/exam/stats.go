package exam

import (
	"net/http"
	"time"

	"siab1/internal/persistence"
)

func (d deps) dashboardStats(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	role := claims.Role
	counts, err := d.store.DashboardCounts(r.Context(), userID, role)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat statistik")
		return
	}
	if isAdminScope(role) {
		n, err := d.store.CountAllUsers(r.Context())
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memuat statistik")
			return
		}
		counts.TotalUsers = n
	}
	if role == "student" || role == "guruplus" {
		counts.DraftExams = 0
	}
	recent := []map[string]any{}
	if role == "teacher" || isAdminScope(role) {
		rows, err := d.store.RecentExams(r.Context(), userID, role, 5)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian terbaru")
			return
		}
		recent = recentJSON(rows)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"total_users": counts.TotalUsers, "total_exams": counts.TotalExams,
		"published_exams": counts.PublishedExams, "draft_exams": counts.DraftExams,
		"active_sessions": counts.ActiveSessions, "completed_today": counts.CompletedToday,
		"upcoming_exams": counts.UpcomingExams, "recent_exams": recent,
	})
}

func recentJSON(rows []persistence.RecentExam) []map[string]any {
	out := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, map[string]any{
			"id": row.ID, "title": row.Title, "duration_minutes": row.DurationMinutes,
			"start_time":   row.StartTime.UTC().Format(time.RFC3339),
			"end_time":     row.EndTime.UTC().Format(time.RFC3339),
			"is_published": row.Published,
		})
	}
	return out
}
