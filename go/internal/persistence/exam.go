package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

var apkTokenPattern = regexp.MustCompile(`BUILD-\d{14}-[A-Z0-9]{6}`)

type UserRow struct {
	ID           int
	Username     string
	FullName     string
	Role         string
	StudentClass *string
	JobTitle     *string
	IsActive     bool
	CreatedAt    time.Time
	LastLogin    *time.Time
	ProfilePic   *string
	PasswordHash string
}

type APKSettings struct {
	Bypass            bool
	BrowserTest       bool
	MinimumToken      string
	AllowedSignatures string
	Freeze            bool
	Maintenance       bool
}

type SubmitProbe struct {
	SessionID    int
	ExamID       int
	Status       string
	Score        *float64
	ShowResults  bool
	PassingScore *float64
}

type ExamRow struct {
	ID               int
	Title            string
	Description      *string
	DurationMinutes  int
	StartTime        time.Time
	EndTime          time.Time
	MaxAttempts      int
	ShuffleQuestions bool
	ShuffleOptions   bool
	ShowResults      bool
	ShowTeacherName  bool
	Subject          *string
	ExamType         *string
	AcademicYear     *string
	AllowReview      bool
	PassingScore     *float64
	Published        bool
	Deleted          bool
	CreatorID        int
	TeacherName      *string
	CreatorRole      *string
	AccessToken      *string
	AllowedClasses   *string
	AllowedStudents  *string
	QuestionCount    int
	CreatedAt        time.Time
}

const examSelect = `
SELECT e.id, e.title, e.description, e.duration_minutes, e.start_time, e.end_time,
       COALESCE(e.max_attempts, 1), COALESCE(e.shuffle_questions, false),
       COALESCE(e.shuffle_options, false), COALESCE(e.show_results, false),
       COALESCE(e.show_teacher_name, true), e.subject, e.exam_type, e.academic_year,
       COALESCE(e.allow_review, false), e.passing_score,
       COALESCE(e.is_published, false), COALESCE(e.is_deleted, false),
       e.creator_id, u.full_name, u.role, e.access_token,
       e.allowed_classes, e.allowed_students,
       (SELECT COUNT(*) FROM questions q WHERE q.exam_id = e.id),
       COALESCE(e.created_at, e.start_time)
  FROM exams e
  LEFT JOIN users u ON u.id = e.creator_id`

func examScan(e *ExamRow) []any {
	return []any{
		&e.ID, &e.Title, &e.Description, &e.DurationMinutes, &e.StartTime, &e.EndTime,
		&e.MaxAttempts, &e.ShuffleQuestions, &e.ShuffleOptions, &e.ShowResults,
		&e.ShowTeacherName, &e.Subject, &e.ExamType, &e.AcademicYear,
		&e.AllowReview, &e.PassingScore, &e.Published, &e.Deleted,
		&e.CreatorID, &e.TeacherName, &e.CreatorRole, &e.AccessToken,
		&e.AllowedClasses, &e.AllowedStudents, &e.QuestionCount, &e.CreatedAt,
	}
}

type SessionRow struct {
	ID                 int
	UserID             int
	ExamID             int
	StartTime          time.Time
	Status             string
	DurationMinutes    int
	TotalPausedSeconds int
	IsPaused           bool
	ViolationCount     int
	EmergencyExit      bool
	TerminatedByAdmin  bool
	ExamTitle          string
}

type QuestionRow struct {
	ID         int     `json:"id"`
	ExamID     int     `json:"-"`
	Text       string  `json:"question_text"`
	Stimulus   *string `json:"stimulus"`
	Type       string  `json:"question_type"`
	PgkType    *string `json:"pgk_type"`
	Difficulty string  `json:"difficulty_level,omitempty"`
	Settings   []byte  `json:"question_settings"`
	Points     float64 `json:"-"`
	PointsText string  `json:"points"`
	OrderIndex int     `json:"order_index"`
	ImageURL   *string `json:"image_url"`
	VideoURL   *string `json:"video_url"`
	AudioURL   *string `json:"audio_url"`
	CategoryID *int
	Options    []OptionRow `json:"options"`
}

type OptionRow struct {
	ID          int     `json:"id"`
	QuestionID  int     `json:"-"`
	Text        string  `json:"option_text"`
	OrderIndex  int     `json:"order_index"`
	OptionGroup string  `json:"option_group"`
	PairID      *string `json:"pair_id"`
	IsCorrect   bool    `json:"-"`
}

func (s *Store) GetUser(ctx context.Context, id int) (*UserRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var u UserRow
	err := s.pool.QueryRow(ctx, `
SELECT id, username, full_name, role, student_class, job_title, is_active,
       created_at, last_login, profile_picture
  FROM users WHERE id = $1`, id).Scan(
		&u.ID, &u.Username, &u.FullName, &u.Role, &u.StudentClass, &u.JobTitle,
		&u.IsActive, &u.CreatedAt, &u.LastLogin, &u.ProfilePic,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (s *Store) GetUserByUsername(ctx context.Context, username string) (*UserRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var u UserRow
	err := s.pool.QueryRow(ctx, `
SELECT id, username, full_name, role, student_class, job_title, is_active,
       created_at, last_login, profile_picture, password_hash
  FROM users WHERE lower(username) = lower($1)`, username).Scan(
		&u.ID, &u.Username, &u.FullName, &u.Role, &u.StudentClass, &u.JobTitle,
		&u.IsActive, &u.CreatedAt, &u.LastLogin, &u.ProfilePic, &u.PasswordHash,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (s *Store) APKSettings(ctx context.Context) (*APKSettings, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row APKSettings
	var token, sigs *string
	err := s.pool.QueryRow(ctx, `
SELECT COALESCE(token_validation_bypass, false),
       COALESCE(allow_browser_testing, false),
       minimum_apk_token,
       allowed_signatures,
       COALESCE(freeze_mode, false),
       COALESCE(maintenance_mode, false)
  FROM system_settings
 ORDER BY id
 LIMIT 1`).Scan(&row.Bypass, &row.BrowserTest, &token, &sigs, &row.Freeze, &row.Maintenance)
	if err == pgx.ErrNoRows {
		return &APKSettings{}, nil
	}
	if err != nil {
		return nil, err
	}
	if token != nil {
		row.MinimumToken = *token
	}
	if sigs != nil {
		row.AllowedSignatures = *sigs
	}
	return &row, nil
}

func ParseAPKTokens(raw string) []string {
	found := apkTokenPattern.FindAllString(strings.ToUpper(raw), -1)
	out := make([]string, 0, len(found))
	seen := map[string]struct{}{}
	for _, tok := range found {
		if _, ok := seen[tok]; ok {
			continue
		}
		seen[tok] = struct{}{}
		out = append(out, tok)
	}
	return out
}

func (s *Store) GetExam(ctx context.Context, examID int) (*ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var e ExamRow
	err := s.pool.QueryRow(ctx, examSelect+" WHERE e.id = $1", examID).Scan(examScan(&e)...)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &e, nil
}

func (s *Store) GetExamByToken(ctx context.Context, token string) (*ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var e ExamRow
	err := s.pool.QueryRow(ctx, examSelect+" WHERE upper(e.access_token) = $1 AND COALESCE(e.is_deleted, false) = false", token).Scan(examScan(&e)...)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &e, nil
}

type ExamListFilter struct {
	Limit         int
	Offset        int
	PublishedOnly bool
	CreatorID     int
	HideDeveloper bool
}

func (s *Store) ListExamsFiltered(ctx context.Context, f ExamListFilter) ([]ExamRow, int, error) {
	if !s.HasPool() {
		return nil, 0, fmt.Errorf("no pgx pool")
	}
	if f.Limit <= 0 {
		f.Limit = 10000
	}
	if f.Offset < 0 {
		f.Offset = 0
	}
	where := []string{"COALESCE(e.is_deleted, false) = false"}
	args := []any{}
	n := 1
	if f.PublishedOnly {
		where = append(where, "COALESCE(e.is_published, false) = true")
	}
	if f.CreatorID > 0 {
		where = append(where, fmt.Sprintf("e.creator_id = $%d", n))
		args = append(args, f.CreatorID)
		n++
	}
	if f.HideDeveloper {
		where = append(where, "COALESCE(lower(u.role), '') <> 'developer'")
	}
	clause := " WHERE " + strings.Join(where, " AND ")
	var total int
	countSQL := `SELECT COUNT(*) FROM exams e LEFT JOIN users u ON u.id = e.creator_id` + clause
	if err := s.pool.QueryRow(ctx, countSQL, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	args = append(args, f.Limit, f.Offset)
	rows, err := s.pool.Query(ctx, examSelect+clause+fmt.Sprintf(`
 ORDER BY e.start_time DESC, e.id DESC
 LIMIT $%d OFFSET $%d`, n, n+1), args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	var out []ExamRow
	for rows.Next() {
		var e ExamRow
		if err := rows.Scan(examScan(&e)...); err != nil {
			return nil, 0, err
		}
		out = append(out, e)
	}
	return out, total, rows.Err()
}

func (s *Store) ExamPauseStatus(ctx context.Context, examID int) (paused bool, pausedAt *time.Time, found bool, err error) {
	if !s.HasPool() {
		return false, nil, false, fmt.Errorf("no pgx pool")
	}
	err = s.pool.QueryRow(ctx, `
SELECT COALESCE(is_globally_paused, false), globally_paused_at
  FROM exams
 WHERE id = $1 AND COALESCE(is_deleted, false) = false`, examID).Scan(&paused, &pausedAt)
	if err == pgx.ErrNoRows {
		return false, nil, false, nil
	}
	if err != nil {
		return false, nil, false, err
	}
	return paused, pausedAt, true, nil
}

func (s *Store) ListPublishedExams(ctx context.Context, limit, offset int) ([]ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if limit <= 0 {
		limit = 10000
	}
	if offset < 0 {
		offset = 0
	}
	rows, err := s.pool.Query(ctx, examSelect+`
 WHERE COALESCE(e.is_published, false) = true
   AND COALESCE(e.is_deleted, false) = false
 ORDER BY e.start_time DESC, e.id DESC
 LIMIT $1 OFFSET $2`, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ExamRow
	for rows.Next() {
		var e ExamRow
		if err := rows.Scan(examScan(&e)...); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

func (s *Store) ListMyResults(ctx context.Context, userID int) ([]ExamRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, examSelect+`
  JOIN exam_sessions es ON es.exam_id = e.id
 WHERE es.user_id = $1 AND es.status IN ('completed', 'submitted')
 ORDER BY es.end_time DESC NULLS LAST, es.id DESC`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ExamRow
	for rows.Next() {
		var e ExamRow
		if err := rows.Scan(examScan(&e)...); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

func (s *Store) ExamSEBKeys(ctx context.Context, examID int) (configKey, browserKey string, found bool, err error) {
	if !s.HasPool() {
		return "", "", false, fmt.Errorf("no pgx pool")
	}
	err = s.pool.QueryRow(ctx, `
SELECT COALESCE(seb_config_key, ''), COALESCE(seb_browser_exam_key, '')
  FROM exams WHERE id = $1 AND COALESCE(is_deleted, false) = false`, examID).Scan(&configKey, &browserKey)
	if err == pgx.ErrNoRows {
		return "", "", false, nil
	}
	if err != nil {
		return "", "", false, err
	}
	return configKey, browserKey, true, nil
}

func (s *Store) HasLiveSession(ctx context.Context, userID, examID int) (bool, error) {
	if !s.HasPool() {
		return false, fmt.Errorf("no pgx pool")
	}
	var id int
	err := s.pool.QueryRow(ctx, `
SELECT id FROM exam_sessions
 WHERE user_id = $1 AND exam_id = $2 AND status IN ('in_progress', 'active', 'paused')
 ORDER BY start_time DESC, id DESC
 LIMIT 1`, userID, examID).Scan(&id)
	if err == pgx.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

func (s *Store) ActiveSession(ctx context.Context, userID, examID int) (*SessionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row SessionRow
	err := s.pool.QueryRow(ctx, `
SELECT id, user_id, exam_id, start_time, status
  FROM exam_sessions
 WHERE user_id = $1 AND exam_id = $2 AND status IN ('in_progress', 'active')
 ORDER BY start_time DESC, id DESC
 LIMIT 1`, userID, examID).Scan(
		&row.ID, &row.UserID, &row.ExamID, &row.StartTime, &row.Status,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) AdminBlockedSession(ctx context.Context, userID, examID int) (*SessionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row SessionRow
	err := s.pool.QueryRow(ctx, `
SELECT es.id, es.user_id, es.exam_id, es.start_time, es.status,
       COALESCE(es.violation_count, 0), true
  FROM exam_sessions es
 WHERE es.user_id = $1
   AND es.exam_id = $2
   AND es.status IN ('terminated', 'kicked')
   AND (
       COALESCE(es.terminated_by_admin, false)
       OR EXISTS (
           SELECT 1 FROM exam_logs el
            WHERE el.session_id = es.id
              AND el.event_type IN (
                  'FORCE_SUBMIT_BY_TEACHER', 'SESSION_TERMINATED',
                  'ADMIN_KICK_STUDENT', 'SESSION_FORCE_KICK'
              )
       )
   )
 ORDER BY es.start_time DESC, es.id DESC
 LIMIT 1`, userID, examID).Scan(
		&row.ID, &row.UserID, &row.ExamID, &row.StartTime, &row.Status,
		&row.ViolationCount, &row.TerminatedByAdmin,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) CompletedAttemptCount(ctx context.Context, userID, examID int) (int, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `
SELECT COUNT(*) FROM exam_sessions
 WHERE user_id = $1 AND exam_id = $2 AND status IN ('completed', 'submitted')`,
		userID, examID).Scan(&n)
	return n, err
}

func (s *Store) CreateSession(ctx context.Context, userID, examID int) (*SessionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row SessionRow
	err := s.pool.QueryRow(ctx, `
INSERT INTO exam_sessions (
  user_id, exam_id, start_time, status, seb_detected, is_secure_app_verified,
  violation_count, emergency_exit_allowed, terminated_by_admin, is_paused,
  total_paused_seconds
) VALUES ($1, $2, NOW(), 'in_progress', true, true, 0, false, false, false, 0)
RETURNING id, user_id, exam_id, start_time, status`,
		userID, examID).Scan(
		&row.ID, &row.UserID, &row.ExamID, &row.StartTime, &row.Status,
	)
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) TimerSession(ctx context.Context, sessionID, userID int) (*SessionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row SessionRow
	err := s.pool.QueryRow(ctx, `
SELECT es.id, es.user_id, es.exam_id, es.start_time, es.status,
       e.duration_minutes, COALESCE(es.total_paused_seconds, 0),
       COALESCE(es.is_paused, false) OR COALESCE(e.is_globally_paused, false),
       COALESCE(es.violation_count, 0),
       COALESCE(es.emergency_exit_allowed, false),
       COALESCE(es.terminated_by_admin, false),
       e.title
  FROM exam_sessions es
  JOIN exams e ON e.id = es.exam_id
 WHERE es.id = $1 AND es.user_id = $2`, sessionID, userID).Scan(
		&row.ID, &row.UserID, &row.ExamID, &row.StartTime, &row.Status,
		&row.DurationMinutes, &row.TotalPausedSeconds, &row.IsPaused,
		&row.ViolationCount, &row.EmergencyExit, &row.TerminatedByAdmin, &row.ExamTitle,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (s *Store) LoadQuestions(ctx context.Context, examID int) ([]QuestionRow, error) {
	return s.loadQuestions(ctx, examID, false)
}

func (s *Store) LoadQuestionsForGrade(ctx context.Context, examID int) ([]QuestionRow, error) {
	return s.loadQuestions(ctx, examID, true)
}

func (s *Store) loadQuestions(ctx context.Context, examID int, withKeys bool) ([]QuestionRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	qrows, err := s.pool.Query(ctx, `
SELECT id, question_text, stimulus, question_type, pgk_type,
       COALESCE(difficulty_level, 'medium'), COALESCE(question_settings, '{}'::jsonb),
       COALESCE(points, 1)::text, order_index, image_url, video_url, audio_url
  FROM questions WHERE exam_id = $1 ORDER BY order_index, id`, examID)
	if err != nil {
		return nil, err
	}
	defer qrows.Close()
	var questions []QuestionRow
	ids := make([]int, 0)
	for qrows.Next() {
		var q QuestionRow
		if err := qrows.Scan(
			&q.ID, &q.Text, &q.Stimulus, &q.Type, &q.PgkType, &q.Difficulty,
			&q.Settings, &q.PointsText, &q.OrderIndex, &q.ImageURL, &q.VideoURL, &q.AudioURL,
		); err != nil {
			return nil, err
		}
		q.Points, _ = strconv.ParseFloat(q.PointsText, 64)
		questions = append(questions, q)
		ids = append(ids, q.ID)
	}
	if err := qrows.Err(); err != nil {
		return nil, err
	}
	if len(ids) == 0 {
		return questions, nil
	}
	optSQL := `
SELECT id, question_id, option_text, order_index,
       COALESCE(option_group, 'standard'), pair_id, false
  FROM question_options
 WHERE question_id = ANY($1)
 ORDER BY order_index, id`
	if withKeys {
		optSQL = `
SELECT id, question_id, option_text, order_index,
       COALESCE(option_group, 'standard'), pair_id, COALESCE(is_correct, false)
  FROM question_options
 WHERE question_id = ANY($1)
 ORDER BY order_index, id`
	}
	orows, err := s.pool.Query(ctx, optSQL, ids)
	if err != nil {
		return nil, err
	}
	defer orows.Close()
	byQ := map[int][]OptionRow{}
	for orows.Next() {
		var o OptionRow
		if err := orows.Scan(&o.ID, &o.QuestionID, &o.Text, &o.OrderIndex, &o.OptionGroup, &o.PairID, &o.IsCorrect); err != nil {
			return nil, err
		}
		byQ[o.QuestionID] = append(byQ[o.QuestionID], o)
	}
	if err := orows.Err(); err != nil {
		return nil, err
	}
	for i := range questions {
		questions[i].Options = byQ[questions[i].ID]
	}
	return questions, nil
}

func SanitizeSettings(raw []byte) map[string]any {
	out := map[string]any{}
	if len(raw) == 0 {
		return out
	}
	_ = json.Unmarshal(raw, &out)
	delete(out, "is_correct")
	delete(out, "correct_statements")
	delete(out, "statement_answers")
	delete(out, "acceptable_answers")
	return out
}
