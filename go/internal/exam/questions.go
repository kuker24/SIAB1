package exam

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"unicode/utf8"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

var htmlTag = regexp.MustCompile(`(?s)<[^>]*>`)

var allowedQuestionTypes = map[string]struct{}{
	"multiple_choice":         {},
	"multiple_choice_complex": {},
	"true_false":              {},
	"essay":                   {},
	"short_answer":            {},
}

type questionPayload struct {
	QuestionText     string          `json:"question_text"`
	Stimulus         *string         `json:"stimulus"`
	QuestionType     string          `json:"question_type"`
	QuestionSubtype  *string         `json:"question_subtype"`
	PgkType          *string         `json:"pgk_type"`
	DifficultyLevel  string          `json:"difficulty_level"`
	CategoryID       *int            `json:"category_id"`
	TagIDs           []int           `json:"tag_ids"`
	QuestionSettings json.RawMessage `json:"question_settings"`
	Points           *float64        `json:"points"`
	OrderIndex       *int            `json:"order_index"`
	ImageURL         *string         `json:"image_url"`
	VideoURL         *string         `json:"video_url"`
	AudioURL         *string         `json:"audio_url"`
	Options          []optionPayload `json:"options"`
}

type optionPayload struct {
	OptionText  string  `json:"option_text"`
	IsCorrect   *bool   `json:"is_correct"`
	OrderIndex  int     `json:"order_index"`
	OptionGroup string  `json:"option_group"`
	PairID      *string `json:"pair_id"`
}

func (d deps) listQuestions(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadQuestionExam(w, r, userID, claims, true)
	if !ok {
		return
	}
	questions, err := d.store.LoadQuestionsForGrade(r.Context(), ex.ID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat soal")
		return
	}
	out := make([]map[string]any, 0, len(questions))
	for i := range questions {
		out = append(out, questionJSON(&questions[i], nil, nil))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) searchQuestions(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	var body struct {
		Query        string `json:"query"`
		CategoryID   *int   `json:"category_id"`
		TagIDs       []int  `json:"tag_ids"`
		Difficulty   string `json:"difficulty"`
		QuestionType string `json:"question_type"`
		Limit        int    `json:"limit"`
		Offset       int    `json:"offset"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	filter := persistence.QuestionSearchFilter{
		Query: body.Query, CategoryID: body.CategoryID, TagIDs: body.TagIDs,
		Difficulty: body.Difficulty, QuestionType: body.QuestionType,
		Limit: body.Limit, Offset: body.Offset,
	}
	if claims.Role == "teacher" && !isPengawas(claims.Role, claims.JobTitle) {
		filter.CreatorID = userID
	}
	filter.HideDeveloper = claims.Role != "developer"
	ids, err := d.store.SearchQuestionIDs(r.Context(), filter)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal mencari soal")
		return
	}
	out := make([]map[string]any, 0, len(ids))
	for _, id := range ids {
		q, err := d.store.GetQuestion(r.Context(), id)
		if err != nil || q == nil {
			if err != nil {
				writeDetail(w, http.StatusInternalServerError, "Gagal memuat hasil pencarian")
				return
			}
			continue
		}
		var category any
		if q.CategoryID != nil {
			if row, err := d.store.LoadCategory(r.Context(), *q.CategoryID); err == nil && row != nil {
				category = map[string]any{
					"id": row.ID, "name": row.Name, "description": row.Description,
					"parent_id": row.ParentID, "created_at": row.CreatedAt,
				}
			}
		}
		tagIDs, err := d.store.QuestionTagIDs(r.Context(), q.ID)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memuat tag soal")
			return
		}
		tagRows, err := d.store.LoadTags(r.Context(), tagIDs)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memuat tag soal")
			return
		}
		tags := make([]any, 0, len(tagRows))
		for _, tag := range tagRows {
			tags = append(tags, map[string]any{"id": tag.ID, "name": tag.Name, "color": tag.Color})
		}
		out = append(out, questionJSON(q, category, tags))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) createQuestion(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadQuestionExam(w, r, userID, claims, false)
	if !ok {
		return
	}
	in, errMsg := readQuestionWrite(r)
	if errMsg != "" {
		writeDetail(w, http.StatusBadRequest, errMsg)
		return
	}
	q, err := d.store.CreateQuestion(r.Context(), ex.ID, in)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat soal")
		return
	}
	d.writeQuestion(r.Context(), w, http.StatusCreated, q, in.TagIDs)
}

func (d deps) updateQuestion(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	q, ok := d.loadMutableQuestion(w, r, userID, claims)
	if !ok {
		return
	}
	in, errMsg := readQuestionWrite(r)
	if errMsg != "" {
		writeDetail(w, http.StatusBadRequest, errMsg)
		return
	}
	updated, err := d.store.UpdateQuestion(r.Context(), q, in)
	if errors.Is(err, persistence.ErrQuestionTypeLocked) {
		writeDetail(w, http.StatusBadRequest, "Tipe soal tidak dapat diubah karena sudah ada jawaban siswa. Duplikasi soal/ujian jika ingin mengganti tipe.")
		return
	}
	if errors.Is(err, persistence.ErrOptionsProtected) {
		writeDetail(w, http.StatusBadRequest, "Sebagian opsi lama sudah dipakai jawaban siswa, jadi tidak bisa dihapus. Kurangi perubahan struktur opsi atau duplikasi ujian untuk sesi berikutnya.")
		return
	}
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memperbarui soal")
		return
	}
	d.writeQuestion(r.Context(), w, http.StatusOK, updated, in.TagIDs)
}

func (d deps) deleteQuestion(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	q, ok := d.loadMutableQuestion(w, r, userID, claims)
	if !ok {
		return
	}
	if err := d.store.DeleteQuestion(r.Context(), q.ID); err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "foreign key") {
			writeDetail(w, http.StatusBadRequest, "Soal tidak dapat dihapus karena sudah ada jawaban siswa")
			return
		}
		writeDetail(w, http.StatusInternalServerError, "Gagal menghapus soal")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (d deps) loadQuestionExam(w http.ResponseWriter, r *http.Request, userID int, claims *auth.Claims, viewOnly bool) (*persistence.ExamRow, bool) {
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
		return nil, false
	}
	return d.authorizeExam(w, r, examID, userID, claims, viewOnly)
}

func (d deps) loadMutableQuestion(w http.ResponseWriter, r *http.Request, userID int, claims *auth.Claims) (*persistence.QuestionRow, bool) {
	questionID, err := strconv.Atoi(r.PathValue("question_id"))
	if err != nil || questionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "question_id tidak valid")
		return nil, false
	}
	q, err := d.store.GetQuestion(r.Context(), questionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat soal")
		return nil, false
	}
	if q == nil {
		writeDetail(w, http.StatusNotFound, "Soal tidak ditemukan")
		return nil, false
	}
	if _, ok := d.authorizeExam(w, r, q.ExamID, userID, claims, false); !ok {
		return nil, false
	}
	return q, true
}

func (d deps) authorizeExam(w http.ResponseWriter, r *http.Request, examID, userID int, claims *auth.Claims, viewOnly bool) (*persistence.ExamRow, bool) {
	ex, err := d.store.GetExam(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian")
		return nil, false
	}
	if ex == nil || ex.Deleted {
		writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
		return nil, false
	}
	if viewOnly {
		ok, hidden := staffCanViewExam(ex, userID, claims.Role, claims.JobTitle)
		if !ok {
			if hidden {
				writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
				return nil, false
			}
			writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
			return nil, false
		}
		return ex, true
	}
	ok, hidden, detail := staffCanMutateExam(ex, userID, claims.Role, claims.JobTitle, false)
	if !ok {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return nil, false
		}
		writeDetail(w, http.StatusForbidden, detail)
		return nil, false
	}
	return ex, true
}

func (d deps) writeQuestion(ctx context.Context, w http.ResponseWriter, code int, q *persistence.QuestionRow, tagIDs []int) {
	var cat any
	if q != nil && q.CategoryID != nil {
		if row, err := d.store.LoadCategory(ctx, *q.CategoryID); err == nil && row != nil {
			cat = map[string]any{
				"id": row.ID, "name": row.Name, "description": row.Description,
				"parent_id": row.ParentID, "created_at": row.CreatedAt,
			}
		}
	}
	tags := []any{}
	if loaded, err := d.store.LoadTags(ctx, tagIDs); err == nil {
		for _, t := range loaded {
			tags = append(tags, map[string]any{"id": t.ID, "name": t.Name, "color": t.Color})
		}
	}
	writeJSON(w, code, questionJSON(q, cat, tags))
}

func questionJSON(q *persistence.QuestionRow, category any, tags []any) map[string]any {
	if tags == nil {
		tags = []any{}
	}
	opts := make([]map[string]any, 0, len(q.Options))
	for _, o := range q.Options {
		opts = append(opts, map[string]any{
			"id":           o.ID,
			"option_text":  o.Text,
			"order_index":  o.OrderIndex,
			"option_group": o.OptionGroup,
			"is_correct":   o.IsCorrect,
			"pair_id":      o.PairID,
		})
	}
	settings := any(map[string]any{})
	if len(q.Settings) > 0 {
		var raw any
		if json.Unmarshal(q.Settings, &raw) == nil {
			settings = raw
		}
	}
	return map[string]any{
		"id":                q.ID,
		"question_text":     q.Text,
		"stimulus":          q.Stimulus,
		"question_type":     q.Type,
		"pgk_type":          q.PgkType,
		"difficulty_level":  q.Difficulty,
		"category":          category,
		"tags":              tags,
		"question_settings": settings,
		"points":            q.Points,
		"order_index":       q.OrderIndex,
		"image_url":         q.ImageURL,
		"video_url":         q.VideoURL,
		"audio_url":         q.AudioURL,
		"options":           opts,
	}
}

func readQuestionWrite(r *http.Request) (persistence.QuestionWrite, string) {
	var body questionPayload
	if err := readJSON(r, &body); err != nil {
		return persistence.QuestionWrite{}, "Payload tidak valid"
	}
	qtype := strings.TrimSpace(body.QuestionType)
	if qtype == "" {
		qtype = "multiple_choice"
	}
	if _, ok := allowedQuestionTypes[qtype]; !ok {
		return persistence.QuestionWrite{}, "Tipe soal tidak valid"
	}
	if body.OrderIndex == nil {
		return persistence.QuestionWrite{}, "order_index wajib diisi"
	}
	text := clipText(body.QuestionText, 10000)
	var stimulus *string
	if body.Stimulus != nil {
		s := clipText(*body.Stimulus, 5000)
		stimulus = &s
	}
	image, err := safeMediaURL(body.ImageURL)
	if err != nil {
		return persistence.QuestionWrite{}, err.Error()
	}
	video, err := safeMediaURL(body.VideoURL)
	if err != nil {
		return persistence.QuestionWrite{}, err.Error()
	}
	audio, err := safeMediaURL(body.AudioURL)
	if err != nil {
		return persistence.QuestionWrite{}, err.Error()
	}
	diff := strings.TrimSpace(body.DifficultyLevel)
	if diff == "" {
		diff = "medium"
	}
	points := 1.0
	if body.Points != nil {
		if *body.Points < 0 {
			return persistence.QuestionWrite{}, "Nilai soal tidak valid"
		}
		points = *body.Points
	}
	var pgk *string
	if qtype == "multiple_choice_complex" {
		v := "checkbox"
		if body.PgkType != nil && strings.TrimSpace(*body.PgkType) != "" {
			v = strings.TrimSpace(*body.PgkType)
		}
		pgk = &v
	}
	settings := map[string]any{}
	if len(body.QuestionSettings) > 0 {
		_ = json.Unmarshal(body.QuestionSettings, &settings)
	}
	if stimulus != nil {
		settings["stimulus"] = *stimulus
	} else {
		settings["stimulus"] = nil
	}
	opts := make([]persistence.OptionWrite, 0, len(body.Options))
	for _, o := range body.Options {
		group := strings.TrimSpace(o.OptionGroup)
		if group == "" {
			group = "standard"
		}
		correct := false
		if o.IsCorrect != nil {
			correct = *o.IsCorrect
		}
		opts = append(opts, persistence.OptionWrite{
			Text:        clipText(o.OptionText, 5000),
			IsCorrect:   correct,
			OrderIndex:  o.OrderIndex,
			OptionGroup: group,
			PairID:      emptyToNil(o.PairID),
		})
	}
	return persistence.QuestionWrite{
		Text:       text,
		Stimulus:   stimulus,
		Type:       qtype,
		Subtype:    emptyToNil(body.QuestionSubtype),
		PgkType:    pgk,
		Difficulty: diff,
		CategoryID: body.CategoryID,
		TagIDs:     body.TagIDs,
		Settings:   persistence.MustJSON(settings),
		Points:     points,
		OrderIndex: *body.OrderIndex,
		ImageURL:   image,
		VideoURL:   video,
		AudioURL:   audio,
		Options:    opts,
	}, ""
}

func clipText(s string, n int) string {
	s = strings.TrimSpace(htmlTag.ReplaceAllString(s, ""))
	if utf8.RuneCountInString(s) <= n {
		return s
	}
	return string([]rune(s)[:n])
}

func safeMediaURL(raw *string) (*string, error) {
	if raw == nil {
		return nil, nil
	}
	cleaned := strings.TrimSpace(*raw)
	if cleaned == "" {
		return nil, nil
	}
	parsed, err := url.Parse(cleaned)
	if err != nil {
		return nil, errors.New("URL media tidak valid")
	}
	if parsed.Scheme != "" {
		scheme := strings.ToLower(parsed.Scheme)
		if scheme != "http" && scheme != "https" {
			return nil, errors.New("URL media tidak valid")
		}
		return clipPtr(cleaned, 255), nil
	}
	if strings.HasPrefix(cleaned, "/") {
		return clipPtr(cleaned, 255), nil
	}
	return nil, errors.New("URL media harus relatif atau HTTP/HTTPS")
}

func clipPtr(s string, n int) *string {
	if utf8.RuneCountInString(s) > n {
		s = string([]rune(s)[:n])
	}
	return &s
}

func emptyToNil(v *string) *string {
	if v == nil {
		return nil
	}
	s := strings.TrimSpace(*v)
	if s == "" {
		return nil
	}
	return &s
}
