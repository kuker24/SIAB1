-- Promote existing developer accounts without changing credentials.
-- Safe to re-run (idempotent).

BEGIN;

-- Promote pre-existing "developer" account from admin -> developer.
UPDATE users
SET
    role = 'developer',
    student_class = NULL
WHERE lower(username) = 'developer';

-- Rename legacy secondary developer account if still using the old username.
-- Only rename when target username does not already exist to avoid conflicts.
UPDATE users
SET
    username = 'kamad',
    full_name = 'kamad',
    role = 'developer',
    student_class = NULL,
    job_title = 'Developer',
    is_active = TRUE
WHERE lower(username) = 'kamat'
  AND NOT EXISTS (
      SELECT 1
      FROM users target
      WHERE lower(target.username) = 'kamad'
  );

-- Normalize an existing secondary developer account.
UPDATE users
SET
    full_name = 'kamad',
    role = 'developer',
    student_class = NULL,
    job_title = 'Developer',
    is_active = TRUE
WHERE lower(username) = 'kamad';

COMMIT;
