package exam

import "net/http"

func (d deps) submitExam(w http.ResponseWriter, r *http.Request) {
	d.proxyExamWrite(w, r)
}
