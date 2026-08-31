package exam

import (
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/persistence"
)

func (d deps) analyticsDashboard(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" || isPengawas(claims.Role, claims.JobTitle) {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	days, ok := boundedQueryInt(w, r, "days", 7, 1, 90)
	if !ok {
		return
	}
	now := time.Now().In(wib)
	oldest := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, wib).AddDate(0, 0, -(days - 1))
	ownerID, hideDeveloper := 0, false
	if claims.Role == "teacher" {
		ownerID = userID
	} else if claims.Role == "admin" {
		hideDeveloper = true
	}
	row, err := d.store.AnalyticsDashboard(r.Context(), oldest.UTC(), ownerID, hideDeveloper)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat dashboard analitik")
		return
	}
	byDay := map[string]int{}
	for _, item := range row.ByDay {
		byDay[item.Name] = item.Count
	}
	trend := make([]map[string]any, 0, days)
	for i := 0; i < days; i++ {
		label := oldest.AddDate(0, 0, i).Format("2006-01-02")
		trend = append(trend, map[string]any{"date": label, "count": byDay[label]})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"period_days": days, "total_sessions": row.TotalSessions,
		"average_score":            roundTwo(floatValue(row.AverageScore)),
		"total_violations":         row.TotalViolations,
		"sessions_with_violations": row.SessionsWithViolations,
		"sessions_clean":           row.TotalSessions - row.SessionsWithViolations,
		"daily_trend":              trend,
	})
}

func (d deps) classPerformance(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return
	}
	if claims.Role == "student" || claims.Role == "guruplus" || isPengawas(claims.Role, claims.JobTitle) {
		writeDetail(w, http.StatusForbidden, "Tidak memiliki akses")
		return
	}
	className := strings.TrimSpace(r.URL.Query().Get("class_name"))
	if className == "" {
		className = strings.TrimSpace(r.PathValue("class_name"))
	}
	if className == "" {
		writeDetail(w, http.StatusBadRequest, "class_name is required")
		return
	}
	examID := 0
	if raw := r.URL.Query().Get("exam_id"); raw != "" {
		var err error
		examID, err = strconv.Atoi(raw)
		if err != nil || examID <= 0 {
			writeDetail(w, http.StatusUnprocessableEntity, "exam_id tidak valid")
			return
		}
		original := r.PathValue("exam_id")
		r.SetPathValue("exam_id", strconv.Itoa(examID))
		_, allowed := d.loadResultsExam(w, r, userID, claims)
		r.SetPathValue("exam_id", original)
		if !allowed {
			return
		}
	}
	ownerID, hideDeveloper := 0, false
	if examID == 0 && claims.Role == "teacher" {
		ownerID = userID
	} else if claims.Role == "admin" {
		hideDeveloper = true
	}
	row, err := d.store.ClassPerformance(r.Context(), className, examID, ownerID, hideDeveloper)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat analitik kelas")
		return
	}
	if row.TotalStudents == 0 {
		writeJSON(w, http.StatusOK, map[string]any{
			"class_name": className, "total_students": 0,
			"message": "No students found in this class",
		})
		return
	}
	top := make([]map[string]any, 0, len(row.TopPerformers))
	for _, item := range row.TopPerformers {
		top = append(top, map[string]any{
			"student_id": item.StudentID, "name": item.Name,
			"average_score": roundTwo(item.AverageScore), "exams_taken": item.ExamsTaken,
		})
	}
	passRate := 0.0
	if row.GradedCount > 0 {
		passRate = roundTwo(float64(row.PassedCount) / float64(row.GradedCount) * 100)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"class_name": className, "total_students": row.TotalStudents,
		"total_exams_taken": row.TotalSessions, "average_score": roundTwo(floatValue(row.AverageScore)),
		"highest_score": floatValue(row.HighestScore), "lowest_score": floatValue(row.LowestScore),
		"pass_rate": passRate, "top_performers": top,
	})
}

func (d deps) assessmentAnalysis(w http.ResponseWriter, r *http.Request) {
	ex, ok := d.loadAnalyticsExam(w, r)
	if !ok {
		return
	}
	classes := csvQueryClasses(r.URL.Query().Get("class_names"))
	if len(classes) == 0 {
		classes = csvQueryClasses(r.URL.Query().Get("class_name"))
	}
	if len(classes) == 0 {
		writeDetail(w, http.StatusBadRequest, "class_name atau class_names wajib diisi")
		return
	}
	if len(classes) > 1 && !isUAMExam(ex) {
		writeDetail(w, http.StatusBadRequest, "Gabungan kelas hanya tersedia untuk Ujian Akhir Madrasah")
		return
	}
	rows, err := d.store.AssessmentParticipants(r.Context(), ex.ID, classes)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat analisis asesmen")
		return
	}
	writeJSON(w, http.StatusOK, buildAssessmentPayload(ex, classes, rows))
}

func buildAssessmentPayload(ex *persistence.ExamRow, classes []string, rows []persistence.AssessmentParticipantRow) map[string]any {
	scores := make([]float64, len(rows))
	mean, highest, lowest := 0.0, 0.0, 0.0
	for i, row := range rows {
		scores[i] = row.Score
		mean += row.Score
		if i == 0 || row.Score > highest {
			highest = row.Score
		}
		if i == 0 || row.Score < lowest {
			lowest = row.Score
		}
	}
	if len(scores) > 0 {
		mean /= float64(len(scores))
	}
	variance := 0.0
	for _, score := range scores {
		variance += (score - mean) * (score - mean)
	}
	stdDev := 0.0
	if len(scores) > 1 {
		stdDev = math.Sqrt(variance / float64(len(scores)))
	}
	thresholds := panThresholds(mean, stdDev)
	scaleThresholds := panScaleThresholds(mean, stdDev)
	kkm := 70.0
	if ex.PassingScore != nil {
		kkm = *ex.PassingScore
	}
	panCounts, papCounts := map[string]int{"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}, map[string]int{"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
	participants := make([]map[string]any, 0, len(rows))
	passed := 0
	for index, row := range rows {
		pan := panLetter(row.Score, mean, stdDev)
		pap := papLetter(row.Score)
		panCounts[pan]++
		papCounts[pap]++
		isPassed := row.Score >= kkm
		if isPassed {
			passed++
		}
		tScore := 50.0
		if stdDev > 0 {
			tScore = 50 + ((row.Score-mean)/stdDev)*10
		}
		participants = append(participants, map[string]any{
			"session_id": row.SessionID, "user_id": row.UserID, "name": row.Name,
			"student_class": row.ClassName, "score": roundTwo(row.Score), "rank": index + 1,
			"submitted_at": persistence.FormatTimePtr(row.SubmittedAt), "pan_letter": pan,
			"pan_scale10": panScale10(row.Score, mean, stdDev), "t_score": roundTwo(tScore),
			"pap_letter": pap, "pap_status": map[bool]string{true: "TUNTAS", false: "TIDAK TUNTAS"}[isPassed],
		})
	}
	panDistribution := assessmentDistribution(panCounts, len(rows), []string{"A", "B", "C", "D", "E"}, panRanges(thresholds, mean, stdDev))
	papRanges := map[string]string{"A": "90 - 100", "B": "80 - 89", "C": "70 - 79", "D": "60 - 69", "E": "< 60"}
	papDistribution := assessmentDistribution(papCounts, len(rows), []string{"A", "B", "C", "D", "E"}, papRanges)
	classCount := 1
	if len(rows) > 1 {
		classCount = int(math.Round(1 + 3.3*math.Log10(float64(len(rows)))))
	}
	interval := 0.0
	if classCount > 0 {
		interval = (highest - lowest) / float64(classCount)
	}
	classLabel := classes[0]
	if len(classes) > 1 {
		classLabel = "Gabungan Kelas: " + strings.Join(classes, ", ")
	}
	return map[string]any{
		"exam":       map[string]any{"id": ex.ID, "title": ex.Title, "subject": deref(ex.Subject), "exam_type": deref(ex.ExamType), "teacher_name": deref(ex.TeacherName), "date_text": ex.StartTime.In(wib).Format("02 January 2006 15:04 WIB")},
		"class_name": classLabel, "class_names": classes, "is_combined_class_scope": len(classes) > 1,
		"generated_at": time.Now().In(wib).Format("02 January 2006 15:04 WIB"),
		"stats":        map[string]any{"participant_count": len(rows), "average": roundTwo(mean), "std_dev": roundTwo(stdDev), "highest": roundTwo(highest), "lowest": roundTwo(lowest)},
		"pan":          map[string]any{"mean": roundTwo(mean), "std_dev": roundTwo(stdDev), "score_range": roundTwo(highest - lowest), "class_count": classCount, "interval": roundTwo(interval), "thresholds": roundMap(thresholds), "scale10_thresholds": roundMap(scaleThresholds), "letter_distribution": panDistribution, "um_conversion_summary": []map[string]any{}},
		"pap":          map[string]any{"kkm": roundTwo(kkm), "pass_count": passed, "fail_count": len(rows) - passed, "pass_percentage": percentage(passed, len(rows)), "grade_distribution": papDistribution},
		"participants": participants,
	}
}

func csvQueryClasses(raw string) []string {
	seen, out := map[string]struct{}{}, []string{}
	for _, item := range strings.Split(raw, ",") {
		item = strings.TrimSpace(item)
		key := strings.ToLower(item)
		if item != "" {
			if _, ok := seen[key]; !ok {
				seen[key] = struct{}{}
				out = append(out, item)
			}
		}
	}
	return out
}

func isUAMExam(ex *persistence.ExamRow) bool {
	value := strings.ToLower(strings.TrimSpace(deref(ex.ExamType) + " " + ex.Title))
	return strings.Contains(value, "ujian akhir madrasah") || strings.Contains(value, "ujian madrasah") || strings.Contains(" "+value+" ", " uam ") || strings.Contains(" "+value+" ", " um ")
}

func panThresholds(mean, std float64) map[string]float64 {
	return map[string]float64{"a_min": mean + 1.5*std, "b_min": mean + .5*std, "c_min": mean - .5*std, "d_min": mean - 1.5*std}
}
func panScaleThresholds(mean, std float64) map[string]float64 {
	return map[string]float64{"10_min": mean + 2.25*std, "9_min": mean + 1.75*std, "8_min": mean + 1.25*std, "7_min": mean + .75*std, "6_min": mean + .25*std, "5_min": mean - .25*std, "4_min": mean - .75*std, "3_min": mean - 1.25*std, "2_min": mean - 1.75*std, "1_min": mean - 2.25*std, "0_max": mean - 2.25*std}
}
func panLetter(score, mean, std float64) string {
	if std <= 0 {
		return "C"
	}
	t := panThresholds(mean, std)
	if score >= t["a_min"] {
		return "A"
	}
	if score >= t["b_min"] {
		return "B"
	}
	if score >= t["c_min"] {
		return "C"
	}
	if score >= t["d_min"] {
		return "D"
	}
	return "E"
}
func panScale10(score, mean, std float64) int {
	if std <= 0 {
		return 5
	}
	t := panScaleThresholds(mean, std)
	for _, item := range []struct {
		k string
		v int
	}{{"10_min", 10}, {"9_min", 9}, {"8_min", 8}, {"7_min", 7}, {"6_min", 6}, {"5_min", 5}, {"4_min", 4}, {"3_min", 3}, {"2_min", 2}, {"1_min", 1}} {
		if score >= t[item.k] {
			return item.v
		}
	}
	return 0
}
func papLetter(score float64) string {
	if score >= 90 {
		return "A"
	}
	if score >= 80 {
		return "B"
	}
	if score >= 70 {
		return "C"
	}
	if score >= 60 {
		return "D"
	}
	return "E"
}
func percentage(value, total int) float64 {
	if total <= 0 {
		return 0
	}
	return roundTwo(float64(value) / float64(total) * 100)
}
func roundMap(values map[string]float64) map[string]float64 {
	out := map[string]float64{}
	for key, value := range values {
		out[key] = roundTwo(value)
	}
	return out
}
func assessmentDistribution(counts map[string]int, total int, grades []string, ranges map[string]string) []map[string]any {
	out := make([]map[string]any, 0, len(grades))
	for _, grade := range grades {
		rangeText := "-"
		if ranges != nil {
			rangeText = ranges[grade]
		}
		out = append(out, map[string]any{"grade": grade, "range": rangeText, "count": counts[grade], "percentage": percentage(counts[grade], total)})
	}
	return out
}

func panRanges(thresholds map[string]float64, mean, stdDev float64) map[string]string {
	format := func(value float64) string { return strconv.FormatFloat(roundTwo(value), 'f', -1, 64) }
	if stdDev <= 0 {
		return map[string]string{"A": "-", "B": "-", "C": "= " + format(mean), "D": "-", "E": "-"}
	}
	return map[string]string{
		"A": ">= " + format(thresholds["a_min"]),
		"B": format(thresholds["b_min"]) + " - < " + format(thresholds["a_min"]),
		"C": format(thresholds["c_min"]) + " - < " + format(thresholds["b_min"]),
		"D": format(thresholds["d_min"]) + " - < " + format(thresholds["c_min"]),
		"E": "< " + format(thresholds["d_min"]),
	}
}

func (d deps) examAnalytics(w http.ResponseWriter, r *http.Request) {
	ex, ok := d.loadAnalyticsExam(w, r)
	if !ok {
		return
	}
	passingThreshold := 0.0
	if ex.PassingScore != nil {
		passingThreshold = *ex.PassingScore
	}
	row, err := d.store.ExamAnalytics(r.Context(), ex.ID, passingThreshold)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat analitik ujian")
		return
	}
	writeJSON(w, http.StatusOK, buildExamAnalytics(ex.ID, ex.PassingScore, row))
}

func (d deps) examClasses(w http.ResponseWriter, r *http.Request) {
	ex, ok := d.loadAnalyticsExam(w, r)
	if !ok {
		return
	}
	rows, err := d.store.ExamClasses(r.Context(), ex.ID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat kelas peserta")
		return
	}
	classes := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		classes = append(classes, map[string]any{
			"class_name": row.ClassName, "participants": row.Participants,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"exam_id": ex.ID, "classes": classes})
}

func (d deps) questionDifficulty(w http.ResponseWriter, r *http.Request) {
	ex, ok := d.loadAnalyticsExam(w, r)
	if !ok {
		return
	}
	rows, err := d.store.QuestionDifficulty(r.Context(), ex.ID)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat analisis soal")
		return
	}
	if len(rows) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{
			"exam_id": ex.ID, "questions": []map[string]any{}, "message": "No questions found",
		})
		return
	}
	questions := make([]map[string]any, 0, len(rows))
	for index, row := range rows {
		rate, difficulty := questionDifficultyStats(row.TotalAnswers, row.CorrectAnswers)
		number := row.OrderIndex
		if number <= 0 {
			number = index + 1
		}
		questions = append(questions, map[string]any{
			"question_id": row.QuestionID, "question_number": number,
			"question_text": truncateQuestionText(row.QuestionText),
			"question_type": row.QuestionType, "total_answers": row.TotalAnswers,
			"correct_answers": row.CorrectAnswers, "correct_rate": rate,
			"difficulty": difficulty,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"exam_id": ex.ID, "total_questions": len(rows), "questions": questions,
	})
}

func (d deps) loadAnalyticsExam(w http.ResponseWriter, r *http.Request) (*persistence.ExamRow, bool) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return nil, false
	}
	return d.loadResultsExam(w, r, userID, claims)
}

func questionDifficultyStats(total, correct int) (float64, string) {
	if total <= 0 {
		return 0, "unknown"
	}
	rate := roundTwo(float64(correct) / float64(total) * 100)
	if rate >= 80 {
		return rate, "easy"
	}
	if rate >= 50 {
		return rate, "medium"
	}
	return rate, "hard"
}

func truncateQuestionText(value string) string {
	runes := []rune(value)
	if len(runes) <= 100 {
		return value
	}
	return string(runes[:100]) + "..."
}

func buildExamAnalytics(examID int, passingScore *float64, row *persistence.ExamAnalyticsRow) map[string]any {
	base := map[string]any{
		"exam_id": examID, "total_participants": row.TotalParticipants,
		"active_sessions": row.ActiveSessions, "completed_sessions": row.CompletedSessions,
		"average_score": 0.0, "highest_score": 0.0, "lowest_score": 0.0,
		"pass_rate": 0.0, "score_distribution": map[string]int{},
		"difficult_questions": []map[string]any{}, "violation_stats": map[string]int{},
	}
	if row.TotalParticipants == 0 {
		return base
	}
	passed := row.PassedSessions
	if passingScore == nil || *passingScore == 0 {
		passed = row.ScoredSessions
	}
	passRate := 0.0
	if row.CompletedSessions > 0 {
		passRate = roundTwo(float64(passed) / float64(row.CompletedSessions) * 100)
	}
	base["average_score"] = roundTwo(floatValue(row.AverageScore))
	base["highest_score"] = floatValue(row.HighestScore)
	base["lowest_score"] = floatValue(row.LowestScore)
	base["pass_rate"] = passRate
	base["score_distribution"] = map[string]int{
		"0-20": row.Score0To20, "21-40": row.Score21To40,
		"41-60": row.Score41To60, "61-80": row.Score61To80,
		"81-100": row.Score81To100,
	}
	base["violation_stats"] = map[string]int{"total_violations": row.TotalViolations}
	return base
}

func floatValue(value *float64) float64 {
	if value == nil {
		return 0
	}
	return *value
}

func roundTwo(value float64) float64 {
	return math.Round(value*100) / 100
}
