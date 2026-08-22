package security

import (
	"net/http"
	"strings"
)

const csp = "default-src 'self'; " +
	"script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://www.youtube.com https://www.youtube-nocookie.com https://static.cloudflareinsights.com; " +
	"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; " +
	"font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; " +
	"img-src 'self' data: https: blob:; " +
	"frame-src 'self' https://www.youtube.com https://youtube.com https://www.youtube-nocookie.com https://youtu.be blob:; " +
	"media-src 'self' https: data: blob:; " +
	"connect-src 'self' wss: ws: https://*.googleapis.com https://cdn.jsdelivr.net https://timeapi.io https://cloudflareinsights.com; " +
	"object-src 'none'; " +
	"base-uri 'self'; " +
	"form-action 'self'; " +
	"frame-ancestors 'none';"

func Headers(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("X-Frame-Options", "DENY")
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("X-XSS-Protection", "1; mode=block")
		h.Set("Referrer-Policy", "strict-origin-when-cross-origin")
		h.Set("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
		h.Set("X-Permitted-Cross-Domain-Policies", "none")
		h.Set("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
		h.Set("Cross-Origin-Resource-Policy", "same-site")
		h.Set("Content-Security-Policy", csp)
		if requestIsHTTPS(r) {
			h.Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
		}
		next.ServeHTTP(w, r)
	})
}

func requestIsHTTPS(r *http.Request) bool {
	if proto := strings.Split(r.Header.Get("X-Forwarded-Proto"), ",")[0]; strings.EqualFold(strings.TrimSpace(proto), "https") {
		return true
	}
	if scheme := strings.Split(r.Header.Get("X-Forwarded-Scheme"), ",")[0]; strings.EqualFold(strings.TrimSpace(scheme), "https") {
		return true
	}
	return r.TLS != nil
}
