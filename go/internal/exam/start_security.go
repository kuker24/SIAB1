package exam

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"siab1/internal/persistence"
)

var buildTokenPattern = regexp.MustCompile(`^BUILD-\d{14}-[A-Z0-9]{6}$`)

type startSecurityRepository interface {
	LoadStartSecuritySettings(context.Context) (persistence.StartSecuritySettings, error)
	StartSEBKeys(context.Context, int) (string, string, bool, error)
	RedisGet(context.Context, string) (string, bool, error)
	RedisSet(context.Context, string, string, time.Duration) error
	RedisDelete(context.Context, string) error
}

func validateStartSXB(
	r *http.Request,
	settings persistence.StartSecuritySettings,
	enforce bool,
) *startHTTPError {
	if !enforce || settings.DeveloperMode {
		return nil
	}
	ua := strings.ToLower(r.Header.Get("User-Agent"))
	isSXB := strings.Contains(ua, "sxb-client") || strings.Contains(ua, "exambro")
	isSEB := strings.Contains(ua, "seb") || strings.Contains(ua, "safe exam browser")
	if !isSXB && !isSEB {
		return &startHTTPError{
			Status:       http.StatusForbidden,
			Detail:       "Akses ditolak. Gunakan Aplikasi Ujian (APK) atau Safe Exam Browser.",
			RedirectHTML: "/student/dashboard.html",
		}
	}
	if !isSXB {
		return nil
	}
	signature := r.Header.Get("X-App-Signature")
	timestamp := r.Header.Get("X-App-Timestamp")
	if signature == "" || timestamp == "" {
		return nil
	}
	allowed := parseSignatureProfiles(settings.AllowedSignatures)
	if len(allowed) == 0 {
		return startError(http.StatusForbidden, "Sistem APK belum dikonfigurasi. Hubungi admin untuk mengatur App Signatures.")
	}
	normalized := normalizeSignature(signature)
	if _, ok := allowed[normalized]; !ok {
		return startError(http.StatusForbidden, "Invalid App Signature. Unofficial app detected.")
	}
	clientTime, err := strconv.ParseInt(timestamp, 10, 64)
	if err == nil && abs64(time.Now().Unix()-clientTime) > 3600 {
		return startError(http.StatusForbidden, "Request Expired (Check Device Time)")
	}
	return nil
}

func validateStartSEB(
	ctx context.Context,
	repo startSecurityRepository,
	r *http.Request,
	examID int,
	settings persistence.StartSecuritySettings,
	defaultConfigKey string,
	challengeEnabled bool,
	challengePrefix string,
) *startHTTPError {
	if settings.DeveloperMode {
		return nil
	}
	buildToken := r.Header.Get("X-Build-Token")
	ua := strings.ToLower(r.Header.Get("User-Agent"))
	isMobile := strings.Contains(ua, "sxb-client") || strings.Contains(ua, "exambro")
	if buildToken != "" || isMobile {
		if settings.AllowMobileApps {
			tokenValid := false
			if buildTokenPattern.MatchString(buildToken) {
				_, tokenValid = parseTokenProfiles(settings.MinimumAPKToken)[strings.ToUpper(strings.TrimSpace(buildToken))]
			}
			signatureValid := false
			if signature := r.Header.Get("X-App-Signature"); signature != "" {
				_, signatureValid = parseSignatureProfiles(settings.AllowedSignatures)[normalizeSignature(signature)]
				if signatureValid {
					clientTime, err := strconv.ParseInt(r.Header.Get("X-App-Timestamp"), 10, 64)
					signatureValid = err == nil && abs64(time.Now().Unix()-clientTime) <= 3600
				}
			}
			if tokenValid || signatureValid {
				return nil
			}
		}
	}

	configHash := r.Header.Get("X-SafeExamBrowser-ConfigKeyHash")
	if configHash == "" {
		return sebStartError(
			examID,
			"SEB_REQUIRED",
			"Ujian ini harus diakses melalui Aplikasi Ujian (APK) atau Safe Exam Browser",
		)
	}
	configKey, browserKey, found, err := repo.StartSEBKeys(ctx, examID)
	if err != nil {
		return startError(http.StatusInternalServerError, "Internal Server Error")
	}
	if !found {
		return startError(http.StatusNotFound, "Ujian tidak ditemukan")
	}
	expectedConfig := sha256.Sum256([]byte(configKey))
	receivedConfig, err := hex.DecodeString(strings.ToLower(configHash))
	if err != nil || !hmac.Equal(receivedConfig, expectedConfig[:]) {
		return sebStartError(examID, "INVALID_SEB_CONFIG", "Konfigurasi SEB tidak valid")
	}
	requestHash := r.Header.Get("X-SafeExamBrowser-RequestHash")
	if browserKey != "" && requestHash != "" {
		mac := hmac.New(sha256.New, []byte(browserKey))
		_, _ = mac.Write([]byte(startRequestURL(r)))
		received, err := hex.DecodeString(strings.ToLower(requestHash))
		if err != nil || !hmac.Equal(received, mac.Sum(nil)) {
			return sebStartError(examID, "INVALID_REQUEST_HASH", "Verifikasi permintaan gagal")
		}
	}
	challengeToken := r.Header.Get("X-SEB-Challenge-Token")
	challengeResponse := r.Header.Get("X-SEB-Challenge-Response")
	if challengeEnabled && challengeToken != "" && challengeResponse != "" {
		if !validateStartChallenge(
			ctx, repo, challengePrefix, challengeToken, challengeResponse,
			defaultConfigKey, examID,
		) {
			return sebStartError(
				examID,
				"CHALLENGE_FAILED",
				"Validasi challenge gagal. Kemungkinan serangan spoofing terdeteksi.",
			)
		}
	}
	return nil
}

func validateStartChallenge(
	ctx context.Context,
	repo startSecurityRepository,
	prefix, token, response, configKey string,
	examID int,
) bool {
	key := prefix + token
	raw, found, err := repo.RedisGet(ctx, key)
	if err != nil || !found {
		return false
	}
	var data struct {
		ExamID int  `json:"exam_id"`
		Used   bool `json:"used"`
	}
	if json.Unmarshal([]byte(raw), &data) != nil {
		return false
	}
	if data.Used {
		_ = repo.RedisDelete(ctx, key)
		return false
	}
	if data.ExamID != examID {
		return false
	}
	expected := sha256.Sum256([]byte(token + configKey + strconv.Itoa(examID)))
	received, err := hex.DecodeString(strings.ToLower(response))
	if err != nil || !hmac.Equal(received, expected[:]) {
		return false
	}
	var payload map[string]any
	if json.Unmarshal([]byte(raw), &payload) != nil {
		return false
	}
	payload["used"] = true
	encoded, err := json.Marshal(payload)
	return err == nil && repo.RedisSet(ctx, key, string(encoded), 5*time.Second) == nil
}

func parseTokenProfiles(raw string) map[string]struct{} {
	out := map[string]struct{}{}
	value := strings.TrimSpace(raw)
	if strings.HasPrefix(value, "TOKENS_V2:") {
		var payload map[string]any
		if json.Unmarshal([]byte(strings.TrimSpace(strings.TrimPrefix(value, "TOKENS_V2:"))), &payload) == nil {
			stableEnabled := true
			if rawEnabled, ok := payload["stable_enabled"]; ok {
				stableEnabled = pythonTruthy(rawEnabled)
			} else if rawEnabled, ok := payload["se"]; ok {
				stableEnabled = pythonTruthy(rawEnabled)
			}
			stable := firstString(payload, "stable", "stable_token", "s")
			if stableEnabled && buildTokenPattern.MatchString(stable) {
				out[stable] = struct{}{}
			}
			update := firstString(payload, "new_update", "new update", "new_update_token", "n")
			if buildTokenPattern.MatchString(update) {
				out[update] = struct{}{}
			}
		}
		return out
	}
	value = strings.ToUpper(value)
	if buildTokenPattern.MatchString(value) {
		out[value] = struct{}{}
	}
	return out
}

func parseSignatureProfiles(raw string) map[string]struct{} {
	out := map[string]struct{}{}
	value := strings.TrimSpace(raw)
	if strings.HasPrefix(value, "SIGS_V2:") {
		var payload map[string]any
		if json.Unmarshal([]byte(strings.TrimSpace(strings.TrimPrefix(value, "SIGS_V2:"))), &payload) == nil {
			for _, key := range []string{"stable", "new_update", "new update"} {
				for _, signature := range securityStringList(payload[key]) {
					if normalized := normalizeSignature(signature); normalized != "" {
						out[normalized] = struct{}{}
					}
				}
			}
		}
		return out
	}
	for _, signature := range strings.Split(value, ",") {
		if normalized := normalizeSignature(signature); normalized != "" {
			out[normalized] = struct{}{}
		}
	}
	return out
}

func normalizeSignature(value string) string {
	return strings.ToLower(strings.ReplaceAll(strings.TrimSpace(value), ":", ""))
}

func firstString(payload map[string]any, keys ...string) string {
	for _, key := range keys {
		if value, ok := payload[key].(string); ok {
			value = strings.ToUpper(strings.TrimSpace(value))
			if value != "" {
				return value
			}
		}
	}
	return ""
}

func securityStringList(value any) []string {
	switch typed := value.(type) {
	case string:
		return strings.Split(typed, ",")
	case []any:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			if text, ok := item.(string); ok {
				out = append(out, text)
			}
		}
		return out
	default:
		return nil
	}
}

func startRequestURL(r *http.Request) string {
	scheme := "http"
	if r.TLS != nil {
		scheme = "https"
	}
	if forwarded := strings.TrimSpace(r.Header.Get("X-Forwarded-Proto")); forwarded != "" {
		scheme = strings.TrimSpace(strings.Split(forwarded, ",")[0])
	}
	host := r.Host
	if forwarded := strings.TrimSpace(r.Header.Get("X-Forwarded-Host")); forwarded != "" {
		host = strings.TrimSpace(strings.Split(forwarded, ",")[0])
	}
	return scheme + "://" + host + r.URL.RequestURI()
}

func sebStartError(examID int, code, message string) *startHTTPError {
	return &startHTTPError{Status: http.StatusForbidden, Detail: map[string]any{
		"error":                 code,
		"message":               message,
		"download_config":       "/api/exams/" + strconv.Itoa(examID) + "/seb-config.seb",
		"mobile_launch_ios":     "/api/exams/" + strconv.Itoa(examID) + "/seb-launch-mobile?platform=ios",
		"mobile_launch_android": "/api/exams/" + strconv.Itoa(examID) + "/seb-launch-mobile?platform=android",
	}}
}

func abs64(value int64) int64 {
	if value < 0 {
		return -value
	}
	return value
}
