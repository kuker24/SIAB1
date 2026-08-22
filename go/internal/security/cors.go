package security

import (
	"net/http"
	"strings"
)

func CORS(origins []string) func(http.Handler) http.Handler {
	allowAll := false
	allowed := make(map[string]struct{}, len(origins))
	for _, o := range origins {
		if o == "*" {
			allowAll = true
		}
		allowed[o] = struct{}{}
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			h := w.Header()
			if allowAll {
				h.Set("Access-Control-Allow-Origin", "*")
			} else if origin != "" {
				if _, ok := allowed[origin]; ok {
					h.Set("Access-Control-Allow-Origin", origin)
					h.Set("Access-Control-Allow-Credentials", "true")
					h.Add("Vary", "Origin")
				}
			}
			h.Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
			h.Set("Access-Control-Allow-Headers", "*")
			h.Set("Access-Control-Expose-Headers", "*")
			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

func ParseOrigins(csv string) []string {
	parts := strings.Split(csv, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
