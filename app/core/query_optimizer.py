"""
Query Optimizer - N+1 Query Prevention and Performance Helpers.

This module provides:
1. Pre-configured eager loading options for common queries
2. Query logging to detect N+1 patterns
3. Batch loading utilities

Usage:
    from app.core.query_optimizer import ExamLoader, SessionLoader

    # In API endpoint:
    query = select(Exam).options(*ExamLoader.with_questions())
"""
from typing import List, Type
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import event
from sqlalchemy.engine import Engine
import logging
import time

logger = logging.getLogger(__name__)


# =============================================================================
# EAGER LOADING PRESETS
# =============================================================================

class ExamLoader:
    """Pre-configured loaders for Exam queries."""

    @staticmethod
    def basic():
        """Load exam without relationships."""
        return []

    @staticmethod
    def with_questions():
        """Load exam with questions (for exam detail/edit)."""
        from app.models.exam import Exam
        return [
            selectinload(Exam.questions)
        ]

    @staticmethod
    def with_questions_and_options():
        """Load exam with questions and their options (for taking exam)."""
        from app.models.exam import Exam
        from app.models.question import Question
        return [
            selectinload(Exam.questions).selectinload(Question.options)
        ]

    @staticmethod
    def with_creator():
        """Load exam with creator info (for list display)."""
        from app.models.exam import Exam
        return [
            joinedload(Exam.creator)
        ]

    @staticmethod
    def full():
        """Load exam with all relationships (for admin detail)."""
        from app.models.exam import Exam
        from app.models.question import Question
        return [
            selectinload(Exam.questions).selectinload(Question.options),
            joinedload(Exam.creator)
        ]


class SessionLoader:
    """Pre-configured loaders for ExamSession queries."""

    @staticmethod
    def basic():
        """Load session without relationships."""
        return []

    @staticmethod
    def with_user():
        """Load session with user info."""
        from app.models.session import ExamSession
        return [
            joinedload(ExamSession.user)
        ]

    @staticmethod
    def with_answers():
        """Load session with answers (for results)."""
        from app.models.session import ExamSession
        return [
            selectinload(ExamSession.answers)
        ]

    @staticmethod
    def with_exam():
        """Load session with exam info."""
        from app.models.session import ExamSession
        return [
            joinedload(ExamSession.exam)
        ]

    @staticmethod
    def full():
        """Load session with all relationships (for result detail)."""
        from app.models.session import ExamSession
        from app.models.exam import Exam
        return [
            joinedload(ExamSession.user),
            joinedload(ExamSession.exam).selectinload(Exam.questions),
            selectinload(ExamSession.answers)
        ]


class UserLoader:
    """Pre-configured loaders for User queries."""

    @staticmethod
    def basic():
        """Load user without relationships."""
        return []

    @staticmethod
    def with_sessions():
        """Load user with exam sessions."""
        from app.models.user import User
        return [
            selectinload(User.exam_sessions)
        ]


# =============================================================================
# QUERY LOGGING (For Development/Debugging)
# =============================================================================

class QueryLogger:
    """
    Log SQL queries to detect N+1 patterns.

    Usage:
        logger = QueryLogger(engine)
        logger.enable()
        # ... run your code ...
        logger.report()
        logger.disable()
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.queries: List[dict] = []
        self.enabled = False

    def _before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        context._query_start_time = time.time()

    def _after_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        elapsed = time.time() - context._query_start_time
        self.queries.append({
            'statement': statement[:200],  # Truncate
            'elapsed_ms': round(elapsed * 1000, 2),
            'timestamp': time.time()
        })

    def enable(self):
        """Start logging queries."""
        if self.enabled:
            return
        self.queries = []
        event.listen(self.engine.sync_engine, "before_cursor_execute", self._before_cursor_execute)
        event.listen(self.engine.sync_engine, "after_cursor_execute", self._after_cursor_execute)
        self.enabled = True

    def disable(self):
        """Stop logging queries."""
        if not self.enabled:
            return
        event.remove(self.engine.sync_engine, "before_cursor_execute", self._before_cursor_execute)
        event.remove(self.engine.sync_engine, "after_cursor_execute", self._after_cursor_execute)
        self.enabled = False

    def report(self) -> dict:
        """Generate query report."""
        total_queries = len(self.queries)
        total_time = sum(q['elapsed_ms'] for q in self.queries)

        # Detect potential N+1 (same query pattern repeated)
        patterns = {}
        for q in self.queries:
            # Normalize query (remove specific values)
            pattern = q['statement'][:50]
            patterns[pattern] = patterns.get(pattern, 0) + 1

        n_plus_one_suspects = {k: v for k, v in patterns.items() if v > 3}

        return {
            'total_queries': total_queries,
            'total_time_ms': round(total_time, 2),
            'avg_time_ms': round(total_time / total_queries, 2) if total_queries else 0,
            'n_plus_one_suspects': n_plus_one_suspects,
            'queries': self.queries[:20]  # First 20 for inspection
        }

    def print_report(self):
        """Log formatted report."""
        report = self.report()
        lines = [
            "",
            "=" * 60,
            "  Query Report",
            "=" * 60,
            f"  Total queries: {report['total_queries']}",
            f"  Total time: {report['total_time_ms']}ms",
            f"  Avg per query: {report['avg_time_ms']}ms",
        ]

        if report['n_plus_one_suspects']:
            lines.append("")
            lines.append("  Potential N+1 Patterns:")
            for pattern, count in report['n_plus_one_suspects'].items():
                lines.append(f"     {count}x: {pattern}...")
        else:
            lines.append("")
            lines.append("  No N+1 patterns detected")

        lines.append("=" * 60)
        logger.info("\n".join(lines))


# =============================================================================
# BATCH LOADING UTILITIES
# =============================================================================

async def batch_load(
    db,
    model: Type,
    ids: List[int],
    options: List = None,
    chunk_size: int = 100
) -> dict:
    """
    Batch load records by IDs to prevent N+1.

    Usage:
        users = await batch_load(db, User, user_ids)
        # users is a dict: {id: record}

    Args:
        db: AsyncSession
        model: SQLAlchemy model class
        ids: List of IDs to load
        options: Eager loading options
        chunk_size: Max IDs per query

    Returns:
        Dict mapping ID to record
    """
    from sqlalchemy import select

    if not ids:
        return {}

    results = {}
    unique_ids = list(set(ids))

    for i in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[i:i + chunk_size]
        query = select(model).where(model.id.in_(chunk))

        if options:
            query = query.options(*options)

        result = await db.execute(query)
        for record in result.scalars():
            results[record.id] = record

    return results


def prefetch_related(query, *loaders):
    """
    Apply multiple loader presets to a query.

    Usage:
        query = prefetch_related(
            select(Exam),
            ExamLoader.with_questions(),
            ExamLoader.with_creator()
        )
    """
    options = []
    for loader in loaders:
        if callable(loader):
            options.extend(loader())
        elif isinstance(loader, list):
            options.extend(loader)
        else:
            options.append(loader)

    return query.options(*options)
