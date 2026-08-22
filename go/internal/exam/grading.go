package exam

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

func (d deps) pendingGrades(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.grader(w, r)
	if !ok {
		return
	}
	examID, _ := strconv.Atoi(r.URL.Query().Get("exam_id"))
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	perPage, _ := strconv.Atoi(r.URL.Query().Get("per_page"))
	if page < 1 {
		page = 1
	}
	if perPage < 1 {
		perPage = 20
	}
	if perPage > 100 {
		perPage = 100
	}
	ownerID, hideDeveloper := gradingScope(userID, claims.Role)
	rows, total, err := d.store.ListPendingGrades(
		r.Context(), examID, ownerID, hideDeveloper, perPage, (page-1)*perPage,
	)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat jawaban tertunda")
		return
	}
	pending := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		settings := map[string]any{}
		_ = json.Unmarshal(row.Settings, &settings)
		var hint any
		if row.QuestionType == "short_answer" {
			accepted := stringList(settings["acceptable_answers"])
			if len(accepted) == 1 {
				hint = accepted[0]
			} else if len(accepted) > 1 {
				if len(accepted) > 3 {
					accepted = accepted[:3]
				}
				hint = strings.Join(accepted, ", ")
			}
		}
		pending = append(pending, map[string]any{
			"answer_id": row.AnswerID, "student_name": row.StudentName,
			"student_username": row.StudentUsername, "student_class": row.StudentClass,
			"exam_id": row.ExamID, "exam_title": row.ExamTitle,
			"question_id": row.QuestionID, "question_text": row.QuestionText,
			"question_type": row.QuestionType, "answer_text": row.AnswerText,
			"max_points": row.MaxPoints, "submitted_at": persistence.FormatTimePtr(row.SubmittedAt),
			"correct_answer": hint, "question_settings": settings,
		})
	}
	pages := 0
	if total > 0 {
		pages = (total + perPage - 1) / perPage
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"pending": pending, "total": total, "page": page,
		"per_page": perPage, "total_pages": pages,
	})
}

func (d deps) gradingStats(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.grader(w, r)
	if !ok {
		return
	}
	ownerID, hideDeveloper := gradingScope(userID, claims.Role)
	row, err := d.store.GradingStats(r.Context(), ownerID, hideDeveloper)
	if err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal memuat statistik penilaian")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"total_pending": row.TotalPending, "essay_pending": row.EssayPending,
		"short_answer_pending": row.ShortAnswerPending, "by_exam": row.ByExam,
		"recently_graded": row.RecentlyGraded,
	})
}

func (d deps) gradeEssay(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.grader(w, r)
	if !ok {
		return
	}
	var body struct {
		AnswerID int     `json:"answer_id"`
		Points   float64 `json:"points_earned"`
		Feedback *string `json:"feedback"`
	}
	if err := readJSON(r, &body); err != nil || body.AnswerID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	answer, ok := d.authorizeGrade(w, r, userID, claims, body.AnswerID)
	if !ok {
		return
	}
	if errMsg := validateGrade(answer, body.Points); errMsg != "" {
		writeDetail(w, http.StatusBadRequest, errMsg)
		return
	}
	feedback := ""
	if body.Feedback != nil {
		feedback = *body.Feedback
	}
	graderName := claims.FullName
	if strings.TrimSpace(graderName) == "" {
		graderName = claims.Username
	}
	if _, err := d.store.GradeAnswer(r.Context(), body.AnswerID, userID, graderName, body.Points, feedback); err != nil {
		writeDetail(w, http.StatusInternalServerError, "Gagal menyimpan nilai")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true, "graded": true, "answer_id": body.AnswerID,
		"points_earned": body.Points,
	})
}

func (d deps) batchGrade(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.grader(w, r)
	if !ok {
		return
	}
	var body struct {
		Grades []struct {
			AnswerID int     `json:"answer_id"`
			Points   float64 `json:"points"`
			Feedback *string `json:"feedback"`
		} `json:"grades"`
	}
	if err := readJSON(r, &body); err != nil {
		writeDetail(w, http.StatusUnprocessableEntity, "Payload tidak valid")
		return
	}
	graded := 0
	errorsOut := []map[string]any{}
	sessions := map[int]struct{}{}
	graderName := claims.FullName
	if strings.TrimSpace(graderName) == "" {
		graderName = claims.Username
	}
	for _, item := range body.Grades {
		answer, status, detail := d.checkGradeAccess(r, userID, claims, item.AnswerID)
		if status != 0 {
			errorsOut = append(errorsOut, map[string]any{"answer_id": item.AnswerID, "error": detail})
			continue
		}
		if errMsg := validateGrade(answer, item.Points); errMsg != "" {
			errorsOut = append(errorsOut, map[string]any{"answer_id": item.AnswerID, "error": errMsg})
			continue
		}
		feedback := ""
		if item.Feedback != nil {
			feedback = *item.Feedback
		}
		sessionID, err := d.store.GradeAnswer(r.Context(), item.AnswerID, userID, graderName, item.Points, feedback)
		if err != nil {
			errorsOut = append(errorsOut, map[string]any{"answer_id": item.AnswerID, "error": "Gagal menyimpan nilai"})
			continue
		}
		graded++
		sessions[sessionID] = struct{}{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true, "graded": graded, "errors": errorsOut,
		"sessions_updated": len(sessions),
	})
}

func (d deps) gradingAnswerDetail(w http.ResponseWriter, r *http.Request) {
	userID, claims, ok := d.grader(w, r)
	if !ok {
		return
	}
	answerID, err := strconv.Atoi(r.PathValue("answer_id"))
	if err != nil || answerID <= 0 {
		writeDetail(w, http.StatusUnprocessableEntity, "answer_id tidak valid")
		return
	}
	row, ok := d.authorizeGrade(w, r, userID, claims, answerID)
	if !ok {
		return
	}
	metadata := map[string]any{}
	_ = json.Unmarshal(row.Metadata, &metadata)
	writeJSON(w, http.StatusOK, map[string]any{
		"answer_id": row.AnswerID,
		"student": map[string]any{
			"id": row.StudentID, "name": row.StudentName,
			"username": row.StudentUsername, "class": row.StudentClass,
		},
		"exam": map[string]any{"id": row.ExamID, "title": row.ExamTitle},
		"question": map[string]any{
			"id": row.QuestionID, "text": row.QuestionText, "type": row.QuestionType,
			"max_points": row.MaxPoints, "image_url": row.QuestionImage,
		},
		"answer_text": row.AnswerText,
		"current_grade": map[string]any{
			"points_earned": row.Points, "is_correct": row.IsCorrect,
			"feedback": metadata["grader_feedback"], "graded_at": metadata["graded_at"],
		},
		"submitted_at": persistence.FormatTimePtr(row.SubmittedAt),
	})
}

func (d deps) grader(w http.ResponseWriter, r *http.Request) (int, *auth.Claims, bool) {
	userID, claims, ok := d.staffOrFallback(w, r)
	if !ok {
		return 0, nil, false
	}
	if claims.Role != "teacher" && claims.Role != "admin" && claims.Role != "developer" {
		writeDetail(w, http.StatusForbidden, "Not authorized")
		return 0, nil, false
	}
	return userID, claims, true
}

func gradingScope(userID int, role string) (ownerID int, hideDeveloper bool) {
	switch role {
	case "teacher", "developer":
		return userID, false
	case "admin":
		return 0, true
	default:
		return -1, true
	}
}

func (d deps) authorizeGrade(w http.ResponseWriter, r *http.Request, userID int, claims *auth.Claims, answerID int) (*persistence.GradingAnswer, bool) {
	row, status, detail := d.checkGradeAccess(r, userID, claims, answerID)
	if status != 0 {
		writeDetail(w, status, detail)
		return nil, false
	}
	return row, true
}

func (d deps) checkGradeAccess(r *http.Request, userID int, claims *auth.Claims, answerID int) (*persistence.GradingAnswer, int, string) {
	row, err := d.store.GetGradingAnswer(r.Context(), answerID)
	if err != nil {
		return nil, http.StatusInternalServerError, "Gagal memuat jawaban"
	}
	if row == nil {
		return nil, http.StatusNotFound, "Answer not found"
	}
	if row.ExamCreatorRole == "developer" && claims.Role != "developer" {
		return nil, http.StatusNotFound, "Ujian tidak ditemukan"
	}
	if (claims.Role == "teacher" || claims.Role == "developer") && row.ExamCreatorID != userID {
		return nil, http.StatusForbidden, "Not authorized"
	}
	if claims.Role != "teacher" && claims.Role != "developer" && claims.Role != "admin" {
		return nil, http.StatusForbidden, "Not authorized"
	}
	return row, 0, ""
}

func validateGrade(answer *persistence.GradingAnswer, points float64) string {
	if answer.SessionStatus != "submitted" && answer.SessionStatus != "completed" {
		return "Jawaban tidak bisa dinilai karena sesi belum submitted/completed"
	}
	allowedMax := answer.MaxPoints * 2
	if points < 0 || points > allowedMax {
		return "Points must be between 0 and " + strconv.FormatFloat(allowedMax, 'f', -1, 64)
	}
	return ""
}
