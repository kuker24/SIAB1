package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	DatabaseURL              string
	RedisURL                 string
	JWTSecretKey             string
	SecretKey                string
	ExamPeakMode             bool
	EnforceSXB               bool
	CORSOrigins              []string
	PythonUpstream           string
	StaticDir                string
	TemplateDir              string
	Port                     string
	DisableRateLimit         bool
	BaseURL                  string
	SEBDesktopLegacy         bool
	SEBStrictMode            bool
	SEBDefaultConfigKey      string
	SEBDefaultBrowserExamKey string
}

func Load() Config {
	return Config{
		DatabaseURL:              os.Getenv("DATABASE_URL"),
		RedisURL:                 os.Getenv("REDIS_URL"),
		JWTSecretKey:             os.Getenv("JWT_SECRET_KEY"),
		SecretKey:                getenv("SECRET_KEY", os.Getenv("JWT_SECRET_KEY")),
		ExamPeakMode:             truthy(getenv("EXAM_PEAK_MODE", "true")),
		EnforceSXB:               truthy(os.Getenv("ENFORCE_SXB")),
		CORSOrigins:              splitCSV(getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000")),
		PythonUpstream:           os.Getenv("PYTHON_UPSTREAM"),
		StaticDir:                getenv("STATIC_DIR", "../../static"),
		TemplateDir:              getenv("TEMPLATE_DIR", "../../templates"),
		Port:                     getenv("PORT", "8000"),
		DisableRateLimit:         truthy(os.Getenv("DISABLE_RATE_LIMIT")),
		BaseURL:                  strings.TrimRight(getenv("BASE_URL", ""), "/"),
		SEBDesktopLegacy:         truthy(os.Getenv("SEB_DESKTOP_LEGACY_ENABLED")),
		SEBStrictMode:            truthy(getenv("SEB_STRICT_MODE", "true")),
		SEBDefaultConfigKey:      getenv("SEB_DEFAULT_CONFIG_KEY", "default-seb-config-key"),
		SEBDefaultBrowserExamKey: getenv("SEB_DEFAULT_BROWSER_EXAM_KEY", "default-browser-exam-key"),
	}
}

func getenv(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func truthy(v string) bool {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func splitCSV(v string) []string {
	parts := strings.Split(v, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func PortNumber(cfg Config) int {
	n, err := strconv.Atoi(cfg.Port)
	if err != nil || n <= 0 {
		return 8000
	}
	return n
}
