package exam

import (
	"context"
	"errors"
	"log"
	"net/http"
	"strings"
	"time"

	"siab1/internal/auth"
	"siab1/internal/persistence"
)

type joinRepository interface {
	LookupJoinUser(context.Context, int) (*persistence.JoinUserRow, error)
	LookupJoinExamByToken(context.Context, string) (*persistence.JoinExamRow, error)
	CompletedAttemptCount(context.Context, int, int) (int, error)
	CountJoinQuestions(context.Context, int) (int, error)
}

type joinHTTPError struct {
	Status int
	Detail any
}

func (e *joinHTTPError) Error() string {
	return "join http error"
}

func joinError(status int, detail any) *joinHTTPError {
	return &joinHTTPError{Status: status, Detail: detail}
}

type joinService struct {
	repo   joinRepository
	secret string
}

type nativeJoinResponse struct {
	ExamID          int     `json:"exam_id"`
	Title           string  `json:"title"`
	Description     *string `json:"description"`
	DurationMinutes int     `json:"duration_minutes"`
	QuestionCount   int     `json:"question_count"`
	Allowed         bool    `json:"allowed"`
	Message         string  `json:"message"`
}

func (d deps) joinExam(w http.ResponseWriter, r *http.Request) {
	if d.store == nil || !d.store.HasPool() {
		writeDetail(w, http.StatusServiceUnavailable, "Database tidak tersedia")
		return
	}
	response, joinErr := joinService{repo: d.store, secret: d.secret}.join(r)
	if joinErr != nil {
		log.Printf("go_join outcome=failure status=%d", joinErr.Status)
		if errors.Is(r.Context().Err(), context.Canceled) {
			return
		}
		if joinErr.Status == http.StatusUnauthorized {
			w.Header().Set("WWW-Authenticate", "Bearer")
		}
		if joinErr.Status == http.StatusTooManyRequests {
			w.Header().Set("Retry-After", "60")
		}
		writeJSON(w, joinErr.Status, map[string]any{"detail": joinErr.Detail})
		return
	}
	log.Printf("go_join outcome=success exam_id=%d", response.ExamID)
	writeJSON(w, http.StatusOK, response)
}

func (s joinService) join(r *http.Request) (*nativeJoinResponse, *joinHTTPError) {
	ctx := r.Context()
	user, err := s.authenticate(r)
	if err != nil {
		return nil, err
	}
	token, err := readJoinToken(r)
	if err != nil {
		return nil, err
	}
	if !allowJoin(itoa(user.ID) + ":" + clientIP(r)) {
		return nil, joinError(
			http.StatusTooManyRequests,
			"Terlalu banyak percobaan token salah. Tunggu 1 menit.",
		)
	}
	role := strings.ToLower(strings.TrimSpace(user.Role))
	if role != "student" && role != "guruplus" {
		return nil, joinError(http.StatusForbidden, "Hanya peserta ujian yang dapat mengikuti ujian")
	}
	if len(token) != 6 {
		return nil, joinError(http.StatusBadRequest, "Token harus 6 karakter")
	}
	exam, lookupErr := s.repo.LookupJoinExamByToken(ctx, token)
	if lookupErr != nil {
		return nil, joinError(http.StatusInternalServerError, "Gagal memuat ujian")
	}
	if exam == nil {
		return nil, joinError(http.StatusNotFound, "Token ujian tidak valid")
	}
	if !exam.Published {
		return nil, joinError(http.StatusForbidden, "Ujian belum dipublikasikan")
	}
	now := time.Now().UTC()
	if now.Before(exam.StartTime.UTC()) {
		return nil, joinError(http.StatusForbidden, "Ujian belum dimulai")
	}
	if now.After(exam.EndTime.UTC()) {
		return nil, joinError(http.StatusForbidden, "Ujian sudah berakhir")
	}
	className := ""
	if user.StudentClass != nil {
		className = *user.StudentClass
	}
	if ok, detail := participantAccess(exam.AccessRow(), user.ID, role, className); !ok {
		return nil, joinError(http.StatusForbidden, detail)
	}
	done, countErr := s.repo.CompletedAttemptCount(ctx, user.ID, exam.ID)
	if countErr != nil {
		return nil, joinError(http.StatusInternalServerError, "Gagal memeriksa percobaan")
	}
	if done >= exam.MaxAttempts {
		return nil, joinError(
			http.StatusForbidden,
			"Anda sudah menggunakan semua kesempatan ("+itoa(exam.MaxAttempts)+"x)",
		)
	}
	questions, questionErr := s.repo.CountJoinQuestions(ctx, exam.ID)
	if questionErr != nil {
		return nil, joinError(http.StatusInternalServerError, "Gagal memuat ujian")
	}
	return &nativeJoinResponse{
		ExamID:          exam.ID,
		Title:           exam.Title,
		Description:     exam.Description,
		DurationMinutes: exam.DurationMinutes,
		QuestionCount:   questions,
		Allowed:         true,
		Message:         "Token valid. Anda dapat memulai ujian.",
	}, nil
}

func (s joinService) authenticate(r *http.Request) (*persistence.JoinUserRow, *joinHTTPError) {
	raw := auth.Bearer(r.Header.Get("Authorization"))
	if raw == "" {
		return nil, joinError(http.StatusUnauthorized, "Not authenticated")
	}
	claims, err := auth.Parse(s.secret, raw)
	if err != nil {
		return nil, joinError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	userID, err := claims.UserID()
	if err != nil {
		return nil, joinError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	user, lookupErr := s.repo.LookupJoinUser(r.Context(), userID)
	if lookupErr != nil {
		return nil, joinError(http.StatusInternalServerError, "Gagal memuat profil")
	}
	if user == nil {
		return nil, joinError(http.StatusUnauthorized, "Token tidak valid atau sudah kadaluarsa")
	}
	if !user.IsActive {
		return nil, joinError(http.StatusForbidden, "Akun tidak aktif")
	}
	return user, nil
}

func readJoinToken(r *http.Request) (string, *joinHTTPError) {
	var body struct {
		Token *string `json:"token"`
	}
	if err := readJSON(r, &body); err != nil {
		return "", joinError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	if body.Token == nil {
		return "", joinError(http.StatusUnprocessableEntity, "Payload tidak valid")
	}
	return strings.ToUpper(strings.TrimSpace(*body.Token)), nil
}
