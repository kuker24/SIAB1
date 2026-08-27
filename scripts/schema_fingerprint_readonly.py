#!/usr/bin/env python3
"""Deterministic read-only public-schema fingerprint.

The command never mutates the database. It opens a READ ONLY transaction,
hashes catalog metadata, and rolls back. Row data, password hashes, PII, and
unstable timestamps are excluded.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

from sqlalchemy import text

from app.database import async_session_write, engine_write

ALGORITHM = "sha256(canonical-json(public-schema-v1))"

FINGERPRINT_QUERIES = {
    "relation": """
        SELECT n.nspname, c.relname, c.relkind,
               COALESCE(pg_get_partkeydef(c.oid), ''),
               COALESCE(pg_get_expr(c.relpartbound, c.oid, true), '')
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
        ORDER BY n.nspname, c.relname
    """,
    "column": """
        SELECT table_schema, table_name, ordinal_position, column_name,
               data_type, udt_schema, udt_name, is_nullable,
               COALESCE(column_default, ''), is_identity, identity_generation,
               is_generated, COALESCE(generation_expression, '')
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_schema, table_name, ordinal_position
    """,
    "index": """
        SELECT schemaname, tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY schemaname, tablename, indexname
    """,
    "constraint": """
        SELECT n.nspname, t.relname, c.conname, c.contype,
               pg_get_constraintdef(c.oid, true)
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
        ORDER BY n.nspname, t.relname, c.conname
    """,
    "view": """
        SELECT n.nspname, c.relname, c.relkind, pg_get_viewdef(c.oid, true)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm')
        ORDER BY n.nspname, c.relname
    """,
    "function": """
        SELECT n.nspname, p.proname,
               pg_get_function_identity_arguments(p.oid),
               pg_get_functiondef(p.oid)
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
        ORDER BY n.nspname, p.proname,
                 pg_get_function_identity_arguments(p.oid)
    """,
    "trigger": """
        SELECT n.nspname, c.relname, t.tgname, pg_get_triggerdef(t.oid, true)
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND NOT t.tgisinternal
        ORDER BY n.nspname, c.relname, t.tgname
    """,
}


def normalize_value(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def digest_records(records: list[list[object]]) -> str:
    encoded = json.dumps(records, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


async def collect_rows(session, sql: str) -> list[list[object]]:
    result = await session.execute(text(sql))
    return [[normalize_value(value) for value in row] for row in result.fetchall()]


async def fingerprint_public_schema() -> dict[str, object]:
    async with async_session_write() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        read_only = await session.execute(text("SHOW transaction_read_only"))
        records: list[list[object]] = []
        counts: dict[str, int] = {}
        for category, sql in FINGERPRINT_QUERIES.items():
            category_rows = await collect_rows(session, sql)
            counts[category] = len(category_rows)
            records.extend([[category, *row] for row in category_rows])
        await session.rollback()

    return {
        "algorithm": ALGORITHM,
        "sha256": digest_records(records),
        "record_count": len(records),
        "counts": counts,
        "transaction_read_only": str(read_only.scalar_one()),
    }


async def main() -> None:
    report = await fingerprint_public_schema()
    await engine_write.dispose()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
