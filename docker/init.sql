-- PostgreSQL Schema for Online Exam System
-- Version 2.1 - Clean Slate (Admin Only, No Email)
-- All timestamps use TIMESTAMPTZ with UTC default

-- ============================================================================
-- USERS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('developer', 'admin', 'teacher', 'student', 'guruplus', 'gurupengawas')),
    student_class VARCHAR(50),  -- Kelas (Untuk Siswa)
    job_title VARCHAR(100),     -- Jabatan (Untuk Guru)
    student_id VARCHAR(50),     -- NIS/NIP (Opsional)
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    last_login TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    profile_picture VARCHAR(255)
);

-- ============================================================================
-- EXAMS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS exams (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    creator_id INTEGER REFERENCES users(id),
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    passing_score DECIMAL(5,2) CHECK (passing_score >= 0 AND passing_score <= 100),
    max_attempts INTEGER DEFAULT 1,
    shuffle_questions BOOLEAN DEFAULT FALSE,
    shuffle_options BOOLEAN DEFAULT FALSE,
    show_results BOOLEAN DEFAULT FALSE,
    allow_review BOOLEAN DEFAULT FALSE,
    seb_config_key VARCHAR(255) NOT NULL,
    seb_browser_exam_key VARCHAR(255),
    seb_mobile_protocol_url TEXT,
    is_published BOOLEAN DEFAULT FALSE,
    access_token VARCHAR(10) UNIQUE,
    subject VARCHAR(100),
    exam_type VARCHAR(100),
    academic_year VARCHAR(20),
    show_teacher_name BOOLEAN DEFAULT TRUE,
    builder_settings JSONB DEFAULT '{}'::jsonb,
    allowed_classes TEXT,
    allowed_students TEXT,
    is_globally_paused BOOLEAN DEFAULT FALSE,
    globally_paused_at TIMESTAMPTZ,
    globally_paused_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMPTZ,
    has_ever_had_results BOOLEAN DEFAULT FALSE NOT NULL
);

-- ============================================================================
-- QUESTION CATEGORIES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS question_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    parent_id INTEGER REFERENCES question_categories(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- QUESTION TAGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS question_tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    color VARCHAR(20) DEFAULT '#6c757d',
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- QUESTIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER REFERENCES exams(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES question_categories(id) ON DELETE SET NULL,
    question_text TEXT NOT NULL,
    stimulus TEXT,
    question_type VARCHAR(50) NOT NULL CHECK (question_type IN (
        'multiple_choice',
        'multiple_choice_complex',
        'true_false',
        'essay',
        'short_answer'
    )),
    question_subtype VARCHAR(50) DEFAULT NULL,
    pgk_type VARCHAR(50) DEFAULT 'checkbox',
    difficulty_level VARCHAR(20) CHECK (difficulty_level IN ('easy', 'medium', 'hard')) DEFAULT 'medium',
    question_settings JSONB DEFAULT '{}',
    points DECIMAL(5,2) NOT NULL DEFAULT 1.00,
    order_index INTEGER NOT NULL,
    image_url VARCHAR(255),
    video_url VARCHAR(255),
    audio_url VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- QUESTION TAGS MAPPING
-- ============================================================================
CREATE TABLE IF NOT EXISTS question_tags_map (
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES question_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, tag_id)
);

-- ============================================================================
-- QUESTION OPTIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS question_options (
    id SERIAL PRIMARY KEY,
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    option_text TEXT NOT NULL,
    is_correct BOOLEAN DEFAULT FALSE,
    order_index INTEGER NOT NULL,
    option_group VARCHAR(20) DEFAULT 'standard',
    pair_id VARCHAR(50) DEFAULT NULL,
    option_metadata JSONB DEFAULT '{}'
);

-- ============================================================================
-- EXAM SESSIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS exam_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    exam_id INTEGER REFERENCES exams(id),
    start_time TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    end_time TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL CHECK (status IN ('in_progress', 'completed', 'submitted', 'abandoned', 'terminated')),
    score DECIMAL(5,2),
    ip_address INET,
    user_agent TEXT,
    seb_detected BOOLEAN DEFAULT FALSE,
    is_secure_app_verified BOOLEAN DEFAULT FALSE,
    violation_count INTEGER DEFAULT 0,
    emergency_exit_allowed BOOLEAN DEFAULT FALSE,
    terminated_by_admin BOOLEAN DEFAULT FALSE,
    is_paused BOOLEAN DEFAULT FALSE,
    paused_at TIMESTAMPTZ,
    total_paused_seconds INTEGER DEFAULT 0,
    archived_exam_title VARCHAR(255),
    archived_exam_subject VARCHAR(100),
    archived_exam_type VARCHAR(100),
    app_signature VARCHAR(128),
    app_version VARCHAR(20),
    is_suspicious BOOLEAN DEFAULT FALSE
);

-- ============================================================================
-- ANSWERS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS answers (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES exam_sessions(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(id),
    selected_option_id INTEGER REFERENCES question_options(id),
    selected_option_ids INTEGER[] DEFAULT NULL,
    matching_pairs JSONB DEFAULT NULL,
    answer_text TEXT,
    is_correct BOOLEAN,
    points_earned DECIMAL(5,2),
    answer_metadata JSONB DEFAULT '{}',
    answered_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- EXAM LOGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS exam_logs (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES exam_sessions(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- SECURITY EVENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    user_id INTEGER REFERENCES users(id),
    session_id INTEGER REFERENCES exam_sessions(id),
    ip_address VARCHAR(45),
    user_agent TEXT,
    endpoint VARCHAR(200),
    method VARCHAR(10),
    app_signature VARCHAR(128),
    app_version VARCHAR(20),
    expected_signature VARCHAR(128),
    extra_data TEXT,
    severity VARCHAR(20) DEFAULT 'medium',
    timestamp TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- USER ACTIVITY LOGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB DEFAULT '{}',
    ip_address VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- EXAM TEMPLATES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS exam_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    creator_id INTEGER REFERENCES users(id),
    template_data JSONB,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- SCHEDULED PUBLICATIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS scheduled_publications (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER REFERENCES exams(id) ON DELETE CASCADE NOT NULL,
    publish_at TIMESTAMPTZ NOT NULL,
    unpublish_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'unpublished', 'cancelled')),
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    executed_at TIMESTAMPTZ,
    error_message TEXT
);

-- ============================================================================
-- MEDIA FILES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS media_files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_url TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    mime_type VARCHAR(100),
    file_size BIGINT NOT NULL,
    width INTEGER,
    height INTEGER,
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    tags TEXT[],
    description TEXT,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ
);

-- ============================================================================
-- NOTIFICATIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    data JSONB DEFAULT '{}'::jsonb,
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    action_url TEXT,
    priority VARCHAR(20) DEFAULT 'normal'
);

-- ============================================================================
-- SUBJECTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    creator_id INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- ============================================================================
-- APK BUILDS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS apk_builds (
    id SERIAL PRIMARY KEY,
    app_name VARCHAR(100) NOT NULL,
    package_name VARCHAR(100) DEFAULT 'com.ujianonline.seb',
    version VARCHAR(20) DEFAULT '1.0.0',
    icon_path VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending',
    build_log TEXT,
    error_message TEXT,
    file_path VARCHAR(255),
    file_size BIGINT,
    build_time_seconds INTEGER,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    completed_at TIMESTAMPTZ
);

-- ============================================================================
-- SEB BUILDS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS seb_builds (
    id SERIAL PRIMARY KEY,
    build_name VARCHAR(200) NOT NULL,
    platform VARCHAR(20) DEFAULT 'all',
    start_url TEXT NOT NULL,
    config_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    config_key VARCHAR(255),
    browser_exam_key VARCHAR(255),
    admin_password_hash VARCHAR(255),
    quit_password_hash VARCHAR(255),
    file_path VARCHAR(255),
    file_size BIGINT,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    completed_at TIMESTAMPTZ,
    CONSTRAINT seb_builds_name_unique UNIQUE (build_name, created_by)
);

-- ============================================================================
-- SEB CONFIG TEMPLATES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS seb_config_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    config_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    preset_type VARCHAR(50) DEFAULT 'custom',
    is_default BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT FALSE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
    CONSTRAINT seb_templates_name_unique UNIQUE (name, created_by)
);

-- ============================================================================
-- SYSTEM SETTINGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_settings (
    id SERIAL PRIMARY KEY,
    allow_browser_testing BOOLEAN NOT NULL DEFAULT FALSE,
    allow_mobile_apps BOOLEAN NOT NULL DEFAULT TRUE,
    maintenance_mode BOOLEAN NOT NULL DEFAULT FALSE,
    minimum_apk_token VARCHAR(100),
    allowed_signatures TEXT,
    token_validation_bypass BOOLEAN NOT NULL DEFAULT FALSE,
    app_name VARCHAR(100) DEFAULT 'Ujian Online',
    timezone VARCHAR(50) DEFAULT 'Asia/Jakarta',
    updated_at TIMESTAMP,
    updated_by INTEGER REFERENCES users(id)
);

-- ============================================================================
-- DEFAULT DATA
-- ============================================================================

-- 1. DEFAULT SUBJECTS
INSERT INTO subjects (name) VALUES
    ('Matematika'), ('Bahasa Indonesia'), ('Bahasa Inggris'),
    ('Fisika'), ('Kimia'), ('Biologi'),
    ('Sejarah'), ('Geografi'), ('Ekonomi'), ('Sosiologi'),
    ('PKn'), ('Seni Budaya'), ('PJOK'), ('TIK')
ON CONFLICT (name) DO NOTHING;

-- 2. DEFAULT SYSTEM SETTINGS
INSERT INTO system_settings (allow_browser_testing, allow_mobile_apps, maintenance_mode, updated_at)
VALUES (FALSE, TRUE, FALSE, NOW())
ON CONFLICT DO NOTHING;

-- 5. DEFAULT SEB TEMPLATES (Standard presets)
INSERT INTO seb_config_templates (name, description, preset_type, config_data, is_default, is_public, created_by)
VALUES
(
    'Strict Security',
    'Maximum security preset for high-stakes exams.',
    'strict',
    '{"browserWindowAllowReload": false, "showTaskBar": false, "enableRightMouse": false, "killExplorerShell": true, "blockPopUpWindows": true}'::jsonb,
    true, true, 1
),
(
    'Standard Balanced',
    'Balanced security and usability.',
    'standard',
    '{"browserWindowAllowReload": true, "showTaskBar": true, "enableRightMouse": false, "killExplorerShell": false, "blockPopUpWindows": true}'::jsonb,
    true, true, 1
)
ON CONFLICT (name, created_by) DO NOTHING;

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_exam_sessions_user_exam ON exam_sessions(user_id, exam_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_role_student_class ON users(role, student_class);
CREATE INDEX IF NOT EXISTS idx_questions_exam ON questions(exam_id);
CREATE INDEX IF NOT EXISTS idx_questions_exam_order ON questions(exam_id, order_index);
CREATE UNIQUE INDEX IF NOT EXISTS uq_answers_session_question ON answers(session_id, question_id);
CREATE INDEX IF NOT EXISTS idx_answers_session_question ON answers(session_id, question_id);
CREATE INDEX IF NOT EXISTS idx_answers_question_id ON answers(question_id);
CREATE INDEX IF NOT EXISTS idx_exam_sessions_exam_status_end_time ON exam_sessions(exam_id, status, end_time);
CREATE UNIQUE INDEX IF NOT EXISTS uq_seb_default_core_presets
    ON seb_config_templates (preset_type)
    WHERE is_default = TRUE AND preset_type IN ('strict', 'standard', 'permissive');
