package exam

import "net/http"

func (d deps) violationTypes(w http.ResponseWriter, r *http.Request) {
	items := make([]map[string]string, 0, len(violationTypeMeta))
	for _, key := range violationTypeOrder {
		meta := violationTypeMeta[key]
		items = append(items, map[string]string{
			"key": key, "label": meta[0], "severity": meta[1],
			"category": meta[2], "description": meta[3],
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"violation_types": items})
}

var violationTypeOrder = []string{
	"accessibility_risk", "apk_tampering", "browser_minimize", "clipboard_violation",
	"copy", "cut", "devtools_open", "external_display", "focus_lost", "overlay_app",
	"paste", "right_click", "screen_recording", "screenshot_attempt", "security_warning",
	"tab_switch",
}

var violationTypeMeta = map[string][4]string{
	"tab_switch":          {"Pindah Tab", "medium", "browser", "Berpindah tab atau aplikasi saat ujian berlangsung."},
	"focus_lost":          {"Fokus Hilang", "medium", "browser", "Jendela ujian kehilangan fokus."},
	"browser_minimize":    {"Browser Diminimize", "low", "browser", "Jendela browser diminimize saat ujian."},
	"copy":                {"Copy", "high", "clipboard", "Percobaan menyalin teks."},
	"paste":               {"Paste", "high", "clipboard", "Percobaan menempelkan teks."},
	"cut":                 {"Cut", "medium", "clipboard", "Percobaan memotong teks."},
	"clipboard_violation": {"Akses Clipboard", "high", "clipboard", "Akses clipboard terdeteksi."},
	"right_click":         {"Klik Kanan", "low", "browser", "Percobaan klik kanan."},
	"devtools_open":       {"Developer Tools", "critical", "browser", "Percobaan membuka developer tools."},
	"screenshot_attempt":  {"Screenshot", "high", "capture", "Percobaan mengambil tangkapan layar."},
	"overlay_app":         {"Overlay App", "critical", "mobile", "Aplikasi overlay/floating terdeteksi."},
	"screen_recording":    {"Rekam Layar", "critical", "mobile", "Perekaman layar aktif."},
	"external_display":    {"Display Eksternal", "high", "mobile", "Display eksternal atau mirroring terdeteksi."},
	"accessibility_risk":  {"Aksesibilitas Berisiko", "high", "mobile", "Layanan aksesibilitas berisiko terdeteksi."},
	"apk_tampering":       {"APK Dimodifikasi", "critical", "mobile", "APK tidak resmi atau dimodifikasi terdeteksi."},
	"security_warning":    {"Peringatan Keamanan", "medium", "security", "Indikator keamanan berisiko terdeteksi."},
}
