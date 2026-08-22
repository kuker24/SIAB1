package security

import (
	"log"
	"net/http"
	"time"
)

type statusWriter struct {
	http.ResponseWriter
	code int
}

func (w *statusWriter) WriteHeader(code int) {
	w.code = code
	w.ResponseWriter.WriteHeader(code)
}

func (w *statusWriter) Write(b []byte) (int, error) {
	if w.code == 0 {
		w.code = http.StatusOK
	}
	return w.ResponseWriter.Write(b)
}

func (w *statusWriter) Unwrap() http.ResponseWriter {
	return w.ResponseWriter
}

func Logging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		sw := &statusWriter{ResponseWriter: w, code: http.StatusOK}
		next.ServeHTTP(sw, r)
		path := r.URL.Path
		if path == "/health" || path == "/favicon.ico" || len(path) >= 8 && path[:8] == "/static/" {
			return
		}
		log.Printf("%s %s %d %s", r.Method, path, sw.code, time.Since(start).Round(time.Millisecond))
	})
}
