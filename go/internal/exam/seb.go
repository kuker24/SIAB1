package exam

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"siab1/internal/auth"
)

func (d deps) defaultSEBConfig(w http.ResponseWriter, r *http.Request) {
	if !d.sebLegacy {
		writeJSON(w, http.StatusNotFound, map[string]any{
			"detail": map[string]string{
				"error":   "FEATURE_DISABLED",
				"feature": "seb_desktop_legacy",
				"message": "Fitur seb_desktop_legacy sedang dinonaktifkan.",
			},
		})
		return
	}
	start := strings.TrimRight(d.requestBase(r), "/") + "/student/"
	body := generateSEBConfig(start, d.sebKey, d.sebBEK, d.sebStrict)
	writeSEB(w, body, "siab1-seb-config.seb")
}

func (d deps) examSEBConfig(w http.ResponseWriter, r *http.Request) {
	if !d.sebLegacy {
		writeJSON(w, http.StatusNotFound, map[string]any{
			"detail": map[string]string{
				"error":   "FEATURE_DISABLED",
				"feature": "seb_desktop_legacy",
				"message": "Fitur seb_desktop_legacy sedang dinonaktifkan.",
			},
		})
		return
	}
	if d.store == nil || !d.store.HasPool() {
		d.tryFallback(w, r)
		return
	}
	userID, ok := d.userOrFallback(w, r)
	if !ok {
		return
	}
	claims, err := auth.Parse(d.secret, auth.Bearer(r.Header.Get("Authorization")))
	if err != nil {
		writeDetail(w, http.StatusUnauthorized, auth.FormatDetail(err))
		return
	}
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
		return
	}
	ex, err := d.store.GetExam(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian")
		return
	}
	if ex == nil || ex.Deleted {
		writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
		return
	}
	role := strings.ToLower(strings.TrimSpace(claims.Role))
	switch role {
	case "student", "guruplus":
		if ok, detail := participantAccess(ex, userID, claims.Role, claims.StudentClass); !ok {
			writeDetail(w, http.StatusForbidden, detail)
			return
		}
	case "admin", "developer":
	case "teacher":
		if ex.CreatorID != userID {
			writeDetail(w, http.StatusForbidden, "Tidak memiliki akses ke konfigurasi SEB ujian ini")
			return
		}
	default:
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses ke konfigurasi SEB ujian ini")
		return
	}
	cfgKey, bek, found, err := d.store.ExamSEBKeys(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat konfigurasi SEB")
		return
	}
	if !found {
		writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
		return
	}
	if strings.TrimSpace(cfgKey) == "" {
		cfgKey = d.sebKey
	}
	if strings.TrimSpace(bek) == "" {
		bek = d.sebBEK
	}
	start := strings.TrimRight(d.requestBase(r), "/") + "/exam/" + strconv.Itoa(examID) + "/start"
	body := generateSEBConfig(start, cfgKey, bek, d.sebStrict)
	writeSEB(w, body, "exam_"+strconv.Itoa(examID)+".seb")
}

func (d deps) requestBase(r *http.Request) string {
	if proto := strings.TrimSpace(r.Header.Get("X-Forwarded-Proto")); proto != "" {
		if host := strings.TrimSpace(r.Header.Get("X-Forwarded-Host")); host != "" {
			return proto + "://" + host
		}
	}
	if d.baseURL != "" {
		return d.baseURL
	}
	scheme := "http"
	if r.TLS != nil {
		scheme = "https"
	}
	return scheme + "://" + r.Host
}

func writeSEB(w http.ResponseWriter, body []byte, filename string) {
	w.Header().Set("Content-Type", "application/seb")
	w.Header().Set("Content-Disposition", `attachment; filename="`+filename+`"`)
	w.Header().Set("Cache-Control", "no-cache, no-store, must-revalidate")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(body)
}

func generateSEBConfig(startURL, configKey, browserKey string, strict bool) []byte {
	adminHash := sha256Hex(configKey)
	quitHash := sha256Hex(browserKey)
	salt := make([]byte, 32)
	_, _ = rand.Read(salt)
	parsed, _ := url.Parse(startURL)
	host := ""
	base := startURL
	if parsed != nil {
		host = parsed.Host
		base = parsed.Scheme + "://" + parsed.Host
	}
	rules := permissiveURLRules()
	if strict {
		rules = strictURLRules(base, host)
	}
	cfg := map[string]any{
		"startURL":                              startURL,
		"startURLAllowDeepLink":                 true,
		"startURLAppendQueryParameter":          false,
		"browserWindowAllowReload":              true,
		"allowBrowsingBackForward":              true,
		"enableBrowserWindowToolbar":            true,
		"showMenuBar":                           false,
		"showTaskBar":                           false,
		"enableTouchExit":                       false,
		"enableZoomPage":                        true,
		"enableZoomText":                        true,
		"browserWindowShowURL":                  2,
		"newBrowserWindowByLinkPolicy":          0,
		"newBrowserWindowByScriptPolicy":        0,
		"newBrowserWindowByLinkBlockForeign":    true,
		"examKeySalt":                           hex.EncodeToString(salt),
		"browserExamKey":                        browserKey,
		"configKey":                             configKey,
		"sendBrowserExamKey":                    true,
		"hashedAdminPassword":                   adminHash,
		"hashedQuitPassword":                    quitHash,
		"URLFilterEnable":                       true,
		"URLFilterEnableContentFilter":          false,
		"URLFilterRules":                        rules,
		"allowWlan":                             true,
		"allowMobileSync":                       true,
		"enablePrivateClipboard":                true,
		"enableJavaScript":                      true,
		"blockPopUpWindows":                     true,
		"enableRightMouse":                      false,
		"enableF12":                             false,
		"allowScreenShot":                       false,
		"allowScreenSharing":                    false,
		"monitorProcesses":                      true,
		"allowVirtualMachine":                   true,
		"enableF5":                              true,
		"enableEsc":                             false,
		"enableAltTab":                          false,
		"enableCtrlAltDel":                      false,
		"enablePrintScreen":                     false,
		"killExplorerShell":                     true,
		"enableWindowsTouch":                    true,
		"allowPreferencesWindow":                false,
		"enablePinchZoom":                       true,
		"quitURLConfirm":                        true,
		"ignoreExitKeys":                        false,
		"exitKey1":                              2,
		"exitKey2":                              81,
		"exitKey3":                              0,
		"enableAppSwitcherCheck":                true,
		"forceAppFolderInstall":                 false,
		"browserUserAgent":                      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SEB/3.5",
		"browserUserAgentWinDesktopModeEnabled": false,
	}
	return encodePlist(cfg)
}

func sha256Hex(v string) string {
	sum := sha256.Sum256([]byte(v))
	return hex.EncodeToString(sum[:])
}

type sebRule struct {
	Action     int
	Active     bool
	Expression string
	Regex      bool
}

func permissiveURLRules() []sebRule {
	return []sebRule{{Action: 1, Active: true, Expression: ".*", Regex: true}}
}

func strictURLRules(baseURL, domainHost string) []sebRule {
	rules := []sebRule{
		{1, true, baseURL + "/*", false},
		{1, true, domainHost + "/*", false},
	}
	for _, port := range []string{"8000", "8080", "80", "443"} {
		rules = append(rules,
			sebRule{1, true, "http://localhost:" + port + "/*", false},
			sebRule{1, true, "http://127.0.0.1:" + port + "/*", false},
		)
	}
	allow := []string{
		"http://192.168.*/*", "http://10.*/*", "192.168.*/*", "10.*/*",
		"https://fonts.googleapis.com/*", "https://fonts.gstatic.com/*",
		"https://cdn.jsdelivr.net/*", "https://cdnjs.cloudflare.com/*",
		"data:*", "blob:*", "about:*",
	}
	for _, expr := range allow {
		rules = append(rules, sebRule{1, true, expr, false})
	}
	block := []string{
		"*google.com*", "*google.co.*", "*bing.com*", "*duckduckgo.com*", "*yahoo.com*",
		"*baidu.com*", "*yandex.*", "*ask.com*",
		"*chatgpt.com*", "*chat.openai.com*", "*openai.com*", "*claude.ai*", "*anthropic.com*",
		"*perplexity.ai*", "*bard.google.com*", "*gemini.google.com*", "*copilot.microsoft.com*",
		"*bing.com/chat*", "*character.ai*", "*poe.com*", "*replika.ai*", "*phind.com*", "*you.com*",
		"*facebook.com*", "*fb.com*", "*twitter.com*", "*x.com*", "*instagram.com*", "*tiktok.com*",
		"*linkedin.com*", "*reddit.com*", "*discord.com*", "*telegram.org*", "*whatsapp.com*", "*snapchat.com*",
		"*wikipedia.org*", "*wiki*", "*stackoverflow.com*", "*stackexchange.com*", "*quora.com*",
		"*brainly.com*", "*chegg.com*", "*coursehero.com*", "*studocu.com*", "*scribd.com*",
		"*pastebin.com*", "*github.com*", "*gitlab.com*",
		"*youtube.com*", "*youtu.be*", "*vimeo.com*", "*twitch.tv*", "*netflix.com*", "*dailymotion.com*",
	}
	for _, expr := range block {
		rules = append(rules, sebRule{0, true, expr, false})
	}
	rules = append(rules, sebRule{0, true, "*", false})
	return rules
}

func encodePlist(cfg map[string]any) []byte {
	var b strings.Builder
	b.WriteString(`<?xml version="1.0" encoding="UTF-8"?>`)
	b.WriteByte('\n')
	b.WriteString(`<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">`)
	b.WriteByte('\n')
	b.WriteString(`<plist version="1.0"><dict>`)
	keys := make([]string, 0, len(cfg))
	for k := range cfg {
		keys = append(keys, k)
	}
	for _, k := range keys {
		writePlistKV(&b, k, cfg[k])
	}
	b.WriteString(`</dict></plist>`)
	return []byte(b.String())
}

func writePlistKV(b *strings.Builder, key string, v any) {
	b.WriteString("<key>")
	b.WriteString(xmlEsc(key))
	b.WriteString("</key>")
	writePlistVal(b, v)
}

func writePlistVal(b *strings.Builder, v any) {
	switch n := v.(type) {
	case bool:
		if n {
			b.WriteString("<true/>")
		} else {
			b.WriteString("<false/>")
		}
	case int:
		b.WriteString("<integer>")
		b.WriteString(strconv.Itoa(n))
		b.WriteString("</integer>")
	case string:
		b.WriteString("<string>")
		b.WriteString(xmlEsc(n))
		b.WriteString("</string>")
	case []sebRule:
		b.WriteString("<array>")
		for _, rule := range n {
			b.WriteString("<dict>")
			writePlistKV(b, "action", rule.Action)
			writePlistKV(b, "active", rule.Active)
			writePlistKV(b, "expression", rule.Expression)
			writePlistKV(b, "regex", rule.Regex)
			b.WriteString("</dict>")
		}
		b.WriteString("</array>")
	default:
		b.WriteString("<string>")
		b.WriteString(xmlEsc(fmt.Sprint(v)))
		b.WriteString("</string>")
	}
}

func xmlEsc(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	s = strings.ReplaceAll(s, `"`, "&quot;")
	return s
}
