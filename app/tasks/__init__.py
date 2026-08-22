# Tasks package
"""
Celery background tasks for async processing.

Includes:
- answer_processor: Batch process answers from Redis queue to PostgreSQL
- partition_maintenance: exam_logs partition lifecycle automation
- dr_drill: non-destructive disaster recovery drill
"""

# Import tasks for Celery autodiscovery
from app.tasks.answer_processor import process_answer_queue
from app.tasks.dr_drill import run_disaster_recovery_drill
from app.tasks.partition_maintenance import maintain_exam_logs_partitions

__all__ = [
    'process_answer_queue',
    'maintain_exam_logs_partitions',
    'run_disaster_recovery_drill',
]
