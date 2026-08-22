"""
Application configuration settings.
Uses pydantic-settings for environment variable management.
"""
import os
from functools import lru_cache
from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Ujian Online"
    app_env: str = "development"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"  # Default FALSE for security
    secret_key: str = os.getenv("SECRET_KEY")

    # Database - Master (Write)
    database_url: str = os.getenv("DATABASE_URL")
    db_password: str = "exampassword"  # Used by docker-compose
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "8"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "16"))
    db_pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "20"))
    db_pool_recycle: int = int(os.getenv("DB_POOL_RECYCLE", "1200"))
    db_pool_pre_ping: bool = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"
    db_use_null_pool_with_pgbouncer: bool = (
        os.getenv("DB_USE_NULL_POOL_WITH_PGBOUNCER", "false").lower() == "true"
    )

    # Database - Replica (Read) - Optional, falls back to master if not set
    database_read_url: Optional[str] = None
    db_read_pool_size: int = int(os.getenv("DB_READ_POOL_SIZE", "8"))
    db_read_max_overflow: int = int(os.getenv("DB_READ_MAX_OVERFLOW", "16"))

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    answer_sync_internal_service: bool = (
        os.getenv("ANSWER_SYNC_INTERNAL_SERVICE", "true").lower() == "true"
    )
    answer_write_mode: str = os.getenv("ANSWER_WRITE_MODE", "direct").lower()
    answer_queue_enabled: bool = os.getenv("ANSWER_QUEUE_ENABLED", "false").lower() == "true"
    answer_queue_percentage: int = int(os.getenv("ANSWER_QUEUE_PERCENTAGE", "0"))
    answer_queue_flush_on_submit: bool = (
        os.getenv("ANSWER_QUEUE_FLUSH_ON_SUBMIT", "true").lower() == "true"
    )
    answer_queue_flush_batch_size: int = int(os.getenv("ANSWER_QUEUE_FLUSH_BATCH_SIZE", "300"))
    answer_queue_flush_max_rounds: int = int(os.getenv("ANSWER_QUEUE_FLUSH_MAX_ROUNDS", "4"))
    monitoring_delta_stream_enabled: bool = (
        os.getenv("MONITORING_DELTA_STREAM_ENABLED", "true").lower() == "true"
    )
    monitoring_delta_stream_max_len: int = int(os.getenv("MONITORING_DELTA_STREAM_MAX_LEN", "5000"))
    monitoring_delta_stream_ttl_seconds: int = int(
        os.getenv("MONITORING_DELTA_STREAM_TTL_SECONDS", "7200")
    )

    # exam_logs partition lifecycle automation
    exam_logs_partition_maintenance_enabled: bool = (
        os.getenv("EXAM_LOGS_PARTITION_MAINTENANCE_ENABLED", "true").lower() == "true"
    )
    exam_logs_partition_months_ahead: int = int(
        os.getenv("EXAM_LOGS_PARTITION_MONTHS_AHEAD", "12")
    )
    exam_logs_partition_retention_months: int = int(
        os.getenv("EXAM_LOGS_PARTITION_RETENTION_MONTHS", "18")
    )
    exam_logs_archive_retention_days: int = int(
        os.getenv("EXAM_LOGS_ARCHIVE_RETENTION_DAYS", "30")
    )
    dr_drill_enabled: bool = os.getenv("DR_DRILL_ENABLED", "false").lower() == "true"
    dr_drill_timeout_seconds: int = int(os.getenv("DR_DRILL_TIMEOUT_SECONDS", "1800"))

    # JWT
    jwt_secret_key: str = "jwt-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 120  # Extended to 120 minutes for long exams

    # SEB Configuration
    # NOTE: sxb_master_key is alias for seb_default_config_key for backward compatibility
    seb_default_config_key: str = "default-seb-config-key"
    seb_default_browser_exam_key: str = "default-browser-exam-key"

    # SEB Security Hardening (v2.0)
    seb_strict_mode: bool = True  # Strict URL filtering enabled by default for production safety
    seb_challenge_enabled: bool = True  # Enable challenge-response anti-spoofing
    seb_challenge_redis_prefix: str = "seb:challenge:"  # Redis key prefix for challenges

    # Mobile-first simplification feature flags
    mobile_apk_primary: bool = os.getenv("MOBILE_APK_PRIMARY", "true").lower() == "true"
    seb_desktop_legacy_enabled: bool = (
        os.getenv("SEB_DESKTOP_LEGACY_ENABLED", "false").lower() == "true"
    )
    seb_qr_enabled: bool = os.getenv("SEB_QR_ENABLED", "false").lower() == "true"
    seb_debug_endpoints_enabled: bool = (
        os.getenv("SEB_DEBUG_ENDPOINTS_ENABLED", "false").lower() == "true"
    )
    apk_build_endpoint_enabled: bool = (
        os.getenv("APK_BUILD_ENDPOINT_ENABLED", "false").lower() == "true"
    )
    telegram_alerting_enabled: bool = (
        os.getenv("TELEGRAM_ALERTING_ENABLED", "false").lower() == "true"
    )
    heavy_export_enabled: bool = os.getenv("HEAVY_EXPORT_ENABLED", "true").lower() == "true"
    exam_peak_mode: bool = os.getenv("EXAM_PEAK_MODE", "false").lower() == "true"
    admin_monitoring_detail_level: str = os.getenv(
        "ADMIN_MONITORING_DETAIL_LEVEL",
        "summary",
    ).lower()
    violation_async_enabled: bool = os.getenv("VIOLATION_ASYNC_ENABLED", "true").lower() == "true"

    @property
    def sxb_master_key(self) -> str:
        """Alias for seb_default_config_key to ensure synchronization."""
        return self.seb_default_config_key

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 8
    tz: str = "UTC"  # Timezone setting

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # Domain
    domain: str = "192.168.18.120:8080"
    protocol: str = "http"

    # Ops monitoring probes (safe and selective)
    monitor_public_base_url: str = os.getenv("MONITOR_PUBLIC_BASE_URL", "")
    monitor_origin_health_url: str = os.getenv("MONITOR_ORIGIN_HEALTH_URL", "http://127.0.0.1:8000/health")
    monitor_probe_timeout_ms: int = int(os.getenv("MONITOR_PROBE_TIMEOUT_MS", "2500"))
    monitor_probe_cache_seconds: int = int(os.getenv("MONITOR_PROBE_CACHE_SECONDS", "15"))
    monitor_expect_cloudflare_proxy: bool = (
        os.getenv("MONITOR_EXPECT_CLOUDFLARE_PROXY", "false").lower() == "true"
    )

    # Activity log lifecycle controls (protect dashboard/query load on production)
    activity_log_auto_prune_enabled: bool = (
        os.getenv("ACTIVITY_LOG_AUTO_PRUNE_ENABLED", "true").lower() == "true"
    )
    activity_log_retention_days: int = int(os.getenv("ACTIVITY_LOG_RETENTION_DAYS", "45"))
    activity_log_max_rows: int = int(os.getenv("ACTIVITY_LOG_MAX_ROWS", "120000"))
    activity_log_prune_batch_size: int = int(os.getenv("ACTIVITY_LOG_PRUNE_BATCH_SIZE", "5000"))
    activity_log_auto_prune_interval_seconds: int = int(
        os.getenv("ACTIVITY_LOG_AUTO_PRUNE_INTERVAL_SECONDS", "900")
    )

    # Redis health scoring for stable production monitoring
    redis_blocked_clients_warning: int = int(os.getenv("REDIS_BLOCKED_CLIENTS_WARNING", "10"))
    redis_blocked_clients_critical: int = int(os.getenv("REDIS_BLOCKED_CLIENTS_CRITICAL", "30"))
    redis_timeout_warning_per_min: float = float(os.getenv("REDIS_TIMEOUT_WARNING_PER_MIN", "0.2"))
    redis_timeout_critical_per_min: float = float(os.getenv("REDIS_TIMEOUT_CRITICAL_PER_MIN", "1.0"))
    redis_cache_hit_warning_percent: float = float(os.getenv("REDIS_CACHE_HIT_WARNING_PERCENT", "35.0"))
    redis_cache_hit_critical_percent: float = float(os.getenv("REDIS_CACHE_HIT_CRITICAL_PERCENT", "20.0"))
    redis_cache_hit_min_lookups: int = int(os.getenv("REDIS_CACHE_HIT_MIN_LOOKUPS", "3000"))
    redis_cache_hit_hard_critical_min_lookups: int = int(
        os.getenv("REDIS_CACHE_HIT_HARD_CRITICAL_MIN_LOOKUPS", "15000")
    )
    redis_cache_hit_penalty_requires_pressure: bool = (
        os.getenv("REDIS_CACHE_HIT_PENALTY_REQUIRES_PRESSURE", "true").lower() == "true"
    )
    redis_cache_hit_penalty_high_volume_min_lookups: int = int(
        os.getenv("REDIS_CACHE_HIT_PENALTY_HIGH_VOLUME_MIN_LOOKUPS", "50000")
    )
    redis_memory_warning_percent: float = float(os.getenv("REDIS_MEMORY_WARNING_PERCENT", "85.0"))
    redis_memory_critical_percent: float = float(os.getenv("REDIS_MEMORY_CRITICAL_PERCENT", "95.0"))
    redis_stability_target_percent: float = float(os.getenv("REDIS_STABILITY_TARGET_PERCENT", "100.0"))

    # Auto restart terjadwal (WIB / Asia-Jakarta)
    auto_restart_enabled: bool = os.getenv("AUTO_RESTART_ENABLED", "false").lower() == "true"
    auto_restart_time_wib: str = os.getenv("AUTO_RESTART_TIME_WIB", "00:30")
    auto_restart_buffer_minutes: int = int(os.getenv("AUTO_RESTART_BUFFER_MINUTES", "30"))
    auto_restart_full_restart: bool = os.getenv("AUTO_RESTART_FULL_RESTART", "true").lower() == "true"
    auto_restart_include_data_services: bool = (
        os.getenv("AUTO_RESTART_INCLUDE_DATA_SERVICES", "true").lower() == "true"
    )
    auto_restart_timeout_seconds: int = int(os.getenv("AUTO_RESTART_TIMEOUT_SECONDS", "300"))

    # Telegram Notifications
    telegram_enabled: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")  # MUST set in production!
    telegram_chat_ids: str = os.getenv("TELEGRAM_CHAT_IDS", "")  # Comma-separated chat IDs

    @property
    def telegram_chat_ids_list(self) -> List[str]:
        """Parse Telegram chat IDs as list."""
        return [chat_id.strip() for chat_id in self.telegram_chat_ids.split(",")]

    @property
    def telegram_alerting_active(self) -> bool:
        """Return True only when legacy Telegram config and mobile-first flag both allow it."""
        return bool(self.telegram_enabled and self.telegram_alerting_enabled)

    @property
    def heavy_exports_active(self) -> bool:
        """Return True when expensive exports are allowed for the current runtime mode."""
        return bool(self.heavy_export_enabled and not self.exam_peak_mode)

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins as list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def base_url(self) -> str:
        """Get base URL for the application."""
        return f"{self.protocol}://{self.domain}"

    @model_validator(mode='after')
    def check_security_keys(self) -> 'Settings':
        """Enforce secure defaults and block risky crypto configuration."""
        jwt_algorithm = (self.jwt_algorithm or "").strip().upper()
        if jwt_algorithm.startswith("ES"):
            raise ValueError(
                "JWT_ALGORITHM berbasis ECDSA (ES*) dinonaktifkan karena risiko timing attack pada dependensi ecdsa."
            )

        allowed_monitoring_detail_levels = {"summary", "standard", "detail"}
        if self.admin_monitoring_detail_level not in allowed_monitoring_detail_levels:
            raise ValueError(
                "ADMIN_MONITORING_DETAIL_LEVEL harus salah satu dari: "
                "summary, standard, detail."
            )

        if self.answer_write_mode not in {"direct", "queue", "hybrid"}:
            raise ValueError("ANSWER_WRITE_MODE harus direct, queue, atau hybrid.")
        if self.answer_queue_percentage < 0 or self.answer_queue_percentage > 100:
            raise ValueError("ANSWER_QUEUE_PERCENTAGE harus antara 0 dan 100.")

        # Enforce secure keys in production - prevent deployment with defaults.
        if self.app_env == "production":
            defaults = [
                "change-this-secret-key",
                "jwt-secret-key",
                "default-seb-config-key",
                "default-browser-exam-key",
                "change-this-sxb-master-key-in-production-must-be-32-chars"
            ]

            unsafe_keys = []
            secret_key = (self.secret_key or "").strip()
            jwt_secret_key = (self.jwt_secret_key or "").strip()
            seb_default_config_key = (self.seb_default_config_key or "").strip()
            seb_default_browser_exam_key = (self.seb_default_browser_exam_key or "").strip()

            if not secret_key or secret_key in defaults:
                unsafe_keys.append("SECRET_KEY")
            if not jwt_secret_key or jwt_secret_key in defaults:
                unsafe_keys.append("JWT_SECRET_KEY")
            if not seb_default_config_key or seb_default_config_key in defaults:
                unsafe_keys.append("SEB_DEFAULT_CONFIG_KEY")
            if not seb_default_browser_exam_key or seb_default_browser_exam_key in defaults:
                unsafe_keys.append("SEB_DEFAULT_BROWSER_EXAM_KEY")

            if unsafe_keys:
                raise ValueError(
                    f"\n{'='*70}\n"
                    f"🚨 CRITICAL SECURITY ERROR 🚨\n"
                    f"{'='*70}\n"
                    f"Cannot start in PRODUCTION mode with default security keys!\n\n"
                    f"Unsafe keys detected: {', '.join(unsafe_keys)}\n\n"
                    f"Please update these values in your .env file with secure random keys.\n"
                    f"You can generate secure keys using:\n"
                    f"  openssl rand -hex 32\n"
                    f"{'='*70}\n"
                )

            # Enforce explicit CORS allowlist in production.
            origins = self.cors_origins_list
            if not origins or "*" in origins:
                raise ValueError(
                    "CORS_ORIGINS tidak boleh kosong atau wildcard (*) di production."
                )

        return self

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
