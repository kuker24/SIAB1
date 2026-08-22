package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type PendingGrade struct {
	AnswerID        int
	StudentName     string
	StudentUsername string
	StudentClass    *string
	ExamID          int
	ExamTitle       string
	QuestionID      int
	QuestionText    string
	QuestionType    string
	AnswerText      *string
	MaxPoints       float64
	SubmittedAt     *time.Time
	Settings        []byte
}

type GradingAnswer struct {
	AnswerID        int
	SessionID       int
	SessionStatus   string
	ExamID          int
	ExamTitle       string
	ExamCreatorID   int
	ExamCreatorRole string
	StudentID       int
	StudentName     string
	StudentUsername string
	StudentClass    *string
	QuestionID      int
	QuestionText    string
	QuestionType    string
	QuestionImage   *string
	MaxPoints       float64
	AnswerText      *string
	Points          *float64
	IsCorrect       *bool
	Metadata        []byte
	SubmittedAt     *time.Time
}

type GradingStatsRow struct {
	TotalPending       int
	EssayPending       int
	ShortAnswerPending int
	RecentlyGraded     int
	ByExam             map[string]int
}

func gradingScope(ownerID int, hideDeveloper bool, args []any) (string, []any) {
	q := ""
	if ownerID > 0 {
		args = append(args, ownerID)
		q += fmt.Sprintf(` AND e.creator_id = $%d`, len(args))
	}
	if hideDeveloper {
		q += ` AND COALESCE(creator.role, '') <> 'developer'`
	}
	return q, args
}

func (s *Store) ListPendingGrades(ctx context.Context, examID, ownerID int, hideDeveloper bool, limit, offset int) ([]PendingGrade, int, error) {
	if !s.HasPool() {
		return nil, 0, fmt.Errorf("no pgx pool")
	}
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	if offset < 0 {
		offset = 0
	}
	base := `
  FROM answers a
  JOIN questions q ON q.id = a.question_id
  JOIN exam_sessions es ON es.id = a.session_id
  JOIN exams e ON e.id = es.exam_id
  JOIN users creator ON creator.id = e.creator_id
  JOIN users student ON student.id = es.user_id
 WHERE COALESCE(e.is_deleted, false) = false
   AND es.status IN ('submitted', 'completed')
   AND q.question_type IN ('essay', 'short_answer')
   AND a.answer_text IS NOT NULL
   AND (a.is_correct IS NULL OR (q.question_type = 'short_answer' AND a.is_correct = false))`
	args := []any{}
	scope, args := gradingScope(ownerID, hideDeveloper, args)
	base += scope
	if examID > 0 {
		args = append(args, examID)
		base += fmt.Sprintf(` AND es.exam_id = $%d`, len(args))
	}
	var total int
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*)`+base, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	args = append(args, limit, offset)
	rows, err := s.pool.Query(ctx, `
SELECT a.id, COALESCE(student.full_name, student.username, ''), COALESCE(student.username, ''),
       student.student_class, e.id, e.title, q.id, q.question_text, q.question_type,
       a.answer_text, COALESCE(q.points, 1), a.answered_at,
       COALESCE(q.question_settings, '{}'::jsonb)`+base+fmt.Sprintf(`
 ORDER BY a.answered_at ASC NULLS LAST, a.id ASC LIMIT $%d OFFSET $%d`, len(args)-1, len(args)), args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	var out []PendingGrade
	for rows.Next() {
		var row PendingGrade
		if err := rows.Scan(
			&row.AnswerID, &row.StudentName, &row.StudentUsername, &row.StudentClass,
			&row.ExamID, &row.ExamTitle, &row.QuestionID, &row.QuestionText,
			&row.QuestionType, &row.AnswerText, &row.MaxPoints, &row.SubmittedAt, &row.Settings,
		); err != nil {
			return nil, 0, err
		}
		out = append(out, row)
	}
	return out, total, rows.Err()
}

func (s *Store) GetGradingAnswer(ctx context.Context, answerID int) (*GradingAnswer, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row GradingAnswer
	err := s.pool.QueryRow(ctx, `
SELECT a.id, a.session_id, COALESCE(es.status, ''), e.id, e.title, e.creator_id,
       COALESCE(creator.role, ''), student.id,
       COALESCE(student.full_name, student.username, ''), COALESCE(student.username, ''),
       student.student_class, q.id, q.question_text, q.question_type, q.image_url,
       COALESCE(q.points, 1), a.answer_text, a.points_earned, a.is_correct,
       COALESCE(a.answer_metadata, '{}'::jsonb), a.answered_at
  FROM answers a
  JOIN questions q ON q.id = a.question_id
  JOIN exam_sessions es ON es.id = a.session_id
  JOIN exams e ON e.id = es.exam_id
  JOIN users creator ON creator.id = e.creator_id
  JOIN users student ON student.id = es.user_id
 WHERE a.id = $1`, answerID).Scan(
		&row.AnswerID, &row.SessionID, &row.SessionStatus, &row.ExamID, &row.ExamTitle,
		&row.ExamCreatorID, &row.ExamCreatorRole, &row.StudentID, &row.StudentName,
		&row.StudentUsername, &row.StudentClass, &row.QuestionID, &row.QuestionText,
		&row.QuestionType, &row.QuestionImage, &row.MaxPoints, &row.AnswerText,
		&row.Points, &row.IsCorrect, &row.Metadata, &row.SubmittedAt,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) GradeAnswer(ctx context.Context, answerID, graderID int, graderName string, points float64, feedback string) (int, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var sessionID int
	var metadata []byte
	err = tx.QueryRow(ctx, `SELECT session_id, COALESCE(answer_metadata, '{}'::jsonb) FROM answers WHERE id = $1 FOR UPDATE`, answerID).Scan(&sessionID, &metadata)
	if err != nil {
		return 0, err
	}
	data := map[string]any{}
	_ = json.Unmarshal(metadata, &data)
	data["grader_feedback"] = feedback
	data["graded_by"] = graderID
	data["grader_name"] = graderName
	data["graded_at"] = time.Now().UTC().Format(time.RFC3339)
	encoded, _ := json.Marshal(data)
	if _, err := tx.Exec(ctx, `
UPDATE answers SET points_earned = $2, is_correct = true, answer_metadata = $3::jsonb
 WHERE id = $1`, answerID, points, string(encoded)); err != nil {
		return 0, err
	}
	if err := recalculateSessionScore(ctx, tx, sessionID); err != nil {
		return 0, err
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return sessionID, nil
}

func recalculateSessionScore(ctx context.Context, tx pgx.Tx, sessionID int) error {
	var score float64
	err := tx.QueryRow(ctx, `
SELECT CASE WHEN totals.possible > 0
            THEN ROUND((COALESCE(earned.value, 0) / totals.possible * 100)::numeric, 2)
            ELSE 0 END
  FROM exam_sessions es
  CROSS JOIN LATERAL (
    SELECT COALESCE(SUM(q.points), 0)::float8 AS possible
      FROM questions q WHERE q.exam_id = es.exam_id
  ) totals
  CROSS JOIN LATERAL (
    SELECT COALESCE(SUM(a.points_earned), 0)::float8 AS value
      FROM answers a WHERE a.session_id = es.id
  ) earned
 WHERE es.id = $1`, sessionID).Scan(&score)
	if err != nil {
		return err
	}
	_, err = tx.Exec(ctx, `UPDATE exam_sessions SET score = $2 WHERE id = $1`, sessionID, score)
	return err
}

func (s *Store) GradingStats(ctx context.Context, ownerID int, hideDeveloper bool) (GradingStatsRow, error) {
	out := GradingStatsRow{ByExam: map[string]int{}}
	if !s.HasPool() {
		return out, fmt.Errorf("no pgx pool")
	}
	base := `
  FROM answers a
  JOIN questions q ON q.id = a.question_id
  JOIN exam_sessions es ON es.id = a.session_id
  JOIN exams e ON e.id = es.exam_id
  JOIN users creator ON creator.id = e.creator_id
 WHERE COALESCE(e.is_deleted, false) = false
   AND es.status IN ('submitted', 'completed')`
	args := []any{}
	scope, args := gradingScope(ownerID, hideDeveloper, args)
	base += scope
	err := s.pool.QueryRow(ctx, `
SELECT COUNT(*) FILTER (WHERE
         (q.question_type IN ('essay','short_answer') AND a.is_correct IS NULL)
         OR (q.question_type = 'short_answer' AND a.is_correct = false))::int,
       COUNT(*) FILTER (WHERE q.question_type = 'essay' AND a.is_correct IS NULL)::int,
       COUNT(*) FILTER (WHERE q.question_type = 'short_answer' AND (a.is_correct IS NULL OR a.is_correct = false))::int,
       COUNT(*) FILTER (WHERE q.question_type IN ('essay','short_answer')
         AND a.is_correct IS NOT NULL AND a.answered_at >= NOW() - interval '24 hours')::int`+base, args...).Scan(
		&out.TotalPending, &out.EssayPending, &out.ShortAnswerPending, &out.RecentlyGraded,
	)
	if err != nil {
		return out, err
	}
	rows, err := s.pool.Query(ctx, `
SELECT e.title, COUNT(*)::int`+base+`
   AND ((q.question_type IN ('essay','short_answer') AND a.is_correct IS NULL)
        OR (q.question_type = 'short_answer' AND a.is_correct = false))
 GROUP BY e.id, e.title`, args...)
	if err != nil {
		return out, err
	}
	defer rows.Close()
	for rows.Next() {
		var title string
		var count int
		if err := rows.Scan(&title, &count); err != nil {
			return out, err
		}
		out.ByExam[title] = count
	}
	return out, rows.Err()
}
