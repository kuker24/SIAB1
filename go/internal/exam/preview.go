package exam

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"
)

func (d deps) previewExam(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadStaffExam(w, r, userID, claims, false)
	if !ok {
		return
	}
	simulate := truthy(r.URL.Query().Get("simulate_student_shuffle"))
	questions, err := d.store.LoadQuestions(r.Context(), ex.ID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat soal")
		return
	}
	seed := ""
	if simulate {
		seed = d.appSecret + "_" + strconv.Itoa(userID) + "_" + strconv.Itoa(ex.ID)
		if ex.ShuffleQuestions {
			shuffleQuestions(questions, seed+"_q")
		}
	}
	payload := make([]map[string]any, 0, len(questions))
	for _, q := range questions {
		settings := settingsMap(q.Settings)
		pgk := "checkbox"
		if q.PgkType != nil && *q.PgkType != "" {
			pgk = *q.PgkType
		} else if v, ok := settings["pgk_type"].(string); ok && v != "" {
			pgk = v
		}
		table := q.Type == "multiple_choice_complex" && pgk == "table_validation"
		if table {
			if _, ok := settings["allow_table_statement_shuffle"]; !ok {
				settings["allow_table_statement_shuffle"] = true
			}
		}
		needOpts := !table && (q.Type == "multiple_choice" || q.Type == "multiple_choice_complex" || q.Type == "true_false")
		opts := q.Options
		hasImage := q.ImageURL != nil && *q.ImageURL != ""
		if simulate && ex.ShuffleOptions && needOpts && canShuffleOptions(settings, hasImage) {
			shuffleOptions(opts, seed+"_question_"+strconv.Itoa(q.ID))
		}
		optJSON := make([]map[string]any, 0, len(opts))
		if needOpts {
			for _, o := range opts {
				optJSON = append(optJSON, map[string]any{
					"id":           o.ID,
					"option_text":  o.Text,
					"order_index":  o.OrderIndex,
					"option_group": o.OptionGroup,
					"pair_id":      o.PairID,
				})
			}
		}
		payload = append(payload, map[string]any{
			"id":                q.ID,
			"question_text":     q.Text,
			"stimulus":          q.Stimulus,
			"question_type":     q.Type,
			"pgk_type":          q.PgkType,
			"difficulty_level":  q.Difficulty,
			"category":          nil,
			"tags":              []any{},
			"question_settings": settings,
			"points":            q.Points,
			"order_index":       q.OrderIndex,
			"image_url":         q.ImageURL,
			"video_url":         q.VideoURL,
			"audio_url":         q.AudioURL,
			"options":           optJSON,
		})
	}
	title := "[PREVIEW] " + ex.Title
	if simulate {
		title = "[SIMULASI SISWA] " + ex.Title
	}
	now := time.Now().UTC()
	end := now.Add(time.Duration(ex.DurationMinutes) * time.Minute)
	teacher := any(nil)
	if ex.ShowTeacherName && ex.TeacherName != nil {
		teacher = *ex.TeacherName
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id":        0,
		"exam_id":           ex.ID,
		"exam_title":        title,
		"duration_minutes":  ex.DurationMinutes,
		"question_count":    len(payload),
		"start_time":        now.Format(time.RFC3339),
		"end_time":          end.Format(time.RFC3339),
		"server_time":       now.Format(time.RFC3339),
		"show_results":      ex.ShowResults,
		"show_teacher_name": ex.ShowTeacherName,
		"teacher_name":      teacher,
		"subject":           ex.Subject,
		"exam_type":         ex.ExamType,
		"shuffle_questions": ex.ShuffleQuestions,
		"shuffle_options":   ex.ShuffleOptions,
		"questions":         payload,
	})
}

func (d deps) duplicateExam(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadStaffExam(w, r, userID, claims, false)
	if !ok {
		return
	}
	include := !strings.EqualFold(r.URL.Query().Get("include_questions"), "false")
	copied, err := d.store.DuplicateExam(r.Context(), ex.ID, userID, include)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menduplikasi ujian")
		return
	}
	writeJSON(w, http.StatusOK, examJSON(copied))
}

func (d deps) regenerateToken(w http.ResponseWriter, r *http.Request) {
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
		writeDetail(w, http.StatusForbidden, "Pengawas hanya dapat refresh token untuk ujian yang sedang/published.")
		return
	}
	updated, err := d.store.RegenerateAccessToken(r.Context(), ex.ID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal generate token baru")
		return
	}
	writeJSON(w, http.StatusOK, examJSON(updated))
}

func settingsMap(raw []byte) map[string]any {
	out := map[string]any{}
	if len(raw) == 0 {
		return out
	}
	_ = json.Unmarshal(raw, &out)
	return out
}

func canShuffleOptions(settings map[string]any, hasImage bool) bool {
	placeholder, _ := settings["is_placeholder"].(bool)
	if !placeholder {
		return true
	}
	if hasImage {
		return false
	}
	src, _ := settings["placeholder_source"].(string)
	if strings.EqualFold(strings.TrimSpace(src), "image") {
		return false
	}
	allow, _ := settings["allow_placeholder_shuffle"].(bool)
	return allow
}

func truthy(v string) bool {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}
