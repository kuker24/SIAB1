-- Add Guru Pengawas role and migrate existing teacher+pengawas accounts.
-- Safe to run repeatedly.

ALTER TABLE users
DROP CONSTRAINT IF EXISTS users_role_check;

ALTER TABLE users
ADD CONSTRAINT users_role_check
CHECK (role IN ('developer', 'admin', 'teacher', 'student', 'guruplus', 'gurupengawas'));

UPDATE users
SET role = 'gurupengawas'
WHERE lower(trim(role)) = 'teacher'
  AND job_title IS NOT NULL
  AND (
    lower(job_title) LIKE '%pengawas%'
    OR lower(trim(job_title)) IN ('proktor', 'invigilator')
  );
