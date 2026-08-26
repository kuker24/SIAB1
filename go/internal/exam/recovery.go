package exam

import (
	"encoding/json"
	"strings"

	"siab1/internal/persistence"
)

const autoSubmitViolationThreshold = 8

type recoveryResult struct {
	Category      string
	AllowContinue bool
	Message       string
}

func evaluateSessionRecovery(status string, terminated bool, violations int, logs []persistence.SessionLog) recoveryResult {
	status = strings.ToLower(strings.TrimSpace(status))
	admin := terminated || containsAdminDecision(logs)
	cheat := containsCheatingSubmit(logs) || violations >= autoSubmitViolationThreshold
	switch status {
	case "submitted", "completed":
		if containsAdminDecision(logs) {
			return recoveryResult{"admin_decision", false, "Sesi dikumpulkan/dihentikan oleh pengawas. Siswa tidak boleh melanjutkan."}
		}
		if cheat {
			return recoveryResult{"cheating_detected", false, "Sesi dihentikan karena pelanggaran. Siswa tidak boleh melanjutkan."}
		}
		cat := "session_submitted"
		if status == "completed" {
			cat = "session_completed"
		}
		return recoveryResult{cat, false, "Sesi sudah selesai/dikumpulkan."}
	case "terminated", "kicked":
		if admin {
			return recoveryResult{"admin_decision", false, "Sesi dihentikan oleh pengawas/admin. Siswa tidak boleh melanjutkan."}
		}
		if containsCheatingSubmit(logs) {
			return recoveryResult{"cheating_detected", false, "Sesi dihentikan karena pelanggaran. Siswa tidak boleh melanjutkan."}
		}
		return recoveryResult{"network_issue", true, "Sesi dihentikan karena kendala koneksi. Siswa boleh melanjutkan dari jawaban terakhir."}
	case "in_progress", "active", "paused":
		return recoveryResult{"network_issue", true, "Sesi aktif dan dapat dilanjutkan."}
	default:
		return recoveryResult{"unknown", false, "Sesi tidak dikenali. Perlu pemeriksaan admin."}
	}
}

func blocksReplacementSession(session *persistence.SessionRow, logs []persistence.SessionLog) bool {
	if session == nil {
		return false
	}
	recovery := evaluateSessionRecovery(
		session.Status,
		session.TerminatedByAdmin,
		session.ViolationCount,
		logs,
	)
	return recovery.Category == "admin_decision" && !recovery.AllowContinue
}

func containsAdminDecision(logs []persistence.SessionLog) bool {
	for _, log := range logs {
		switch strings.ToUpper(strings.TrimSpace(log.EventType)) {
		case "FORCE_SUBMIT_BY_TEACHER", "SESSION_TERMINATED", "ADMIN_KICK_STUDENT", "SESSION_FORCE_KICK":
			return true
		}
	}
	return false
}

func containsCheatingSubmit(logs []persistence.SessionLog) bool {
	for _, log := range logs {
		ev := strings.ToUpper(strings.TrimSpace(log.EventType))
		if ev == "AUTO_SUBMIT_VIOLATION" {
			return true
		}
		if ev == "EXAM_SUBMIT" || ev == "EXAM_SUBMITTED" {
			var data map[string]any
			if json.Unmarshal(log.Data, &data) == nil {
				if v, ok := data["force_submit"].(bool); ok && v {
					return true
				}
			}
		}
	}
	return false
}

func deriveSubmitMode(logs []persistence.SessionLog) string {
	for _, log := range logs {
		ev := strings.ToUpper(strings.TrimSpace(log.EventType))
		if ev == "AUTO_SUBMIT_VIOLATION" {
			return "auto_violation"
		}
		if ev == "EXAM_SUBMIT" || ev == "EXAM_SUBMITTED" {
			var data map[string]any
			if json.Unmarshal(log.Data, &data) == nil {
				if v, ok := data["force_submit"].(bool); ok && v {
					return "force_submit"
				}
			}
			return "user_submit"
		}
		if ev == "FORCE_SUBMIT_BY_TEACHER" {
			return "admin_force_submit"
		}
	}
	return "unknown"
}

func deriveReasonBucket(status, category, submitMode string) string {
	switch strings.ToLower(category) {
	case "network_issue":
		return "network_issue"
	case "cheating_detected":
		return "cheating_detected"
	case "admin_decision":
		return "admin_decision"
	}
	switch strings.ToLower(submitMode) {
	case "user_submit":
		return "user_submit"
	case "auto_violation", "force_submit":
		return "cheating_detected"
	case "admin_force_submit":
		return "admin_decision"
	}
	st := strings.ToLower(status)
	if st == "submitted" || st == "completed" {
		return "user_submit"
	}
	return "unknown"
}

var recoveryReasonLabels = map[string]string{
	"network_issue":     "Gangguan jaringan / koneksi",
	"cheating_detected": "Pelanggaran / auto-submit",
	"admin_decision":    "Keputusan pengawas/admin",
	"user_submit":       "Submit normal oleh siswa",
	"unknown":           "Perlu verifikasi admin",
}

var recoveryReasonSort = map[string]int{
	"network_issue":     0,
	"unknown":           1,
	"cheating_detected": 2,
	"admin_decision":    3,
	"user_submit":       4,
}
