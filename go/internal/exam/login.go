package exam

import (
	"net"
	"net/http"
	"regexp"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

var buildTokenRe = regexp.MustCompile(`BUILD-\d{14}-[A-Z0-9]{6}`)

func (d deps) loginAny(w http.ResponseWriter, r *http.Request) {
	d.handleLogin(w, r, nil, "")
}

func (d deps) loginStudent(w http.ResponseWriter, r *http.Request) {
	d.handleLogin(w, r, map[string]struct{}{"student": {}, "guruplus": {}}, "student")
}

func (d deps) loginControl(w http.ResponseWriter, r *http.Request) {
	d.handleLogin(w, r, map[string]struct{}{"developer": {}, "admin": {}, "teacher": {}}, "control")
}

func (d deps) loginAdmin(w http.ResponseWriter, r *http.Request) {
	d.handleLogin(w, r, map[string]struct{}{"developer": {}, "admin": {}}, "admin")
}

func (d deps) loginTeacher(w http.ResponseWriter, r *http.Request) {
	d.handleLogin(w, r, map[string]struct{}{"teacher": {}}, "teacher")
}

func (d deps) loginPengawas(w http.ResponseWriter, r *http.Request) {
	d.handleLogin(w, r, map[string]struct{}{"teacher": {}}, "pengawas")
}

func (d deps) handleLogin(w http.ResponseWriter, r *http.Request, allowed map[string]struct{}, scope string) {
	if d.store == nil || !d.store.HasPool() {
		d.tryFallback(w, r)
		return
	}
	var body struct {
		Username      string `json:"username"`
		Password      string `json:"password"`
		BuildToken    string `json:"build_token"`
		CaptchaID     string `json:"captcha_id"`
		CaptchaAnswer string `json:"captcha_answer"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	username := strings.TrimSpace(body.Username)
	ip := clientIP(r)
	key := strings.ToLower(username) + ":" + ip
	if mins := auth.LockoutRemainingMinutes(key); mins > 0 {
		w.Header().Set("X-Lockout-Remaining", itoa(mins))
		writeDetail(w, http.StatusLocked, "Akun terkunci. Coba lagi dalam "+itoa(mins)+" menit.")
		return
	}
	if ok, remaining := auth.AllowLoginAttempt(key); !ok {
		w.Header().Set("Retry-After", "60")
		w.Header().Set("X-RateLimit-Remaining", itoa(remaining))
		writeDetail(w, http.StatusTooManyRequests, "Terlalu banyak percobaan login untuk akun ini. Tunggu 1 menit.")
		return
	}
	user, err := d.store.GetUserByUsername(r.Context(), username)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat akun")
		return
	}
	if user == nil || !auth.VerifyPassword(body.Password, user.PasswordHash) {
		attempts, warning := auth.RecordLoginFailure(key)
		w.Header().Set("WWW-Authenticate", "Bearer")
		w.Header().Set("X-Login-Attempts", itoa(attempts))
		detail := "Username atau password salah"
		if warning != "" {
			detail = detail + ". " + warning
		}
		writeDetail(w, http.StatusUnauthorized, detail)
		return
	}
	if !user.IsActive {
		writeDetail(w, http.StatusForbidden, "Akun tidak aktif")
		return
	}
	role := strings.ToLower(strings.TrimSpace(user.Role))
	job := ""
	if user.JobTitle != nil {
		job = *user.JobTitle
	}
	if allowed != nil {
		if _, ok := allowed[role]; !ok {
			label := scope
			if label == "" {
				label = "umum"
			}
			writeDetail(w, http.StatusForbidden, "Akses ditolak untuk jalur login "+label+". Role akun: "+role)
			return
		}
	}
	if scope == "pengawas" && !isPengawas(role, job) {
		writeDetail(w, http.StatusForbidden, "Akses ditolak untuk jalur login pengawas.")
		return
	}
	settings, err := d.store.APKSettings(r.Context())
	if err != nil {
		d.tryFallback(w, r)
		return
	}
	if settings != nil && settings.Freeze && (role == "student" || role == "guruplus") {
		writeDetail(w, http.StatusUnauthorized, "Username atau password salah")
		return
	}
	if settings != nil && settings.Maintenance && role != "admin" && role != "developer" {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{
			"detail": map[string]any{
				"type":    "maintenance",
				"message": "Sistem sedang dalam pemeliharaan. Hanya admin yang dapat mengakses saat ini.",
			},
		})
		return
	}
	if role == "student" || role == "guruplus" {
		if settings == nil || (!settings.Bypass && !settings.BrowserTest) {
			if detail := checkStudentSignature(settings, r); detail != nil {
				writeJSON(w, http.StatusForbidden, map[string]any{"detail": detail["message"]})
				return
			}
		}
		token := strings.TrimSpace(body.BuildToken)
		if token == "" {
			token = strings.TrimSpace(r.Header.Get("X-Build-Token"))
		}
		if detail := checkStudentAPK(settings, token); detail != nil {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"detail": detail})
			return
		}
	}
	auth.ClearLoginFailures(key)
	className := ""
	if user.StudentClass != nil {
		className = *user.StudentClass
	}
	tok, err := auth.Sign(d.secret, auth.Claims{
		Sub:          itoa(user.ID),
		Username:     user.Username,
		Role:         user.Role,
		FullName:     user.FullName,
		StudentClass: className,
		JobTitle:     job,
		IsActive:     user.IsActive,
	})
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat token")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"access_token": tok,
		"token_type":   "bearer",
		"expires_in":   auth.TokenTTLSeconds(),
		"user":         userJSON(user),
	})
}

func checkStudentAPK(settings *persistence.APKSettings, clientToken string) map[string]any {
	if settings == nil {
		return apkFail("APK_NOT_CONFIGURED", "Sistem APK belum dikonfigurasi oleh admin.", "Hubungi admin untuk mengatur APK Token di Pengaturan Sistem.")
	}
	if settings.Bypass || settings.BrowserTest {
		return nil
	}
	allowed := extractBuildTokens(settings.MinimumToken)
	if len(allowed) == 0 {
		return apkFail("APK_NOT_CONFIGURED", "Sistem APK belum dikonfigurasi oleh admin.", "Hubungi admin untuk mengatur APK Token di Pengaturan Sistem.")
	}
	if clientToken == "" {
		return apkFail("APK_TOKEN_MISSING", "Aplikasi mobile diperlukan untuk ujian. Silakan gunakan aplikasi resmi.", "Hubungi guru atau admin untuk mendapatkan aplikasi ujian.")
	}
	clientToken = strings.ToUpper(strings.TrimSpace(clientToken))
	if !buildTokenRe.MatchString(clientToken) {
		return apkFail("APK_TOKEN_INVALID_FORMAT", "Token aplikasi tidak valid.", "Silakan install ulang aplikasi dari sumber resmi.")
	}
	for _, tok := range allowed {
		if tok == clientToken {
			return nil
		}
	}
	return apkFail("APK_VERSION_MISMATCH", "Versi aplikasi Anda tidak sesuai dengan yang diizinkan.", "Silakan hubungi guru atau admin untuk mendapatkan aplikasi versi yang benar.")
}

func checkStudentSignature(settings *persistence.APKSettings, r *http.Request) map[string]any {
	if settings == nil {
		return apkFail("APK_NOT_CONFIGURED", "Sistem APK belum dikonfigurasi. Hubungi admin untuk mengatur App Signatures.", "Hubungi admin.")
	}
	allowed := extractSignatures(settings.AllowedSignatures)
	if len(allowed) == 0 {
		return apkFail("APK_NOT_CONFIGURED", "Sistem APK belum dikonfigurasi. Hubungi admin untuk mengatur App Signatures.", "Hubungi admin.")
	}
	sig := strings.ReplaceAll(strings.ToLower(strings.TrimSpace(r.Header.Get("X-App-Signature"))), ":", "")
	ts := strings.TrimSpace(r.Header.Get("X-App-Timestamp"))
	if sig == "" || ts == "" {
		return apkFail("SECURITY_HEADERS_MISSING", "Security Headers Missing. Update aplikasi ujian Anda.", "Update aplikasi ujian Anda.")
	}
	ok := false
	for _, want := range allowed {
		if want == sig {
			ok = true
			break
		}
	}
	if !ok {
		return apkFail("INVALID_APP_SIGNATURE", "Invalid App Signature. Unofficial app detected.", "Gunakan aplikasi resmi.")
	}
	return nil
}

func extractBuildTokens(raw string) []string {
	found := buildTokenRe.FindAllString(strings.ToUpper(raw), -1)
	out := make([]string, 0, len(found))
	seen := map[string]struct{}{}
	for _, tok := range found {
		if _, ok := seen[tok]; ok {
			continue
		}
		seen[tok] = struct{}{}
		out = append(out, tok)
	}
	return out
}

func extractSignatures(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	seen := map[string]struct{}{}
	for _, p := range parts {
		p = strings.ReplaceAll(strings.ToLower(strings.TrimSpace(p)), ":", "")
		if p == "" {
			continue
		}
		if _, ok := seen[p]; ok {
			continue
		}
		seen[p] = struct{}{}
		out = append(out, p)
	}
	return out
}

func apkFail(reason, message, action string) map[string]any {
	return map[string]any{
		"type":            "apk_validation_failed",
		"error":           reason,
		"message":         message,
		"action_required": action,
	}
}

func userJSON(u *persistence.UserRow) map[string]any {
	created := u.CreatedAt.UTC().Format(time.RFC3339)
	return map[string]any{
		"id":              u.ID,
		"username":        u.Username,
		"full_name":       u.FullName,
		"role":            u.Role,
		"student_class":   u.StudentClass,
		"is_active":       u.IsActive,
		"created_at":      created,
		"last_login":      u.LastLogin,
		"profile_picture": u.ProfilePic,
		"job_title":       u.JobTitle,
	}
}

func isPengawas(role, jobTitle string) bool {
	if strings.ToLower(strings.TrimSpace(role)) != "teacher" {
		return false
	}
	title := strings.ToLower(strings.TrimSpace(jobTitle))
	if title == "" {
		return false
	}
	return strings.Contains(title, "pengawas") || title == "proktor" || title == "invigilator"
}

func clientIP(r *http.Request) string {
	if xff := strings.TrimSpace(r.Header.Get("X-Forwarded-For")); xff != "" {
		return strings.TrimSpace(strings.Split(xff, ",")[0])
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var b [12]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}
