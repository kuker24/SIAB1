package exam

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"
	"unicode/utf8"

	"siab1/internal/persistence"
)

func (d deps) listSubjects(w http.ResponseWriter, r *http.Request) {
	if _, ok := d.userOrFallback(w, r); !ok {
		return
	}
	rows, err := d.store.ListSubjects(r.Context())
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat bidang studi")
		return
	}
	out := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, subjectJSON(row))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) createSubject(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	name, desc, errMsg := readSubjectName(r)
	if errMsg != "" {
		writeDetail(w, http.StatusBadRequest, errMsg)
		return
	}
	row, err := d.store.CreateSubject(r.Context(), name, desc, userID)
	if errors.Is(err, persistence.ErrSubjectExists) {
		writeDetail(w, http.StatusBadRequest, "Bidang studi dengan nama ini sudah ada")
		return
	}
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat bidang studi")
		return
	}
	writeJSON(w, http.StatusCreated, subjectJSON(*row))
}

func (d deps) deleteSubject(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	id, err := strconv.Atoi(r.PathValue("subject_id"))
	if err != nil || id <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "subject_id tidak valid")
		return
	}
	row, err := d.store.GetSubject(r.Context(), id)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat bidang studi")
		return
	}
	if row == nil {
		writeDetail(w, http.StatusNotFound, "Bidang studi tidak ditemukan")
		return
	}
	admin := claims.Role == "admin" || claims.Role == "developer"
	if !admin && (row.CreatorID == nil || *row.CreatorID != userID) {
		writeDetail(w, http.StatusForbidden, "Anda tidak memiliki akses untuk menghapus bidang studi ini")
		return
	}
	if err := d.store.DeleteSubject(r.Context(), id); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menghapus bidang studi")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func readSubjectName(r *http.Request) (string, *string, string) {
	defer r.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil || len(raw) == 0 {
		return "", nil, "Payload tidak valid"
	}
	var name string
	var desc *string
	trim := strings.TrimSpace(string(raw))
	if strings.HasPrefix(trim, "\"") {
		if err := json.Unmarshal(raw, &name); err != nil {
			return "", nil, "Payload tidak valid"
		}
	} else {
		var body struct {
			Name        string  `json:"name"`
			Description *string `json:"description"`
		}
		if err := json.Unmarshal(raw, &body); err != nil {
			return "", nil, "Payload tidak valid"
		}
		name = body.Name
		desc = body.Description
	}
	name = strings.TrimSpace(name)
	if name == "" || utf8.RuneCountInString(name) > 100 {
		return "", nil, "Nama bidang studi tidak valid"
	}
	return name, emptyToNil(desc), ""
}

func subjectJSON(row persistence.SubjectRow) map[string]any {
	return map[string]any{"id": row.ID, "name": row.Name, "description": row.Description}
}
