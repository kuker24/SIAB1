#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

import asyncpg
import httpx
import jwt
import redis


PREFIX = os.getenv("GOSTAGE_PREFIX", "GOSTAGE0")
CLASS_NAME = "XII-GO-START"
PHASES = (10, 25, 50)


def postgres_dsn(raw: str) -> str:
    parsed = urlparse(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
    return urlunparse(parsed._replace(query=""))


def mint_token(user_id: int, username: str, secret: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": "student",
        "full_name": username,
        "student_class": CLASS_NAME,
        "is_active": True,
        "exp": int((now + timedelta(hours=2)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def seb_headers(token: str, seb_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "SEB/3.6 (Safe Exam Browser)",
        "X-SafeExamBrowser-ConfigKeyHash": hashlib.sha256(seb_key.encode()).hexdigest(),
        "Accept": "application/json",
    }


async def connect_pg(dsn: str) -> asyncpg.Connection:
    return await asyncpg.connect(postgres_dsn(dsn), statement_cache_size=0)


async def cleanup(conn: asyncpg.Connection, rds: redis.Redis, exam_id: int | None) -> None:
    user_ids = [
        int(row["id"])
        for row in await conn.fetch(
            "SELECT id FROM users WHERE username LIKE $1", f"{PREFIX}_%"
        )
    ]
    exam_ids = [
        int(row["id"])
        for row in await conn.fetch(
            "SELECT id FROM exams WHERE title LIKE $1", f"{PREFIX}_%"
        )
    ]
    if exam_id is not None and exam_id not in exam_ids:
        exam_ids.append(exam_id)
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
        rds.delete(f"monitoring:delta:exam:{eid}")
        rds.delete(f"cache:exam-start-validation:v1:{eid}")
        rds.delete(f"cache:exam-start-validation:v1:{eid}:lock")
        rds.delete(f"exam:{eid}:questions:payload:v1")
    if user_ids:
        await conn.execute("DELETE FROM users WHERE id = ANY($1::int[])", user_ids)


async def seed(conn: asyncpg.Connection, count: int, seb_key: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    teacher_id = int(
        await conn.fetchval(
            """
            INSERT INTO users (username, password_hash, full_name, role, is_active)
            VALUES ($1, 'x', 'Go Stage0 Teacher', 'teacher', true)
            RETURNING id
            """,
            f"{PREFIX}_teacher",
        )
    )
    student_ids: list[int] = []
    usernames: list[str] = []
    for index in range(count):
        username = f"{PREFIX}_s{index:03d}"
        user_id = int(
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
        student_ids.append(user_id)
        usernames.append(username)
    exam_id = int(
        await conn.fetchval(
            """
            INSERT INTO exams (
                title, creator_id, duration_minutes, start_time, end_time, max_attempts,
                shuffle_questions, shuffle_options, show_results, seb_config_key,
                is_published, subject, exam_type, show_teacher_name, allowed_classes,
                is_deleted, has_ever_had_results
            ) VALUES (
                $1, $2, 90, $3, $4, 3, true, true, false, $5, true, 'MTK', 'UTS', true, $6,
                false, false
            )
            RETURNING id
            """,
            f"{PREFIX}_EXAM",
            teacher_id,
            now - timedelta(hours=1),
            now + timedelta(hours=8),
            seb_key,
            CLASS_NAME,
        )
    )
    for index in range(4):
        question_id = int(
            await conn.fetchval(
                """
                INSERT INTO questions (
                    exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings
                ) VALUES ($1, $2, 'multiple_choice', 'hard', 1, $3, '{}'::jsonb)
                RETURNING id
                """,
                exam_id,
                f"GO Q{index + 1}",
                index,
            )
        )
        for option_index, letter in enumerate("ABCD"):
            await conn.execute(
                """
                INSERT INTO question_options (question_id, option_text, is_correct, order_index, option_group)
                VALUES ($1, $2, $3, $4, 'standard')
                """,
                question_id,
                f"{letter}{index + 1}",
                option_index == 0,
                option_index,
            )
    return {"exam_id": exam_id, "student_ids": student_ids, "usernames": usernames}


def start_one(base: str, exam_id: int, token: str, seb_key: str) -> dict[str, Any]:
    started = time.perf_counter()
    response = httpx.post(
        f"{base.rstrip('/')}/api/exams/{exam_id}/start",
        headers=seb_headers(token, seb_key),
        timeout=30.0,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    body: dict[str, Any] = {}
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text[:300]}
    return {
        "status": response.status_code,
        "elapsed_ms": elapsed_ms,
        "replica": response.headers.get("X-SIAB-Replica", ""),
        "body": body,
        "text": response.text[:300],
    }


def admission_snapshot(base: str) -> dict[str, Any]:
    response = httpx.get(f"{base.rstrip('/')}/internal/start-admission", timeout=5.0)
    response.raise_for_status()
    return response.json()


async def verify_phase(
    conn: asyncpg.Connection,
    rds: redis.Redis,
    exam_id: int,
    user_ids: list[int],
    results: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if any(item["status"] != 200 for item in results):
        errors.append(
            "http "
            + ",".join(f"{item['status']}" for item in results if item["status"] != 200)
        )
    session_ids = [
        int(item["body"]["session_id"])
        for item in results
        if item["status"] == 200 and item["body"].get("session_id")
    ]
    if len(session_ids) != len(user_ids):
        errors.append(f"session_ids={len(session_ids)} users={len(user_ids)}")
    if len(set(session_ids)) != len(session_ids):
        errors.append("duplicate session_id in HTTP responses")
    rows = await conn.fetch(
        """
        SELECT user_id, count(*)::int AS sessions,
               count(*) FILTER (WHERE status IN ('in_progress', 'active'))::int AS live
          FROM exam_sessions
         WHERE exam_id=$1 AND user_id = ANY($2::int[])
         GROUP BY user_id
        """,
        exam_id,
        user_ids,
    )
    by_user = {int(row["user_id"]): row for row in rows}
    for user_id in user_ids:
        row = by_user.get(user_id)
        if row is None or int(row["sessions"]) != 1 or int(row["live"]) != 1:
            errors.append(f"session row user={user_id} {dict(row) if row else None}")
    start_logs = int(
        await conn.fetchval(
            """
            SELECT count(*) FROM exam_logs l
              JOIN exam_sessions s ON s.id = l.session_id
             WHERE s.exam_id=$1 AND s.user_id = ANY($2::int[])
               AND l.event_type='SESSION_START'
            """,
            exam_id,
            user_ids,
        )
        or 0
    )
    if start_logs != len(user_ids):
        errors.append(f"SESSION_START={start_logs}")
    json_bad = int(
        await conn.fetchval(
            """
            SELECT count(*) FROM exam_logs l
              JOIN exam_sessions s ON s.id = l.session_id
             WHERE s.exam_id=$1 AND s.user_id = ANY($2::int[])
               AND l.event_type='SESSION_START'
               AND jsonb_typeof(l.event_data) IS DISTINCT FROM 'object'
            """,
            exam_id,
            user_ids,
        )
        or 0
    )
    if json_bad:
        errors.append(f"json_encoding_errors={json_bad}")
    missing_redis = 0
    for session_id in session_ids:
        raw = rds.get(f"exam_session:{session_id}")
        if not raw:
            missing_redis += 1
            continue
        snapshot = json.loads(raw)
        if snapshot.get("status") != "in_progress":
            errors.append(f"redis status session={session_id}")
    if missing_redis:
        errors.append(f"missing_redis={missing_redis}")
    stream = rds.xlen(f"monitoring:delta:exam:{exam_id}")
    if int(stream or 0) < len(user_ids):
        errors.append(f"monitoring={stream}")
    return errors


async def run_resume_and_race(
    conn: asyncpg.Connection,
    base: str,
    exam_id: int,
    user_id: int,
    token: str,
    seb_key: str,
) -> list[str]:
    errors: list[str] = []
    first = start_one(base, exam_id, token, seb_key)
    second = start_one(base, exam_id, token, seb_key)
    if first["status"] != 200 or second["status"] != 200:
        errors.append(f"resume http {first['status']} {second['status']}")
        return errors
    if first["body"].get("session_id") != second["body"].get("session_id"):
        errors.append("resume created a new session")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(start_one, base, exam_id, token, seb_key) for _ in range(2)]
        raced = [fut.result() for fut in futs]
    live = int(
        await conn.fetchval(
            """
            SELECT count(*) FROM exam_sessions
             WHERE user_id=$1 AND exam_id=$2 AND status IN ('in_progress', 'active')
            """,
            user_id,
            exam_id,
        )
        or 0
    )
    starts = int(
        await conn.fetchval(
            """
            SELECT count(*) FROM exam_logs l
              JOIN exam_sessions s ON s.id = l.session_id
             WHERE s.user_id=$1 AND s.exam_id=$2 AND l.event_type='SESSION_START'
            """,
            user_id,
            exam_id,
        )
        or 0
    )
    if any(item["status"] != 200 for item in raced) or live != 1 or starts != 1:
        errors.append(f"race live={live} starts={starts} http={[item['status'] for item in raced]}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-0 synthetic START against Go")
    parser.add_argument("--go-url", default=os.getenv("GO_START_URL", "http://127.0.0.1:18001"))
    parser.add_argument(
        "--start-url",
        default=os.getenv("GO_START_HTTP_URL", ""),
        help="Public START base (nginx). Defaults to --go-url.",
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://127.0.0.1:56379/0"))
    parser.add_argument("--jwt-secret", default=os.getenv("JWT_SECRET_KEY", ""))
    parser.add_argument("--seb-key", default=os.getenv("SEB_DEFAULT_CONFIG_KEY", "go-stage0-seb"))
    parser.add_argument("--phases", default=",".join(str(item) for item in PHASES))
    parser.add_argument(
        "--allow-mixed-replica",
        action="store_true",
        help="Allow FastAPI replica headers when START is split by nginx.",
    )
    return parser.parse_args()


async def amain() -> dict[str, Any]:
    args = parse_args()
    if not args.database_url or not args.jwt_secret:
        raise SystemExit("DATABASE_URL and JWT_SECRET_KEY are required")
    phases = [int(item) for item in args.phases.split(",") if item.strip()]
    start_url = (args.start_url or args.go_url).rstrip("/")
    rds = redis.Redis.from_url(args.redis_url, decode_responses=True)
    conn = await connect_pg(args.database_url)
    report: dict[str, Any] = {"phases": [], "errors": [], "start_url": start_url}
    try:
        await cleanup(conn, rds, None)
        fixture = await seed(conn, sum(phases), args.seb_key)
        tokens = [
            mint_token(user_id, username, args.jwt_secret)
            for user_id, username in zip(fixture["student_ids"], fixture["usernames"])
        ]
        health = httpx.get(f"{args.go_url.rstrip('/')}/health", timeout=5.0)
        if health.status_code != 200:
            raise RuntimeError(f"go health {health.status_code}")
        report["runtime"] = health.json() if health.headers.get("content-type", "").startswith("application/json") else {}
        cursor = 0
        peak_holders = 0
        for count in phases:
            slice_ids = fixture["student_ids"][cursor : cursor + count]
            slice_tokens = tokens[cursor : cursor + count]
            cursor += count
            with ThreadPoolExecutor(max_workers=count) as pool:
                futs = [
                    pool.submit(start_one, start_url, fixture["exam_id"], token, args.seb_key)
                    for token in slice_tokens
                ]
                results = [fut.result() for fut in futs]
            snapshot = admission_snapshot(args.go_url)
            peak_holders = max(peak_holders, int(snapshot.get("peak_holders") or 0))
            errors = await verify_phase(conn, rds, fixture["exam_id"], slice_ids, results)
            if int(snapshot.get("peak_holders") or 0) > 4:
                errors.append(f"peak_holders={snapshot.get('peak_holders')}")
            go_count = sum(item["replica"] == "go-start" for item in results)
            fastapi_count = count - go_count
            elapsed = sorted(item["elapsed_ms"] for item in results)
            def pct(p: float) -> float:
                if not elapsed:
                    return 0.0
                idx = min(len(elapsed) - 1, max(0, int(round((p / 100) * (len(elapsed) - 1)))))
                return round(elapsed[idx], 2)
            if not args.allow_mixed_replica:
                if any(item["replica"] != "go-start" for item in results):
                    errors.append("unexpected replica header")
            report["phases"].append(
                {
                    "users": count,
                    "success": sum(item["status"] == 200 for item in results),
                    "go_start": go_count,
                    "fastapi_start": fastapi_count,
                    "replica": sorted({item["replica"] for item in results}),
                    "p95_ms": pct(95),
                    "p99_ms": pct(99),
                    "admission": snapshot,
                    "errors": errors,
                }
            )
            report["errors"].extend(errors)
        resume_user = fixture["student_ids"][0]
        report["resume_race"] = await run_resume_and_race(
            conn,
            start_url,
            fixture["exam_id"],
            resume_user,
            tokens[0],
            args.seb_key,
        )
        report["errors"].extend(report["resume_race"])
        report["peak_holders"] = peak_holders
        report["cleanup"] = "pending"
        await cleanup(conn, rds, fixture["exam_id"])
        leftover_users = int(
            await conn.fetchval("SELECT count(*) FROM users WHERE username LIKE $1", f"{PREFIX}_%")
            or 0
        )
        leftover_exams = int(
            await conn.fetchval("SELECT count(*) FROM exams WHERE title LIKE $1", f"{PREFIX}_%")
            or 0
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
