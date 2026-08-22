package exam

import (
	"testing"

	"siab1/internal/persistence"
)

func TestEvaluateSessionRecovery(t *testing.T) {
	rec := evaluateSessionRecovery("in_progress", false, 0, nil)
	if !rec.AllowContinue || rec.Category != "network_issue" {
		t.Fatalf("%+v", rec)
	}
	rec = evaluateSessionRecovery("terminated", true, 0, nil)
	if rec.AllowContinue || rec.Category != "admin_decision" {
		t.Fatalf("%+v", rec)
	}
	rec = evaluateSessionRecovery("submitted", false, 0, []persistence.SessionLog{{EventType: "FORCE_SUBMIT_BY_TEACHER"}})
	if rec.AllowContinue || rec.Category != "admin_decision" {
		t.Fatalf("%+v", rec)
	}
	rec = evaluateSessionRecovery("terminated", false, 0, nil)
	if !rec.AllowContinue || rec.Category != "network_issue" {
		t.Fatalf("%+v", rec)
	}
}
