# Ujian Online Jules Up5 V1 — Codebase Map

> Complete file registry and dependency map for the Ujian Online Jules Up5 V1 system.
> Last updated: 2026-02-24

---

## 📁 Entry Points

| File | Purpose |
| :--- | :--- |
| `app/main.py` | FastAPI application entry point (14KB, CORS, middleware, routers) |
| `flutter_client_code/lib/main.dart` | Flutter client entry point |
| `docker-compose.production.yml` | Production infrastructure orchestration |

---

## ⚙️ Configuration Files

| File | Purpose |
| :--- | :--- |
| `.env.production` | Environment variables for production (secrets, DB URL, Redis) |
| `.env.example` | Environment variable template |
| `app/config.py` | Pydantic Settings — centralizes all env vars |
| `app/logging_config.py` | Logging format and handler configuration |
| `requirements.txt` | Python package dependencies |

---

## 🛣️ API Endpoints (`app/api/`)

| File | Domain | Notes |
| :--- | :--- | :--- |
| `auth.py` | Authentication | Login, refresh tokens, logout |
| `exams.py` | Exams (core) | CRUD, session join, submit answers (115KB — largest file) |
| `exam_admin.py` | Admin exam tools | Publish, archive, clone exams |
| `exam_seb.py` | SEB exams | SEB-only exam controls |
| `questions.py` | Question bank | CRUD, import/export |
| `grading.py` | Grading | Manual/auto grading, result release |
| `analytics.py` | Analytics | IRT, score distributions, item analysis |
| `users.py` | User management | CRUD, roles, bulk CSV upload |
| `account_security.py` | Account security | Lockout status, unlock, password policy |
| `activity.py` | Activity logs | User activity trail |
| `alerts.py` | Alerts | System alert triggers |
| `apk.py` | APK distribution | APK upload, download, version tracking |
| `backup.py` | Backup/restore | DB backup, restore (20KB) |
| `media.py` | Media | Image/file upload for questions |
| `metrics.py` | Prometheus | `/metrics` endpoint |
| `monitoring.py` | System health | Service checks, warmup (25KB) |
| `notifications.py` | Notifications | Push + in-app notifications |
| `scheduled.py` | Scheduled tasks | CRUD for scheduled jobs |
| `seb_autoconfig.py` | SEB autoconfig | Auto-generate SEB configs (17KB) |
| `seb_builder.py` | SEB builder | Build/export SEB packages (17KB) |
| `security_analytics.py` | Security events | Security event query & reporting |
| `stats.py` | Dashboard stats | Summary statistics for dashboards |
| `subjects.py` | Subjects | Academic subject management |
| `sxb.py` | SXB | SXB (custom SEB wrapper) integration |
| `system_settings.py` | System settings | Admin-level system configuration |
| `telegram_admin.py` | Telegram admin | Bot command handlers |
| `templates.py` | Exam templates | Reusable exam template management |
| `upload.py` | File upload | Generic file upload utility |
| `websocket.py` | WebSocket | Real-time notifications (9KB) |

---

## 🧱 Core Modules (`app/core/`)

| File | Responsibility |
| :--- | :--- |
| `security.py` | JWT creation/validation, password hashing |
| `token_service.py` | Refresh/access token lifecycle |
| `cache.py` | Redis get/set helpers |
| `cache_manager.py` | Cache invalidation, key management (9KB) |
| `rate_limiter.py` | Per-user/IP rate limiting (Redis-backed) |
| `account_lockout.py` | Brute-force protection, lockout logic (9KB) |
| `captcha.py` | CAPTCHA validation integration |
| `sanitization.py` | Input sanitization & XSS prevention |
| `seb.py` | Safe Exam Browser protocol handling (17KB) |
| `sxb_security.py` | SXB enforcement logic |
| `audit_logger.py` | Security audit trail to DB |
| `security_logging.py` | Structured security event logging |
| `alerting.py` | Multi-channel alerting system (11KB) |
| `error_handlers.py` | Global FastAPI exception handlers |
| `metrics_collector.py` | Prometheus metrics collection (11KB) |
| `pdf_generator.py` | PDF report generation (13KB) |
| `irt_analysis.py` | Item Response Theory scoring (10KB) |
| `query_optimizer.py` | SQLAlchemy query optimization helpers |
| `redis_pubsub.py` | Redis pub/sub for WebSocket events |
| `structured_logging.py` | JSON structured log output |
| `assets.py` | Static asset path management |

---

## 🔒 Middleware (`app/middleware/`)

| File | Purpose | Order |
| :--- | :--- | :--- |
| `security.py` | Security headers, HTTPS enforcement | 1st |
| `csrf_protection.py` | CSRF token validation | 2nd |
| `seb_validation.py` | SEB request header verification (10KB) | 3rd |
| `sxb_enforcer.py` | SXB protocol enforcement (9KB) | 4th |
| `logging_middleware.py` | Request/response logging | 5th |
| `performance.py` | Response time measurement | 6th |
| `performance_monitoring.py` | Perf metrics to Prometheus | 7th |

---

## 🗄️ Database Models (`app/models/`)

| File | Entity | Key Relationships |
| :--- | :--- | :--- |
| `user.py` | User | → Session, ActivityLog, SecurityEvent |
| `exam.py` | Exam | → Session, Question, Subject (4KB) |
| `question.py` | Question | → Exam, Answer, Tag, Media (13KB — complex) |
| `session.py` | ExamSession | → User, Exam, Answer (5KB) |
| `notification.py` | Notification | → User |
| `security_event.py` | SecurityEvent | → User |
| `activity_log.py` | ActivityLog | → User |
| `scheduled.py` | ScheduledTask | standalone |
| `seb_config_template.py` | SEBConfigTemplate | → Exam |
| `seb_build.py` | SEBBuild | → SEBConfigTemplate |
| `apk_build.py` | APKBuild | standalone |
| `tag.py` | Tag | → Question |
| `category.py` | Category | → Question |
| `subject.py` | Subject | → Exam |
| `media.py` | Media | → Question |
| `refresh_token.py` | RefreshToken | → User |
| `exam_template.py` | ExamTemplate | → Exam |

---

## 📐 Schemas (`app/schemas/`)

| File | Covers |
| :--- | :--- |
| `exam.py` | ExamCreate, ExamUpdate, ExamResponse (11KB) |
| `answer.py` | AnswerSubmit, BulkAnswerSubmit (7KB) |
| `question_bank.py` | QuestionBankImport/Export |
| `user.py` | UserCreate, UserUpdate, UserResponse |
| `common.py` | PaginatedResponse, StatusResponse (3KB) |
| `template.py` | TemplateCreate, TemplateResponse |
| `scheduled.py` | ScheduledTaskCreate/Response |
| `notification.py` | NotificationCreate/Response |
| `media.py` | MediaUploadResponse |

---

## ⚙️ Background Tasks (`app/tasks/`)

| File | Celery Task | Trigger |
| :--- | :--- | :--- |
| `answer_processor.py` | `process_answers` | On exam submission (7KB) |
| `scheduler.py` | Beat schedule | Time-based (11KB) |
| `views_refresher.py` | `refresh_views` | Periodic |

---

## 🛠️ Utilities (`app/utils/`)

| File | Purpose |
| :--- | :--- |
| `telegram_alerts.py` | Send Telegram messages/alerts (8KB) |
| `telegram_utils.py` | Bot helpers, formatting |
| `apk_validation.py` | APK signature & integrity checks (10KB) |
| `seed_presets.py` | Seed database with preset data |

---

## 🔗 Core Dependency Map

```
app/main.py
  ├── app/api/*.py              (all 30 routers)
  │     ├── app/services/       (business logic)
  │     ├── app/models/         (DB entities via SQLAlchemy)
  │     ├── app/schemas/        (Pydantic validation)
  │     └── app/core/           (security, cache, etc.)
  ├── app/middleware/           (ASGI stack, applied in order)
  ├── app/database.py           (async session factory)
  └── app/config.py             (settings singleton)

app/tasks/*.py
  ├── app/core/celery_app       (broker=Redis)
  ├── app/models/               (DB writes)
  └── app/core/pdf_generator.py (PDF output via tasks)

flutter_client_code/
  └── → app/api/                (REST + WebSocket)
```

---

## 📊 Codebase Statistics

| Metric | Value |
| :--- | :--- |
| **API endpoint files** | 30 |
| **Database models** | 17+ |
| **Pydantic schemas** | 10 |
| **Core utility modules** | 22 |
| **Middleware layers** | 7 |
| **Celery task modules** | 4 |
| **HTML templates** | 28 |
| **Static asset files** | 38+ |
| **Primary language** | Python + Dart |
| **Largest file** | `app/api/exams.py` (~115KB) |
