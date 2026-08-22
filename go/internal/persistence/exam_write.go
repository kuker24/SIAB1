package persistence

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

type ExamWrite struct {
	Title            string
	Description      *string
	DurationMinutes  int
	StartTime        time.Time
	EndTime          time.Time
	PassingScore     *float64
	MaxAttempts      int
	ShuffleQuestions bool
	ShuffleOptions   bool
	ShowResults      bool
	AllowReview      bool
	Published        bool
	Subject          *string
	ExamType         *string
	AcademicYear     *string
	ShowTeacherName  bool
	BuilderSettings  []byte
	AllowedClasses   *string
	AllowedStudents  *string
}

func (s *Store) CountSessions(ctx context.Context, examID int) (int, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM exam_sessions WHERE exam_id = $1`, examID).Scan(&n)
	return n, err
}

func (s *Store) CreateExam(ctx context.Context, creatorID int, in ExamWrite) (*ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if in.MaxAttempts < 1 {
		in.MaxAttempts = 1
	}
	if len(in.BuilderSettings) == 0 {
		in.BuilderSettings = []byte("{}")
	}
	var last error
	for i := 0; i < 5; i++ {
		token := randomHex(3)
		seb := randomURL(32)
		bek := randomURL(32)
		var id int
		err := s.pool.QueryRow(ctx, `
INSERT INTO exams (
  title, description, creator_id, duration_minutes, start_time, end_time,
  passing_score, max_attempts, shuffle_questions, shuffle_options,
  show_results, allow_review, is_published, subject, exam_type, academic_year,
  show_teacher_name, builder_settings, allowed_classes, allowed_students,
  access_token, seb_config_key, seb_browser_exam_key, created_at, updated_at
) VALUES (
  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18::jsonb,$19,$20,$21,$22,$23,NOW(),NOW()
) RETURNING id`,
			in.Title, in.Description, creatorID, in.DurationMinutes, in.StartTime, in.EndTime,
			in.PassingScore, in.MaxAttempts, in.ShuffleQuestions, in.ShuffleOptions,
			in.ShowResults, in.AllowReview, in.Published, in.Subject, in.ExamType, in.AcademicYear,
			in.ShowTeacherName, string(in.BuilderSettings), in.AllowedClasses, in.AllowedStudents,
			token, seb, bek,
		).Scan(&id)
		if err != nil {
			last = err
			if strings.Contains(strings.ToLower(err.Error()), "unique") {
				continue
			}
			return nil, err
		}
		return s.GetExam(ctx, id)
	}
	if last == nil {
		last = fmt.Errorf("token collision")
	}
	return nil, last
}

func (s *Store) UpdateExam(ctx context.Context, examID int, in ExamWrite) (*ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if in.MaxAttempts < 1 {
		in.MaxAttempts = 1
	}
	if len(in.BuilderSettings) == 0 {
		in.BuilderSettings = []byte("{}")
	}
	tag, err := s.pool.Exec(ctx, `
UPDATE exams SET
  title=$2, description=$3, duration_minutes=$4, start_time=$5, end_time=$6,
  passing_score=$7, max_attempts=$8, shuffle_questions=$9, shuffle_options=$10,
  show_results=$11, allow_review=$12, is_published=$13, subject=$14, exam_type=$15,
  academic_year=$16, show_teacher_name=$17, builder_settings=$18::jsonb,
  allowed_classes=$19, allowed_students=$20, updated_at=NOW()
 WHERE id=$1 AND COALESCE(is_deleted,false)=false`,
		examID, in.Title, in.Description, in.DurationMinutes, in.StartTime, in.EndTime,
		in.PassingScore, in.MaxAttempts, in.ShuffleQuestions, in.ShuffleOptions,
		in.ShowResults, in.AllowReview, in.Published, in.Subject, in.ExamType,
		in.AcademicYear, in.ShowTeacherName, string(in.BuilderSettings),
		in.AllowedClasses, in.AllowedStudents,
	)
	if err != nil {
		return nil, err
	}
	if tag.RowsAffected() == 0 {
		return nil, pgx.ErrNoRows
	}
	return s.GetExam(ctx, examID)
}

func (s *Store) SoftDeleteExam(ctx context.Context, examID int) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	tag, err := s.pool.Exec(ctx, `
UPDATE exams SET is_deleted=true, deleted_at=NOW(), updated_at=NOW()
 WHERE id=$1 AND COALESCE(is_deleted,false)=false`, examID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

func (s *Store) SetExamPublished(ctx context.Context, examID int, published bool) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	_, err := s.pool.Exec(ctx, `
UPDATE exams SET is_published=$2, updated_at=NOW()
 WHERE id=$1 AND COALESCE(is_deleted,false)=false`, examID, published)
	return err
}

func randomHex(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	return strings.ToUpper(hex.EncodeToString(b))
}

func randomURL(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

func MustJSON(v any) []byte {
	if v == nil {
		return []byte("{}")
	}
	b, err := json.Marshal(v)
	if err != nil {
		return []byte("{}")
	}
	return b
}
