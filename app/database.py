"""
Async database connection using SQLAlchemy 2.0 with asyncpg.

ENHANCED VERSION (v2.0):
- Separate engines for master (write) and replica (read)
- get_db_write() for INSERT/UPDATE/DELETE
- get_db_read() for SELECT queries
- Automatic fallback to master if replica unavailable
"""
import logging
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# MASTER ENGINE (Write Operations)
# ============================================================================

def build_connect_args(database_url: str) -> dict:
    """
    Build DBAPI connect args.

    asyncpg + PgBouncer transaction pooling must disable statement caches,
    otherwise duplicate prepared statement errors can occur under concurrency.
    """
    if not database_url.startswith("postgresql+asyncpg"):
        return {}

    parsed = urlparse(database_url)
    host = (parsed.hostname or "").lower()
    url_lower = database_url.lower()
    if "pgbouncer" in host or "@pgbouncer" in url_lower:
        return {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            # Transaction-pooled PgBouncer can reuse backend sockets across clients.
            # Randomized statement names avoid collisions under extreme concurrency.
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4().hex}__",
        }
    return {}


def uses_pgbouncer(database_url: str) -> bool:
    parsed = urlparse(database_url)
    host = (parsed.hostname or "").lower()
    url_lower = database_url.lower()
    return "pgbouncer" in host or "@pgbouncer" in url_lower


def _build_engine(database_url: str, pool_size: int, max_overflow: int):
    """
    Build async SQLAlchemy engine with bounded pool settings.

    Per-process pool defaults are intentionally conservative because Uvicorn runs
    multiple worker processes. Total max connections ~= workers * (pool+overflow).
    """
    is_pgbouncer = uses_pgbouncer(database_url)
    use_null_pool = is_pgbouncer and settings.db_use_null_pool_with_pgbouncer
    pool_pre_ping = settings.db_pool_pre_ping
    pool_recycle = settings.db_pool_recycle
    # PgBouncer transaction pooling can close idle backend sessions relatively
    # aggressively. If pre-ping is disabled for latency reasons, keep recycle
    # below idle timeout window to reduce stale-connection reuse.
    if is_pgbouncer and not use_null_pool and not pool_pre_ping:
        pool_recycle = min(pool_recycle, 240)

    engine_kwargs = {
        "echo": settings.debug,
        "pool_pre_ping": pool_pre_ping,
        "connect_args": build_connect_args(database_url),
    }

    if use_null_pool:
        engine_kwargs["poolclass"] = NullPool
    else:
        engine_kwargs.update(
            {
                "pool_size": max(1, pool_size),
                "max_overflow": max(0, max_overflow),
                "pool_timeout": settings.db_pool_timeout,
                "pool_recycle": max(30, int(pool_recycle)),
                "pool_use_lifo": True,
            }
        )

    return create_async_engine(
        database_url,
        **engine_kwargs,
    )


def create_task_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
        connect_args=build_connect_args(settings.database_url),
    )


engine_write = _build_engine(
    settings.database_url,
    settings.db_pool_size,
    settings.db_max_overflow,
)

async_session_write = async_sessionmaker(
    engine_write,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ============================================================================
# REPLICA ENGINE (Read Operations)
# ============================================================================

# Use replica URL if configured, otherwise reuse master pool to avoid
# doubling connection pools on the same PostgreSQL instance.
_replica_url = getattr(settings, "database_read_url", None)
if _replica_url and _replica_url != settings.database_url:
    engine_read = _build_engine(
        _replica_url,
        settings.db_read_pool_size,
        settings.db_read_max_overflow,
    )
    async_session_read = async_sessionmaker(
        engine_read,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
else:
    engine_read = engine_write
    async_session_read = async_session_write

# Legacy compatibility alias
engine = engine_write
async_session_maker = async_session_write

# Base class for models
Base = declarative_base()


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

async def _safe_rollback(session: AsyncSession, *, context: str) -> None:
    """
    Roll back only when a transaction is active.

    In high-concurrency asyncpg/PgBouncer paths, connection invalidation can
    happen before rollback during request teardown. We treat this as safe
    cleanup and continue closing the session.
    """
    if not session.in_transaction():
        return
    try:
        await session.rollback()
    except SQLAlchemyError:
        logger.debug("Skip rollback on closed connection (%s)", context, exc_info=True)


async def get_db() -> AsyncSession:
    """Legacy dependency - routes to write database for backward compatibility."""
    async with async_session_write() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await _safe_rollback(session, context="get_db")
            raise
        finally:
            await session.close()


async def get_db_write() -> AsyncSession:
    """Dependency for WRITE operations (INSERT, UPDATE, DELETE)."""
    async with async_session_write() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await _safe_rollback(session, context="get_db_write")
            raise
        finally:
            await session.close()


async def get_db_read() -> AsyncSession:
    """Dependency for READ operations (SELECT) - uses replica if available."""
    async with async_session_read() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await _safe_rollback(session, context="get_db_read")
            await session.close()


async def init_db():
    """Initialize database tables on master."""
    async with engine_write.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Keep legacy deployments compatible when new settings columns are added.
        await _ensure_system_settings_columns(conn)
        # Keep legacy deployments compatible when role values are extended.
        await _ensure_users_role_constraint(conn)


async def _ensure_system_settings_columns(conn) -> None:
    """Add backward-compatible columns that may be missing on existing deployments."""
    try:
        dialect = str(conn.dialect.name).lower()
        if dialect == "postgresql":
            await conn.execute(
                text(
                    "ALTER TABLE system_settings "
                    "ADD COLUMN IF NOT EXISTS freeze_mode BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        elif dialect == "sqlite":
            # SQLite has no ADD COLUMN IF NOT EXISTS; inspect table info first.
            pragma = await conn.execute(text("PRAGMA table_info(system_settings)"))
            existing_columns = {str(row[1]) for row in pragma.fetchall()}
            if "freeze_mode" not in existing_columns:
                await conn.execute(
                    text(
                        "ALTER TABLE system_settings "
                        "ADD COLUMN freeze_mode BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
    except Exception:
        # Fail-open: startup must continue even if compatibility migration fails.
        logger.exception("Failed ensuring system_settings compatibility columns")


async def _ensure_users_role_constraint(conn) -> None:
    """Ensure users.role constraint supports the current role set in legacy DBs."""
    try:
        if str(conn.dialect.name).lower() != "postgresql":
            return

        constraint_result = await conn.execute(
            text(
                "SELECT pg_get_constraintdef(c.oid) AS constraint_def "
                "FROM pg_constraint c "
                "JOIN pg_class t ON c.conrelid = t.oid "
                "WHERE t.relname = 'users' "
                "AND c.conname = 'users_role_check' "
                "AND c.contype = 'c'"
            )
        )
        constraint_row = constraint_result.first()
        existing_def = str(getattr(constraint_row, "constraint_def", "") or "").lower()
        if "guruplus" in existing_def and "developer" in existing_def:
            return

        await conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"))
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD CONSTRAINT users_role_check "
                "CHECK (role IN ('developer', 'admin', 'teacher', 'student', 'guruplus'))"
            )
        )
        logger.info("Updated users_role_check constraint to include 'developer' and 'guruplus'")
    except Exception:
        # Fail-open: startup must continue even if compatibility migration fails.
        logger.exception("Failed ensuring users role compatibility constraint")


async def get_async_session():
    """
    Async generator for standalone database sessions.
    Use this for background tasks that need DB access outside request context.
    """
    async with async_session_write() as session:
        try:
            yield session
        except Exception:
            await _safe_rollback(session, context="get_async_session")
            raise
        finally:
            await session.close()
