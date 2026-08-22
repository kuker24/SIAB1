package exam

import (
	"errors"
	"net/http"
	"strings"
	"unicode/utf8"

	"siab1/internal/persistence"
)

func (d deps) listCategories(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.teacherOrFallback(w, r); !ok {
		return
	}
	rows, err := d.store.ListCategories(r.Context())
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat kategori")
		return
	}
	out := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, categoryJSON(row))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) createCategory(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.teacherOrFallback(w, r); !ok {
		return
	}
	var body struct {
		Name        string  `json:"name"`
		Description *string `json:"description"`
		ParentID    *int    `json:"parent_id"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusBadRequest, "Payload tidak valid")
		return
	}
	name := strings.TrimSpace(body.Name)
	if name == "" || utf8.RuneCountInString(name) > 100 {
		writeDetail(w, http.StatusBadRequest, "Nama kategori tidak valid")
		return
	}
	row, err := d.store.CreateCategory(r.Context(), name, emptyToNil(body.Description), body.ParentID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat kategori")
		return
	}
	writeJSON(w, http.StatusCreated, categoryJSON(*row))
}

func (d deps) listTags(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.teacherOrFallback(w, r); !ok {
		return
	}
	rows, err := d.store.ListTags(r.Context())
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat tag")
		return
	}
	out := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, tagJSON(row))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) createTag(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := d.teacherOrFallback(w, r); !ok {
		return
	}
	var body struct {
		Name  string  `json:"name"`
		Color *string `json:"color"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusBadRequest, "Payload tidak valid")
		return
	}
	name := strings.TrimSpace(body.Name)
	if name == "" || utf8.RuneCountInString(name) > 50 {
		writeDetail(w, http.StatusBadRequest, "Nama tag tidak valid")
		return
	}
	color := "#6c757d"
	if body.Color != nil && strings.TrimSpace(*body.Color) != "" {
		color = strings.TrimSpace(*body.Color)
	}
	row, err := d.store.CreateTag(r.Context(), name, color)
	if errors.Is(err, persistence.ErrTagExists) {
		writeDetail(w, http.StatusBadRequest, "Tag already exists")
		return
	}
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat tag")
		return
	}
	writeJSON(w, http.StatusCreated, tagJSON(*row))
}

func (d deps) teacherOrFallback(w http.ResponseWriter, r *http.Request) (int, bool, bool) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return 0, false, false
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return 0, false, false
	}
	return userID, true, true
}

func categoryJSON(row persistence.CategoryRow) map[string]any {
	return map[string]any{
		"id":          row.ID,
		"name":        row.Name,
		"description": row.Description,
		"parent_id":   row.ParentID,
		"created_at":  persistence.FormatTimePtr(row.CreatedAt),
	}
}

func tagJSON(row persistence.TagRow) map[string]any {
	return map[string]any{"id": row.ID, "name": row.Name, "color": row.Color}
}
