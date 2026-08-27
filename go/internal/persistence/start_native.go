package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/redis/go-redis/v9"
)

type StartSecuritySettings struct {
	DeveloperMode     bool
	AllowMobileApps   bool
	MinimumAPKToken   string
	AllowedSignatures string
}

type StartExamRow struct {
	ID               int
	CreatorID        int
	Published        bool
	StartTime        time.Time
	EndTime          time.Time
	MaxAttempts      int
	AllowedClasses   *string
	AllowedStudents  *string
	DurationMinutes  int
	ShuffleQuestions bool
	ShuffleOptions   bool
	Title            string
	Subject          *string
	ExamType         *string
	ShowResults      bool
	ShowTeacherName  *bool
	TeacherName      *string
	CreatorRole      *string
	SEBConfigKey     string
	SEBBrowserKey    *string
}

func (e *StartExamRow) TeacherVisible() bool {
	return e != nil && e.ShowTeacherName != nil && *e.ShowTeacherName
}

func (e *StartExamRow) ShowTeacher() bool {
	return e == nil || e.ShowTeacherName == nil || *e.ShowTeacherName
}

type StartSessionRow struct {
	ID                   int
	UserID               int
	ExamID               int
	Status               string
	StartTime            time.Time
	EndTime              *time.Time
	TerminatedByAdmin    bool
	EmergencyExitAllowed bool
	ViolationCount       int
	TotalPausedSeconds   int
}

type StartSessionState struct {
	AttemptCount int
	Sessions     []StartSessionRow
}

type StartClientInfo struct {
	IPAddress   string
	UserAgent   string
	SEBDetected bool
	StartTime   time.Time
}

type SessionStartLog struct {
	IP              string
	SEBDetected     bool
	Title           string
	Subject         *string
	ExamType        *string
	AllowedClasses  *string
	AllowedStudents *string
	ExamStartTime   time.Time
	ExamEndTime     time.Time
	DurationMinutes int
}

type StartTransaction interface {
	Exam(context.Context, int) (*StartExamRow, error)
	ValidateOptionIntegrity(context.Context, int) ([]int, error)
	SessionState(context.Context, int, int) (StartSessionState, error)
	AnswerCounts(context.Context, []int) (map[int]int, error)
	SessionLogs(context.Context, int, int) ([]SessionLog, error)
	RecoverSession(context.Context, StartSessionRow, string, string) (*StartSessionRow, error)
	CreateSessionWithLog(context.Context, int, int, StartClientInfo, SessionStartLog) (*StartSessionRow, error)
	Commit(context.Context) error
	Rollback(context.Context) error
}

type pgStartTransaction struct {
	tx pgx.Tx
}

func (s *Store) BeginStart(ctx context.Context) (StartTransaction, error) {
	if s == nil || s.pool == nil {
		return nil, fmt.Errorf("no pgx pool")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	return &pgStartTransaction{tx: tx}, nil
}

func (s *Store) LoadStartSecuritySettings(ctx context.Context) (StartSecuritySettings, error) {
	if s == nil || s.pool == nil {
		return StartSecuritySettings{}, fmt.Errorf("no pgx pool")
	}
	var row StartSecuritySettings
	err := s.pool.QueryRow(ctx, `
SELECT COALESCE(allow_browser_testing, false),
       COALESCE(allow_mobile_apps, true),
       COALESCE(minimum_apk_token, ''),
       COALESCE(allowed_signatures, '')
  FROM system_settings
 ORDER BY id
 LIMIT 1`).Scan(
		&row.DeveloperMode,
		&row.AllowMobileApps,
		&row.MinimumAPKToken,
		&row.AllowedSignatures,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return StartSecuritySettings{AllowMobileApps: true}, nil
	}
	return row, err
}

func (s *Store) StartSEBKeys(ctx context.Context, examID int) (configKey, browserKey string, found bool, err error) {
	if s == nil || s.pool == nil {
		return "", "", false, fmt.Errorf("no pgx pool")
	}
	err = s.pool.QueryRow(ctx, `
SELECT COALESCE(seb_config_key, ''), COALESCE(seb_browser_exam_key, '')
  FROM exams
 WHERE id = $1`, examID).Scan(&configKey, &browserKey)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", "", false, nil
	}
	if err != nil {
		return "", "", false, err
	}
	return configKey, browserKey, true, nil
}

func (t *pgStartTransaction) Exam(ctx context.Context, examID int) (*StartExamRow, error) {
	var row StartExamRow
	err := t.tx.QueryRow(ctx, `
SELECT e.id, e.creator_id, COALESCE(e.is_published, false), e.start_time, e.end_time,
       COALESCE(e.max_attempts, 1), e.allowed_classes, e.allowed_students,
       COALESCE(e.duration_minutes, 0), COALESCE(e.shuffle_questions, false),
       COALESCE(e.shuffle_options, false), e.title, e.subject, e.exam_type,
       COALESCE(e.show_results, false), e.show_teacher_name,
       u.full_name, u.role, COALESCE(e.seb_config_key, ''), e.seb_browser_exam_key
  FROM exams e
  LEFT JOIN users u ON u.id = e.creator_id
 WHERE e.id = $1`, examID).Scan(
		&row.ID, &row.CreatorID, &row.Published, &row.StartTime, &row.EndTime,
		&row.MaxAttempts, &row.AllowedClasses, &row.AllowedStudents,
		&row.DurationMinutes, &row.ShuffleQuestions, &row.ShuffleOptions,
		&row.Title, &row.Subject, &row.ExamType, &row.ShowResults,
		&row.ShowTeacherName, &row.TeacherName, &row.CreatorRole,
		&row.SEBConfigKey, &row.SEBBrowserKey,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (t *pgStartTransaction) ValidateOptionIntegrity(ctx context.Context, examID int) ([]int, error) {
	rows, err := t.tx.Query(ctx, `
SELECT q.id
  FROM questions q
  LEFT JOIN question_options qo ON q.id = qo.question_id
 WHERE q.exam_id = $1
   AND qo.id IS NULL
   AND (
       q.question_type IN ('multiple_choice', 'true_false')
       OR (
           q.question_type = 'multiple_choice_complex'
           AND COALESCE(q.pgk_type, 'checkbox') <> 'table_validation'
       )
   )
 GROUP BY q.id, q.question_text, q.question_type`, examID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ids []int
	for rows.Next() {
		var id int
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func (t *pgStartTransaction) SessionState(ctx context.Context, userID, examID int) (StartSessionState, error) {
	rows, err := t.tx.Query(ctx, `
WITH attempt_count AS (
    SELECT COUNT(*)::int AS count
      FROM exam_sessions
     WHERE user_id = $1 AND exam_id = $2
       AND status IN ('completed', 'submitted')
), existing AS (
    SELECT id, user_id, exam_id, status, start_time, end_time,
           COALESCE(terminated_by_admin, false) AS terminated_by_admin,
           COALESCE(emergency_exit_allowed, false) AS emergency_exit_allowed,
           COALESCE(violation_count, 0) AS violation_count,
           COALESCE(total_paused_seconds, 0) AS total_paused_seconds
      FROM exam_sessions
     WHERE user_id = $1 AND exam_id = $2
       AND status IN ('in_progress', 'active', 'terminated', 'kicked')
     ORDER BY start_time DESC, id DESC
     LIMIT 16
)
SELECT attempt_count.count, existing.id, existing.user_id, existing.exam_id,
       existing.status, existing.start_time, existing.end_time,
       existing.terminated_by_admin, existing.emergency_exit_allowed,
       existing.violation_count, existing.total_paused_seconds
  FROM attempt_count
  LEFT JOIN existing ON true`, userID, examID)
	if err != nil {
		return StartSessionState{}, err
	}
	defer rows.Close()
	state := StartSessionState{}
	for rows.Next() {
		var id, uid, eid *int
		var status *string
		var start *time.Time
		var end *time.Time
		var terminated, emergency *bool
		var violations, paused *int
		if err := rows.Scan(
			&state.AttemptCount, &id, &uid, &eid, &status, &start, &end,
			&terminated, &emergency, &violations, &paused,
		); err != nil {
			return StartSessionState{}, err
		}
		if id == nil {
			continue
		}
		state.Sessions = append(state.Sessions, StartSessionRow{
			ID: *id, UserID: *uid, ExamID: *eid, Status: *status,
			StartTime: *start, EndTime: end,
			TerminatedByAdmin: *terminated, EmergencyExitAllowed: *emergency,
			ViolationCount: *violations, TotalPausedSeconds: *paused,
		})
	}
	return state, rows.Err()
}

func (t *pgStartTransaction) AnswerCounts(ctx context.Context, sessionIDs []int) (map[int]int, error) {
	counts := map[int]int{}
	if len(sessionIDs) == 0 {
		return counts, nil
	}
	rows, err := t.tx.Query(ctx, `
SELECT session_id, COUNT(*)::int
  FROM answers
 WHERE session_id = ANY($1)
 GROUP BY session_id`, sessionIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var id, count int
		if err := rows.Scan(&id, &count); err != nil {
			return nil, err
		}
		counts[id] = count
	}
	return counts, rows.Err()
}

func (t *pgStartTransaction) SessionLogs(ctx context.Context, sessionID, limit int) ([]SessionLog, error) {
	rows, err := t.tx.Query(ctx, `
SELECT event_type, COALESCE(event_data, '{}'::jsonb), created_at
  FROM exam_logs
 WHERE session_id = $1
 ORDER BY created_at DESC, id DESC
 LIMIT $2`, sessionID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var logs []SessionLog
	for rows.Next() {
		var log SessionLog
		if err := rows.Scan(&log.EventType, &log.Data, &log.CreatedAt); err != nil {
			return nil, err
		}
		logs = append(logs, log)
	}
	return logs, rows.Err()
}

func (t *pgStartTransaction) RecoverSession(
	ctx context.Context,
	session StartSessionRow,
	category string,
	message string,
) (*StartSessionRow, error) {
	err := t.tx.QueryRow(ctx, `
UPDATE exam_sessions
   SET status = 'in_progress', end_time = NULL,
       terminated_by_admin = false, emergency_exit_allowed = false
 WHERE id = $1
RETURNING id, user_id, exam_id, status, start_time, end_time,
          COALESCE(terminated_by_admin, false),
          COALESCE(emergency_exit_allowed, false),
          COALESCE(violation_count, 0),
          COALESCE(total_paused_seconds, 0)`, session.ID).Scan(
		&session.ID, &session.UserID, &session.ExamID, &session.Status,
		&session.StartTime, &session.EndTime, &session.TerminatedByAdmin,
		&session.EmergencyExitAllowed, &session.ViolationCount,
		&session.TotalPausedSeconds,
	)
	if err != nil {
		return nil, err
	}
	payload, err := json.Marshal(map[string]any{
		"category": category,
		"message":  message,
		"trigger":  "start_exam_session",
	})
	if err != nil {
		return nil, err
	}
	if _, err := t.tx.Exec(ctx, `
INSERT INTO exam_logs (session_id, event_type, event_data, created_at)
VALUES ($1, 'SESSION_AUTO_RESET_NETWORK', $2::jsonb, NOW())`, session.ID, string(payload)); err != nil {
		return nil, err
	}
	return &session, nil
}

func (t *pgStartTransaction) CreateSessionWithLog(
	ctx context.Context,
	userID int,
	examID int,
	client StartClientInfo,
	logData SessionStartLog,
) (*StartSessionRow, error) {
	var row StartSessionRow
	err := t.tx.QueryRow(ctx, `
INSERT INTO exam_sessions (
    user_id, exam_id, start_time, status, ip_address, user_agent, seb_detected
) VALUES ($1, $2, $6, 'in_progress', NULLIF($3, '')::inet, $4, $5)
RETURNING id, user_id, exam_id, status, start_time, end_time,
          COALESCE(terminated_by_admin, false),
          COALESCE(emergency_exit_allowed, false),
          COALESCE(violation_count, 0),
          COALESCE(total_paused_seconds, 0)`,
		userID, examID, client.IPAddress, client.UserAgent, client.SEBDetected, client.StartTime,
	).Scan(
		&row.ID, &row.UserID, &row.ExamID, &row.Status, &row.StartTime,
		&row.EndTime, &row.TerminatedByAdmin, &row.EmergencyExitAllowed,
		&row.ViolationCount, &row.TotalPausedSeconds,
	)
	if err != nil {
		return nil, err
	}
	payload, err := json.Marshal(map[string]any{
		"ip":           logData.IP,
		"seb_detected": logData.SEBDetected,
		"exam_snapshot": map[string]any{
			"title":            logData.Title,
			"subject":          logData.Subject,
			"exam_type":        logData.ExamType,
			"allowed_classes":  logData.AllowedClasses,
			"allowed_students": logData.AllowedStudents,
			"start_time":       formatPythonTime(logData.ExamStartTime),
			"end_time":         formatPythonTime(logData.ExamEndTime),
			"duration_minutes": logData.DurationMinutes,
		},
	})
	if err != nil {
		return nil, err
	}
	if _, err := t.tx.Exec(ctx, `
INSERT INTO exam_logs (session_id, event_type, event_data, created_at)
VALUES ($1, 'SESSION_START', $2::jsonb, NOW())`, row.ID, string(payload)); err != nil {
		return nil, err
	}
	return &row, nil
}

func (t *pgStartTransaction) Commit(ctx context.Context) error {
	return t.tx.Commit(ctx)
}

func (t *pgStartTransaction) Rollback(ctx context.Context) error {
	return t.tx.Rollback(ctx)
}

func (s *Store) CanonicalActiveStartSession(ctx context.Context, userID, examID int) (*StartSessionRow, error) {
	if s == nil || s.pool == nil {
		return nil, fmt.Errorf("no pgx pool")
	}
	var row StartSessionRow
	err := s.pool.QueryRow(ctx, `
SELECT id, user_id, exam_id, status, start_time, end_time,
       COALESCE(terminated_by_admin, false),
       COALESCE(emergency_exit_allowed, false),
       COALESCE(violation_count, 0),
       COALESCE(total_paused_seconds, 0)
  FROM exam_sessions
 WHERE user_id = $1 AND exam_id = $2
   AND status IN ('in_progress', 'active')
 ORDER BY start_time DESC, id DESC`, userID, examID).Scan(
		&row.ID, &row.UserID, &row.ExamID, &row.Status, &row.StartTime,
		&row.EndTime, &row.TerminatedByAdmin, &row.EmergencyExitAllowed,
		&row.ViolationCount, &row.TotalPausedSeconds,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func IsIntegrityError(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && len(pgErr.Code) >= 2 && pgErr.Code[:2] == "23"
}

func (s *Store) RedisGet(ctx context.Context, key string) (string, bool, error) {
	if s == nil || s.redis == nil {
		return "", false, fmt.Errorf("no redis client")
	}
	value, err := s.redis.Get(ctx, key).Result()
	if errors.Is(err, redis.Nil) {
		return "", false, nil
	}
	return value, err == nil, err
}

func (s *Store) RedisSet(ctx context.Context, key, value string, ttl time.Duration) error {
	if s == nil || s.redis == nil {
		return fmt.Errorf("no redis client")
	}
	return s.redis.Set(ctx, key, value, ttl).Err()
}

func (s *Store) RedisSetNX(ctx context.Context, key, value string, ttl time.Duration) (bool, error) {
	if s == nil || s.redis == nil {
		return false, fmt.Errorf("no redis client")
	}
	return s.redis.SetNX(ctx, key, value, ttl).Result()
}

func (s *Store) RedisDelete(ctx context.Context, key string) error {
	if s == nil || s.redis == nil {
		return fmt.Errorf("no redis client")
	}
	return s.redis.Del(ctx, key).Err()
}

func (s *Store) RedisPublish(ctx context.Context, channel, value string) error {
	if s == nil || s.redis == nil {
		return fmt.Errorf("no redis client")
	}
	return s.redis.Publish(ctx, channel, value).Err()
}

func (s *Store) RedisXAdd(ctx context.Context, key, event string, maxLen, ttlSeconds int) error {
	if s == nil || s.redis == nil {
		return fmt.Errorf("no redis client")
	}
	if maxLen < 500 {
		maxLen = 500
	}
	if ttlSeconds < 300 {
		ttlSeconds = 300
	}
	if err := s.redis.XAdd(ctx, &redis.XAddArgs{
		Stream: key,
		MaxLen: int64(maxLen),
		Approx: true,
		Values: map[string]any{"event": event},
	}).Err(); err != nil {
		return err
	}
	return s.redis.Expire(ctx, key, time.Duration(ttlSeconds)*time.Second).Err()
}

func formatPythonTime(value time.Time) string {
	return pythonISOTime(value)
}

func pythonISOTime(value time.Time) string {
	value = value.UTC().Truncate(time.Microsecond)
	base := value.Format("2006-01-02T15:04:05")
	if micros := value.Nanosecond() / 1000; micros > 0 {
		base += fmt.Sprintf(".%06d", micros)
	}
	return base + "+00:00"
}
