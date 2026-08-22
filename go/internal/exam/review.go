package exam

import (
	"encoding/json"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"siab1/internal/persistence"
)

var questionTypeLabels = map[string]string{
	"multiple_choice":         "Pilihan Ganda",
	"multiple_choice_complex": "PG Kompleks",
	"true_false":              "Benar / Salah",
	"essay":                   "Essay",
	"short_answer":            "Isian Singkat",
}

func (d deps) sessionReview(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
		return
	}
	sessionID, err := strconv.Atoi(r.PathValue("session_id"))
	if err != nil || sessionID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "session_id tidak valid")
		return
	}
	sess, err := d.store.GetControlSession(r.Context(), sessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat sesi")
		return
	}
	if sess == nil || sess.ExamID != examID || sess.Deleted {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	ex, err := d.store.GetExam(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian")
		return
	}
	if ex == nil {
		writeDetail(w, http.StatusNotFound, "Sesi ujian tidak ditemukan")
		return
	}
	okView, hidden := staffCanViewResults(ex, userID, claims.Role)
	if !okView {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return
		}
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	questions, err := d.store.LoadQuestionsForGrade(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat soal")
		return
	}
	answers, err := d.store.ListAnswers(r.Context(), sessionID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat jawaban")
		return
	}
	byQ := map[int]persistence.AnswerRow{}
	for _, a := range answers {
		byQ[a.QuestionID] = a
	}
	items := make([]map[string]any, 0, len(questions))
	correct, partial, incorrect, pending, unanswered := 0, 0, 0, 0, 0
	for i, q := range questions {
		item, status := reviewItem(q, byQ[q.ID], i+1)
		switch status {
		case "correct":
			correct++
		case "partial":
			partial++
		case "pending":
			pending++
		case "not_answered":
			unanswered++
		default:
			incorrect++
		}
		items = append(items, item)
	}
	sort.SliceStable(items, func(i, j int) bool {
		oi, _ := items[i]["order_index"].(int)
		oj, _ := items[j]["order_index"].(int)
		if oi != oj {
			return oi < oj
		}
		ii, _ := items[i]["question_id"].(int)
		ij, _ := items[j]["question_id"].(int)
		return ii < ij
	})
	score := 0.0
	if sess.Score != nil {
		score = *sess.Score
	}
	pass := 70.0
	if ex.PassingScore != nil {
		pass = *ex.PassingScore
	}
	name := sess.UserName
	if name == "" {
		name = sess.Username
	}
	cls := ""
	if sess.Class != nil {
		cls = *sess.Class
	}
	var started, ended any
	if sess.StartTime != nil {
		started = sess.StartTime.UTC().Format(time.RFC3339)
	}
	if sess.EndTime != nil {
		ended = sess.EndTime.UTC().Format(time.RFC3339)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"session_id": sess.SessionID,
		"exam": map[string]any{
			"id": ex.ID, "title": ex.Title, "subject": deref(ex.Subject),
			"exam_type": deref(ex.ExamType), "passing_score": pass,
		},
		"student": map[string]any{
			"id": sess.UserID, "full_name": name, "username": sess.Username, "student_class": cls,
		},
		"session": map[string]any{
			"status": sess.Status, "start_time": started, "end_time": ended,
			"score": score, "passed": score >= pass,
		},
		"summary": map[string]any{
			"total_questions": len(questions), "answered_questions": len(questions) - unanswered,
			"correct": correct, "partial": partial, "incorrect": incorrect,
			"pending": pending, "unanswered": unanswered,
		},
		"questions":    items,
		"generated_at": time.Now().UTC().Format(time.RFC3339),
	})
}

func reviewItem(q persistence.QuestionRow, ans persistence.AnswerRow, number int) (map[string]any, string) {
	has := ans.QuestionID == q.ID
	var ansPtr *persistence.AnswerRow
	if has {
		ansPtr = &ans
	}
	status := reviewStatus(ansPtr, q.Points)
	earned := 0.0
	var isCorrect any
	var answered any
	if has {
		if ans.Points != nil {
			earned = *ans.Points
		}
		if ans.IsCorrect != nil {
			isCorrect = *ans.IsCorrect
		}
		if ans.AnsweredAt != nil {
			answered = ans.AnsweredAt.UTC().Format(time.RFC3339)
		}
	}
	opts := reviewOptions(q.Options)
	student, key := reviewAnswers(q, ansPtr, opts)
	label := questionTypeLabels[q.Type]
	if label == "" {
		label = q.Type
	}
	stim := ""
	if q.Stimulus != nil {
		stim = *q.Stimulus
	}
	return map[string]any{
		"question_id": q.ID, "order_index": q.OrderIndex, "question_number": number,
		"question_type": q.Type, "question_type_label": label, "question_text": q.Text,
		"stimulus": stim, "max_points": q.Points, "points_earned": earned, "status": status,
		"is_correct": isCorrect, "answered_at": answered,
		"student_answer": student, "answer_key": key,
		"student_answer_display": student["display"], "answer_key_display": key["display"],
		"options": opts,
	}, status
}

func reviewStatus(ans *persistence.AnswerRow, max float64) string {
	if ans == nil {
		return "not_answered"
	}
	if ans.Points == nil {
		return "pending"
	}
	pts := *ans.Points
	if ans.IsCorrect != nil && *ans.IsCorrect {
		return "correct"
	}
	if ans.IsCorrect != nil && !*ans.IsCorrect && pts <= 0 {
		return "incorrect"
	}
	if max > 0 {
		if pts >= max {
			return "correct"
		}
		if pts > 0 {
			return "partial"
		}
	}
	return "incorrect"
}

func reviewOptions(opts []persistence.OptionRow) []map[string]any {
	sorted := append([]persistence.OptionRow(nil), opts...)
	sort.SliceStable(sorted, func(i, j int) bool {
		if sorted[i].OrderIndex != sorted[j].OrderIndex {
			return sorted[i].OrderIndex < sorted[j].OrderIndex
		}
		return sorted[i].ID < sorted[j].ID
	})
	out := make([]map[string]any, 0, len(sorted))
	for i, o := range sorted {
		out = append(out, map[string]any{
			"id": o.ID, "label": optionLabel(i), "text": o.Text, "is_correct": o.IsCorrect,
		})
	}
	return out
}

func reviewAnswers(q persistence.QuestionRow, ans *persistence.AnswerRow, opts []map[string]any) (map[string]any, map[string]any) {
	student := map[string]any{"type": q.Type, "display": "-"}
	key := map[string]any{"type": q.Type, "display": "-"}
	byID := map[int]map[string]any{}
	var correct []map[string]any
	for _, o := range opts {
		id, _ := o["id"].(int)
		byID[id] = o
		if ok, _ := o["is_correct"].(bool); ok {
			correct = append(correct, o)
		}
	}
	settings := map[string]any{}
	_ = json.Unmarshal(q.Settings, &settings)
	switch q.Type {
	case "multiple_choice", "true_false":
		if ans != nil && ans.SelectedOptionID != nil {
			if o := byID[*ans.SelectedOptionID]; o != nil {
				disp := o["label"].(string) + ". " + o["text"].(string)
				student["selected_option_id"] = o["id"]
				student["selected_option_label"] = o["label"]
				student["selected_option_text"] = o["text"]
				student["display"] = disp
			}
		}
		if len(correct) > 0 {
			o := correct[0]
			disp := o["label"].(string) + ". " + o["text"].(string)
			key["correct_option_id"] = o["id"]
			key["correct_option_label"] = o["label"]
			key["correct_option_text"] = o["text"]
			key["display"] = disp
		}
	case "multiple_choice_complex":
		pgk := "checkbox"
		if q.PgkType != nil && *q.PgkType != "" {
			pgk = *q.PgkType
		} else if v, _ := settings["pgk_type"].(string); v != "" {
			pgk = v
		}
		if pgk == "table_validation" {
			return tableReview(q.Type, settings, ans)
		}
		var selected []map[string]any
		if ans != nil {
			for _, id := range ans.SelectedOptionIDs {
				if o := byID[int(id)]; o != nil {
					selected = append(selected, o)
				}
			}
		}
		student["pgk_type"] = "checkbox"
		student["selected_option_ids"] = idsOf(selected)
		student["selected_options"] = selected
		student["display"] = joinOpts(selected)
		key["pgk_type"] = "checkbox"
		key["correct_option_ids"] = idsOf(correct)
		key["correct_options"] = correct
		key["display"] = joinOpts(correct)
	case "short_answer":
		text := "-"
		if ans != nil && ans.AnswerText != nil && strings.TrimSpace(*ans.AnswerText) != "" {
			text = strings.TrimSpace(*ans.AnswerText)
		}
		accepted := stringList(settings["acceptable_answers"])
		student["answer_text"] = strings.TrimPrefix(text, "-")
		if text == "-" {
			student["answer_text"] = ""
		}
		student["display"] = text
		key["acceptable_answers"] = accepted
		if len(accepted) > 0 {
			key["display"] = strings.Join(accepted, " / ")
		}
	default:
		text := "-"
		if ans != nil && ans.AnswerText != nil && strings.TrimSpace(*ans.AnswerText) != "" {
			text = strings.TrimSpace(*ans.AnswerText)
		}
		sample := strings.TrimSpace(asSettingString(settings, "answer_key"))
		if sample == "" {
			sample = strings.TrimSpace(asSettingString(settings, "sample_answer"))
		}
		student["answer_text"] = ""
		if text != "-" {
			student["answer_text"] = text
		}
		student["display"] = text
		key["sample_answer"] = sample
		if sample != "" {
			key["display"] = sample
		}
	}
	return student, key
}

func tableReview(qtype string, settings map[string]any, ans *persistence.AnswerRow) (map[string]any, map[string]any) {
	stmts := statementList(settings)
	keys := statementKeys(settings, len(stmts))
	studentAns := map[string]any{}
	if ans != nil {
		var meta map[string]any
		if json.Unmarshal(ans.Metadata, &meta) == nil {
			if m, ok := meta["statement_answers"].(map[string]any); ok {
				studentAns = m
			}
		}
	}
	maxN := len(stmts)
	if len(keys) > maxN {
		maxN = len(keys)
	}
	if len(studentAns) > maxN {
		maxN = len(studentAns)
	}
	rows := []map[string]any{}
	sLines, kLines := []string{}, []string{}
	for i := 0; i < maxN; i++ {
		text := "Pernyataan " + strconv.Itoa(i+1)
		if i < len(stmts) {
			text = stmts[i]
		}
		key := strconv.Itoa(i)
		correct := coerceReviewBool(keys[key])
		got := coerceReviewBool(studentAns[key])
		rows = append(rows, map[string]any{
			"index": i + 1, "statement": text, "student_answer": got, "correct_answer": correct,
		})
		sLines = append(sLines, strconv.Itoa(i+1)+". "+text+": "+boolLabel(got))
		kLines = append(kLines, strconv.Itoa(i+1)+". "+text+": "+boolLabel(correct))
	}
	sDisp, kDisp := "-", "-"
	if len(sLines) > 0 {
		sDisp = strings.Join(sLines, " | ")
	}
	if len(kLines) > 0 {
		kDisp = strings.Join(kLines, " | ")
	}
	student := map[string]any{"type": qtype, "pgk_type": "table_validation", "rows": rows, "display": sDisp}
	key := map[string]any{"type": qtype, "pgk_type": "table_validation", "rows": rows, "display": kDisp}
	return student, key
}

func optionLabel(idx int) string {
	n := idx
	if n < 0 {
		n = 0
	}
	label := ""
	for {
		rem := n % 26
		label = string(rune('A'+rem)) + label
		n = n / 26
		if n == 0 {
			break
		}
		n--
	}
	return label
}

func joinOpts(opts []map[string]any) string {
	if len(opts) == 0 {
		return "-"
	}
	parts := make([]string, 0, len(opts))
	for _, o := range opts {
		parts = append(parts, o["label"].(string)+". "+o["text"].(string))
	}
	return strings.Join(parts, ", ")
}

func idsOf(opts []map[string]any) []int {
	out := make([]int, 0, len(opts))
	for _, o := range opts {
		if id, ok := o["id"].(int); ok {
			out = append(out, id)
		}
	}
	return out
}

func stringList(v any) []string {
	list, ok := v.([]any)
	if !ok {
		return []string{}
	}
	out := []string{}
	for _, item := range list {
		s := strings.TrimSpace(asSettingString(map[string]any{"v": item}, "v"))
		if s == "" {
			if t, ok := item.(string); ok {
				s = strings.TrimSpace(t)
			}
		}
		if s != "" {
			out = append(out, s)
		}
	}
	return out
}

func asSettingString(m map[string]any, key string) string {
	v, ok := m[key]
	if !ok || v == nil {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func statementList(settings map[string]any) []string {
	raw, _ := settings["statements"].([]any)
	out := []string{}
	for _, item := range raw {
		switch t := item.(type) {
		case string:
			if s := strings.TrimSpace(t); s != "" {
				out = append(out, s)
			}
		case map[string]any:
			s := strings.TrimSpace(asSettingString(t, "text"))
			if s == "" {
				s = strings.TrimSpace(asSettingString(t, "statement"))
			}
			if s != "" {
				out = append(out, s)
			}
		}
	}
	return out
}

func statementKeys(settings map[string]any, n int) map[string]any {
	out := map[string]any{}
	if list, ok := settings["statement_answers"].([]any); ok {
		for i, v := range list {
			out[strconv.Itoa(i)] = v
		}
	} else if m, ok := settings["correct_statements"].(map[string]any); ok {
		for k, v := range m {
			out[k] = v
		}
	}
	for i := 0; i < n; i++ {
		if _, ok := out[strconv.Itoa(i)]; !ok {
			out[strconv.Itoa(i)] = nil
		}
	}
	return out
}

func coerceReviewBool(v any) any {
	switch t := v.(type) {
	case bool:
		return t
	case float64:
		return t != 0
	case json.Number:
		n, _ := t.Float64()
		return n != 0
	case string:
		s := strings.ToLower(strings.TrimSpace(t))
		if s == "true" || s == "1" || s == "yes" || s == "y" || s == "benar" {
			return true
		}
		if s == "false" || s == "0" || s == "no" || s == "n" || s == "salah" {
			return false
		}
	}
	return nil
}

func boolLabel(v any) string {
	switch v {
	case true:
		return "Benar"
	case false:
		return "Salah"
	default:
		return "-"
	}
}
