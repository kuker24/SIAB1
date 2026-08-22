"""API package marker.

Keep this package lazy so importing a single router module does not eagerly import
every other API module and their transitive dependencies.
"""

__all__ = [
    "auth",
    "users",
    "exams",
    "questions",
    "websocket",
    "stats",
    "sxb",
    "seb_autoconfig",
    "exam_seb",
    "exam_admin",
    "grading",
    "analytics",
    "monitoring",
    "upload",
    "telegram_admin",
    "metrics",
    "scheduled",
    "templates",
    "activity",
    "media",
    "notifications",
    "subjects",
    "apk",
    "seb_builder",
    "backup",
    "system_settings",
    "account_security",
    "security_analytics",
    "alerts",
]
