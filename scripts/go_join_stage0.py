#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

import asyncpg
import httpx
import jwt
import redis


PREFIX = os.getenv("GOJOIN_PREFIX", "GOJOIN0")
CLASS_NAME = "XII-GO-JOIN"
PHASES = (10, 25, 50)
TOKEN = "JOIN00"


def postgres_dsn(raw: str) -> str:
    parsed = urlparse(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
    return urlunparse(parsed._replace(query=""))


def mint_token(user_id: int, username: str, secret: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "username": username,
            "role": "student",
            "full_name": username,
            "student_class": CLASS_NAME,
            "is_active": True,
            "exp": int((now + timedelta(hours=2)).timestamp()),
        },
        secret,
        algorithm="HS256",
    )


def join_one(base: str, token: str) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    response = httpx.post(
        f"{base.rstrip('/')}/api/exams/join",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        content=json.dumps({"token": TOKEN}).encode(),
        timeout=30.0,
    )
    elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    body: Any
    try:
        body = response.json()
    except Exception:
        body = response.text[:200]
    return {
        "status": response.status_code,
        "body": body,
        "elapsed_ms": elapsed_ms,
        "replica": response.headers.get("x-siab-replica", ""),
    }


async def connect_pg(dsn: str) -> asyncpg.Connection:
    return await asyncpg.connect(postgres_dsn(dsn), statement_cache_size=0)


async def cleanup(conn: asyncpg.Connection, rds: redis.Redis) -> None:
    user_ids = [
        int(row["id"])
        for row in await conn.fetch("SELECT id FROM users WHERE username LIKE $1", f"{PREFIX}_%")
    ]
    exam_ids = [
        int(row["id"])
        for row in await conn.fetch("SELECT id FROM exams WHERE title LIKE $1", f"{PREFIX}_%")
    ]
    session_ids: list[int] = []
    if user_ids or exam_ids:
        rows = await conn.fetch(
            """
            SELECT id FROM exam_sessions
             WHERE ($1::int[] = '{}'::int[] OR user_id = ANY($1::int[]))
                OR ($2::int[] = '{}'::int[] OR exam_id = ANY($2::int[]))
            """,
            user_ids or [],
            exam_ids or [],
        )
        session_ids = [int(row["id"]) for row in rows]
    if session_ids:
        await conn.execute("DELETE FROM answers WHERE session_id = ANY($1::int[])", session_ids)
        await conn.execute("DELETE FROM exam_logs WHERE session_id = ANY($1::int[])", session_ids)
        await conn.execute("DELETE FROM exam_sessions WHERE id = ANY($1::int[])", session_ids)
        rds.delete(*[f"exam_session:{sid}" for sid in session_ids])
    for eid in exam_ids:
        await conn.execute(
            "DELETE FROM question_options WHERE question_id IN (SELECT id FROM questions WHERE exam_id=$1)",
            eid,
        )
        await conn.execute("DELETE FROM questions WHERE exam_id=$1", eid)
        await conn.execute("DELETE FROM exams WHERE id=$1", eid)
    if user_ids:
        await conn.execute("DELETE FROM users WHERE id = ANY($1::int[])", user_ids)


async def seed(conn: asyncpg.Connection, count: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    teacher_id = int(
        await conn.fetchval(
            """
            INSERT INTO users (username, password_hash, full_name, role, is_active)
            VALUES ($1, 'x', 'Go Join0 Teacher', 'teacher', true)
            RETURNING id
            """,
            f"{PREFIX}_teacher",
        )
    )
    student_ids: list[int] = []
    usernames: list[str] = []
    for index in range(count):
        username = f"{PREFIX}_s{index:03d}"
        student_ids.append(
            int(
                await conn.fetchval(
                    """
                    INSERT INTO users (username, password_hash, full_name, role, student_class, is_active)
                    VALUES ($1, 'x', $1, 'student', $2, true)
                    RETURNING id
                    """,
                    username,
                    CLASS_NAME,
                )
            )
        )
        usernames.append(username)
    exam_id = int(
        await conn.fetchval(
            """
            INSERT INTO exams (
                title, creator_id, duration_minutes, start_time, end_time, max_attempts,
                shuffle_questions, shuffle_options, show_results, seb_config_key,
                is_published, subject, exam_type, show_teacher_name, allowed_classes,
                allowed_students, access_token, is_deleted, has_ever_had_results
            ) VALUES (
                $1, $2, 90, $3, $4, 3, false, false, false, 'join-seb',
                true, 'MTK', 'UTS', true, $5, NULL, $6, false, false
            )
            RETURNING id
            """,
            f"{PREFIX}_{TOKEN}",
            teacher_id,
            now - timedelta(hours=1),
            now + timedelta(hours=3),
            CLASS_NAME,
            TOKEN,
        )
    )
    for index in range(3):
        await conn.execute(
            """
            INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings)
            VALUES ($1, $2, 'multiple_choice', 'easy', 1, $3, '{}'::jsonb)
            """,
            exam_id,
            f"Q{index+1}",
            index,
        )
    return {"exam_id": exam_id, "student_ids": student_ids, "usernames": usernames}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-0 synthetic JOIN against Go")
    parser.add_argument("--go-url", default=os.getenv("GO_JOIN_URL", "http://go_server:8000"))
    parser.add_argument("--join-url", default=os.getenv("GO_JOIN_HTTP_URL", ""))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://redis:6379/0"))
    parser.add_argument("--jwt-secret", default=os.getenv("JWT_SECRET_KEY", ""))
    parser.add_argument("--phases", default=",".join(str(item) for item in PHASES))
    parser.add_argument("--allow-mixed-replica", action="store_true")
    return parser.parse_args()


async def amain() -> dict[str, Any]:
    args = parse_args()
    if not args.database_url or not args.jwt_secret:
        raise SystemExit("DATABASE_URL and JWT_SECRET_KEY are required")
    phases = [int(item) for item in args.phases.split(",") if item.strip()]
    join_url = (args.join_url or args.go_url).rstrip("/")
    rds = redis.Redis.from_url(args.redis_url, decode_responses=True)
    conn = await connect_pg(args.database_url)
    report: dict[str, Any] = {"phases": [], "errors": [], "join_url": join_url}
    try:
        await cleanup(conn, rds)
        fixture = await seed(conn, sum(phases))
        tokens = [
            mint_token(user_id, username, args.jwt_secret)
            for user_id, username in zip(fixture["student_ids"], fixture["usernames"])
        ]
        health = httpx.get(f"{args.go_url.rstrip('/')}/health", timeout=5.0)
        if health.status_code != 200:
            raise RuntimeError(f"go health {health.status_code}")
        cursor = 0
        for count in phases:
            slice_tokens = tokens[cursor : cursor + count]
            slice_ids = fixture["student_ids"][cursor : cursor + count]
            cursor += count
            with ThreadPoolExecutor(max_workers=count) as pool:
                results = list(pool.map(lambda tok: join_one(join_url, tok), slice_tokens))
            errors: list[str] = []
            success = sum(item["status"] == 200 for item in results)
            if success != count:
                errors.append(f"http_success={success}/{count}")
            go_count = sum(item["replica"] == "go-start" for item in results)
            if not args.allow_mixed_replica and go_count != count:
                errors.append(f"replica={sorted({item['replica'] for item in results})}")
            sessions = int(
                await conn.fetchval(
                    """
                    SELECT count(*) FROM exam_sessions
                     WHERE exam_id=$1 AND user_id = ANY($2::int[])
                    """,
                    fixture["exam_id"],
                    slice_ids,
                )
                or 0
            )
            if sessions:
                errors.append(f"sessions_created={sessions}")
            elapsed = sorted(item["elapsed_ms"] for item in results)

            def pct(p: float) -> float:
                if not elapsed:
                    return 0.0
                idx = min(len(elapsed) - 1, max(0, int(round((p / 100) * (len(elapsed) - 1)))))
                return round(elapsed[idx], 2)

            report["phases"].append(
                {
                    "users": count,
                    "success": success,
                    "go_join": go_count,
                    "p95_ms": pct(95),
                    "p99_ms": pct(99),
                    "errors": errors,
                }
            )
            report["errors"].extend(errors)
        await cleanup(conn, rds)
        leftover_users = int(
            await conn.fetchval("SELECT count(*) FROM users WHERE username LIKE $1", f"{PREFIX}_%") or 0
        )
        leftover_exams = int(
            await conn.fetchval("SELECT count(*) FROM exams WHERE title LIKE $1", f"{PREFIX}_%") or 0
        )
        report["cleanup"] = "PASS" if leftover_users == 0 and leftover_exams == 0 else "FAIL"
        if report["cleanup"] != "PASS":
            report["errors"].append(f"leftovers users={leftover_users} exams={leftover_exams}")
    finally:
        await conn.close()
    report["verdict"] = "PASS" if not report["errors"] else "FAIL"
    print(json.dumps(report, default=str))
    return report


def main() -> int:
    result = asyncio.run(amain())
    return 0 if result.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
