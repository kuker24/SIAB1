package exam

import (
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

const guruPlusClass = "GuruPlus"

func (d deps) studentClasses(w http.ResponseWriter, r *http.Request) {
	_, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	classes, err := d.store.ListStudentClasses(r.Context())
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat kelas")
		return
	}
	if classes == nil {
		classes = []string{}
	}
	if claims.Role == "developer" {
		seen := false
		for _, c := range classes {
			if strings.EqualFold(c, guruPlusClass) {
				seen = true
				break
			}
		}
		if !seen {
			classes = append(classes, guruPlusClass)
			sort.Strings(classes)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"classes": classes})
}

func (d deps) studentsByClass(w http.ResponseWriter, r *http.Request) {
	_, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	className := strings.TrimSpace(r.URL.Query().Get("student_class"))
	role := "student"
	if strings.EqualFold(className, guruPlusClass) {
		if claims.Role != "developer" {
			writeDetail(w, http.StatusForbidden, "Kelas GuruPlus hanya dapat diakses developer")
			return
		}
		role = "guruplus"
	}
	rows, err := d.store.ListStudentsByClass(r.Context(), role, className)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat siswa")
		return
	}
	out := make([]map[string]any, 0, len(rows))
	for i := range rows {
		out = append(out, userJSON(&rows[i]))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) listUsers(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.requireAdmin(w, r); !ok {
		return
	}
	f := parseUserFilter(r)
	if f.Limit == 0 {
		f.Limit = 1000
	}
	rows, err := d.store.ListUsers(r.Context(), f)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat pengguna")
		return
	}
	out := make([]map[string]any, 0, len(rows))
	for i := range rows {
		out = append(out, userJSON(&rows[i]))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) searchUsers(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.requireAdmin(w, r); !ok {
		return
	}
	f := parseUserFilter(r)
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	perPage, _ := strconv.Atoi(r.URL.Query().Get("per_page"))
	if page < 1 {
		page = 1
	}
	if perPage < 1 {
		perPage = 20
	}
	if perPage > 100 {
		perPage = 100
	}
	f.Limit = perPage
	f.Offset = (page - 1) * perPage
	total, err := d.store.CountUsers(r.Context(), f)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menghitung pengguna")
		return
	}
	rows, err := d.store.ListUsers(r.Context(), f)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat pengguna")
		return
	}
	users := make([]map[string]any, 0, len(rows))
	for i := range rows {
		users = append(users, userJSON(&rows[i]))
	}
	pages := 1
	if perPage > 0 {
		pages = (total + perPage - 1) / perPage
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"users": users, "total": total, "page": page, "per_page": perPage, "total_pages": pages,
	})
}

func (d deps) getUser(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.requireAdmin(w, r); !ok {
		return
	}
	id, err := strconv.Atoi(r.PathValue("user_id"))
	if err != nil || id <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "user_id tidak valid")
		return
	}
	u, err := d.store.GetUser(r.Context(), id)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat pengguna")
		return
	}
	if u == nil {
		writeDetail(w, http.StatusNotFound, "User tidak ditemukan")
		return
	}
	writeJSON(w, http.StatusOK, userJSON(u))
}

func (d deps) createUser(w http.ResponseWriter, r *http.Request) {
	_, claims, ok := d.requireAdmin(w, r)
	if !ok {
		return
	}
	var body struct {
		Username     string  `json:"username"`
		Password     string  `json:"password"`
		FullName     string  `json:"full_name"`
		Role         string  `json:"role"`
		StudentClass *string `json:"student_class"`
		JobTitle     *string `json:"job_title"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	username := strings.TrimSpace(body.Username)
	fullName := strings.TrimSpace(body.FullName)
	if utf8.RuneCountInString(username) < 3 || utf8.RuneCountInString(username) > 100 {
		writeDetail(w, http.StatusUnprocessableEntity, "Username minimal 3 karakter")
		return
	}
	if utf8.RuneCountInString(fullName) < 1 || utf8.RuneCountInString(fullName) > 255 {
		writeDetail(w, http.StatusUnprocessableEntity, "Nama lengkap wajib diisi")
		return
	}
	if len(body.Password) < 6 {
		writeDetail(w, http.StatusUnprocessableEntity, "Password minimal 6 karakter")
		return
	}
	role := strings.ToLower(strings.TrimSpace(body.Role))
	if role == "" {
		role = "student"
	}
	if !validUserRole(role) {
		writeDetail(w, http.StatusUnprocessableEntity, "Role tidak valid")
		return
	}
	if !canAssignRole(claims.Role, role) {
		writeRoleDenied(w, role)
		return
	}
	taken, err := d.store.UsernameTaken(r.Context(), username, 0)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa username")
		return
	}
	if taken {
		writeDetail(w, http.StatusBadRequest, "Username sudah digunakan")
		return
	}
	hash, err := auth.HashPassword(body.Password)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menyimpan password")
		return
	}
	cls := applyRoleStudentClass(role, body.StudentClass)
	created, err := d.store.CreateUser(r.Context(), username, hash, fullName, role, cls, trimPtr(body.JobTitle))
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat pengguna")
		return
	}
	writeJSON(w, http.StatusCreated, userJSON(created))
}

func (d deps) updateUser(w http.ResponseWriter, r *http.Request) {
	actorID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	id, err := strconv.Atoi(r.PathValue("user_id"))
	if err != nil || id <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "user_id tidak valid")
		return
	}
	target, err := d.store.GetUser(r.Context(), id)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat pengguna")
		return
	}
	if target == nil {
		writeDetail(w, http.StatusNotFound, "User tidak ditemukan")
		return
	}
	self := actorID == id
	admin := isAdminScope(claims.Role)
	if !self && !admin {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki izin untuk mengubah user ini")
		return
	}
	if !self && !canManageUserAccount(claims.Role, target.Role) {
		writeDetail(w, http.StatusForbidden, "Akun developer hanya dapat dikelola oleh developer.")
		return
	}
	var body struct {
		Username     *string `json:"username"`
		FullName     *string `json:"full_name"`
		Password     *string `json:"password"`
		Role         *string `json:"role"`
		StudentClass *string `json:"student_class"`
		JobTitle     *string `json:"job_title"`
		IsActive     *bool   `json:"is_active"`
		ProfilePic   *string `json:"profile_picture"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	patch := persistence.UserPatch{}
	if body.Username != nil {
		name := strings.TrimSpace(*body.Username)
		if utf8.RuneCountInString(name) < 3 || utf8.RuneCountInString(name) > 100 {
			writeDetail(w, http.StatusUnprocessableEntity, "Username minimal 3 karakter")
			return
		}
		if name != target.Username {
			taken, err := d.store.UsernameTaken(r.Context(), name, id)
			if err != nil {
				writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa username")
				return
			}
			if taken {
				writeDetail(w, http.StatusBadRequest, "Username sudah digunakan")
				return
			}
		}
		patch.Username = &name
	}
	if body.FullName != nil {
		name := strings.TrimSpace(*body.FullName)
		if utf8.RuneCountInString(name) < 1 {
			writeDetail(w, http.StatusUnprocessableEntity, "Nama lengkap wajib diisi")
			return
		}
		patch.FullName = &name
	}
	if body.Password != nil && strings.TrimSpace(*body.Password) != "" {
		if len(*body.Password) < 6 {
			writeDetail(w, http.StatusBadRequest, "Password minimal 6 karakter")
			return
		}
		hash, err := auth.HashPassword(*body.Password)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal menyimpan password")
			return
		}
		patch.PasswordHash = &hash
	}
	role := target.Role
	if admin {
		if body.Role != nil && strings.TrimSpace(*body.Role) != "" {
			role = strings.ToLower(strings.TrimSpace(*body.Role))
			if !validUserRole(role) {
				writeDetail(w, http.StatusUnprocessableEntity, "Role tidak valid")
				return
			}
			if !canAssignRole(claims.Role, role) {
				writeRoleDenied(w, role)
				return
			}
			patch.Role = &role
		}
		if body.StudentClass != nil {
			patch.SetClass = true
			patch.StudentClass = body.StudentClass
		}
		if body.JobTitle != nil {
			patch.JobTitle = trimPtr(body.JobTitle)
		}
		if body.IsActive != nil {
			patch.IsActive = body.IsActive
		}
		if patch.SetClass || patch.Role != nil {
			cls := target.StudentClass
			if patch.SetClass {
				cls = patch.StudentClass
			}
			patch.SetClass = true
			patch.StudentClass = applyRoleStudentClass(role, cls)
		}
	}
	if body.ProfilePic != nil {
		pic, err := normalizeProfilePic(*body.ProfilePic)
		if err != nil {
			writeDetail(w, http.StatusBadRequest, err.Error())
			return
		}
		patch.SetPic = true
		patch.ProfilePic = pic
	}
	updated, err := d.store.UpdateUser(r.Context(), id, patch)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memperbarui pengguna")
		return
	}
	if admin && !self {
		_ = d.store.LogUserActivity(r.Context(), actorID, "admin_user_update", persistence.MustJSON(map[string]any{
			"admin_username": claims.Username, "action": "update",
			"target_user_id": id, "target_username": updated.Username,
		}))
	}
	writeJSON(w, http.StatusOK, userJSON(updated))
}

func (d deps) deleteUser(w http.ResponseWriter, r *http.Request) {
	actorID, claims, ok := d.requireAdmin(w, r)
	if !ok {
		return
	}
	id, err := strconv.Atoi(r.PathValue("user_id"))
	if err != nil || id <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "user_id tidak valid")
		return
	}
	if id == actorID {
		writeDetail(w, http.StatusBadRequest, "Tidak dapat menghapus diri sendiri")
		return
	}
	target, err := d.store.GetUser(r.Context(), id)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat pengguna")
		return
	}
	if target == nil {
		writeDetail(w, http.StatusNotFound, "User tidak ditemukan")
		return
	}
	if !canManageUserAccount(claims.Role, target.Role) {
		writeDetail(w, http.StatusForbidden, "Akun developer hanya dapat dikelola oleh developer.")
		return
	}
	if err := d.store.SoftDeleteUser(r.Context(), id); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menghapus pengguna")
		return
	}
	_ = d.store.LogUserActivity(r.Context(), actorID, "admin_user_delete", persistence.MustJSON(map[string]any{
		"admin_username": claims.Username, "action": "delete",
		"target_user_id": id, "target_username": target.Username,
		"soft_delete": true, "previous_is_active": true,
	}))
	w.WriteHeader(http.StatusNoContent)
}

func (d deps) batchCreateUsers(w http.ResponseWriter, r *http.Request) {
	_, claims, ok := d.requireAdmin(w, r)
	if !ok {
		return
	}
	var users []struct {
		Username     string  `json:"username"`
		Password     string  `json:"password"`
		FullName     string  `json:"full_name"`
		Role         string  `json:"role"`
		StudentClass *string `json:"student_class"`
		JobTitle     *string `json:"job_title"`
	}
	if err := readJSON(r, &users); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	if len(users) > 500 {
		writeDetail(w, http.StatusBadRequest, "Maximum 500 users per batch")
		return
	}
	created := []string{}
	errors := []string{}
	seen := map[string]struct{}{}
	for i, body := range users {
		name := strings.TrimSpace(body.Username)
		key := strings.ToLower(name)
		if _, ok := seen[key]; ok {
			errors = append(errors, "Row "+strconv.Itoa(i+1)+": Duplicate username in payload ("+name+")")
			continue
		}
		seen[key] = struct{}{}
		role := strings.ToLower(strings.TrimSpace(body.Role))
		if role == "" {
			role = "student"
		}
		if !validUserRole(role) || !canAssignRole(claims.Role, role) {
			errors = append(errors, "Row "+strconv.Itoa(i+1)+": Role tidak diizinkan ("+role+")")
			continue
		}
		if utf8.RuneCountInString(name) < 3 || strings.TrimSpace(body.FullName) == "" || len(body.Password) < 6 {
			errors = append(errors, "Row "+strconv.Itoa(i+1)+": Incomplete data")
			continue
		}
		taken, err := d.store.UsernameTaken(r.Context(), name, 0)
		if err != nil || taken {
			errors = append(errors, "Row "+strconv.Itoa(i+1)+": Username exists ("+name+")")
			continue
		}
		hash, err := auth.HashPassword(body.Password)
		if err != nil {
			errors = append(errors, "Row "+strconv.Itoa(i+1)+": Gagal hash password")
			continue
		}
		if _, err := d.store.CreateUser(r.Context(), name, hash, strings.TrimSpace(body.FullName), role,
			applyRoleStudentClass(role, body.StudentClass), trimPtr(body.JobTitle)); err != nil {
			errors = append(errors, "Row "+strconv.Itoa(i+1)+": Username conflict ("+name+")")
			continue
		}
		created = append(created, name)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": len(created), "failed": len(errors),
		"created_usernames": created, "errors": errors,
	})
}

func (d deps) batchUpdateUsers(w http.ResponseWriter, r *http.Request) {
	actorID, claims, ok := d.requireAdmin(w, r)
	if !ok {
		return
	}
	var body struct {
		UserIDs    []int          `json:"user_ids"`
		UpdateData map[string]any `json:"update_data"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	fields := map[string]any{}
	if v, ok := body.UpdateData["is_active"]; ok {
		fields["is_active"] = v
		if b, ok := v.(bool); ok && !b {
			for _, id := range body.UserIDs {
				if id == actorID {
					writeDetail(w, http.StatusBadRequest, "Cannot deactivate yourself in batch update")
					return
				}
			}
		}
	}
	if v, ok := body.UpdateData["role"]; ok {
		role := strings.ToLower(strings.TrimSpace(fmtString(v)))
		if !validUserRole(role) || !canAssignRole(claims.Role, role) {
			writeRoleDenied(w, role)
			return
		}
		fields["role"] = role
		if role == "guruplus" {
			fields["student_class"] = guruPlusClass
		} else if role == "teacher" || role == "admin" || role == "developer" {
			fields["student_class"] = nil
		}
	}
	if v, ok := body.UpdateData["student_class"]; ok {
		if _, has := fields["student_class"]; !has {
			fields["student_class"] = v
		}
	}
	if len(fields) == 0 {
		writeDetail(w, http.StatusBadRequest, "No valid fields to update")
		return
	}
	n, err := d.store.CountUsersByRole(r.Context(), body.UserIDs, "developer")
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa pengguna")
		return
	}
	if n > 0 && claims.Role != "developer" {
		writeDetail(w, http.StatusForbidden, "Akun developer hanya dapat dikelola oleh developer.")
		return
	}
	updated, err := d.store.BatchUpdateUsers(r.Context(), body.UserIDs, fields)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memperbarui pengguna")
		return
	}
	keys := make([]string, 0, len(fields))
	for k := range fields {
		keys = append(keys, k)
	}
	writeJSON(w, http.StatusOK, map[string]any{"updated": updated, "fields": keys})
}

func (d deps) batchDeleteUsers(w http.ResponseWriter, r *http.Request) {
	actorID, claims, ok := d.requireAdmin(w, r)
	if !ok {
		return
	}
	ids := []int{}
	for _, raw := range r.URL.Query()["user_ids"] {
		id, err := strconv.Atoi(raw)
		if err == nil && id > 0 {
			ids = append(ids, id)
		}
	}
	if len(ids) == 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "user_ids wajib")
		return
	}
	for _, id := range ids {
		if id == actorID {
			writeDetail(w, http.StatusBadRequest, "Cannot delete yourself")
			return
		}
	}
	n, err := d.store.CountUsersByRole(r.Context(), ids, "developer")
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memeriksa pengguna")
		return
	}
	if n > 0 && claims.Role != "developer" {
		writeDetail(w, http.StatusForbidden, "Akun developer hanya dapat dihapus oleh developer.")
		return
	}
	permanent := r.URL.Query().Get("permanent") == "true"
	var deleted int64
	if permanent {
		deleted, err = d.store.BatchHardDeleteUsers(r.Context(), ids)
	} else {
		deleted, err = d.store.BatchSoftDeleteUsers(r.Context(), ids)
	}
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menghapus pengguna")
		return
	}
	mode := "soft"
	if permanent {
		mode = "permanent"
	}
	writeJSON(w, http.StatusOK, map[string]any{"deleted": deleted, "mode": mode})
}

func (d deps) exportUsers(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.requireAdmin(w, r); !ok {
		return
	}
	if d.examPeak {
		writeDetail(w, http.StatusServiceUnavailable, "Export pengguna sedang dinonaktifkan selama mode ujian/puncak.")
		return
	}
	if format := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("format"))); format != "" && format != "csv" {
		writeDetail(w, http.StatusBadRequest, "Only CSV format currently supported")
		return
	}
	var body struct {
		Role          string  `json:"role"`
		StudentClass  string  `json:"student_class"`
		IsActive      *bool   `json:"is_active"`
		SearchQuery   string  `json:"search_query"`
		CreatedAfter  *string `json:"created_after"`
		CreatedBefore *string `json:"created_before"`
	}
	_ = readJSON(r, &body)
	f := persistence.UserListFilter{
		StudentClass: strings.TrimSpace(body.StudentClass),
		Search:       strings.TrimSpace(body.SearchQuery),
		IsActive:     body.IsActive,
	}
	role := strings.ToLower(strings.TrimSpace(body.Role))
	if role != "" && role != "admin" && role != "developer" {
		f.Role = role
	}
	if body.CreatedAfter != nil {
		if t, err := time.Parse(time.RFC3339, strings.TrimSpace(*body.CreatedAfter)); err == nil {
			f.CreatedAfter = &t
		}
	}
	if body.CreatedBefore != nil {
		if t, err := time.Parse(time.RFC3339, strings.TrimSpace(*body.CreatedBefore)); err == nil {
			f.CreatedBefore = &t
		}
	}
	rows, err := d.store.ListExportUsers(r.Context(), f)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mengekspor pengguna")
		return
	}
	var b strings.Builder
	b.WriteString("ID,Username,Full Name,Role,Class,Status,Created At\n")
	for _, u := range rows {
		cls := ""
		if u.StudentClass != nil {
			cls = *u.StudentClass
		}
		status := "Inactive"
		if u.IsActive {
			status = "Active"
		}
		b.WriteString(strconv.Itoa(u.ID) + "," + csvCell(u.Username) + "," + csvCell(u.FullName) + "," +
			u.Role + "," + csvCell(cls) + "," + status + "," + u.CreatedAt.UTC().Format("2006-01-02 15:04:05") + "\n")
	}
	w.Header().Set("Content-Type", "text/csv")
	w.Header().Set("Content-Disposition", "attachment; filename=users_export_"+time.Now().UTC().Format("20060102")+".csv")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(b.String()))
}

func (d deps) userTemplateCSV(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.requireAdmin(w, r); !ok {
		return
	}
	body := "username,password,full_name,role,student_class\n" +
		"siswa001,password123,Ahmad Fauzi,student,XII-IPA-1\n" +
		"siswa002,password123,Budi Santoso,student,XII-IPA-1\n" +
		"guru001,password123,Drs. Eko Prasetyo,teacher,\n"
	w.Header().Set("Content-Type", "text/csv")
	w.Header().Set("Content-Disposition", "attachment; filename=template_users.csv")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(body))
}

func csvCell(v string) string {
	if strings.ContainsAny(v, ",\"\n") {
		return `"` + strings.ReplaceAll(v, `"`, `""`) + `"`
	}
	return v
}

func fmtString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func (d deps) requireAdmin(w http.ResponseWriter, r *http.Request) (int, *auth.Claims, bool) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return 0, nil, false
	}
	if !isAdminScope(claims.Role) {
		writeDetail(w, http.StatusForbidden, "Akses ditolak. Hanya admin yang dapat mengakses.")
		return 0, nil, false
	}
	return userID, claims, true
}

func parseUserFilter(r *http.Request) persistence.UserListFilter {
	q := r.URL.Query()
	f := persistence.UserListFilter{
		Role:         strings.TrimSpace(q.Get("role")),
		StudentClass: strings.TrimSpace(q.Get("student_class")),
		Search:       strings.TrimSpace(q.Get("search_query")),
		SortBy:       q.Get("sort_by"),
		SortOrder:    q.Get("sort_order"),
	}
	if v := q.Get("is_active"); v == "true" || v == "false" {
		b := v == "true"
		f.IsActive = &b
	}
	if n, err := strconv.Atoi(q.Get("skip")); err == nil {
		f.Offset = n
	}
	if n, err := strconv.Atoi(q.Get("limit")); err == nil {
		f.Limit = n
	}
	if raw := strings.TrimSpace(q.Get("created_after")); raw != "" {
		if t, err := time.Parse(time.RFC3339, raw); err == nil {
			f.CreatedAfter = &t
		}
	}
	if raw := strings.TrimSpace(q.Get("created_before")); raw != "" {
		if t, err := time.Parse(time.RFC3339, raw); err == nil {
			f.CreatedBefore = &t
		}
	}
	return f
}

func validUserRole(role string) bool {
	switch role {
	case "developer", "admin", "teacher", "student", "guruplus":
		return true
	default:
		return false
	}
}

func writeRoleDenied(w http.ResponseWriter, role string) {
	switch role {
	case "guruplus":
		writeDetail(w, http.StatusForbidden, "Role GuruPlus hanya dapat dikelola oleh developer.")
	case "developer":
		writeDetail(w, http.StatusForbidden, "Role developer hanya dapat dikelola oleh developer.")
	default:
		writeDetail(w, http.StatusForbidden, "Tidak memiliki izin untuk menetapkan role ini.")
	}
}

func trimPtr(v *string) *string {
	if v == nil {
		return nil
	}
	s := strings.TrimSpace(*v)
	if s == "" {
		return nil
	}
	return &s
}

func normalizeProfilePic(raw string) (*string, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return nil, nil
	}
	if strings.ContainsAny(value, "\"'<> \n\r\t") {
		return nil, errInvalidProfilePic
	}
	if strings.HasPrefix(value, "/") {
		return &value, nil
	}
	parsed, err := url.Parse(value)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		return nil, errInvalidProfilePicURL
	}
	return &value, nil
}

type simpleError string

func (e simpleError) Error() string { return string(e) }

const (
	errInvalidProfilePic    simpleError = "URL foto profil tidak valid"
	errInvalidProfilePicURL simpleError = "URL foto profil harus http(s) atau path lokal"
)
