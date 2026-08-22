package exam

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

type templatePayload struct {
	Name        string          `json:"name"`
	Description *string         `json:"description"`
	Data        json.RawMessage `json:"template_data"`
	Public      bool            `json:"is_public"`
}

type templateUpdatePayload struct {
	Name        *string          `json:"name"`
	Description *string          `json:"description"`
	Data        *json.RawMessage `json:"template_data"`
	Public      *bool            `json:"is_public"`
}

type templateExamPayload struct {
	Title           string   `json:"title"`
	Description     *string  `json:"description"`
	StartTime       string   `json:"start_time"`
	EndTime         string   `json:"end_time"`
	AllowedClasses  *string  `json:"allowed_classes"`
	DurationMinutes *int     `json:"duration_minutes"`
	PassingScore    *float64 `json:"passing_score"`
	MaxAttempts     *int     `json:"max_attempts"`
}

type templateConfig struct {
	DurationMinutes  *int               `json:"duration_minutes"`
	PassingScore     *float64           `json:"passing_score"`
	MaxAttempts      *int               `json:"max_attempts"`
	ShuffleQuestions bool               `json:"shuffle_questions"`
	ShuffleOptions   bool               `json:"shuffle_options"`
	ShowResults      *bool              `json:"show_results"`
	AllowReview      bool               `json:"allow_review"`
	Questions        []templateQuestion `json:"questions"`
}

type templateQuestion struct {
	Text       string           `json:"question_text"`
	Type       *string          `json:"question_type"`
	Subtype    *string          `json:"question_subtype"`
	Difficulty *string          `json:"difficulty_level"`
	CategoryID *int             `json:"category_id"`
	Settings   json.RawMessage  `json:"question_settings"`
	Points     *float64         `json:"points"`
	OrderIndex int              `json:"order_index"`
	ImageURL   *string          `json:"image_url"`
	PgkType    *string          `json:"pgk_type"`
	Stimulus   *string          `json:"stimulus"`
	VideoURL   *string          `json:"video_url"`
	AudioURL   *string          `json:"audio_url"`
	Options    []templateOption `json:"options"`
}

type templateOption struct {
	Text       string          `json:"option_text"`
	Correct    bool            `json:"is_correct"`
	OrderIndex int             `json:"order_index"`
	Group      *string         `json:"option_group"`
	PairID     *string         `json:"pair_id"`
	Metadata   json.RawMessage `json:"option_metadata"`
}

func (d deps) listTemplates(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.templateUser(w, r)
	if !ok {
		return
	}
	page, ok := positiveQuery(w, r, "page", 1, 0)
	if !ok {
		return
	}
	perPage, ok := positiveQuery(w, r, "per_page", 20, 100)
	if !ok {
		return
	}
	publicOnly, err := queryBool(r.URL.Query().Get("public_only"))
	if err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "public_only tidak valid")
		return
	}
	rows, total, err := d.store.ListTemplates(r.Context(), persistence.TemplateListFilter{
		ViewerID: userID, ViewerRole: claims.Role, PublicOnly: publicOnly,
		Limit: perPage, Offset: (page - 1) * perPage,
	})
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat template")
		return
	}
	templates := make([]map[string]any, 0, len(rows))
	for i := range rows {
		templates = append(templates, templateJSON(&rows[i]))
	}
	writeJSON(w, http.StatusOK, map[string]any{"templates": templates, "total": total})
}

func (d deps) createTemplate(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.templateUser(w, r)
	if !ok {
		return
	}
	var body templatePayload
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	if !validTemplateName(body.Name) {
		writeDetail(w, http.StatusUnprocessableEntity, "Nama template harus 3-200 karakter")
		return
	}
	data, ok := jsonObject(body.Data)
	if !ok {
		writeDetail(w, http.StatusUnprocessableEntity, "template_data harus berupa objek")
		return
	}
	row, err := d.store.CreateTemplate(r.Context(), userID, persistence.TemplateWrite{
		Name: body.Name, Description: body.Description, Data: data,
		Public: body.Public && isAdminScope(claims.Role),
	})
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat template")
		return
	}
	writeJSON(w, http.StatusCreated, templateJSON(row))
}

func (d deps) getTemplate(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.templateUser(w, r)
	if !ok {
		return
	}
	row, ok := d.loadTemplate(w, r)
	if !ok {
		return
	}
	if allowed, hidden := templateCanAccess(row, userID, claims.Role, false); !allowed {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Template tidak ditemukan")
		} else {
			writeDetail(w, http.StatusForbidden, "Template tidak dapat diakses")
		}
		return
	}
	writeJSON(w, http.StatusOK, templateJSON(row))
}

func (d deps) updateTemplate(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.templateUser(w, r)
	if !ok {
		return
	}
	row, ok := d.loadTemplate(w, r)
	if !ok {
		return
	}
	if allowed, hidden := templateCanAccess(row, userID, claims.Role, true); !allowed {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Template tidak ditemukan")
		} else {
			writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		}
		return
	}
	var body templateUpdatePayload
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	if body.Name != nil && !validTemplateName(*body.Name) {
		writeDetail(w, http.StatusUnprocessableEntity, "Nama template harus 3-200 karakter")
		return
	}
	var data []byte
	updateData := body.Data != nil
	if updateData {
		var valid bool
		data, valid = jsonObject(*body.Data)
		if !valid {
			writeDetail(w, http.StatusUnprocessableEntity, "template_data harus berupa objek")
			return
		}
	}
	updated, err := d.store.UpdateTemplate(r.Context(), row.ID, persistence.TemplateUpdate{
		Name: body.Name, Description: body.Description, Data: data, UpdateData: updateData,
		Public: body.Public, CanSetPublic: isAdminScope(claims.Role),
	})
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memperbarui template")
		return
	}
	writeJSON(w, http.StatusOK, templateJSON(updated))
}

func (d deps) deleteTemplate(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.templateUser(w, r)
	if !ok {
		return
	}
	row, ok := d.loadTemplate(w, r)
	if !ok {
		return
	}
	if allowed, hidden := templateCanAccess(row, userID, claims.Role, true); !allowed {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Template tidak ditemukan")
		} else {
			writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		}
		return
	}
	if err := d.store.DeleteTemplate(r.Context(), row.ID); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menghapus template")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"message": "Template berhasil dihapus"})
}

func (d deps) createExamFromTemplate(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.templateUser(w, r)
	if !ok {
		return
	}
	row, ok := d.loadTemplate(w, r)
	if !ok {
		return
	}
	if allowed, hidden := templateCanAccess(row, userID, claims.Role, false); !allowed {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Template tidak ditemukan")
		} else {
			writeDetail(w, http.StatusForbidden, "Template tidak dapat diakses")
		}
		return
	}
	var body templateExamPayload
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	if utf8.RuneCountInString(body.Title) < 3 {
		writeDetail(w, http.StatusUnprocessableEntity, "Judul ujian minimal 3 karakter")
		return
	}
	start, err := parseFlexTime(body.StartTime)
	if err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Waktu mulai tidak valid")
		return
	}
	end, err := parseFlexTime(body.EndTime)
	if err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Waktu selesai tidak valid")
		return
	}
	if body.DurationMinutes != nil && *body.DurationMinutes < 1 {
		writeDetail(w, http.StatusUnprocessableEntity, "duration_minutes harus lebih dari 0")
		return
	}
	if body.PassingScore != nil && (*body.PassingScore < 0 || *body.PassingScore > 100) {
		writeDetail(w, http.StatusUnprocessableEntity, "passing_score harus antara 0 dan 100")
		return
	}
	if body.MaxAttempts != nil && *body.MaxAttempts < 1 {
		writeDetail(w, http.StatusUnprocessableEntity, "max_attempts harus lebih dari 0")
		return
	}
	write, err := buildTemplateExam(row.Data, body, start, end)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Konfigurasi template tidak valid")
		return
	}
	examRow, err := d.store.CreateExamFromTemplate(r.Context(), userID, write)
	if errors.Is(err, persistence.ErrTemplateAccessToken) {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat access token unik")
		return
	}
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal membuat ujian dari template")
		return
	}
	writeJSON(w, http.StatusCreated, examJSON(examRow))
}

func (d deps) templateUser(w http.ResponseWriter, r *http.Request) (int, *auth.Claims, bool) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return 0, nil, false
	}
	role := strings.ToLower(strings.TrimSpace(claims.Role))
	if role != "teacher" && role != "admin" && role != "developer" {
		writeDetail(w, http.StatusForbidden, "Akses ditolak. Hanya guru atau admin yang dapat mengakses.")
		return 0, nil, false
	}
	return userID, claims, true
}

func (d deps) loadTemplate(w http.ResponseWriter, r *http.Request) (*persistence.TemplateRow, bool) {
	templateID, err := strconv.Atoi(r.PathValue("template_id"))
	if err != nil || templateID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "template_id tidak valid")
		return nil, false
	}
	row, err := d.store.GetTemplate(r.Context(), templateID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat template")
		return nil, false
	}
	if row == nil {
		writeDetail(w, http.StatusNotFound, "Template tidak ditemukan")
		return nil, false
	}
	return row, true
}

func templateCanAccess(row *persistence.TemplateRow, userID int, role string, mutate bool) (bool, bool) {
	creatorRole := ""
	if row.CreatorRole != nil {
		creatorRole = *row.CreatorRole
	}
	if developerExamHidden(role, creatorRole) {
		return false, true
	}
	owned := row.CreatorID != nil && *row.CreatorID == userID
	if mutate {
		return owned || isAdminScope(role), false
	}
	return row.Public || owned || isAdminScope(role), false
}

func templateJSON(row *persistence.TemplateRow) map[string]any {
	data := map[string]any{}
	_ = json.Unmarshal(row.Data, &data)
	return map[string]any{
		"id": row.ID, "name": row.Name, "description": row.Description,
		"creator_id": row.CreatorID, "template_data": data, "is_public": row.Public,
		"created_at": row.CreatedAt.UTC().Format(time.RFC3339),
	}
}

func buildTemplateExam(raw []byte, body templateExamPayload, start, end time.Time) (persistence.TemplateExamWrite, error) {
	var config templateConfig
	if err := json.Unmarshal(raw, &config); err != nil {
		return persistence.TemplateExamWrite{}, err
	}
	duration := 60
	if config.DurationMinutes != nil {
		duration = *config.DurationMinutes
	}
	if body.DurationMinutes != nil {
		duration = *body.DurationMinutes
	}
	passing := 70.0
	if config.PassingScore != nil {
		passing = *config.PassingScore
	}
	if body.PassingScore != nil && *body.PassingScore != 0 {
		passing = *body.PassingScore
	}
	maxAttempts := 1
	if config.MaxAttempts != nil {
		maxAttempts = *config.MaxAttempts
	}
	if body.MaxAttempts != nil {
		maxAttempts = *body.MaxAttempts
	}
	showResults := true
	if config.ShowResults != nil {
		showResults = *config.ShowResults
	}
	questions := make([]persistence.TemplateQuestion, 0, len(config.Questions))
	for _, question := range config.Questions {
		questionType := "multiple_choice"
		if question.Type != nil {
			questionType = *question.Type
		}
		difficulty := "medium"
		if question.Difficulty != nil {
			difficulty = *question.Difficulty
		}
		points := 1.0
		if question.Points != nil {
			points = *question.Points
		}
		options := make([]persistence.TemplateOption, 0, len(question.Options))
		for _, option := range question.Options {
			group := "standard"
			if option.Group != nil {
				group = *option.Group
			}
			options = append(options, persistence.TemplateOption{
				Text: option.Text, Correct: option.Correct, OrderIndex: option.OrderIndex,
				Group: group, PairID: option.PairID, Metadata: rawOrDefault(option.Metadata),
			})
		}
		questions = append(questions, persistence.TemplateQuestion{
			Text: question.Text, Type: questionType, Subtype: question.Subtype,
			Difficulty: difficulty, CategoryID: question.CategoryID,
			Settings: rawOrDefault(question.Settings), Points: points, OrderIndex: question.OrderIndex,
			ImageURL: question.ImageURL, PgkType: question.PgkType, Stimulus: question.Stimulus,
			VideoURL: question.VideoURL, AudioURL: question.AudioURL, Options: options,
		})
	}
	return persistence.TemplateExamWrite{
		Exam: persistence.ExamWrite{
			Title: body.Title, Description: body.Description, DurationMinutes: duration,
			StartTime: start, EndTime: end, PassingScore: &passing, MaxAttempts: maxAttempts,
			ShuffleQuestions: config.ShuffleQuestions, ShuffleOptions: config.ShuffleOptions,
			ShowResults: showResults, AllowReview: config.AllowReview, Published: false,
			ShowTeacherName: true, BuilderSettings: []byte("{}"), AllowedClasses: body.AllowedClasses,
		},
		Questions: questions,
	}, nil
}

func validTemplateName(name string) bool {
	length := utf8.RuneCountInString(name)
	return length >= 3 && length <= 200
}

func jsonObject(raw json.RawMessage) ([]byte, bool) {
	if len(raw) == 0 || bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return nil, false
	}
	var object map[string]any
	if err := json.Unmarshal(raw, &object); err != nil || object == nil {
		return nil, false
	}
	return raw, true
}

func rawOrDefault(raw json.RawMessage) []byte {
	if len(raw) == 0 {
		return []byte("{}")
	}
	return raw
}

func positiveQuery(w http.ResponseWriter, r *http.Request, name string, fallback, max int) (int, bool) {
	raw := strings.TrimSpace(r.URL.Query().Get(name))
	if raw == "" {
		return fallback, true
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value < 1 || (max > 0 && value > max) {
		writeDetail(w, http.StatusUnprocessableEntity, name+" tidak valid")
		return 0, false
	}
	return value, true
}

func queryBool(raw string) (bool, error) {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "", "0", "false", "off", "no":
		return false, nil
	case "1", "true", "on", "yes":
		return true, nil
	default:
		return false, strconv.ErrSyntax
	}
}
