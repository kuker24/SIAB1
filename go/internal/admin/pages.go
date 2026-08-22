package admin

import (
	"bytes"
	"encoding/json"
	"html/template"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

func Serve(w http.ResponseWriter, dir, page string) {
	name, ok := normalizePage(page)
	if !ok {
		writeNotFound(w)
		return
	}
	full, ok := safeJoin(dir, name)
	if !ok {
		writeNotFound(w)
		return
	}
	data, err := os.ReadFile(full)
	if err != nil {
		writeNotFound(w)
		return
	}
	w.Header().Set("Cache-Control", "no-cache, no-store, must-revalidate")
	w.Header().Set("Pragma", "no-cache")
	w.Header().Set("Expires", "0")
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	tmpl, err := template.New(name).Option("missingkey=error").Parse(string(data))
	if err != nil {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(data)
		return
	}
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, map[string]any{}); err != nil {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(data)
		return
	}
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(buf.Bytes())
}

func normalizePage(page string) (string, bool) {
	page = strings.TrimSpace(page)
	if page == "" {
		page = "index.html"
	}
	if strings.Contains(page, "/") || strings.Contains(page, `\`) || strings.Contains(page, "..") {
		return "", false
	}
	if strings.HasSuffix(page, ".html") {
		return page, true
	}
	if strings.Contains(page, ".") {
		return "", false
	}
	return page + ".html", true
}

func safeJoin(dir, name string) (string, bool) {
	full := filepath.Join(dir, name)
	rel, err := filepath.Rel(dir, full)
	if err != nil || strings.HasPrefix(rel, "..") {
		return "", false
	}
	return full, true
}

func writeNotFound(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusNotFound)
	_ = json.NewEncoder(w).Encode(map[string]string{"detail": "Halaman tidak ditemukan"})
}
