package exam

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"siab1/internal/persistence"
)

var wib = time.FixedZone("WIB", 7*60*60)

func (d deps) activityLogs(w http.ResponseWriter, r *http.Request) {
	if !d.activityAdmin(w, r) {
		return
	}
	page, ok := boundedQueryInt(w, r, "page", 1, 1, 0)
	if !ok {
		return
	}
	perPage, ok := boundedQueryInt(w, r, "per_page", 50, 1, 200)
	if !ok {
		return
	}
	userID, _ := strconv.Atoi(r.URL.Query().Get("user_id"))
	dateFrom, ok := optionalQueryTime(w, r, "date_from")
	if !ok {
		return
	}
	dateTo, ok := optionalQueryTime(w, r, "date_to")
	if !ok {
		return
	}
	rows, total, err := d.store.ListActivity(r.Context(), persistence.ActivityFilter{
		UserID: userID, EventType: r.URL.Query().Get("event_type"), DateFrom: dateFrom, DateTo: dateTo,
		Limit: perPage, Offset: (page - 1) * perPage,
	})
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat log aktivitas")
		return
	}
	logs := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		data := map[string]any{}
		_ = json.Unmarshal(row.EventData, &data)
		logs = append(logs, map[string]any{
			"id": row.ID, "user_id": row.UserID, "user_name": row.UserName,
			"user_role": row.UserRole, "event_type": row.EventType, "event_data": data,
			"ip_address": row.IPAddress, "created_at": row.CreatedAt.In(wib).Format("2006-01-02T15:04:05-07:00"),
		})
	}
	pages := 0
	if total > 0 {
		pages = (total + perPage - 1) / perPage
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"logs": logs, "total": total, "page": page, "per_page": perPage, "total_pages": pages,
	})
}

func (d deps) activityStats(w http.ResponseWriter, r *http.Request) {
	if !d.activityAdmin(w, r) {
		return
	}
	days, ok := boundedQueryInt(w, r, "days", 7, 1, 90)
	if !ok {
		return
	}
	startWIB := time.Now().In(wib).AddDate(0, 0, -days)
	row, err := d.store.ActivityStats(r.Context(), startWIB.UTC())
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat statistik aktivitas")
		return
	}
	byType := map[string]int{}
	for _, item := range row.ByType {
		byType[item.Name] = item.Count
	}
	byDay := map[string]int{}
	for _, item := range row.ByDay {
		byDay[item.Name] = item.Count
	}
	daily := make([]map[string]any, 0, days)
	for i := 0; i < days; i++ {
		day := startWIB.AddDate(0, 0, i).Format("2006-01-02")
		daily = append(daily, map[string]any{"date": day, "count": byDay[day]})
	}
	top := make([]map[string]any, 0, len(row.TopUsers))
	for _, item := range row.TopUsers {
		top = append(top, map[string]any{
			"user_id": item.UserID, "user_name": item.UserName, "activity_count": item.Count,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"period_days": days, "total_activities": row.Total, "by_type": byType,
		"daily_trend": daily, "top_users": top,
	})
}

func (d deps) resetActivityLogs(w http.ResponseWriter, r *http.Request) {
	if !d.activityAdmin(w, r) {
		return
	}
	mode := r.URL.Query().Get("mode")
	if mode == "" {
		mode = "all"
	}
	if mode != "all" && mode != "smart" {
		writeDetail(w, http.StatusUnprocessableEntity, "mode tidak valid")
		return
	}
	retention, ok := boundedQueryInt(w, r, "retention_days", 14, 1, 3650)
	if !ok {
		return
	}
	maxRows, ok := boundedQueryInt(w, r, "max_rows", 50000, 1000, 1000000)
	if !ok {
		return
	}
	before, deleted, remaining, err := d.store.ResetActivity(r.Context(), mode, retention, maxRows)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mereset log aktivitas")
		return
	}
	message := "All activity logs were reset"
	if mode == "smart" {
		message = "Activity logs cleaned up using smart prune"
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"mode": mode, "deleted_total": deleted, "before_total": before,
		"remaining_total": remaining, "message": message,
	})
}

func (d deps) activityAdmin(w http.ResponseWriter, r *http.Request) bool {
	_, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return false
	}
	if !isAdminScope(claims.Role) {
		writeDetail(w, http.StatusForbidden, "Akses admin diperlukan")
		return false
	}
	return true
}

func boundedQueryInt(w http.ResponseWriter, r *http.Request, name string, fallback, minValue, maxValue int) (int, bool) {
	value := fallback
	if raw := r.URL.Query().Get(name); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil {
			writeDetail(w, http.StatusUnprocessableEntity, name+" tidak valid")
			return 0, false
		}
		value = parsed
	}
	if value < minValue || (maxValue > 0 && value > maxValue) {
		writeDetail(w, http.StatusUnprocessableEntity, name+" tidak valid")
		return 0, false
	}
	return value, true
}

func optionalQueryTime(w http.ResponseWriter, r *http.Request, name string) (*time.Time, bool) {
	raw := r.URL.Query().Get(name)
	if raw == "" {
		return nil, true
	}
	value, err := time.Parse(time.RFC3339, raw)
	if err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, name+" tidak valid")
		return nil, false
	}
	return &value, true
}
