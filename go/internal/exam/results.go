package exam

import (
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

func (d deps) examsWithResults(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	creatorID := 0
	if claims.Role == "teacher" {
		creatorID = userID
	}
	exams, err := d.store.ListExamsWithResults(r.Context(), creatorID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat hasil")
		return
	}
	out := make([]map[string]any, 0, len(exams))
	for i := range exams {
		out = append(out, examJSON(&exams[i]))
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) examResults(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadResultsExam(w, r, userID, claims)
	if !ok {
		return
	}
	rows, err := d.store.ListResultSessions(r.Context(), ex.ID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat hasil ujian")
		return
	}
	selected := pickLatestScored(rows)
	breakdown := strings.EqualFold(r.URL.Query().Get("include_breakdown"), "true")
	var questions []persistence.QuestionRow
	bySession := map[int]map[int]persistence.AnswerScore{}
	if breakdown && len(selected) > 0 {
		questions, err = d.store.LoadQuestionsForGrade(r.Context(), ex.ID)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memuat soal")
			return
		}
		ids := make([]int, 0, len(selected))
		for _, row := range selected {
			ids = append(ids, row.SessionID)
		}
		scores, err := d.store.ListAnswerScores(r.Context(), ids)
		if err != nil {
			writeDetail(w, http.StatusInternalServerError, "Gagal memuat rincian nilai")
			return
		}
		for _, ans := range scores {
			m := bySession[ans.SessionID]
			if m == nil {
				m = map[int]persistence.AnswerScore{}
				bySession[ans.SessionID] = m
			}
			m[ans.QuestionID] = ans
		}
	}
	pass := 70.0
	if ex.PassingScore != nil {
		pass = *ex.PassingScore
	}
	out := make([]map[string]any, 0, len(selected))
	for _, row := range selected {
		score := 0.0
		passed := false
		if row.Score != nil {
			score = *row.Score
			passed = score >= pass
		}
		dur := 0
		if row.StartTime != nil && row.EndTime != nil {
			dur = int(row.EndTime.Sub(*row.StartTime).Seconds())
			if dur < 0 {
				dur = 0
			}
		}
		class := ""
		if row.Class != nil {
			class = *row.Class
		}
		meta := map[string]any{}
		if breakdown {
			meta["score_breakdown"] = scoreBreakdown(questions, bySession[row.SessionID])
		}
		out = append(out, map[string]any{
			"id":      row.SessionID,
			"user_id": row.UserID,
			"user": map[string]any{
				"id":            row.UserID,
				"full_name":     row.FullName,
				"username":      row.Username,
				"student_class": class,
			},
			"exam": map[string]any{
				"id":            ex.ID,
				"title":         ex.Title,
				"subject":       deref(ex.Subject),
				"exam_type":     deref(ex.ExamType),
				"passing_score": pass,
			},
			"score":            score,
			"start_time":       rfcOrNil(row.StartTime),
			"end_time":         rfcOrNil(row.EndTime),
			"submitted_at":     rfcOrNil(row.EndTime),
			"duration_seconds": dur,
			"violation_count":  row.Violations,
			"passed":           passed,
			"status":           row.Status,
			"session_metadata": meta,
		})
	}
	writeJSON(w, http.StatusOK, out)
}

func (d deps) participationSummary(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	ex, ok := d.loadResultsExam(w, r, userID, claims)
	if !ok {
		return
	}
	classes := csvList(ex.AllowedClasses, false)
	students := csvList(ex.AllowedStudents, false)
	targets, err := d.store.ListTargetStudents(r.Context(), classes, students)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat peserta target")
		return
	}
	sessions, err := d.store.ListExamSessionUsers(r.Context(), ex.ID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat sesi")
		return
	}
	targetIDs := map[int]persistence.TargetStudent{}
	for _, t := range targets {
		targetIDs[t.ID] = t
	}
	byUser := map[int][]persistence.SessionUser{}
	submitted := map[int]struct{}{}
	for _, s := range sessions {
		byUser[s.UserID] = append(byUser[s.UserID], s)
		st := strings.ToLower(s.Status)
		if st == "submitted" || st == "completed" {
			submitted[s.UserID] = struct{}{}
		}
	}
	var notStarted, startedNS, outside []map[string]any
	statusCounts := map[string]int{}
	for id, t := range targetIDs {
		if _, ok := byUser[id]; !ok {
			if len(notStarted) < 200 {
				notStarted = append(notStarted, studentEntry(t.ID, t.Username, t.FullName, t.Class))
			}
			continue
		}
		if _, ok := submitted[id]; ok {
			continue
		}
		st := "unknown"
		if rows := byUser[id]; len(rows) > 0 {
			st = rows[0].Status
			if st == "" {
				st = "unknown"
			}
		}
		statusCounts[st]++
		if len(startedNS) < 200 {
			startedNS = append(startedNS, studentEntry(t.ID, t.Username, t.FullName, t.Class))
		}
	}
	submittedIn := 0
	for id := range submitted {
		if _, ok := targetIDs[id]; ok {
			submittedIn++
			continue
		}
		if len(outside) >= 200 {
			continue
		}
		latest := byUser[id][0]
		outside = append(outside, studentEntry(id, latest.Username, latest.FullName, latest.Class))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"exam_id":                           ex.ID,
		"exam_title":                        ex.Title,
		"restrictions":                      map[string]any{"allowed_classes": classes, "allowed_students_count": len(students)},
		"target_count":                      len(targetIDs),
		"submitted_in_target_count":         submittedIn,
		"submitted_total_count":             len(submitted),
		"submitted_outside_target_count":    len(submitted) - submittedIn,
		"not_started_count":                 countMissing(targetIDs, byUser),
		"started_not_submitted_count":       countStartedNS(targetIDs, byUser, submitted),
		"session_total_count":               len(sessions),
		"non_submitted_status_counts":       statusCounts,
		"not_started_students":              notStarted,
		"started_not_submitted_students":    startedNS,
		"submitted_outside_target_students": outside,
	})
}

func (d deps) loadResultsExam(w http.ResponseWriter, r *http.Request, userID int, claims *auth.Claims) (*persistence.ExamRow, bool) {
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
		return nil, false
	}
	ex, err := d.store.GetExam(r.Context(), examID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat ujian")
		return nil, false
	}
	if ex == nil || ex.Deleted {
		writeDetail(w, http.StatusNotFound, "Exam not found")
		return nil, false
	}
	ok, hidden := staffCanViewResults(ex, userID, claims.Role)
	if !ok {
		if hidden {
			writeDetail(w, http.StatusNotFound, "Ujian tidak ditemukan")
			return nil, false
		}
		writeDetail(w, http.StatusForbidden, "Not authorized to view this exam's results")
		return nil, false
	}
	return ex, true
}

func pickLatestScored(rows []persistence.ResultSession) []persistence.ResultSession {
	latestAny := map[int]persistence.ResultSession{}
	latestScored := map[int]persistence.ResultSession{}
	order := make([]int, 0)
	for _, row := range rows {
		if _, ok := latestAny[row.UserID]; !ok {
			latestAny[row.UserID] = row
			order = append(order, row.UserID)
		}
		if row.Score != nil {
			if _, ok := latestScored[row.UserID]; !ok {
				latestScored[row.UserID] = row
			}
		}
	}
	out := make([]persistence.ResultSession, 0, len(order))
	for _, id := range order {
		if scored, ok := latestScored[id]; ok {
			out = append(out, scored)
			continue
		}
		out = append(out, latestAny[id])
	}
	return out
}

func scoreBreakdown(questions []persistence.QuestionRow, answers map[int]persistence.AnswerScore) []map[string]any {
	out := make([]map[string]any, 0, len(questions))
	for _, q := range questions {
		ans, has := answers[q.ID]
		status := "not_answered"
		var correct any = false
		earned := 0.0
		if !has {
			out = append(out, map[string]any{
				"question_id": strconv.Itoa(q.ID), "question_type": q.Type,
				"points_earned": 0.0, "max_points": q.Points, "is_correct": false, "status": status,
			})
			continue
		}
		if ans.Points == nil {
			status = "pending"
			correct = nil
			out = append(out, map[string]any{
				"question_id": strconv.Itoa(q.ID), "question_type": q.Type,
				"points_earned": nil, "max_points": q.Points, "is_correct": correct, "status": status,
			})
			continue
		}
		earned = *ans.Points
		if q.Type == "essay" || q.Type == "short_answer" {
			switch {
			case earned >= q.Points:
				status, correct = "correct", true
			case earned <= 0:
				status, correct = "incorrect", false
			default:
				status, correct = "partial", nil
			}
		} else if ans.IsCorrect != nil && *ans.IsCorrect {
			status, correct = "correct", true
		} else if ans.IsCorrect != nil && !*ans.IsCorrect && earned > 0 {
			status, correct = "partial", false
		} else if ans.IsCorrect != nil && !*ans.IsCorrect {
			status, correct = "incorrect", false
		} else if earned > 0 {
			status, correct = "partial", nil
		} else {
			status, correct = "incorrect", false
		}
		out = append(out, map[string]any{
			"question_id": strconv.Itoa(q.ID), "question_type": q.Type,
			"points_earned": earned, "max_points": q.Points, "is_correct": correct, "status": status,
		})
	}
	return out
}

func csvList(raw *string, _ bool) []string {
	if raw == nil {
		return []string{}
	}
	parts := strings.Split(*raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func studentEntry(id int, username, full string, class *string) map[string]any {
	c := ""
	if class != nil {
		c = *class
	}
	if full == "" {
		full = username
	}
	return map[string]any{"id": id, "username": username, "full_name": full, "student_class": c}
}

func deref(v *string) string {
	if v == nil {
		return ""
	}
	return *v
}

func rfcOrNil(t *time.Time) any {
	if t == nil {
		return nil
	}
	return t.UTC().Format(time.RFC3339)
}

func countMissing(targets map[int]persistence.TargetStudent, sessions map[int][]persistence.SessionUser) int {
	n := 0
	for id := range targets {
		if _, ok := sessions[id]; !ok {
			n++
		}
	}
	return n
}

func countStartedNS(targets map[int]persistence.TargetStudent, sessions map[int][]persistence.SessionUser, submitted map[int]struct{}) int {
	n := 0
	for id := range targets {
		if _, ok := sessions[id]; !ok {
			continue
		}
		if _, ok := submitted[id]; !ok {
			n++
		}
	}
	return n
}
