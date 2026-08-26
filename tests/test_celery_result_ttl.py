from pathlib import Path


SOURCE = Path("app/tasks/scheduler.py").read_text(encoding="utf-8")


def test_celery_results_expire_and_are_ignored_by_default() -> None:
    assert "result_expires=3600" in SOURCE
    assert "task_ignore_result=True" in SOURCE
    assert "backend=settings.redis_url.replace('/0', '/1')" in SOURCE
