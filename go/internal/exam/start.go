package exam

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

func (d deps) startExam(w http.ResponseWriter, r *http.Request) {
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
		writeDetail(w, http.StatusForbidden, "Hanya peserta ujian yang dapat mengikuti ujian")
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
	if !ex.Published {
		writeDetail(w, http.StatusBadRequest, "Ujian belum dipublikasikan")
		return
	}
	if ok, detail := participantAccess(ex, userID, claims.Role, claims.StudentClass); !ok {
		writeDetail(w, http.StatusForbidden, detail)
		return
	}
	now := time.Now().UTC()
	if now.Before(ex.StartTime.UTC()) {
		writeDetail(w, http.StatusBadRequest, "Ujian belum dimulai")
		return
	}
	if now.After(ex.EndTime.UTC()) {
		writeDetail(w, http.StatusBadRequest, "Ujian sudah berakhir")
		return
	}
	session, err := d.store.ActiveSession(r.Context(), userID, examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa sesi")
		return
	}
	if session == nil {
		done, err := d.store.CompletedAttemptCount(r.Context(), userID, examID)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa percobaan")
			return
		}
		if done >= ex.MaxAttempts {
			writeDetail(w, http.StatusBadRequest, "Batas percobaan sudah tercapai")
			return
		}
		session, err = d.store.CreateSession(r.Context(), userID, examID)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memulai sesi")
			return
		}
	}
	questions, err := d.store.LoadQuestions(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat soal")
		return
	}
	seed := fmt.Sprintf("%s_%d_%d", d.appSecret, userID, examID)
	if ex.ShuffleQuestions {
		shuffleQuestions(questions, seed+"_q")
	}
	payload := make([]map[string]any, 0, len(questions))
	for _, q := range questions {
		opts := q.Options
		if ex.ShuffleOptions {
			shuffleOptions(opts, fmt.Sprintf("%s_question_%d", seed, q.ID))
		}
		optJSON := make([]map[string]any, 0, len(opts))
		for _, o := range opts {
			item := map[string]any{
				"id":           o.ID,
				"option_text":  o.Text,
				"order_index":  o.OrderIndex,
				"option_group": o.OptionGroup,
				"pair_id":      o.PairID,
			}
			optJSON = append(optJSON, item)
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
			"question_settings": persistence.SanitizeSettings(q.Settings),
			"points":            q.Points,
			"order_index":       q.OrderIndex,
			"image_url":         q.ImageURL,
			"video_url":         q.VideoURL,
			"audio_url":         q.AudioURL,
			"options":           optJSON,
		})
	}
	poll, _ := auth.SessionPollToken(d.secret, session.ID, userID)
	teacher := any(nil)
	if ex.ShowTeacherName && ex.TeacherName != nil {
		teacher = *ex.TeacherName
	}
	end := session.StartTime.UTC().Add(time.Duration(ex.DurationMinutes) * time.Minute)
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id":                         session.ID,
		"exam_id":                            ex.ID,
		"exam_title":                         ex.Title,
		"duration_minutes":                   ex.DurationMinutes,
		"question_count":                     len(payload),
		"start_time":                         session.StartTime.UTC().Format(time.RFC3339),
		"end_time":                           end.Format(time.RFC3339),
		"server_time":                        now.Format(time.RFC3339),
		"show_results":                       ex.ShowResults,
		"show_teacher_name":                  ex.ShowTeacherName,
		"teacher_name":                       teacher,
		"subject":                            ex.Subject,
		"exam_type":                          ex.ExamType,
		"shuffle_questions":                  ex.ShuffleQuestions,
		"shuffle_options":                    ex.ShuffleOptions,
		"session_poll_token":                 poll,
		"session_poll_token_expires_minutes": 15,
		"questions":                          payload,
	})
}

func (d deps) remainingTime(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	sessionID, err := strconv.Atoi(r.PathValue("session_id"))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id tidak valid")
		return
	}
	row, err := d.store.TimerSession(r.Context(), sessionID, userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat timer")
		return
	}
	if row == nil {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	elapsed, remaining, total, expired := timerParts(row)
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id":        sessionID,
		"remaining_seconds": remaining,
		"elapsed_seconds":   elapsed,
		"total_seconds":     total,
		"started_at":        row.StartTime.UTC().Format(time.RFC3339),
		"is_expired":        expired,
	})
}

func (d deps) me(w http.ResponseWriter, r *http.Request) {
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	u, err := d.store.GetUser(r.Context(), userID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat profil")
		return
	}
	if u == nil {
		writeDetail(w, http.StatusUnauthorized, "Pengguna tidak ditemukan")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"id":              u.ID,
		"username":        u.Username,
		"full_name":       u.FullName,
		"role":            u.Role,
		"student_class":   u.StudentClass,
		"is_active":       u.IsActive,
		"created_at":      u.CreatedAt.UTC().Format(time.RFC3339),
		"last_login":      u.LastLogin,
		"profile_picture": u.ProfilePic,
		"job_title":       u.JobTitle,
	})
}

func (d deps) runtimePolicy(w http.ResponseWriter, r *http.Request) {
	mode := "normal"
	if d.examPeak {
		mode = "exam_peak"
	}
	interval := 15
	batch := 30
	poll := 25
	flush := 30
	retry := 8
	if mode == "exam_peak" {
		interval, batch, poll, flush = 45, 50, 60, 120
	}
	w.Header().Set("Cache-Control", "no-store, max-age=0")
	w.Header().Set("X-Runtime-Policy-Version", "20260606-mobile-runtime-adaptive-v2")
	writeJSON(w, http.StatusOK, map[string]any{
		"answer_sync_interval_seconds":      interval,
		"answer_sync_batch_size":            batch,
		"command_poll_seconds":              poll,
		"violation_flush_seconds":           flush,
		"retry_after_seconds":               retry,
		"mode":                              mode,
		"cheating_detection_enabled":        true,
		"cheating_detail_level":             "aggregate",
		"cheating_reporting_mode":           "normal",
		"disabled_violation_types":          []any{},
		"force_submit_on_violation_enabled": true,
		"final_submit_priority":             true,
		"server_time":                       time.Now().UTC().Format(time.RFC3339),
		"policy_version":                    "20260606-mobile-runtime-adaptive-v2",
		"source":                            "server_runtime_policy",
	})
}

func shuffleQuestions(items []persistence.QuestionRow, seed string) {
	rnd := seeded(seed)
	for i := len(items) - 1; i > 0; i-- {
		j := int(rnd.Uint32() % uint32(i+1))
		items[i], items[j] = items[j], items[i]
	}
}

func shuffleOptions(items []persistence.OptionRow, seed string) {
	rnd := seeded(seed)
	for i := len(items) - 1; i > 0; i-- {
		j := int(rnd.Uint32() % uint32(i+1))
		items[i], items[j] = items[j], items[i]
	}
}

type rng struct{ s uint64 }

func seeded(seed string) *rng {
	sum := sha256.Sum256([]byte(seed))
	return &rng{s: binary.BigEndian.Uint64(sum[:8])}
}

func (r *rng) Uint32() uint32 {
	r.s = r.s*1664525 + 1013904223
	return uint32(r.s >> 32)
}
