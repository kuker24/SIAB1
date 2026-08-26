from pathlib import Path

import pytest
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import create_task_engine
from app.tasks.scheduler import celery_app


SOURCE = Path("app/tasks/scheduler.py").read_text(encoding="utf-8")


def test_celery_results_expire_and_are_ignored_by_default() -> None:
    assert "result_expires=3600" in SOURCE
    assert "task_ignore_result=True" in SOURCE
    assert "backend=settings.redis_url.replace('/0', '/1')" in SOURCE


def test_direct_mode_does_not_schedule_answer_queue_beat() -> None:
    assert "process-answer-queue-rapid" in SOURCE
    assert "answer_queue_processing_enabled()" in SOURCE
    assert not settings.answer_queue_processing_enabled()
    assert "process-answer-queue-rapid" not in celery_app.conf.beat_schedule
    assert "close-expired-sessions" in celery_app.conf.beat_schedule


def test_answer_queue_processing_gate(monkeypatch) -> None:
    monkeypatch.setattr(settings, "answer_write_mode", "direct")
    monkeypatch.setattr(settings, "answer_queue_enabled", True)
    assert settings.answer_queue_processing_enabled() is False

    monkeypatch.setattr(settings, "answer_write_mode", "queue")
    monkeypatch.setattr(settings, "answer_queue_enabled", True)
    assert settings.answer_queue_processing_enabled() is True

    monkeypatch.setattr(settings, "answer_queue_enabled", False)
    assert settings.answer_queue_processing_enabled() is False

    monkeypatch.setattr(settings, "answer_write_mode", "hybrid")
    monkeypatch.setattr(settings, "answer_queue_enabled", True)
    assert settings.answer_queue_processing_enabled() is True


@pytest.mark.asyncio
async def test_process_answer_queue_skips_redis_when_direct(monkeypatch) -> None:
    from app.tasks import answer_processor

    monkeypatch.setattr(answer_processor.settings, "answer_write_mode", "direct")
    monkeypatch.setattr(answer_processor.settings, "answer_queue_enabled", False)

    async def fail_redis(*_args, **_kwargs):
        raise AssertionError("direct mode must not open a Redis client")

    monkeypatch.setattr(answer_processor, "aioredis", None, raising=False)
    assert await answer_processor.process_answer_queue_once() == 0


def test_create_task_engine_uses_nullpool() -> None:
    engine = create_task_engine()
    try:
        assert engine.sync_engine.pool.__class__ is NullPool
    finally:
        engine.sync_engine.dispose()


def test_celery_tasks_keep_nullpool_and_stay_out_of_api() -> None:
    scheduler = Path("app/tasks/scheduler.py").read_text(encoding="utf-8")
    views = Path("app/tasks/views_refresher.py").read_text(encoding="utf-8")
    partitions = Path("app/tasks/partition_maintenance.py").read_text(encoding="utf-8")
    answers = Path("app/tasks/answer_processor.py").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")
    compose = Path("docker-compose.production.yml").read_text(encoding="utf-8")

    assert "create_task_engine" in scheduler
    assert "asyncio.run(_close_expired_sessions_async())" in scheduler
    assert "create_async_engine" not in scheduler
    assert "pool_size=2" not in scheduler
    assert "engine_write" not in scheduler
    assert "async_session_maker" not in scheduler

    assert "create_task_engine" in views
    assert "_build_engine" not in views
    assert "asyncio.run(_refresh_async())" in views

    assert "create_task_engine" in partitions
    assert "from app.database import async_session_maker" not in partitions
    assert "asyncio.run(run_partition_maintenance())" in partitions

    assert "create_task_engine" in answers
    assert "_run_queue_with_task_engine" in answers
    assert "drain_answer_queue" in answers
    assert "async_session_maker" in answers

    assert "close_expired_sessions" not in main
    assert "celery_worker:" in compose
    assert "celery_beat:" in compose
    assert "./app:/app/app" in compose
