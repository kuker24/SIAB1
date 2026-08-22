#!/usr/bin/env python3
"""Normalize stored quote HTML entities in question content.

Default mode is dry-run. Use --apply to update production data.
Only quote entities are decoded; other HTML entities are left untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from typing import Optional

import asyncpg

QUOTE_ENTITY_MARKERS = (
    "&quot;",
    "&#x27;",
    "&#39;",
    "&amp;quot;",
    "&amp;#x27;",
    "&amp;#39;",
)

QUOTE_ENTITY_REPLACEMENTS = (
    ("&amp;quot;", '"'),
    ("&amp;#x27;", "'"),
    ("&amp;#39;", "'"),
    ("&quot;", '"'),
    ("&#x27;", "'"),
    ("&#39;", "'"),
)


def _database_dsn() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)

    user = os.getenv("POSTGRES_USER") or os.getenv("DB_USER") or "examuser"
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD") or ""
    host = os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST") or "db"
    port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or "5432"
    database = os.getenv("POSTGRES_DB") or os.getenv("DB_NAME") or "exam_system"
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def normalize_quote_entities(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value
    # Two passes handle already double-encoded values safely without touching
    # unrelated entities such as &lt; or &amp;.
    for _ in range(2):
        before = normalized
        for source, target in QUOTE_ENTITY_REPLACEMENTS:
            normalized = normalized.replace(source, target)
        if normalized == before:
            break
    return normalized


def contains_quote_entity(value: Optional[str]) -> bool:
    return bool(value and any(marker in value for marker in QUOTE_ENTITY_MARKERS))


async def _normalize_questions(conn: asyncpg.Connection, apply: bool) -> tuple[int, int]:
    rows = await conn.fetch(
        """
        SELECT id, question_text, stimulus
        FROM questions
        WHERE question_text LIKE '%&quot;%'
           OR question_text LIKE '%&#x27;%'
           OR question_text LIKE '%&#39;%'
           OR question_text LIKE '%&amp;quot;%'
           OR question_text LIKE '%&amp;#x27;%'
           OR question_text LIKE '%&amp;#39;%'
           OR stimulus LIKE '%&quot;%'
           OR stimulus LIKE '%&#x27;%'
           OR stimulus LIKE '%&#39;%'
           OR stimulus LIKE '%&amp;quot;%'
           OR stimulus LIKE '%&amp;#x27;%'
           OR stimulus LIKE '%&amp;#39;%'
        ORDER BY id
        """
    )

    changed = 0
    for row in rows:
        new_question_text = normalize_quote_entities(row["question_text"])
        new_stimulus = normalize_quote_entities(row["stimulus"])
        if new_question_text == row["question_text"] and new_stimulus == row["stimulus"]:
            continue
        changed += 1
        if apply:
            await conn.execute(
                """
                UPDATE questions
                SET question_text = $2, stimulus = $3
                WHERE id = $1
                """,
                row["id"],
                new_question_text,
                new_stimulus,
            )
    return len(rows), changed


async def _normalize_options(conn: asyncpg.Connection, apply: bool) -> tuple[int, int]:
    rows = await conn.fetch(
        """
        SELECT id, option_text
        FROM question_options
        WHERE option_text LIKE '%&quot;%'
           OR option_text LIKE '%&#x27;%'
           OR option_text LIKE '%&#39;%'
           OR option_text LIKE '%&amp;quot;%'
           OR option_text LIKE '%&amp;#x27;%'
           OR option_text LIKE '%&amp;#39;%'
        ORDER BY id
        """
    )

    changed = 0
    for row in rows:
        new_option_text = normalize_quote_entities(row["option_text"])
        if new_option_text == row["option_text"]:
            continue
        changed += 1
        if apply:
            await conn.execute(
                "UPDATE question_options SET option_text = $2 WHERE id = $1",
                row["id"],
                new_option_text,
            )
    return len(rows), changed


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist changes to database")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    conn = await asyncpg.connect(_database_dsn(), statement_cache_size=0)
    try:
        async with conn.transaction():
            question_candidates, question_changed = await _normalize_questions(conn, args.apply)
            option_candidates, option_changed = await _normalize_options(conn, args.apply)
            print(f"mode={mode}")
            print(f"questions candidates={question_candidates} changed={question_changed}")
            print(f"question_options candidates={option_candidates} changed={option_changed}")
            if not args.apply:
                raise RuntimeError("dry-run rollback")
    except RuntimeError as exc:
        if str(exc) != "dry-run rollback":
            raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
