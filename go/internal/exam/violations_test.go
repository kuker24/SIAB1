package exam

import (
	"testing"
	"time"

	"siab1/internal/persistence"
)

func TestBuildViolationsPayload(t *testing.T) {
	now := time.Now().UTC()
	rows := []persistence.ViolationRow{
		{ID: 1, SessionID: 2, ExamID: 3, ExamTitle: "Ujian", UserID: 4,
			Name: "Siswa", Username: "siswa", EventType: "violation_tab_switch", CreatedAt: now},
		{ID: 2, SessionID: 2, ExamID: 3, ExamTitle: "Ujian", UserID: 4,
			Name: "Siswa", Username: "siswa", EventType: "violation_copy", CreatedAt: now},
	}
	payload := buildViolationsPayload(rows, 3, now.Add(-time.Hour), now)
	if payload["total_violations"] != 2 || payload["unique_offender_count"] != 1 {
		t.Fatalf("payload=%v", payload)
	}
	if payload["average_per_session"] != 2.0 {
		t.Fatalf("average=%v", payload["average_per_session"])
	}
}
