package exam

import (
	"encoding/json"
	"strconv"
	"strings"

	"siab1/internal/persistence"
)

func gradeAnswer(q persistence.QuestionRow, ans persistence.AnswerRow) (correct *bool, points *float64) {
	switch q.Type {
	case "multiple_choice", "true_false":
		ok, pts := gradeSingle(q, ans)
		return boolPtr(ok), floatPtr(pts)
	case "multiple_choice_complex":
		pgk := ""
		if q.PgkType != nil {
			pgk = *q.PgkType
		}
		if pgk == "" {
			pgk = settingString(q.Settings, "pgk_type", "checkbox")
		}
		if pgk == "table_validation" {
			ok, pts := gradeTable(q, ans)
			return boolPtr(ok), floatPtr(pts)
		}
		ok, pts := gradeComplex(q, ans)
		return boolPtr(ok), floatPtr(pts)
	case "essay":
		return nil, nil
	case "short_answer":
		return gradeShort(q, ans)
	default:
		return boolPtr(false), floatPtr(0)
	}
}

func gradeSingle(q persistence.QuestionRow, ans persistence.AnswerRow) (bool, float64) {
	if ans.SelectedOptionID == nil {
		return false, 0
	}
	for _, o := range q.Options {
		if o.ID == *ans.SelectedOptionID {
			if o.IsCorrect {
				return true, q.Points
			}
			return false, 0
		}
	}
	return false, 0
}

func gradeComplex(q persistence.QuestionRow, ans persistence.AnswerRow) (bool, float64) {
	if len(ans.SelectedOptionIDs) == 0 {
		return false, 0
	}
	correctIDs := map[int]struct{}{}
	for _, o := range q.Options {
		if o.IsCorrect {
			correctIDs[o.ID] = struct{}{}
		}
	}
	if len(correctIDs) == 0 {
		return false, 0
	}
	selected := map[int]struct{}{}
	for _, id := range ans.SelectedOptionIDs {
		selected[int(id)] = struct{}{}
	}
	correctCount := 0
	incorrectCount := 0
	for id := range selected {
		if _, ok := correctIDs[id]; ok {
			correctCount++
		} else {
			incorrectCount++
		}
	}
	if settingBool(q.Settings, "partial_scoring") {
		ratio := float64(correctCount-incorrectCount) / float64(len(correctIDs))
		if ratio < 0 {
			ratio = 0
		}
		return ratio >= 0.5, q.Points * ratio
	}
	if len(selected) != len(correctIDs) {
		return false, 0
	}
	for id := range correctIDs {
		if _, ok := selected[id]; !ok {
			return false, 0
		}
	}
	return true, q.Points
}

func gradeShort(q persistence.QuestionRow, ans persistence.AnswerRow) (*bool, *float64) {
	text := ""
	if ans.AnswerText != nil {
		text = strings.TrimSpace(*ans.AnswerText)
	}
	if text == "" {
		return nil, nil
	}
	if settingBool(q.Settings, "require_manual_grading") {
		return nil, nil
	}
	acceptable := settingStringSlice(q.Settings, "acceptable_answers")
	if len(acceptable) == 0 {
		return nil, nil
	}
	if !settingBool(q.Settings, "case_sensitive") {
		text = strings.ToLower(text)
		for i := range acceptable {
			acceptable[i] = strings.ToLower(acceptable[i])
		}
	}
	for _, want := range acceptable {
		if text == want {
			return boolPtr(true), floatPtr(q.Points)
		}
	}
	return boolPtr(false), floatPtr(0)
}

func gradeTable(q persistence.QuestionRow, ans persistence.AnswerRow) (bool, float64) {
	student := statementAnswers(ans)
	if len(student) == 0 {
		return false, 0
	}
	settings := map[string]any{}
	_ = json.Unmarshal(q.Settings, &settings)
	correct := map[string]bool{}
	if list, ok := settings["statement_answers"].([]any); ok && len(list) > 0 {
		for i, v := range list {
			if b, ok := coerceBool(v); ok {
				correct[strconv.Itoa(i)] = b
			}
		}
	} else if dict, ok := settings["correct_statements"].(map[string]any); ok {
		for k, v := range dict {
			if b, ok := coerceBool(v); ok {
				correct[k] = b
			}
		}
	}
	if len(correct) == 0 {
		return false, 0
	}
	hits := 0
	for k, want := range correct {
		if got, ok := student[k]; ok && got == want {
			hits++
		}
	}
	ratio := float64(hits) / float64(len(correct))
	return ratio == 1.0, q.Points * ratio
}

func statementAnswers(ans persistence.AnswerRow) map[string]bool {
	out := map[string]bool{}
	if len(ans.Metadata) == 0 {
		return out
	}
	var meta map[string]any
	if json.Unmarshal(ans.Metadata, &meta) != nil {
		return out
	}
	raw, ok := meta["statement_answers"]
	if !ok {
		return out
	}
	switch v := raw.(type) {
	case map[string]any:
		for k, val := range v {
			if b, ok := coerceBool(val); ok {
				out[k] = b
			}
		}
	}
	return out
}

func settingBool(raw []byte, key string) bool {
	settings := map[string]any{}
	_ = json.Unmarshal(raw, &settings)
	v, ok := settings[key]
	if !ok {
		return false
	}
	b, _ := coerceBool(v)
	return b
}

func settingString(raw []byte, key, fallback string) string {
	settings := map[string]any{}
	_ = json.Unmarshal(raw, &settings)
	if v, ok := settings[key].(string); ok && v != "" {
		return v
	}
	return fallback
}

func settingStringSlice(raw []byte, key string) []string {
	settings := map[string]any{}
	_ = json.Unmarshal(raw, &settings)
	list, ok := settings[key].([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(list))
	for _, item := range list {
		if s, ok := item.(string); ok {
			out = append(out, s)
		}
	}
	return out
}

func coerceBool(v any) (bool, bool) {
	switch t := v.(type) {
	case bool:
		return t, true
	case float64:
		return t != 0, true
	case json.Number:
		n, err := t.Int64()
		if err != nil {
			return false, false
		}
		return n != 0, true
	case string:
		switch strings.ToLower(strings.TrimSpace(t)) {
		case "true", "1", "yes", "y", "benar":
			return true, true
		case "false", "0", "no", "n", "salah":
			return false, true
		}
	}
	return false, false
}

func boolPtr(v bool) *bool { return &v }

func floatPtr(v float64) *float64 { return &v }
