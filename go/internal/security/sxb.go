package security

import (
	"encoding/json"
	"net/http"
	"regexp"
	"strings"
)

var protectedPaths = []*regexp.Regexp{
	regexp.MustCompile(`^/student/exam`),
	regexp.MustCompile(`^/api/exams/\d+/start`),
	regexp.MustCompile(`^/api/exams/\d+/submit`),
	regexp.MustCompile(`^/api/exams/submit$`),
	regexp.MustCompile(`^/api/exams/submit-answer$`),
	regexp.MustCompile(`^/api/exams/auto-save$`),
	regexp.MustCompile(`^/api/exams/auto-save-batch$`),
	regexp.MustCompile(`^/api/exams/answer-journal/sync$`),
	regexp.MustCompile(`^/api/exams/\d+/answer`),
	regexp.MustCompile(`^/api/sessions/\d+`),
}

var sxbWhitelist = []string{
	"/static",
	"/admin",
	"/health",
	"/api/auth",
	"/api/exams/join",
	"/api/validate-apk-token",
	"/api/seb",
}

const sxbDenied = "Akses ditolak. Gunakan Aplikasi Ujian (APK) atau Safe Exam Browser."

func SXB(enforce bool) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !enforce {
				next.ServeHTTP(w, r)
				return
			}
			path := r.URL.Path
			if path == "/" {
				next.ServeHTTP(w, r)
				return
			}
			for _, wpath := range sxbWhitelist {
				if strings.HasPrefix(path, wpath) {
					next.ServeHTTP(w, r)
					return
				}
			}
			protected := false
			for _, re := range protectedPaths {
				if re.MatchString(path) {
					protected = true
					break
				}
			}
			if !protected {
				next.ServeHTTP(w, r)
				return
			}
			ua := strings.ToLower(r.Header.Get("User-Agent"))
			isSXB := strings.Contains(ua, "sxb-client") || strings.Contains(ua, "exambro")
			isSEB := strings.Contains(ua, "seb") || strings.Contains(ua, "safe exam browser")
			if isSXB || isSEB {
				next.ServeHTTP(w, r)
				return
			}
			accept := r.Header.Get("Accept")
			if strings.Contains(accept, "text/html") {
				http.Redirect(w, r, "/student/dashboard.html", http.StatusSeeOther)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			_ = json.NewEncoder(w).Encode(map[string]string{"detail": sxbDenied})
		})
	}
}
