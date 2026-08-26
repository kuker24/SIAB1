package exam

import (
	"crypto/sha256"
	"encoding/binary"
	"net/http"
	"strconv"
	"time"

	"siab1/internal/persistence"
)

func (d deps) startExam(w http.ResponseWriter, r *http.Request) {
	d.proxyExamWrite(w, r)
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
