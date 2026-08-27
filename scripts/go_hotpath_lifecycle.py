#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
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


PREFIX = os.getenv("GOLIFE_PREFIX", "GOLIFE")
CLASS_NAME = "XII-GO-LIFE"
SEB_KEY = "life-seb"
BASE = os.getenv("HOTPATH_BASE", "http://nginx").rstrip("/")


def postgres_dsn(raw: str) -> str:
    parsed = urlparse(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
    return urlunparse(parsed._replace(query=""))


def mint(user_id: int, username: str, secret: str) -> str:
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


def hdr(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SEB/3.6 (Safe Exam Browser)",
        "X-SafeExamBrowser-ConfigKeyHash": hashlib.sha256(SEB_KEY.encode()).hexdigest(),
    }


async def cleanup(conn: asyncpg.Connection, rds: redis.Redis) -> None:
    user_ids = [int(r["id"]) for r in await conn.fetch("SELECT id FROM users WHERE username LIKE $1", f"{PREFIX}_%")]
    exam_ids = [int(r["id"]) for r in await conn.fetch("SELECT id FROM exams WHERE title LIKE $1", f"{PREFIX}_%")]
    sids: list[int] = []
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
        sids = [int(r["id"]) for r in rows]
    if sids:
        await conn.execute("DELETE FROM answers WHERE session_id = ANY($1::int[])", sids)
        await conn.execute("DELETE FROM exam_logs WHERE session_id = ANY($1::int[])", sids)
        await conn.execute("DELETE FROM exam_sessions WHERE id = ANY($1::int[])", sids)
        for sid in sids:
            rds.delete(f"exam_session:{sid}", f"exam_answers:{sid}", f"exam_answered_questions:{sid}")
    for eid in exam_ids:
        await conn.execute(
            "DELETE FROM question_options WHERE question_id IN (SELECT id FROM questions WHERE exam_id=$1)", eid
        )
        await conn.execute("DELETE FROM questions WHERE exam_id=$1", eid)
        await conn.execute("DELETE FROM exams WHERE id=$1", eid)
    if user_ids:
        await conn.execute("DELETE FROM users WHERE id = ANY($1::int[])", user_ids)


def one_lifecycle(token: str, exam_token: str, exam_id: int, qid: int, oid: int) -> dict[str, Any]:
    errors: list[str] = []
    client = httpx.Client(timeout=30.0)
    join = client.post(f"{BASE}/api/exams/join", headers=hdr(token), json={"token": exam_token})
    if join.status_code != 200:
        return {"ok": False, "errors": [f"join {join.status_code}"], "elapsed_ms": 0}
    started = datetime.now(timezone.utc)
    start = client.post(f"{BASE}/api/exams/{exam_id}/start", headers=hdr(token), json={})
    if start.status_code != 200:
        return {"ok": False, "errors": [f"start {start.status_code} {start.text[:120]}"], "elapsed_ms": 0}
    session_id = int(start.json()["session_id"])
    ans = client.post(
        f"{BASE}/api/exams/submit-answer",
        headers=hdr(token),
        json={"session_id": session_id, "question_id": qid, "selected_option_id": oid},
    )
    if ans.status_code != 200:
        errors.append(f"answer {ans.status_code}")
    auto = client.post(
        f"{BASE}/api/exams/auto-save",
        headers=hdr(token),
        json={"session_id": session_id, "answers": {str(qid): oid}, "timestamp": datetime.now(timezone.utc).isoformat()},
    )
    if auto.status_code != 200:
        errors.append(f"autosave {auto.status_code}")
    resume = client.get(f"{BASE}/api/exams/session/{session_id}/resume", headers=hdr(token))
    if resume.status_code != 200:
        errors.append(f"resume {resume.status_code}")
    upd = client.post(
        f"{BASE}/api/exams/submit-answer",
        headers=hdr(token),
        json={"session_id": session_id, "question_id": qid, "selected_option_id": oid},
    )
    if upd.status_code != 200:
        errors.append(f"update {upd.status_code}")
    sub = client.post(f"{BASE}/api/exams/submit", headers=hdr(token), json={"session_id": session_id})
    if sub.status_code != 200:
        errors.append(f"submit {sub.status_code} {sub.text[:120]}")
    elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    return {
        "ok": not errors,
        "errors": errors,
        "elapsed_ms": elapsed,
        "session_id": session_id,
        "join_replica": join.headers.get("x-siab-replica", ""),
        "start_replica": start.headers.get("x-siab-replica", ""),
        "answer_replica": ans.headers.get("x-siab-replica", ""),
    }


async def amain() -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL", "")
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    mixed = int(os.getenv("HOTPATH_MIXED", "50"))
    if not database_url or not jwt_secret:
        raise SystemExit("DATABASE_URL and JWT_SECRET_KEY are required")
    rds = redis.Redis.from_url(redis_url, decode_responses=True)
    conn = await asyncpg.connect(postgres_dsn(database_url), statement_cache_size=0)
    report: dict[str, Any] = {"errors": []}
    try:
        await cleanup(conn, rds)
        now = datetime.now(timezone.utc)
        teacher = int(
            await conn.fetchval(
                """
                INSERT INTO users (username, password_hash, full_name, role, is_active)
                VALUES ($1,'x',$1,'teacher',true) RETURNING id
                """,
                f"{PREFIX}_teacher",
            )
        )
        exam_id = int(
            await conn.fetchval(
                """
                INSERT INTO exams (
                    title, creator_id, duration_minutes, start_time, end_time, max_attempts,
                    shuffle_questions, shuffle_options, show_results, seb_config_key,
                    is_published, subject, exam_type, show_teacher_name, access_token,
                    is_deleted, has_ever_had_results
                ) VALUES (
                    $1,$2,90,$3,$4,3,false,false,true,$5,true,'MTK','UTS',true,'LIFE01',false,false
                ) RETURNING id
                """,
                f"{PREFIX}_exam",
                teacher,
                now - timedelta(hours=1),
                now + timedelta(hours=3),
                SEB_KEY,
            )
        )
        qid = int(
            await conn.fetchval(
                """
                INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings)
                VALUES ($1,'MC','multiple_choice','easy',1,0,'{}'::jsonb) RETURNING id
                """,
                exam_id,
            )
        )
        oid = int(
            await conn.fetchval(
                "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'A',true,0) RETURNING id",
                qid,
            )
        )
        uid = int(
            await conn.fetchval(
                """
                INSERT INTO users (username, password_hash, full_name, role, student_class, is_active)
                VALUES ($1,'x',$1,'student',$2,true) RETURNING id
                """,
                f"{PREFIX}_s",
                CLASS_NAME,
            )
        )
        tok = mint(uid, f"{PREFIX}_s", jwt_secret)
        life = one_lifecycle(tok, "LIFE01", exam_id, qid, oid)
        report["lifecycle"] = life
        if not life["ok"]:
            report["errors"].extend(life["errors"])
        session_id = int(life.get("session_id") or 0)
        answers = int(await conn.fetchval("SELECT count(*) FROM answers WHERE session_id=$1", session_id) or 0)
        status = await conn.fetchval("SELECT status FROM exam_sessions WHERE id=$1", session_id)
        report["session_status"] = status
        report["answers"] = answers
        if status != "submitted" or answers < 1:
            report["errors"].append(f"final state status={status} answers={answers}")
        users = []
        tokens = []
        for i in range(mixed):
            name = f"{PREFIX}_m{i:03d}"
            mid = int(
                await conn.fetchval(
                    """
                    INSERT INTO users (username, password_hash, full_name, role, student_class, is_active)
                    VALUES ($1,'x',$1,'student',$2,true) RETURNING id
                    """,
                    name,
                    CLASS_NAME,
                )
            )
            users.append(mid)
            tokens.append(mint(mid, name, jwt_secret))
        with ThreadPoolExecutor(max_workers=mixed) as pool:
            mixed_rows = list(
                pool.map(lambda tok: one_lifecycle(tok, "LIFE01", exam_id, qid, oid), tokens)
            )
        elapsed = sorted(item["elapsed_ms"] for item in mixed_rows if item["elapsed_ms"])
        success = sum(1 for item in mixed_rows if item["ok"])
        report["mixed"] = {
            "n": mixed,
            "success": success,
            "correctness": round(100.0 * success / mixed, 2) if mixed else 0,
            "p95": elapsed[min(len(elapsed) - 1, max(0, int(round(0.95 * (len(elapsed) - 1)))))] if elapsed else 0,
            "p99": elapsed[min(len(elapsed) - 1, max(0, int(round(0.99 * (len(elapsed) - 1)))))] if elapsed else 0,
            "errors": [item["errors"] for item in mixed_rows if not item["ok"]][:5],
        }
        if success != mixed:
            report["errors"].append(f"mixed {success}/{mixed}")
        origin = httpx.get("http://nginx/health", timeout=5).status_code
        report["origin"] = origin
        await cleanup(conn, rds)
        leftover = int(await conn.fetchval("SELECT count(*) FROM users WHERE username LIKE $1", f"{PREFIX}_%") or 0)
        report["cleanup"] = "PASS" if leftover == 0 else "FAIL"
        if leftover:
            report["errors"].append(f"leftovers={leftover}")
    finally:
        await conn.close()
    report["verdict"] = "PASS" if not report["errors"] else "FAIL"
    print(json.dumps(report, default=str))
    return report


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(amain()).get("verdict") == "PASS" else 1)
