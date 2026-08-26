import asyncio
import logging

from sqlalchemy import text

from app.tasks.scheduler import celery_app

logger = logging.getLogger(__name__)

_VIEW_DDL_STATEMENTS = (
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS exam_results_summary AS
    SELECT
        e.id as exam_id,
        e.title as exam_title,
        e.subject,
        e.creator_id,
        COUNT(es.id) as total_sessions,
        COUNT(DISTINCT es.user_id) as total_participants,
        ROUND(AVG(es.score), 2) as avg_score,
        MAX(es.score) as highest_score,
        MIN(es.score) as lowest_score,
        COUNT(CASE WHEN es.score >= COALESCE(e.passing_score, 0) THEN 1 END) as passed_count,
        NOW() as last_updated
    FROM exams e
    JOIN exam_sessions es ON e.id = es.exam_id
    WHERE es.status IN ('completed', 'submitted')
    GROUP BY e.id, e.title, e.subject, e.creator_id
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_exam_results_summary_id ON exam_results_summary (exam_id)",
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS class_exam_performance AS
    SELECT
        u.student_class as class_name,
        e.id as exam_id,
        e.title as exam_title,
        COUNT(DISTINCT es.user_id) as total_students,
        ROUND(AVG(es.score), 2) as avg_score,
        MAX(es.score) as highest_score,
        MIN(es.score) as lowest_score,
        COUNT(CASE WHEN es.score >= COALESCE(e.passing_score, 0) THEN 1 END) as passed_count,
        NOW() as last_updated
    FROM exam_sessions es
    JOIN users u ON es.user_id = u.id
    JOIN exams e ON es.exam_id = e.id
    WHERE es.status IN ('completed', 'submitted')
      AND u.student_class IS NOT NULL
    GROUP BY u.student_class, e.id, e.title
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_class_exam_perf_class_exam ON class_exam_performance (class_name, exam_id)",
)

_CONCURRENT_REFRESH = (
    "REFRESH MATERIALIZED VIEW CONCURRENTLY exam_results_summary",
    "REFRESH MATERIALIZED VIEW CONCURRENTLY class_exam_performance",
)

_PLAIN_REFRESH = (
    "REFRESH MATERIALIZED VIEW exam_results_summary",
    "REFRESH MATERIALIZED VIEW class_exam_performance",
)

@celery_app.task(name='app.tasks.views_refresher.refresh_analytics_views')
def refresh_analytics_views():
    """
    Refresh Materialized Views for analytics.
    Runs periodically via Celery Beat.
    """
    from app.config import settings

    if settings.exam_peak_mode:
        logger.info("Analytics view refresh skipped while exam peak mode is active")
        return {"status": "skipped", "reason": "exam_peak_mode"}

    try:
        asyncio.run(_refresh_async())
        logger.info("Analytics views refreshed successfully")
    except Exception as e:
        logger.error(f"Error refreshing analytics views: {e}")

async def _refresh_async():
    """Async implementation."""
    from app.database import create_task_engine

    engine = create_task_engine()

    # Ensure views/indexes exist first to prevent noisy periodic failures.
    async with engine.begin() as conn:
        for ddl in _VIEW_DDL_STATEMENTS:
            await conn.execute(text(ddl))

    # Run concurrent refresh outside a transaction block.
    try:
        async with engine.connect() as raw_conn:
            conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
            for stmt in _CONCURRENT_REFRESH:
                await conn.execute(text(stmt))
    except Exception as exc:
        # Fallback keeps analytics fresh even if concurrent refresh is unavailable.
        logger.warning("Concurrent MV refresh failed, falling back to non-concurrent refresh: %s", str(exc))
        async with engine.begin() as conn:
            for stmt in _PLAIN_REFRESH:
                await conn.execute(text(stmt))

    await engine.dispose()
