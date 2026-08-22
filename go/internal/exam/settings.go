package exam

import "net/http"

func (d deps) systemTimezone(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.staffOrFallback(w, r); !ok {
		return
	}
	timezone, err := d.store.SystemTimezone(r.Context())
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat timezone")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"timezone": timezone})
}
