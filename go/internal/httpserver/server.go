package httpserver

import (
	"encoding/json"
	"net/http"
	"net/http/httputil"
	"net/url"
	"path/filepath"
	"strings"
	"time"

	"siab1/internal/admin"
	"siab1/internal/audit"
	"siab1/internal/auth"
	"siab1/internal/config"
	"siab1/internal/exam"
	"siab1/internal/persistence"
	"siab1/internal/security"
	"siab1/internal/student"
)

func New(cfg config.Config, store *persistence.Store) http.Handler {
	_ = auth.ExamJWTExpiryMinutes
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", health(store))
	mux.HandleFunc("POST /api/validate-apk-token", validateAPK(store))
	mux.HandleFunc("POST /api/apk/validate-token", validateAPK(store))
	mux.HandleFunc("GET /api/apk/version", apkVersion)
	mux.HandleFunc("GET /api/apk/config", apkConfig)
	staticDir := cfg.StaticDir
	if staticDir == "" {
		staticDir = "../../static"
	}
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.Dir(staticDir))))
	tmpl := cfg.TemplateDir
	if tmpl == "" {
		tmpl = "../../templates"
	}
	studentDir := filepath.Join(tmpl, "student")
	adminDir := filepath.Join(tmpl, "admin")
	mux.HandleFunc("GET /student/{page}", func(w http.ResponseWriter, r *http.Request) {
		student.Serve(w, studentDir, r.PathValue("page"))
	})
	mux.HandleFunc("GET /student/", func(w http.ResponseWriter, r *http.Request) {
		student.Serve(w, studentDir, "index.html")
	})
	mux.HandleFunc("GET /admin/{page}", func(w http.ResponseWriter, r *http.Request) {
		admin.Serve(w, adminDir, r.PathValue("page"))
	})
	mux.HandleFunc("GET /admin/", func(w http.ResponseWriter, r *http.Request) {
		admin.Serve(w, adminDir, "index.html")
	})
	var fallback http.Handler
	if u := strings.TrimSpace(cfg.PythonUpstream); u != "" {
		if proxy, err := newUpstreamProxy(u); err == nil {
			fallback = proxy
			mux.Handle("/api/", proxy)
			mux.Handle("/ws/", proxy)
		}
	}
	exam.Register(mux, store, cfg, fallback)
	mux.HandleFunc("GET /seb/{exam_id}", func(w http.ResponseWriter, r *http.Request) {
		student.Serve(w, filepath.Join(tmpl, "seb"), "landing.html")
	})
	mux.HandleFunc("GET /exam/{exam_id}/start", func(w http.ResponseWriter, r *http.Request) {
		student.Serve(w, studentDir, "dashboard.html")
	})
	mux.HandleFunc("GET /ws/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "message": "WebSocket service is running"})
	})

	var h http.Handler = rewriteRoleAPI(mux)
	h = security.Logging(h)
	h = security.SXB(cfg.EnforceSXB)(h)
	if !cfg.DisableRateLimit {
		h = security.RateLimit(h)
	}
	h = security.Headers(h)
	h = security.CORS(cfg.CORSOrigins)(h)
	audit.Record("httpserver_ready", "")
	return h
}

func health(store *persistence.Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		body := map[string]any{
			"status":  "healthy",
			"app":     "Ujian Online",
			"version": "1.0.0",
			"runtime": "go",
		}
		if store != nil && store.HasDatabase() {
			ctx := r.Context()
			if !store.PingDB(ctx) {
				body["db"] = "down"
			}
		}
		writeJSON(w, http.StatusOK, body)
	}
}

func validateAPK(store *persistence.Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ok := map[string]any{"valid": true, "message": "", "update_required": false}
		if store == nil || !store.HasPool() {
			writeJSON(w, http.StatusOK, ok)
			return
		}
		var body struct {
			Token string `json:"token"`
		}
		_ = json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<16)).Decode(&body)
		settings, err := store.APKSettings(r.Context())
		if err != nil || settings == nil {
			writeJSON(w, http.StatusOK, ok)
			return
		}
		if settings.Bypass || settings.BrowserTest {
			writeJSON(w, http.StatusOK, map[string]any{
				"valid": true, "message": "", "update_required": false, "validation_enabled": false,
			})
			return
		}
		allowed := persistence.ParseAPKTokens(settings.MinimumToken)
		if len(allowed) == 0 {
			writeJSON(w, http.StatusOK, ok)
			return
		}
		token := strings.ToUpper(strings.TrimSpace(body.Token))
		if token == "" {
			token = strings.ToUpper(strings.TrimSpace(r.Header.Get("X-Build-Token")))
		}
		for _, want := range allowed {
			if want == token {
				writeJSON(w, http.StatusOK, ok)
				return
			}
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"valid":           false,
			"message":         "Versi aplikasi tidak sesuai. Silakan gunakan APK stable/new update resmi dari admin.",
			"update_required": true,
		})
	}
}

func apkVersion(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"current_version": "1.0.0",
		"min_version":     "1.0.0",
		"force_update":    false,
		"update_message":  nil,
		"changelog": []map[string]any{
			{"version": "1.0.0", "changes": []string{"Initial release", "Kiosk mode", "Anti-cheat features"}},
		},
	})
}

func apkConfig(w http.ResponseWriter, r *http.Request) {
	base := requestBase(r)
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "ok",
		"server": map[string]any{"url": base, "name": "SIAB1", "version": "1.0.0"},
		"config": map[string]any{
			"exam_url":       base + "/student/",
			"api_url":        base + "/api",
			"seb_config_url": base + "/api/seb/download-config",
			"qr_code_url":    base + "/api/seb/qr-code",
		},
		"security": map[string]any{"seb_required": true, "challenge_enabled": true, "strict_mode": true},
		"app":      map[string]any{"min_version": "1.0.0", "update_url": nil, "force_update": false},
	})
}

func requestBase(r *http.Request) string {
	if proto := strings.TrimSpace(r.Header.Get("X-Forwarded-Proto")); proto != "" {
		if host := strings.TrimSpace(r.Header.Get("X-Forwarded-Host")); host != "" {
			return proto + "://" + host
		}
	}
	scheme := "http"
	if r.TLS != nil {
		scheme = "https"
	}
	return scheme + "://" + r.Host
}

func rewriteRoleAPI(next http.Handler) http.Handler {
	lanes := []string{"student", "control", "admin", "teacher", "pengawas"}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		// Account lockout and CAPTCHA state are Redis-backed FastAPI contracts.
		if strings.HasPrefix(path, "/api/admin/security/") {
			next.ServeHTTP(w, r)
			return
		}
		for _, lane := range lanes {
			if path == "/api/"+lane+"/auth/login" || path == "/api/"+lane+"/auth/signin" {
				next.ServeHTTP(w, r)
				return
			}
		}
		for _, lane := range lanes {
			if rest, ok := strings.CutPrefix(path, "/api/"+lane+"/"); ok {
				clone := r.Clone(r.Context())
				u := *r.URL
				u.Path = "/api/" + rest
				clone.URL = &u
				next.ServeHTTP(w, clone)
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func newUpstreamProxy(raw string) (http.Handler, error) {
	target, err := url.Parse(raw)
	if err != nil {
		return nil, err
	}
	proxy := &httputil.ReverseProxy{
		FlushInterval: 100 * time.Millisecond,
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(target)
			r.SetXForwarded()
			r.Out.Host = target.Host
		},
	}
	return proxy, nil
}
