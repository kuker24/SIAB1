"""
FastAPI Main Application Entry Point
SIAB1 - Sistem Informasi Asesmen Berintegritas
"""
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from jinja2 import TemplateNotFound
import logging

from app.config import settings
from app.database import init_db
from app.core.redis_pubsub import init_redis, close_redis
from app.api import auth, users, exams, exam_crud, answer_sync, final_submit, violation_events, exam_answer_sync, exam_session_runtime, exam_offline_package, exam_pause_control, exam_exports, questions, websocket, stats, sxb, seb_autoconfig, runtime
from app.api import grading, analytics, monitoring
from app.api import exam_seb, exam_admin

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""

    # Startup
    logger.info("Starting application...")

    # Initialize database tables (creates any missing tables)
    try:
        # Import all models to ensure they're registered with Base
        import app.models as models_registry
        _ = models_registry
        await init_db()
        logger.info("Database tables initialized successfully")

        # Seed default SEB presets if they don't exist
        try:
            from app.database import async_session_write
            from app.utils.seed_presets import seed_default_presets
            async with async_session_write() as session:
                await seed_default_presets(session)
                await session.commit()
            logger.info("SEB presets seeded successfully")
        except Exception as seed_err:
            logger.warning(f"Could not seed SEB presets: {seed_err}")
    except Exception as db_err:
        logger.error(f"Database initialization failed: {db_err}")

    # Initialize Redis
    await init_redis()
    logger.info("Redis connection established")

    # Send Telegram startup notification (fire and forget)
    # Use Redis lock to prevent duplicate notifications from multiple workers
    if settings.telegram_alerting_active:
        try:
            from app.utils.telegram_utils import send_system_startup_notification
            from app.core.redis_pubsub import get_redis
            import asyncio

            redis = await get_redis()
            lock_key = "startup_notification_lock"

            # Try to acquire lock (expires in 10 seconds)
            lock_acquired = await redis.set(lock_key, "1", nx=True, ex=10)

            if lock_acquired:
                # Schedule notification and give it time to complete
                asyncio.ensure_future(send_system_startup_notification())
                logger.info("Telegram startup notification scheduled (lock acquired)")
                # Wait 2 seconds to ensure notification sends before startup completes
                await asyncio.sleep(2)
            else:
                logger.info("Startup notification skipped (another worker already sent)")
        except Exception as telegram_err:
            logger.warning(f"Could not send startup notification: {telegram_err}")
    else:
        logger.info("Telegram startup notification disabled by feature flag")

    # Start async violation event drain loop (best-effort, non-critical path)
    app.state.violation_event_task = None
    app.state.violation_event_stop = None
    try:
        import asyncio
        if settings.violation_async_enabled:
            from app.services.violation_event_service import violation_event_drain_loop

            app.state.violation_event_stop = asyncio.Event()
            app.state.violation_event_task = asyncio.create_task(
                violation_event_drain_loop(app.state.violation_event_stop)
            )
            logger.info("Async violation event drain loop scheduled")
        else:
            logger.info("Async violation event drain loop disabled by feature flag")
    except Exception as violation_task_err:
        logger.warning(f"Could not start violation event drain loop: {violation_task_err}")

    # Start runtime answer buffer drain loop (active only when answer queue flags enable it)
    app.state.answer_buffer_task = None
    app.state.answer_buffer_stop = None
    try:
        import asyncio
        from app.services.answer_runtime_buffer import (
            answer_runtime_buffer_drain_loop,
            is_runtime_answer_buffer_enabled,
        )

        if is_runtime_answer_buffer_enabled():
            app.state.answer_buffer_stop = asyncio.Event()
            app.state.answer_buffer_task = asyncio.create_task(
                answer_runtime_buffer_drain_loop(app.state.answer_buffer_stop)
            )
            logger.info("Answer runtime buffer drain loop scheduled")
        else:
            logger.info("Answer runtime buffer drain loop disabled by feature flags")
    except Exception as answer_buffer_err:
        logger.warning(f"Could not start answer runtime buffer drain loop: {answer_buffer_err}")

    # Start background alerting system
    app.state.alerting_task = None
    app.state.alerting_lock_owner = False
    app.state.alerting_lock_key = "alerting_monitor_lock"
    app.state.alerting_lock_value = None
    try:
        import os
        import asyncio
        if os.getenv("ENABLE_ALERTING_SYSTEM", "true").lower() == "true":
            from app.core.alerting import alerting_system
            from app.core.redis_pubsub import get_redis

            redis = await get_redis()
            lock_key = app.state.alerting_lock_key
            lock_value = f"pid-{os.getpid()}-{datetime.utcnow().timestamp()}"
            lock_acquired = await redis.set(lock_key, lock_value, nx=True, ex=86400)

            if lock_acquired:
                app.state.alerting_task = asyncio.create_task(alerting_system.start_monitoring())
                app.state.alerting_lock_owner = True
                app.state.alerting_lock_value = lock_value
                logger.info("Alerting system background task started (single instance lock acquired)")
            else:
                logger.info("Alerting system skipped (another worker holds monitoring lock)")
        else:
            logger.info("Alerting system disabled by ENABLE_ALERTING_SYSTEM env")
    except Exception as alert_err:
        logger.warning(f"Could not start alerting system: {alert_err}")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Stop async violation event drain loop
    try:
        violation_stop = getattr(app.state, "violation_event_stop", None)
        violation_task = getattr(app.state, "violation_event_task", None)
        if violation_stop:
            violation_stop.set()
        if violation_task and not violation_task.done():
            violation_task.cancel()
            try:
                await violation_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        logger.info("Violation event drain loop stopped")
    except Exception:
        logger.exception("Failed to stop violation event drain loop cleanly")

    # Stop runtime answer buffer drain loop
    try:
        answer_buffer_stop = getattr(app.state, "answer_buffer_stop", None)
        answer_buffer_task = getattr(app.state, "answer_buffer_task", None)
        if answer_buffer_stop:
            answer_buffer_stop.set()
        if answer_buffer_task and not answer_buffer_task.done():
            answer_buffer_task.cancel()
            try:
                await answer_buffer_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        logger.info("Answer runtime buffer drain loop stopped")
    except Exception:
        logger.exception("Failed to stop answer runtime buffer drain loop cleanly")

    # Stop alerting system
    try:
        from app.core.alerting import alerting_system
        alerting_system.stop_monitoring()
        alert_task = getattr(app.state, "alerting_task", None)
        if alert_task and not alert_task.done():
            alert_task.cancel()

        if getattr(app.state, "alerting_lock_owner", False):
            from app.core.redis_pubsub import get_redis
            redis = await get_redis()
            lock_key = getattr(app.state, "alerting_lock_key", None)
            lock_value = getattr(app.state, "alerting_lock_value", None)
            if lock_key and lock_value:
                current = await redis.get(lock_key)
                if isinstance(current, bytes):
                    current = current.decode("utf-8", errors="ignore")
                if current == lock_value:
                    await redis.delete(lock_key)
        logger.info("Alerting system stopped")
    except Exception:
        logger.exception("Failed to stop alerting system cleanly")

    await close_redis()
    logger.info("Redis connection closed")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description=(
        "SIAB1 - Sistem Informasi Asesmen Berintegritas dengan integrasi "
        "Safe Exam Browser"
    ),
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,  # Only in debug mode
    redoc_url="/redoc" if settings.debug else None,  # Only in debug mode
    redirect_slashes=False,  # Prevent 307 redirects that drop POST/PUT bodies
    lifespan=lifespan
)

# CORS Middleware
cors_origins = settings.cors_origins_list
cors_allow_credentials = "*" not in cors_origins
if not cors_allow_credentials:
    logger.warning("CORS wildcard origin detected; disabling credentialed CORS responses.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# ✅ SECURITY FIX: Security Headers Middleware
from app.middleware.security import (
    SecurityHeadersMiddleware,
    RangeHeaderGuardMiddleware,
    RateLimitMiddleware
)

# HTTPS redirect — DISABLED for Cloudflare Flexible SSL setup
# Cloudflare handles HTTPS termination. VPS only serves HTTP (port 80).
# Enabling this would cause infinite redirect loop!
# app.add_middleware(HTTPSRedirectMiddleware)

# Guard malformed/multi-range headers before handlers (DoS mitigation for file responses)
app.add_middleware(RangeHeaderGuardMiddleware)

# Add security headers (X-Frame-Options, CSP, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# Emergency Freeze Mode guard (global lock for non-developer activity)
from app.middleware.freeze_mode_guard import FreezeModeGuardMiddleware
app.add_middleware(FreezeModeGuardMiddleware)

# Add global rate limiting (1000 req/min general, 300 req/min writes, 2000 req/min login burst)
# Can be disabled via DISABLE_RATE_LIMIT=true for development
import os
if os.getenv("DISABLE_RATE_LIMIT", "false").lower() != "true":
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=1000,
        max_write_requests=300,
        login_write_requests=2000,
        window_seconds=60
    )

# Peak protection middleware (active only when degrade mode is enabled)
from app.middleware.degrade_mode_guard import DegradeModeGuardMiddleware
app.add_middleware(DegradeModeGuardMiddleware)

# SXB Strict Enforcer Middleware
from app.middleware.sxb_enforcer import SXBEnforcerMiddleware
app.add_middleware(SXBEnforcerMiddleware)

# Logging Middleware (Phase 5: Centralized Logging)
from app.middleware.logging_middleware import LoggingMiddleware
app.add_middleware(LoggingMiddleware)

# Performance Monitoring Middleware (Audit Recommendation)
from app.middleware.performance_monitoring import PerformanceMonitoringMiddleware
app.add_middleware(PerformanceMonitoringMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve a favicon at the browser default path to avoid noisy 404s."""
    return FileResponse("static/favicon.gif", media_type="image/gif")


# Templates
jinja_templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(exams.public_router)
app.include_router(exams.router)
app.include_router(exam_crud.router)
app.include_router(answer_sync.router)
app.include_router(final_submit.router)
app.include_router(violation_events.router)
app.include_router(exam_answer_sync.router)
app.include_router(exam_session_runtime.router)
app.include_router(exam_offline_package.router)
app.include_router(exam_pause_control.router)
app.include_router(exam_exports.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(questions.router)
app.include_router(websocket.router)
app.include_router(stats.router)
app.include_router(runtime.router)  # APK/mobile adaptive runtime policy
app.include_router(sxb.router) # SXB Private API
app.include_router(seb_autoconfig.router)  # SEB Auto-Configuration (Dynamic)

from app.api import upload
app.include_router(upload.router)

# Enterprise Dashboard Enhancement Routers
app.include_router(grading.router)      # Essay grading endpoints
app.include_router(analytics.router)    # Performance analytics endpoints
app.include_router(monitoring.router)   # Violation & live monitoring endpoints

# Telegram Admin
from app.api import telegram_admin
app.include_router(telegram_admin.router)  # Telegram broadcast (admin only)

# Metrics (Prometheus)
from app.api import metrics
app.include_router(metrics.router, tags=["Monitoring"])

# Modular Exam Routers (Phase 6: Code Splitting)
app.include_router(exam_seb.router)          # SEB configuration endpoints
app.include_router(exam_seb.public_router)   # Public SEB endpoints
app.include_router(exam_admin.router)        # Admin exam control endpoints

# New Feature Routers (Phase 1-5)
from app.api import scheduled, templates as exam_templates_api, activity, media, notifications, subjects, apk, seb_builder
app.include_router(scheduled.router)              # Scheduled publishing
app.include_router(exam_templates_api.router)     # Exam templates CRUD
app.include_router(activity.router)               # User activity logging
app.include_router(media.router)                  # Media library management
app.include_router(notifications.router)          # In-app notifications
app.include_router(subjects.router)               # Subjects (Bidang Studi)
app.include_router(seb_builder.router)            # SEB Builder for PC (Windows/Mac/Linux)

# Data Management
from app.api import backup, system_settings, account_security, security_analytics, alerts
app.include_router(backup.router)                 # Backup & Restore
app.include_router(system_settings.router)        # System Settings
app.include_router(account_security.router)       # Account Security (Lockout/Unlock)
app.include_router(security_analytics.router)     # Security Analytics & Attack Detection
app.include_router(alerts.router)                 # Alerting System API
# app.include_router(question_import.router)        # Bulk Question Import (Removed)
app.include_router(apk.router)                    # APK Builder & Version Control
app.include_router(apk.legacy_builder_router)     # Legacy APK Builder Compatibility


# ============== HEALTH CHECK ==============

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker/Kubernetes."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Redirect visitors to the student login page."""
    return RedirectResponse(url="/student/", status_code=302)


# ============== PUBLIC APK TOKEN VALIDATION ==============
# This is a public endpoint for mobile app to validate build tokens

from pydantic import BaseModel
from typing import Optional
from app.core.apk_profiles import get_allowed_tokens, get_token_label

class PublicTokenRequest(BaseModel):
    token: str
    timestamp: Optional[int] = None

@app.post("/api/validate-apk-token")
async def public_validate_apk_token(request: PublicTokenRequest):
    """
    Public endpoint for APK build token validation.
    Called by mobile app on startup to check if APK version is still valid.
    """
    from sqlalchemy import select
    from app.database import async_session_read
    from app.models.system_settings import SystemSettings

    try:
        async with async_session_read() as db:
            result = await db.execute(select(SystemSettings))
            settings_obj = result.scalar_one_or_none()

            # Validation is intentionally disabled by admin (tokens remain stored)
            if settings_obj and bool(getattr(settings_obj, "token_validation_bypass", False)):
                return {"valid": True, "message": "", "update_required": False, "validation_enabled": False}

            # If no settings or no token configured, allow all
            if not settings_obj or not settings_obj.minimum_apk_token:
                return {"valid": True, "message": "", "update_required": False}

            app_token = str(request.token or "").strip().upper()
            allowed_tokens = get_allowed_tokens(settings_obj.minimum_apk_token)
            if not allowed_tokens:
                return {
                    "valid": False,
                    "message": "Tidak ada profil token APK yang aktif. Hubungi admin.",
                    "update_required": True,
                }

            if app_token in allowed_tokens:
                return {
                    "valid": True,
                    "message": "",
                    "update_required": False,
                    "accepted_label": get_token_label(settings_obj.minimum_apk_token, app_token),
                }

            return {
                "valid": False,
                "message": "Versi aplikasi tidak diizinkan. Silakan gunakan APK stable atau new update resmi dari admin.",
                "update_required": True,
            }

    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return {"valid": True, "message": "", "update_required": False}



# ============== ADMIN PAGES ==============

@app.get("/admin/")
@app.get("/admin/{page}")
async def admin_pages(request: Request, page: str = "index.html"):
    """Serve admin dashboard pages."""
    normalized_page = (page or "index.html").strip() or "index.html"
    if "/" in normalized_page or "\\" in normalized_page or ".." in normalized_page:
        return JSONResponse(status_code=404, content={"detail": "Halaman tidak ditemukan"})
    if normalized_page.endswith(".html"):
        template_page = normalized_page
    elif "." in normalized_page:
        # Prevent scanner-like probes such as /admin/config.php from raising 500 traces.
        return JSONResponse(status_code=404, content={"detail": "Halaman tidak ditemukan"})
    else:
        template_page = f"{normalized_page}.html"

    template_name = f"admin/{template_page}"
    try:
        jinja_templates.get_template(template_name)
    except TemplateNotFound:
        return JSONResponse(status_code=404, content={"detail": "Halaman tidak ditemukan"})
    response = jinja_templates.TemplateResponse(
        request,
        template_name,
        {
            "feature_flags": {
                "seb_desktop_legacy_enabled": settings.seb_desktop_legacy_enabled,
                "seb_qr_enabled": settings.seb_qr_enabled,
                "apk_build_endpoint_enabled": settings.apk_build_endpoint_enabled,
                "mobile_apk_primary": settings.mobile_apk_primary,
            },
        },
    )
    # Admin/guru UI should not be cached aggressively to avoid stale JS/HTML after hot patches.
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ============== STUDENT PAGES ==============

@app.get("/student/")
@app.get("/student/{page}")
async def student_pages(request: Request, page: str = "index.html"):
    """Serve student interface pages."""
    normalized_page = (page or "index.html").strip() or "index.html"
    if "/" in normalized_page or "\\" in normalized_page or ".." in normalized_page:
        return JSONResponse(status_code=404, content={"detail": "Halaman tidak ditemukan"})
    if normalized_page.endswith(".html"):
        template_page = normalized_page
    elif "." in normalized_page:
        return JSONResponse(status_code=404, content={"detail": "Halaman tidak ditemukan"})
    else:
        template_page = f"{normalized_page}.html"

    template_name = f"student/{template_page}"
    try:
        jinja_templates.get_template(template_name)
    except TemplateNotFound:
        return JSONResponse(status_code=404, content={"detail": "Halaman tidak ditemukan"})

    response = jinja_templates.TemplateResponse(request, template_name)
    # Student exam pages must stay fresh to avoid stale UI/security state in WebView/CDN cache.
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ============== SEB PAGES ==============

@app.get("/seb/{exam_id}")
async def seb_landing(request: Request, exam_id: int):
    """Serve SEB landing page for an exam."""
    return jinja_templates.TemplateResponse(
        request,
        "seb/landing.html",
        {"exam_id": exam_id},
    )


@app.get("/exam/{exam_id}/start")
async def exam_start_redirect(request: Request, exam_id: int):
    """Redirect to student dashboard for exam (SEB entry point)."""
    return jinja_templates.TemplateResponse(request, "student/dashboard.html")




# ============== ERROR HANDLERS ==============

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={"detail": "Halaman tidak ditemukan"}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Custom 500 handler."""
    import traceback
    error_details = traceback.format_exc()
    logger.error(f"Internal error: {exc}\n{error_details}")

    # Emergency logging to file
    try:
        with open("critical_error.log", "a") as f:
            f.write(f"TIMESTAMP: {datetime.now()}\n")
            f.write(f"URL: {request.url}\n")
            f.write(f"ERROR: {exc}\n")
            f.write(f"TRACEBACK:\n{error_details}\n")
            f.write("-" * 50 + "\n")
    except Exception as log_file_error:
        logger.error(
            "Failed to append emergency error log for %s: %s",
            request.url,
            str(log_file_error),
            exc_info=True,
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Terjadi kesalahan pada server"}
    )


# ============== RUN WITH UVICORN ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers
    )
