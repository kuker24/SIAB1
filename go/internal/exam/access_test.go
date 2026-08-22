package exam

import (
	"testing"

	"siab1/internal/persistence"
)

func strp(v string) *string { return &v }

func TestStudentClassAccess(t *testing.T) {
	ex := &persistence.ExamRow{AllowedClasses: strp("XII IPA 1, XII IPA 2")}
	ok, _ := participantAccess(ex, 9, "student", "XII IPA 1")
	if !ok {
		t.Fatal("expected access")
	}
	ok, _ = participantAccess(ex, 9, "student", "X IPS")
	if ok {
		t.Fatal("expected deny")
	}
}

func TestStudentAllowList(t *testing.T) {
	ex := &persistence.ExamRow{AllowedStudents: strp("9,10")}
	ok, _ := participantAccess(ex, 9, "student", "")
	if !ok {
		t.Fatal("expected listed student")
	}
	ok, _ = participantAccess(ex, 8, "student", "XII")
	if ok {
		t.Fatal("unlisted student denied")
	}
}

func TestGuruPlusNeedsDeveloperExam(t *testing.T) {
	ex := &persistence.ExamRow{CreatorRole: strp("teacher"), AllowedClasses: strp("GuruPlus")}
	ok, _ := participantAccess(ex, 1, "guruplus", "GuruPlus")
	if ok {
		t.Fatal("guruplus should need developer creator")
	}
	ex.CreatorRole = strp("developer")
	ok, _ = participantAccess(ex, 1, "guruplus", "GuruPlus")
	if !ok {
		t.Fatal("expected guruplus access")
	}
}

func TestStaffCanViewExam(t *testing.T) {
	ex := &persistence.ExamRow{CreatorID: 4, Published: true, CreatorRole: strp("teacher")}
	if ok, hidden := staffCanViewExam(ex, 4, "teacher", ""); !ok || hidden {
		t.Fatal("owner teacher")
	}
	if ok, _ := staffCanViewExam(ex, 9, "teacher", ""); ok {
		t.Fatal("other teacher denied")
	}
	if ok, _ := staffCanViewExam(ex, 9, "teacher", "Pengawas"); !ok {
		t.Fatal("pengawas published")
	}
	ex.CreatorRole = strp("developer")
	if ok, hidden := staffCanViewExam(ex, 1, "admin", ""); ok || !hidden {
		t.Fatal("admin hidden from developer exam")
	}
}

func TestReviewStatusAndOptionLabel(t *testing.T) {
	if reviewStatus(nil, 10) != "not_answered" {
		t.Fatal("empty")
	}
	pts := 10.0
	ok := true
	if reviewStatus(&persistence.AnswerRow{Points: &pts, IsCorrect: &ok}, 10) != "correct" {
		t.Fatal("correct")
	}
	if optionLabel(0) != "A" || optionLabel(25) != "Z" || optionLabel(26) != "AA" {
		t.Fatalf("labels %s %s %s", optionLabel(0), optionLabel(25), optionLabel(26))
	}
}

func TestValidateGrade(t *testing.T) {
	answer := &persistence.GradingAnswer{SessionStatus: "submitted", MaxPoints: 5}
	if got := validateGrade(answer, 10); got != "" {
		t.Fatalf("valid upper bound: %s", got)
	}
	if got := validateGrade(answer, 10.1); got == "" {
		t.Fatal("expected upper-bound rejection")
	}
	answer.SessionStatus = "in_progress"
	if got := validateGrade(answer, 1); got == "" {
		t.Fatal("expected session rejection")
	}
}

func TestCanAssignRole(t *testing.T) {
	if canAssignRole("admin", "developer") || canAssignRole("admin", "guruplus") {
		t.Fatal("admin cannot assign privileged roles")
	}
	if !canAssignRole("developer", "guruplus") || !canAssignRole("admin", "teacher") {
		t.Fatal("expected assign")
	}
	if canManageUserAccount("admin", "developer") || !canManageUserAccount("developer", "developer") {
		t.Fatal("developer account guard")
	}
	cls := applyRoleStudentClass("guruplus", strp("XII"))
	if cls == nil || *cls != guruPlusClass {
		t.Fatal("guruplus class")
	}
}

func TestStaffCanMonitor(t *testing.T) {
	ex := &persistence.ExamRow{CreatorID: 4, Published: true}
	if !staffCanMonitor(ex, 4, "teacher", "") {
		t.Fatal("owner")
	}
	if staffCanMonitor(ex, 9, "teacher", "") {
		t.Fatal("other teacher")
	}
	if !staffCanMonitor(ex, 9, "teacher", "Pengawas") {
		t.Fatal("pengawas")
	}
}

func TestStaffCanMutateExam(t *testing.T) {
	ex := &persistence.ExamRow{CreatorID: 4, Published: true, CreatorRole: strp("teacher")}
	if ok, _, _ := staffCanMutateExam(ex, 4, "teacher", "", false); !ok {
		t.Fatal("owner")
	}
	if ok, _, _ := staffCanMutateExam(ex, 9, "teacher", "Pengawas", false); ok {
		t.Fatal("pengawas cannot publish")
	}
	if ok, _, _ := staffCanMutateExam(ex, 9, "teacher", "Pengawas", true); !ok {
		t.Fatal("pengawas unpublish")
	}
}
