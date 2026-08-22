package exam

import (
	"strings"

	"siab1/internal/persistence"
)

func parseCSV(raw *string, upper bool) map[string]struct{} {
	out := map[string]struct{}{}
	if raw == nil {
		return out
	}
	for _, part := range strings.Split(*raw, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if upper {
			part = strings.ToUpper(part)
		}
		out[part] = struct{}{}
	}
	return out
}

func studentHasAccess(ex *persistence.ExamRow, userID int, studentClass string) bool {
	students := parseCSV(ex.AllowedStudents, false)
	if _, ok := students[itoa(userID)]; ok {
		return true
	}
	classes := parseCSV(ex.AllowedClasses, true)
	if len(classes) > 0 {
		sc := strings.ToUpper(strings.TrimSpace(studentClass))
		_, ok := classes[sc]
		return ok
	}
	if len(students) > 0 {
		return false
	}
	return true
}

func guruPlusHasAccess(ex *persistence.ExamRow, userID int, studentClass, creatorRole string) bool {
	if strings.ToLower(strings.TrimSpace(creatorRole)) != "developer" {
		return false
	}
	students := parseCSV(ex.AllowedStudents, false)
	if _, ok := students[itoa(userID)]; ok {
		return true
	}
	classes := parseCSV(ex.AllowedClasses, true)
	sc := strings.TrimSpace(studentClass)
	if sc == "" {
		return false
	}
	_, ok := classes[strings.ToUpper(sc)]
	return ok
}

func participantAccess(ex *persistence.ExamRow, userID int, role, studentClass string) (ok bool, detail string) {
	role = strings.ToLower(strings.TrimSpace(role))
	creator := ""
	if ex.CreatorRole != nil {
		creator = *ex.CreatorRole
	}
	switch role {
	case "student":
		if studentHasAccess(ex, userID, studentClass) {
			return true, ""
		}
		if ex.AllowedClasses != nil && strings.TrimSpace(*ex.AllowedClasses) != "" {
			cls := studentClass
			if cls == "" {
				cls = "belum diatur"
			}
			return false, "Kelas Anda (" + cls + ") tidak diizinkan mengikuti ujian ini"
		}
		return false, "Anda tidak termasuk peserta yang diizinkan untuk ujian ini"
	case "guruplus":
		if guruPlusHasAccess(ex, userID, studentClass, creator) {
			return true, ""
		}
		if strings.ToLower(strings.TrimSpace(creator)) != "developer" {
			return false, "Akun GuruPlus hanya dapat mengikuti ujian yang dibuat developer."
		}
		return false, "Akun GuruPlus hanya dapat mengikuti ujian yang ditargetkan ke kelas GuruPlus atau ditambahkan sebagai peserta khusus."
	default:
		return false, "Role akun tidak diizinkan mengikuti ujian peserta."
	}
}

func creatorRole(ex *persistence.ExamRow) string {
	if ex == nil || ex.CreatorRole == nil {
		return ""
	}
	return strings.ToLower(strings.TrimSpace(*ex.CreatorRole))
}

func developerExamHidden(viewerRole, creator string) bool {
	return strings.ToLower(strings.TrimSpace(creator)) == "developer" &&
		strings.ToLower(strings.TrimSpace(viewerRole)) != "developer"
}

func isAdminScope(role string) bool {
	switch strings.ToLower(strings.TrimSpace(role)) {
	case "admin", "developer":
		return true
	default:
		return false
	}
}

func canAssignRole(actor, target string) bool {
	actor = strings.ToLower(strings.TrimSpace(actor))
	target = strings.ToLower(strings.TrimSpace(target))
	if target == "" {
		return true
	}
	if (target == "developer" || target == "guruplus") && actor != "developer" {
		return false
	}
	return isAdminScope(actor)
}

func canManageUserAccount(actor, target string) bool {
	if !isAdminScope(actor) {
		return false
	}
	if strings.ToLower(strings.TrimSpace(target)) == "developer" &&
		strings.ToLower(strings.TrimSpace(actor)) != "developer" {
		return false
	}
	return true
}

func applyRoleStudentClass(role string, studentClass *string) *string {
	role = strings.ToLower(strings.TrimSpace(role))
	var cls *string
	if studentClass != nil {
		trimmed := strings.TrimSpace(*studentClass)
		if trimmed != "" {
			cls = &trimmed
		}
	}
	if role == "guruplus" {
		name := guruPlusClass
		return &name
	}
	if (role == "teacher" || role == "admin" || role == "developer") &&
		cls != nil && strings.EqualFold(*cls, guruPlusClass) {
		return nil
	}
	return cls
}

func staffCanViewExam(ex *persistence.ExamRow, userID int, role, jobTitle string) (ok bool, hidden bool) {
	role = strings.ToLower(strings.TrimSpace(role))
	if developerExamHidden(role, creatorRole(ex)) {
		return false, true
	}
	switch role {
	case "developer", "admin":
		return true, false
	case "teacher":
		if isPengawas(role, jobTitle) {
			return ex.Published, false
		}
		return ex.CreatorID == userID, false
	default:
		return false, false
	}
}

func staffCanMonitor(ex *persistence.ExamRow, userID int, role, jobTitle string) bool {
	role = strings.ToLower(strings.TrimSpace(role))
	switch role {
	case "developer", "admin":
		return true
	case "teacher":
		if isPengawas(role, jobTitle) {
			return true
		}
		return ex.CreatorID == userID
	default:
		return false
	}
}

func staffCanPauseExam(ex *persistence.ExamRow, userID int, role, jobTitle string) (ok bool, hidden bool) {
	role = strings.ToLower(strings.TrimSpace(role))
	if developerExamHidden(role, creatorRole(ex)) {
		return false, true
	}
	switch role {
	case "developer", "admin":
		return true, false
	case "teacher":
		if isPengawas(role, jobTitle) || ex.CreatorID == userID {
			return true, false
		}
		return false, false
	default:
		return false, false
	}
}

func staffCanViewResults(ex *persistence.ExamRow, userID int, role string) (ok bool, hidden bool) {
	role = strings.ToLower(strings.TrimSpace(role))
	if developerExamHidden(role, creatorRole(ex)) {
		return false, true
	}
	switch role {
	case "developer", "admin":
		return true, false
	case "teacher":
		return ex.CreatorID == userID, false
	default:
		return false, false
	}
}

func staffCanMutateExam(ex *persistence.ExamRow, userID int, role, jobTitle string, pengawasUnpublish bool) (ok bool, hidden bool, detail string) {
	role = strings.ToLower(strings.TrimSpace(role))
	if developerExamHidden(role, creatorRole(ex)) {
		return false, true, ""
	}
	switch role {
	case "developer", "admin":
		return true, false, ""
	case "teacher":
		if isPengawas(role, jobTitle) {
			if pengawasUnpublish && ex.Published {
				return true, false, ""
			}
			return false, false, "Pengawas tidak diizinkan mengubah ujian ini"
		}
		if ex.CreatorID != userID {
			return false, false, "Tidak memiliki akses ke ujian ini"
		}
		return true, false, ""
	default:
		return false, false, "Hanya guru atau admin yang dapat mengelola ujian"
	}
}
