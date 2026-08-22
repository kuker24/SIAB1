package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type ViolationRow struct {
	ID        int
	SessionID int
	ExamID    int
	ExamTitle string
	UserID    int
	Name      string
	Username  string
	Class     *string
	EventType string
	EventData []byte
	CreatedAt time.Time
}

func (s *Store) ListViolations(ctx context.Context, examID, ownerID int, hideDeveloper bool, from, to time.Time, countedOnly bool) ([]ViolationRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	args := []any{from, to}
	where := []string{
		"l.created_at >= $1", "l.created_at <= $2", "COALESCE(e.is_deleted,false)=false",
		"lower(l.event_type) LIKE 'violation_%'",
		"lower(l.event_type) NOT IN ('violation_security_warning','violation_accessibility_risk')",
	}
	if examID > 0 {
		args = append(args, examID)
		where = append(where, fmt.Sprintf("es.exam_id=$%d", len(args)))
	}
	if ownerID > 0 {
		args = append(args, ownerID)
		where = append(where, fmt.Sprintf("e.creator_id=$%d", len(args)))
	}
	if hideDeveloper {
		where = append(where, "COALESCE(c.role,'') <> 'developer'")
	}
	if countedOnly {
		where = append(where, `lower(COALESCE(l.event_data->>'counted_for_score','true')) IN ('true','t','1','yes','y','on')`)
	}
	rows, err := s.pool.Query(ctx, `
SELECT l.id,l.session_id,es.exam_id,COALESCE(e.title,es.archived_exam_title,'Ujian #'||es.exam_id),
       u.id,COALESCE(u.full_name,u.username),u.username,u.student_class,
       l.event_type,COALESCE(l.event_data,'{}'::jsonb),l.created_at
  FROM exam_logs l JOIN exam_sessions es ON es.id=l.session_id
  JOIN users u ON u.id=es.user_id LEFT JOIN exams e ON e.id=es.exam_id
  LEFT JOIN users c ON c.id=e.creator_id
 WHERE `+strings.Join(where, " AND ")+` ORDER BY l.created_at DESC,l.id DESC LIMIT 10000`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []ViolationRow{}
	for rows.Next() {
		var row ViolationRow
		if err := rows.Scan(&row.ID, &row.SessionID, &row.ExamID, &row.ExamTitle,
			&row.UserID, &row.Name, &row.Username, &row.Class, &row.EventType,
			&row.EventData, &row.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}
