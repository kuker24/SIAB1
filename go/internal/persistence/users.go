package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type UserListFilter struct {
	Role          string
	StudentClass  string
	IsActive      *bool
	Search        string
	CreatedAfter  *time.Time
	CreatedBefore *time.Time
	SortBy        string
	SortOrder     string
	Offset        int
	Limit         int
}

type UserPatch struct {
	Username     *string
	FullName     *string
	PasswordHash *string
	Role         *string
	StudentClass *string
	SetClass     bool
	JobTitle     *string
	IsActive     *bool
	ProfilePic   *string
	SetPic       bool
}

func (s *Store) ListStudentClasses(ctx context.Context) ([]string, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	rows, err := s.pool.Query(ctx, `
SELECT DISTINCT TRIM(student_class)
  FROM users
 WHERE role = 'student'
   AND student_class IS NOT NULL
   AND TRIM(student_class) <> ''
 ORDER BY 1`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		if name != "" {
			out = append(out, name)
		}
	}
	return out, rows.Err()
}

func (s *Store) ListStudentsByClass(ctx context.Context, role, className string) ([]UserRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	q := `
SELECT id, username, full_name, role, student_class, job_title, is_active,
       created_at, last_login, profile_picture
  FROM users WHERE role = $1`
	args := []any{role}
	if className != "" {
		q += ` AND student_class = $2`
		args = append(args, className)
	}
	q += ` ORDER BY full_name ASC, username ASC`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []UserRow
	for rows.Next() {
		var u UserRow
		if err := rows.Scan(&u.ID, &u.Username, &u.FullName, &u.Role, &u.StudentClass, &u.JobTitle,
			&u.IsActive, &u.CreatedAt, &u.LastLogin, &u.ProfilePic); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	return out, rows.Err()
}

func userSortColumn(sortBy string) string {
	switch sortBy {
	case "id":
		return "id"
	case "username":
		return "username"
	case "full_name":
		return "full_name"
	default:
		return "created_at"
	}
}

func appendUserFilters(q string, args []any, f UserListFilter) (string, []any) {
	if f.Role != "" {
		args = append(args, f.Role)
		q += fmt.Sprintf(` AND role = $%d`, len(args))
	}
	if f.StudentClass != "" {
		args = append(args, f.StudentClass)
		q += fmt.Sprintf(` AND student_class = $%d`, len(args))
	}
	if f.IsActive != nil {
		args = append(args, *f.IsActive)
		q += fmt.Sprintf(` AND is_active = $%d`, len(args))
	}
	if strings.TrimSpace(f.Search) != "" {
		args = append(args, "%"+strings.TrimSpace(f.Search)+"%")
		q += fmt.Sprintf(` AND (username ILIKE $%d OR full_name ILIKE $%d)`, len(args), len(args))
	}
	if f.CreatedAfter != nil {
		args = append(args, *f.CreatedAfter)
		q += fmt.Sprintf(` AND created_at >= $%d`, len(args))
	}
	if f.CreatedBefore != nil {
		args = append(args, *f.CreatedBefore)
		q += fmt.Sprintf(` AND created_at <= $%d`, len(args))
	}
	return q, args
}

func (s *Store) ListUsers(ctx context.Context, f UserListFilter) ([]UserRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	if f.Limit <= 0 {
		f.Limit = 1000
	}
	if f.Limit > 2000 {
		f.Limit = 2000
	}
	if f.Offset < 0 {
		f.Offset = 0
	}
	q := `
SELECT id, username, full_name, role, student_class, job_title, is_active,
       created_at, last_login, profile_picture
  FROM users WHERE 1=1`
	args := []any{}
	q, args = appendUserFilters(q, args, f)
	dir := "DESC"
	if strings.EqualFold(f.SortOrder, "asc") {
		dir = "ASC"
	}
	col := userSortColumn(f.SortBy)
	args = append(args, f.Limit, f.Offset)
	q += fmt.Sprintf(` ORDER BY %s %s, id %s LIMIT $%d OFFSET $%d`, col, dir, dir, len(args)-1, len(args))
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []UserRow
	for rows.Next() {
		var u UserRow
		if err := rows.Scan(&u.ID, &u.Username, &u.FullName, &u.Role, &u.StudentClass, &u.JobTitle,
			&u.IsActive, &u.CreatedAt, &u.LastLogin, &u.ProfilePic); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	return out, rows.Err()
}

func (s *Store) CountUsers(ctx context.Context, f UserListFilter) (int, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	q := `SELECT COUNT(*) FROM users WHERE 1=1`
	args := []any{}
	q, args = appendUserFilters(q, args, f)
	var n int
	if err := s.pool.QueryRow(ctx, q, args...).Scan(&n); err != nil {
		return 0, err
	}
	return n, nil
}

func (s *Store) UsernameTaken(ctx context.Context, username string, exceptID int) (bool, error) {
	if !s.HasPool() {
		return false, fmt.Errorf("no pgx pool")
	}
	var n int
	err := s.pool.QueryRow(ctx, `
SELECT COUNT(*) FROM users WHERE username = $1 AND id <> $2`, username, exceptID).Scan(&n)
	return n > 0, err
}

func (s *Store) CreateUser(ctx context.Context, username, hash, fullName, role string, studentClass, jobTitle *string) (*UserRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	var u UserRow
	err := s.pool.QueryRow(ctx, `
INSERT INTO users (username, password_hash, full_name, role, student_class, job_title, is_active, created_at)
VALUES ($1, $2, $3, $4, $5, $6, true, NOW())
RETURNING id, username, full_name, role, student_class, job_title, is_active,
          created_at, last_login, profile_picture`,
		username, hash, fullName, role, studentClass, jobTitle,
	).Scan(&u.ID, &u.Username, &u.FullName, &u.Role, &u.StudentClass, &u.JobTitle,
		&u.IsActive, &u.CreatedAt, &u.LastLogin, &u.ProfilePic)
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (s *Store) UpdateUser(ctx context.Context, id int, patch UserPatch) (*UserRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	sets := []string{}
	args := []any{}
	add := func(col string, val any) {
		args = append(args, val)
		sets = append(sets, fmt.Sprintf("%s = $%d", col, len(args)))
	}
	if patch.Username != nil {
		add("username", *patch.Username)
	}
	if patch.FullName != nil {
		add("full_name", *patch.FullName)
	}
	if patch.PasswordHash != nil {
		add("password_hash", *patch.PasswordHash)
	}
	if patch.Role != nil {
		add("role", *patch.Role)
	}
	if patch.SetClass {
		add("student_class", patch.StudentClass)
	}
	if patch.JobTitle != nil {
		add("job_title", *patch.JobTitle)
	}
	if patch.IsActive != nil {
		add("is_active", *patch.IsActive)
	}
	if patch.SetPic {
		add("profile_picture", patch.ProfilePic)
	}
	if len(sets) == 0 {
		return s.GetUser(ctx, id)
	}
	args = append(args, id)
	q := `UPDATE users SET ` + strings.Join(sets, ", ") + fmt.Sprintf(` WHERE id = $%d
RETURNING id, username, full_name, role, student_class, job_title, is_active,
          created_at, last_login, profile_picture`, len(args))
	var u UserRow
	err := s.pool.QueryRow(ctx, q, args...).Scan(
		&u.ID, &u.Username, &u.FullName, &u.Role, &u.StudentClass, &u.JobTitle,
		&u.IsActive, &u.CreatedAt, &u.LastLogin, &u.ProfilePic,
	)
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (s *Store) SoftDeleteUser(ctx context.Context, id int) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	_, err := s.pool.Exec(ctx, `UPDATE users SET is_active = false WHERE id = $1`, id)
	return err
}

func (s *Store) BatchUpdateUsers(ctx context.Context, ids []int, fields map[string]any) (int64, error) {
	if !s.HasPool() {
		return 0, fmt.Errorf("no pgx pool")
	}
	if len(ids) == 0 || len(fields) == 0 {
		return 0, nil
	}
	sets := []string{}
	args := []any{}
	for col, val := range fields {
		args = append(args, val)
		sets = append(sets, fmt.Sprintf("%s = $%d", col, len(args)))
	}
	args = append(args, ids)
	q := `UPDATE users SET ` + strings.Join(sets, ", ") + fmt.Sprintf(` WHERE id = ANY($%d)`, len(args))
	tag, err := s.pool.Exec(ctx, q, args...)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

func (s *Store) CountUsersByRole(ctx context.Context, ids []int, role string) (int, error) {
	if !s.HasPool() || len(ids) == 0 {
		return 0, nil
	}
	var n int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM users WHERE id = ANY($1) AND role = $2`, ids, role).Scan(&n)
	return n, err
}

func (s *Store) BatchSoftDeleteUsers(ctx context.Context, ids []int) (int64, error) {
	if !s.HasPool() || len(ids) == 0 {
		return 0, nil
	}
	tag, err := s.pool.Exec(ctx, `UPDATE users SET is_active = false WHERE id = ANY($1)`, ids)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

func (s *Store) BatchHardDeleteUsers(ctx context.Context, ids []int) (int64, error) {
	if !s.HasPool() || len(ids) == 0 {
		return 0, nil
	}
	tag, err := s.pool.Exec(ctx, `DELETE FROM users WHERE id = ANY($1)`, ids)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

func (s *Store) ListExportUsers(ctx context.Context, f UserListFilter) ([]UserRow, error) {
	if !s.HasPool() {
		return nil, fmt.Errorf("no pgx pool")
	}
	q := `
SELECT id, username, full_name, role, student_class, job_title, is_active,
       created_at, last_login, profile_picture
  FROM users WHERE role NOT IN ('admin', 'developer')`
	args := []any{}
	q, args = appendUserFilters(q, args, f)
	q += ` ORDER BY created_at DESC, id DESC`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []UserRow
	for rows.Next() {
		var u UserRow
		if err := rows.Scan(&u.ID, &u.Username, &u.FullName, &u.Role, &u.StudentClass, &u.JobTitle,
			&u.IsActive, &u.CreatedAt, &u.LastLogin, &u.ProfilePic); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	return out, rows.Err()
}

func (s *Store) LogUserActivity(ctx context.Context, userID int, eventType string, data []byte) error {
	if !s.HasPool() {
		return fmt.Errorf("no pgx pool")
	}
	if len(data) == 0 {
		data = []byte("{}")
	}
	_, err := s.pool.Exec(ctx, `
INSERT INTO user_activity_logs (user_id, event_type, event_data) VALUES ($1, $2, $3::jsonb)`,
		userID, eventType, data)
	return err
}
