package exam

import (
	"bytes"
	"crypto/md5"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"siab1/internal/persistence"
)

type startOptionResponse struct {
	ID          int     `json:"id"`
	OptionText  string  `json:"option_text"`
	OrderIndex  int     `json:"order_index"`
	OptionGroup string  `json:"option_group"`
	PairID      *string `json:"pair_id"`
}

type startQuestionResponse struct {
	ID               int                   `json:"id"`
	QuestionText     string                `json:"question_text"`
	Stimulus         *string               `json:"stimulus"`
	QuestionType     string                `json:"question_type"`
	PgkType          *string               `json:"pgk_type"`
	DifficultyLevel  string                `json:"difficulty_level"`
	Category         any                   `json:"category"`
	Tags             []any                 `json:"tags"`
	QuestionSettings map[string]any        `json:"question_settings"`
	Points           string                `json:"points"`
	OrderIndex       int                   `json:"order_index"`
	ImageURL         *string               `json:"image_url"`
	VideoURL         *string               `json:"video_url"`
	AudioURL         *string               `json:"audio_url"`
	Options          []startOptionResponse `json:"options"`
}

func buildStartQuestions(
	rows []persistence.QuestionRow,
	examID int,
	userID int,
	shuffleQuestionsEnabled bool,
	shuffleOptionsEnabled bool,
	secret string,
) ([]startQuestionResponse, *startHTTPError) {
	questions := append([]persistence.QuestionRow(nil), rows...)
	sort.SliceStable(questions, func(i, j int) bool {
		return questions[i].OrderIndex < questions[j].OrderIndex
	})
	if shuffleQuestionsEnabled {
		sort.SliceStable(questions, func(i, j int) bool {
			left := md5.Sum([]byte(fmt.Sprintf(
				"%s_%d_%d_question_%d", secret, userID, examID, questions[i].ID,
			)))
			right := md5.Sum([]byte(fmt.Sprintf(
				"%s_%d_%d_question_%d", secret, userID, examID, questions[j].ID,
			)))
			return bytes.Compare(left[:], right[:]) < 0
		})
	}

	responses := make([]startQuestionResponse, 0, len(questions))
	skipped := 0
	for _, question := range questions {
		settings := decodeQuestionSettings(question.Settings)
		text := strings.TrimSpace(question.Text)
		placeholder := boolSetting(settings, "is_placeholder")
		placeholderSource := strings.ToLower(strings.TrimSpace(stringSetting(settings, "placeholder_source")))
		hasImage := question.ImageURL != nil && *question.ImageURL != ""
		if text == "" {
			if placeholder && hasImage && placeholderSource == "image" {
				text = "Perhatikan gambar soal berikut, lalu pilih jawaban yang benar."
			} else {
				skipped++
				continue
			}
		}

		pgk := "checkbox"
		if question.PgkType != nil && *question.PgkType != "" {
			pgk = *question.PgkType
		} else if configured := stringSetting(settings, "pgk_type"); configured != "" {
			pgk = configured
		}
		tableValidation := question.Type == "multiple_choice_complex" && pgk == "table_validation"
		requiresOptions := !tableValidation && (question.Type == "multiple_choice" ||
			question.Type == "multiple_choice_complex" ||
			question.Type == "true_false")
		options := append([]persistence.OptionRow(nil), question.Options...)
		sort.SliceStable(options, func(i, j int) bool {
			return options[i].OrderIndex < options[j].OrderIndex
		})
		if requiresOptions && len(options) == 0 {
			skipped++
			continue
		}
		if requiresOptions && shuffleOptionsEnabled && canShuffleStartOptions(settings, hasImage) {
			seed := fmt.Sprintf(
				"%s_%d_%d_question_%d_options", secret, userID, examID, question.ID,
			)
			pythonShuffle(options, seed)
		}
		optionResponses := make([]startOptionResponse, 0, len(options))
		if requiresOptions {
			for _, option := range options {
				group := option.OptionGroup
				if group == "" {
					group = "standard"
				}
				optionResponses = append(optionResponses, startOptionResponse{
					ID:          option.ID,
					OptionText:  option.Text,
					OrderIndex:  option.OrderIndex,
					OptionGroup: group,
					PairID:      option.PairID,
				})
			}
		}

		if tableValidation {
			allowed := true
			if raw, exists := settings["allow_table_statement_shuffle"]; exists {
				allowed = pythonTruthy(raw)
			}
			settings["allow_table_statement_shuffle"] = allowed
			if shuffleOptionsEnabled && allowed {
				shuffleTableStatements(settings, hasImage, fmt.Sprintf(
					"%s_%d_%d_question_%d_statements",
					secret, userID, examID, question.ID,
				))
			}
		}

		difficulty := "medium"
		if question.Difficulty != "" {
			difficulty = question.Difficulty
		}
		responses = append(responses, startQuestionResponse{
			ID:               question.ID,
			QuestionText:     text,
			Stimulus:         question.Stimulus,
			QuestionType:     question.Type,
			PgkType:          question.PgkType,
			DifficultyLevel:  difficulty,
			Category:         nil,
			Tags:             []any{},
			QuestionSettings: settings,
			Points:           pythonDecimalFromFloat(question.Points),
			OrderIndex:       question.OrderIndex,
			ImageURL:         question.ImageURL,
			VideoURL:         question.VideoURL,
			AudioURL:         question.AudioURL,
			Options:          optionResponses,
		})
	}
	if skipped > 0 {
		return nil, startError(
			500,
			fmt.Sprintf(
				"Gagal memuat %d soal dari ujian. Data ujian tidak lengkap. Silakan hubungi pengawas atau administrator.",
				skipped,
			),
		)
	}
	return responses, nil
}

func decodeQuestionSettings(raw []byte) map[string]any {
	settings := map[string]any{}
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &settings)
	}
	return settings
}

func canShuffleStartOptions(settings map[string]any, hasImage bool) bool {
	if !boolSetting(settings, "is_placeholder") {
		return true
	}
	if hasImage || strings.EqualFold(strings.TrimSpace(stringSetting(settings, "placeholder_source")), "image") {
		return false
	}
	return boolSetting(settings, "allow_placeholder_shuffle")
}

func shuffleTableStatements(settings map[string]any, hasImage bool, seed string) {
	raw, ok := settings["statements"].([]any)
	if !ok || len(raw) == 0 || hasImage {
		return
	}
	meaningful := map[string]struct{}{}
	for _, statement := range raw {
		text := ""
		if object, ok := statement.(map[string]any); ok {
			value, exists := object["text"]
			if exists {
				text = strings.TrimSpace(pyString(value))
			}
		} else {
			text = strings.TrimSpace(pyString(statement))
		}
		if text != "" && text != "-" && text != "--" && text != "\u2014" && text != "\u2013" {
			meaningful[text] = struct{}{}
		}
	}
	if len(meaningful) < 2 {
		return
	}
	indexed := make([]any, 0, len(raw))
	for index, statement := range raw {
		indexed = append(indexed, map[string]any{
			"text":           statement,
			"original_index": index,
		})
	}
	pythonShuffle(indexed, seed)
	settings["statements"] = indexed
}

func pythonTruthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case float64:
		return typed != 0
	case json.Number:
		return typed.String() != "0" && typed.String() != "0.0"
	case []any:
		return len(typed) > 0
	case map[string]any:
		return len(typed) > 0
	default:
		return true
	}
}

func boolSetting(settings map[string]any, key string) bool {
	value, ok := settings[key]
	return ok && pythonTruthy(value)
}

func stringSetting(settings map[string]any, key string) string {
	value, _ := settings[key].(string)
	return value
}

func pyString(value any) string {
	if value == nil {
		return "None"
	}
	if typed, ok := value.(bool); ok {
		if typed {
			return "True"
		}
		return "False"
	}
	return fmt.Sprint(value)
}

func pythonDecimalFromFloat(value float64) string {
	formatted := strconv.FormatFloat(value, 'f', -1, 64)
	if !strings.Contains(formatted, ".") {
		formatted += ".0"
	}
	return formatted
}
