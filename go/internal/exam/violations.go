package exam

import (
	"encoding/json"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"siab1/internal/persistence"
)

type violationMeta struct{ Label, Severity, Category, Description string }

var violationMetadata = map[string]violationMeta{
	"tab_switch":         {"Pindah Tab", "medium", "browser", "Berpindah tab atau aplikasi saat ujian berlangsung."},
	"focus_lost":         {"Fokus Hilang", "medium", "browser", "Jendela ujian kehilangan fokus."},
	"copy":               {"Copy", "high", "clipboard", "Percobaan menyalin teks."},
	"paste":              {"Paste", "high", "clipboard", "Percobaan menempelkan teks."},
	"cut":                {"Cut", "medium", "clipboard", "Percobaan memotong teks."},
	"right_click":        {"Klik Kanan", "low", "browser", "Percobaan klik kanan."},
	"devtools_open":      {"Developer Tools", "critical", "browser", "Percobaan membuka developer tools."},
	"screenshot_attempt": {"Screenshot", "high", "capture", "Percobaan mengambil tangkapan layar."},
	"overlay_app":        {"Overlay App", "critical", "mobile", "Aplikasi overlay terdeteksi."},
	"screen_recording":   {"Rekam Layar", "critical", "mobile", "Perekaman layar aktif."},
	"external_display":   {"Display Eksternal", "high", "mobile", "Display eksternal terdeteksi."},
	"apk_tampering":      {"APK Dimodifikasi", "critical", "mobile", "APK tidak resmi terdeteksi."},
}

func (d deps) violationsDashboard(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	detailLevel := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("detail_level")))
	if detailLevel == "" {
		detailLevel = "auto"
	}
	if detailLevel != "auto" && detailLevel != "summary" && detailLevel != "detail" {
		writeDetail(w, http.StatusBadRequest, "detail_level harus auto, summary, atau detail")
		return
	}
	examID := 0
	if raw := r.URL.Query().Get("exam_id"); raw != "" {
		var err error
		examID, err = strconv.Atoi(raw)
		if err != nil || examID <= 0 {
			writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
			return
		}
		r.SetPathValue("exam_id", strconv.Itoa(examID))
		if _, ok := d.loadResultsExam(w, r, userID, claims); !ok {
			return
		}
	}
	from, to, ok := violationDateRange(w, r)
	if !ok {
		return
	}
	ownerID, hideDeveloper := 0, false
	if claims.Role == "teacher" {
		ownerID = userID
	} else if claims.Role == "admin" {
		hideDeveloper = true
	}
	rows, err := d.store.ListViolations(r.Context(), examID, ownerID, hideDeveloper, from, to,
		strings.EqualFold(r.URL.Query().Get("counted_only"), "true"))
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat pelanggaran")
		return
	}
	payload := buildViolationsPayload(rows, examID, from, to)
	if detailLevel == "summary" || strings.EqualFold(r.URL.Query().Get("summary_only"), "true") {
		payload["aggregate_only"] = true
		payload["violations"] = []map[string]any{}
	}
	if examID > 0 {
		if ex, _ := d.store.GetExam(r.Context(), examID); ex != nil {
			payload["selected_exam_title"] = ex.Title
		}
	}
	writeJSON(w, http.StatusOK, payload)
}

func buildViolationsPayload(rows []persistence.ViolationRow, examID int, from, to time.Time) map[string]any {
	byType, timeline := map[string]int{}, map[string]int{}
	sessions, exams := map[int]struct{}{}, map[int]struct{}{}
	typeUsers := map[string]map[int]struct{}{}
	offenders := map[int]map[string]any{}
	records := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		typeName := strings.TrimPrefix(strings.ToLower(row.EventType), "violation_")
		meta, exists := violationMetadata[typeName]
		if !exists {
			meta = violationMeta{strings.ReplaceAll(strings.Title(strings.ReplaceAll(typeName, "_", " ")), " ", " "), "medium", "lainnya", "Aktivitas tidak wajar terdeteksi."}
		}
		data := map[string]any{}
		_ = json.Unmarshal(row.EventData, &data)
		created := row.CreatedAt.UTC().Format(time.RFC3339)
		display := row.CreatedAt.In(wib).Format("02 Jan 2006 15:04 WIB")
		record := map[string]any{
			"id": row.ID, "exam_id": row.ExamID, "exam_title": row.ExamTitle,
			"exam_session_id": row.SessionID, "session_id": row.SessionID,
			"user_id": row.UserID, "name": row.Name, "username": row.Username, "class": row.Class,
			"event_type": "violation_" + typeName, "violation_type": typeName,
			"label": meta.Label, "severity": meta.Severity, "category": meta.Category,
			"description": meta.Description, "message": row.Name + " melakukan " + meta.Label,
			"detail_summary": "-", "source": stringValue(data["source"], "unknown"),
			"created_at": created, "created_at_display": display, "event_data": data,
			"counted_for_score": boolValue(data["counted_for_score"], true),
		}
		records = append(records, record)
		byType[typeName]++
		timeline[row.CreatedAt.In(wib).Format("2006-01-02 15:00")]++
		sessions[row.SessionID] = struct{}{}
		exams[row.ExamID] = struct{}{}
		if typeUsers[typeName] == nil {
			typeUsers[typeName] = map[int]struct{}{}
		}
		typeUsers[typeName][row.UserID] = struct{}{}
		bucket := offenders[row.UserID]
		if bucket == nil {
			bucket = map[string]any{"user_id": row.UserID, "name": row.Name, "username": row.Username,
				"class": row.Class, "count": 0, "exam_titles": []string{}, "recent_violations": []map[string]any{}}
			offenders[row.UserID] = bucket
		}
		bucket["count"] = bucket["count"].(int) + 1
		recent := bucket["recent_violations"].([]map[string]any)
		if len(recent) < 4 {
			bucket["recent_violations"] = append(recent, map[string]any{
				"created_at": created, "created_at_display": display, "label": meta.Label,
				"violation_type": typeName, "severity": meta.Severity, "exam_title": row.ExamTitle,
			})
		}
	}
	top := make([]map[string]any, 0, len(offenders))
	for _, item := range offenders {
		top = append(top, item)
	}
	sort.Slice(top, func(i, j int) bool { return top[i]["count"].(int) > top[j]["count"].(int) })
	typeBreakdown := make([]map[string]any, 0, len(byType))
	typeDetails := map[string]any{}
	for name, count := range byType {
		meta := violationMetadata[name]
		if meta.Label == "" {
			meta = violationMeta{name, "medium", "lainnya", "Aktivitas tidak wajar terdeteksi."}
		}
		detail := map[string]any{"label": meta.Label, "severity": meta.Severity, "category": meta.Category, "description": meta.Description}
		typeDetails[name] = detail
		typeBreakdown = append(typeBreakdown, map[string]any{
			"violation_type": name, "label": meta.Label, "severity": meta.Severity,
			"category": meta.Category, "description": meta.Description, "count": count,
			"offender_count": len(typeUsers[name]), "offenders": []map[string]any{}, "recent_violations": []map[string]any{},
		})
	}
	sort.Slice(typeBreakdown, func(i, j int) bool { return typeBreakdown[i]["count"].(int) > typeBreakdown[j]["count"].(int) })
	average := 0.0
	if len(sessions) > 0 {
		average = roundTwo(float64(len(records)) / float64(len(sessions)))
	}
	now := time.Now()
	return map[string]any{
		"total_violations": len(records), "by_type": byType, "type_details": typeDetails,
		"type_breakdown": typeBreakdown, "top_offenders": firstMaps(top, 10), "offender_details": top,
		"unique_offender_count": len(offenders), "timeline": timeline, "violations": records,
		"unique_exam_count": len(exams), "affected_session_count": len(sessions), "average_per_session": average,
		"selected_exam_title": nil, "date_range_label": from.In(wib).Format("02 Jan 2006") + " - " + to.In(wib).Format("02 Jan 2006"),
		"generated_at": now.UTC().Format(time.RFC3339), "generated_at_display": now.In(wib).Format("02 Jan 2006 15:04 WIB"),
		"aggregate_only": false, "filters": map[string]any{"exam_id": examID, "date_from": from.Format(time.RFC3339), "date_to": to.Format(time.RFC3339)},
	}
}

func violationDateRange(w http.ResponseWriter, r *http.Request) (time.Time, time.Time, bool) {
	from, to := time.Now().AddDate(0, 0, -7), time.Now()
	for name, target := range map[string]*time.Time{"date_from": &from, "date_to": &to} {
		raw := r.URL.Query().Get(name)
		if raw == "" {
			continue
		}
		parsed, err := time.Parse(time.RFC3339, raw)
		if err != nil {
			parsed, err = time.ParseInLocation("2006-01-02", raw, wib)
		}
		if err != nil {
			writeDetail(w, http.StatusUnprocessableEntity, name+" tidak valid")
			return time.Time{}, time.Time{}, false
		}
		*target = parsed
	}
	return from.UTC(), to.UTC(), true
}

func firstMaps(values []map[string]any, limit int) []map[string]any {
	if len(values) <= limit {
		return values
	}
	return values[:limit]
}

func stringValue(value any, fallback string) string {
	if text, ok := value.(string); ok && strings.TrimSpace(text) != "" {
		return text
	}
	return fallback
}

func boolValue(value any, fallback bool) bool {
	switch v := value.(type) {
	case bool:
		return v
	case string:
		if parsed, err := strconv.ParseBool(v); err == nil {
			return parsed
		}
	}
	return fallback
}
