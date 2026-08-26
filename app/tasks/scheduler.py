"""
Celery task scheduler for processing scheduled publications.
Runs every 60 seconds to check for pending schedules.
"""
from celery import Celery
from celery.schedules import crontab
from datetime import datetime, timezone, timedelta
import asyncio
import logging

from app.config import settings
from app.database import build_connect_args

# Setup logging
logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    'exam_scheduler',
    broker=settings.redis_url.replace('/0', '/1'),  # Use DB 1 for Celery
    backend=settings.redis_url.replace('/0', '/1'),
    include=[
        'app.tasks.answer_processor',
        'app.tasks.views_refresher',
        'app.tasks.partition_maintenance',
        'app.tasks.dr_drill',
    ]
)

celery_app.conf.update(
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True,  # Fix: Celery 6.0 compatibility
    result_expires=3600,
    task_ignore_result=True,
    beat_schedule={
        'check-scheduled-publications': {
            'task': 'app.tasks.scheduler.process_scheduled_publications',
            'schedule': 60.0,  # Every 60 seconds
        },
        'process-answer-queue-rapid': {
            'task': 'app.tasks.answer_processor.process_answer_queue',
            'schedule': 5.0,  # Every 5 seconds for rapid feedback
            'kwargs': {'batch_size': 100}
        },
        'refresh-analytics-views': {
            'task': 'app.tasks.views_refresher.refresh_analytics_views',
            'schedule': 300.0,  # Every 5 minutes
        },
        'close-expired-sessions': {
            'task': 'app.tasks.scheduler.close_expired_sessions',
            'schedule': 30.0,  # Check twice per minute so timeout auto-submit is timely
        },
        'maintain-exam-log-partitions': {
            'task': 'app.tasks.partition_maintenance.maintain_exam_logs_partitions',
            'schedule': crontab(hour=2, minute=15),  # Daily low-traffic maintenance
        },
        'run-disaster-recovery-drill': {
            'task': 'app.tasks.dr_drill.run_disaster_recovery_drill',
            'schedule': crontab(day_of_week='sun', hour=3, minute=40),  # Weekly drill
        },
    },
)


@celery_app.task(name='app.tasks.scheduler.close_expired_sessions')
def close_expired_sessions():
    """
    Auto-close sessions that have exceeded time limit + tolerance.
    """
    try:
        asyncio.run(_close_expired_sessions_async())
        logger.info("Expired sessions check completed")
    except Exception as e:
        logger.error(f"Error closing expired sessions: {e}")


@celery_app.task(name='app.tasks.scheduler.process_scheduled_publications')
def process_scheduled_publications():
    """
    Process pending scheduled publications.
    Runs every 60 seconds via Celery Beat.
    """
    try:
        asyncio.run(_process_async())
        logger.info("Scheduled publications processed successfully")
    except Exception as e:
        logger.error(f"Error processing scheduled publications: {e}")


async def _process_async():
    """Async function to process schedules.

    Note: Creates its own database connection to avoid event loop conflicts
    in Celery forked worker processes.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.models.exam import Exam
    from app.models.scheduled import ScheduledPublication
    from app.config import settings

    # Create a fresh engine for this task to avoid event loop conflicts
    task_engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=2,
        max_overflow=3,
        pool_timeout=30,
        pool_pre_ping=True,
        connect_args=build_connect_args(settings.database_url),
    )

    task_session_maker = async_sessionmaker(
        task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with task_session_maker() as db:
            try:
                now = datetime.now(timezone.utc)

                # Get pending schedules that are due for publish
                result = await db.execute(
                    select(ScheduledPublication)
                    .where(
                        ScheduledPublication.status == 'pending',
                        ScheduledPublication.publish_at <= now
                    )
                )
                schedules = result.scalars().all()

                logger.info(f"Found {len(schedules)} pending schedules to process")

                for schedule in schedules:
                    try:
                        # Get exam
                        exam_result = await db.execute(
                            select(Exam).where(Exam.id == schedule.exam_id)
                        )
                        exam = exam_result.scalar_one_or_none()

                        if exam:
                            # Publish exam
                            exam.is_published = True
                            exam.updated_at = now

                            # Update schedule status
                            schedule.status = 'published'
                            schedule.executed_at = now

                            logger.info(f"Published exam {exam.id}: {exam.title}")

                            # Schedule unpublish task if set
                            if schedule.unpublish_at and schedule.unpublish_at > now:
                                delay = (schedule.unpublish_at - now).total_seconds()
                                unpublish_exam.apply_async(
                                    args=[schedule.id, schedule.exam_id],
                                    countdown=delay
                                )
                                logger.info(f"Scheduled unpublish for exam {exam.id} in {delay} seconds")
                        else:
                            schedule.status = 'cancelled'
                            schedule.error_message = "Exam not found"

                    except Exception as e:
                        schedule.status = 'cancelled'
                        schedule.error_message = str(e)
                        logger.error(f"Error processing schedule {schedule.id}: {e}")

                await db.commit()

            except Exception as e:
                logger.error(f"Database error: {e}")
                await db.rollback()
    finally:
        # Cleanup engine to prevent connection leaks
        await task_engine.dispose()


@celery_app.task(name='app.tasks.scheduler.unpublish_exam')
def unpublish_exam(schedule_id: int, exam_id: int):
    """Unpublish exam at scheduled time."""
    try:
        asyncio.run(_unpublish_async(schedule_id, exam_id))
        logger.info(f"Unpublished exam {exam_id}")
    except Exception as e:
        logger.error(f"Error unpublishing exam {exam_id}: {e}")


async def _unpublish_async(schedule_id: int, exam_id: int):
    """Async function to unpublish exam.

    Note: Creates its own database connection to avoid event loop conflicts
    in Celery forked worker processes.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.models.exam import Exam
    from app.models.scheduled import ScheduledPublication
    from app.config import settings

    # Create a fresh engine for this task to avoid event loop conflicts
    task_engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=2,
        max_overflow=3,
        pool_timeout=30,
        pool_pre_ping=True,
        connect_args=build_connect_args(settings.database_url),
    )

    task_session_maker = async_sessionmaker(
        task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with task_session_maker() as db:
            try:
                result = await db.execute(
                    select(Exam).where(Exam.id == exam_id)
                )
                exam = result.scalar_one_or_none()

                if exam:
                    exam.is_published = False
                    exam.updated_at = datetime.now(timezone.utc)

                    # Update schedule record
                    schedule_result = await db.execute(
                        select(ScheduledPublication).where(
                            ScheduledPublication.id == schedule_id
                        )
                    )
                    schedule = schedule_result.scalar_one_or_none()
                    if schedule:
                        schedule.status = 'unpublished'
                        schedule.executed_at = datetime.now(timezone.utc)

                    await db.commit()

            except Exception as e:
                logger.error(f"Error in _unpublish_async: {e}")
                await db.rollback()
    finally:
        # Cleanup engine to prevent connection leaks
        await task_engine.dispose()


async def _close_expired_sessions_async():
    """Async function to close zombie sessions."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.orm import selectinload
    from app.models.exam import Exam
    from app.models.question import Question
    from app.models.session import ExamSession
    from app.models.session import ExamLog
    from app.config import settings
    from app.services.exam_submission_service import finalize_exam_session_submission

    # Create fresh engine
    task_engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=2,
        pool_timeout=30,
        pool_pre_ping=True,
        connect_args=build_connect_args(settings.database_url),
    )

    task_session_maker = async_sessionmaker(
        task_engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with task_session_maker() as db:
            now = datetime.now(timezone.utc)

            # Phase 1 (lightweight): scan active sessions without heavy relationships.
            # This avoids loading all exam questions/options/answers on every beat tick.
            candidate_result = await db.execute(
                select(
                    ExamSession.id,
                    ExamSession.start_time,
                    ExamSession.total_paused_seconds,
                    ExamSession.is_paused,
                    ExamSession.paused_at,
                    Exam.duration_minutes,
                    Exam.end_time,
                    Exam.is_globally_paused,
                    Exam.globally_paused_at,
                )
                .join(Exam, Exam.id == ExamSession.exam_id)
                .where(ExamSession.status == 'in_progress')
            )
            candidate_rows = candidate_result.all()

            expired_ids = []
            for (
                session_id,
                session_start,
                total_paused_seconds,
                is_session_paused,
                session_paused_at,
                duration_minutes,
                exam_end,
                is_exam_globally_paused,
                exam_globally_paused_at,
            ) in candidate_rows:
                if not session_start:
                    continue

                timeout_tolerance_seconds = 5 * 60
                stale_pause_grace_seconds = 6 * 60 * 60

                normalized_exam_end = None
                if exam_end:
                    normalized_exam_end = (
                        exam_end
                        if exam_end.tzinfo is not None
                        else exam_end.replace(tzinfo=timezone.utc)
                    )

                # Never auto-submit while a pause is still active during a valid exam window.
                # However, stale global pauses from ended exams must not keep sessions alive forever
                # and block inter-session restart maintenance.
                pause_active = bool(is_session_paused or is_exam_globally_paused)
                stale_paused_exam_expired = bool(
                    pause_active
                    and normalized_exam_end is not None
                    and now > normalized_exam_end + timedelta(seconds=stale_pause_grace_seconds)
                )
                if pause_active and not stale_paused_exam_expired:
                    continue

                normalized_start = (
                    session_start
                    if session_start.tzinfo is not None
                    else session_start.replace(tzinfo=timezone.utc)
                )
                base_paused_seconds = max(0, int(total_paused_seconds or 0))

                # Safety net: if pause flags are stale but paused_at is still set,
                # count that ongoing pause so timeout logic remains conservative.
                # Once an exam is stale beyond the hard pause grace, stop extending time forever.
                ongoing_pause_seconds = 0
                if session_paused_at and not stale_paused_exam_expired:
                    normalized_session_paused_at = (
                        session_paused_at
                        if session_paused_at.tzinfo is not None
                        else session_paused_at.replace(tzinfo=timezone.utc)
                    )
                    ongoing_pause_seconds = max(
                        ongoing_pause_seconds,
                        max(0, int((now - normalized_session_paused_at).total_seconds())),
                    )
                if exam_globally_paused_at and not stale_paused_exam_expired:
                    normalized_global_paused_at = (
                        exam_globally_paused_at
                        if exam_globally_paused_at.tzinfo is not None
                        else exam_globally_paused_at.replace(tzinfo=timezone.utc)
                    )
                    ongoing_pause_seconds = max(
                        ongoing_pause_seconds,
                        max(0, int((now - normalized_global_paused_at).total_seconds())),
                    )

                effective_paused_seconds = base_paused_seconds + ongoing_pause_seconds
                elapsed_seconds = max(0, int((now - normalized_start).total_seconds()))
                effective_elapsed_seconds = max(0, elapsed_seconds - effective_paused_seconds)
                duration_limit_seconds = int(duration_minutes or 0) * 60

                duration_expired = effective_elapsed_seconds > (duration_limit_seconds + timeout_tolerance_seconds)

                exam_end_expired = stale_paused_exam_expired
                if normalized_exam_end is not None and not exam_end_expired:
                    exam_end_with_pause = normalized_exam_end + timedelta(
                        seconds=effective_paused_seconds + timeout_tolerance_seconds
                    )
                    exam_end_expired = now > exam_end_with_pause

                if duration_expired or exam_end_expired:
                    expired_ids.append(int(session_id))

            if not expired_ids:
                return

            closed_count = 0
            batch_size = 50
            for idx in range(0, len(expired_ids), batch_size):
                batch_ids = expired_ids[idx: idx + batch_size]
                sessions_result = await db.execute(
                    select(ExamSession)
                    .options(
                        selectinload(ExamSession.exam)
                        .selectinload(Exam.questions)
                        .selectinload(Question.options),
                        selectinload(ExamSession.answers),
                    )
                    .where(
                        ExamSession.id.in_(batch_ids),
                        ExamSession.status == 'in_progress',
                    )
                )
                sessions = sessions_result.scalars().all()
                for session in sessions:
                    if not session.exam:
                        continue
                    finalize_result = finalize_exam_session_submission(session, submitted_at=now)
                    db.add(
                        ExamLog(
                            session_id=session.id,
                            event_type="EXAM_AUTO_SUBMITTED_TIMEOUT",
                            event_data={
                                "score": finalize_result.percentage,
                                "submitted_at": now.isoformat(),
                                "reason": "Session expired and was finalized by scheduler",
                            },
                        )
                    )
                    db.add(
                        ExamLog(
                            session_id=session.id,
                            event_type="SCORE_BREAKDOWN",
                            event_data={"score_breakdown": finalize_result.score_breakdown},
                        )
                    )
                    closed_count += 1

            if closed_count > 0:
                await db.commit()
                logger.info(
                    "Auto-closed %s expired sessions (candidates=%s)",
                    closed_count,
                    len(expired_ids),
                )

    except Exception as e:
        logger.error(f"Error in zombie session cleanup: {e}")
    finally:
        await task_engine.dispose()
