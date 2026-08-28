#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


PREFIX = os.getenv("GOREM_PREFIX", "GOREM0")
CLASS_NAME = "XII-GO-REM"
PHASES = (10, 25, 50)
SEB_KEY = "rem-stage0-seb"
SEB_HASH = hashlib.sha256(SEB_KEY.encode()).hexdigest()


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


def headers(token: str, seb: bool) -> dict[str, str]:
    out = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SEB/3.6 (Safe Exam Browser)" if seb else "Mozilla/5.0",
    }
    if seb:
        out["X-SafeExamBrowser-ConfigKeyHash"] = SEB_HASH
    return out


def call_one(kind: str, base: str, token: str, session_id: int, question_id: int, option_id: int) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    if kind == "autosave":
        path, body, seb = "/api/exams/auto-save", {
            "session_id": session_id,
            "answers": {str(question_id): option_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, True
    elif kind == "batch":
        path, body, seb = "/api/exams/auto-save-batch", {
            "session_id": session_id,
            "answers": [{"question_id": question_id, "selected_option_id": option_id}],
        }, True
    else:
        path, body, seb = "/api/exams/submit", {"session_id": session_id}, True
    response = httpx.post(f"{base.rstrip('/')}{path}", headers=headers(token, seb), json=body, timeout=30.0)
    try:
        payload = response.json()
    except Exception:
        payload = response.text[:200]
    return {
        "status": response.status_code,
        "body": payload,
        "elapsed_ms": (datetime.now(timezone.utc) - started).total_seconds() * 1000,
        "replica": response.headers.get("x-siab-replica", ""),
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


async def seed(conn: asyncpg.Connection, count: int, kind: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    teacher = int(
        await conn.fetchval(
            "INSERT INTO users (username, password_hash, full_name, role, is_active) VALUES ($1,'x',$1,'teacher',true) RETURNING id",
            f"{PREFIX}_teacher",
        )
    )
    exam_id = int(
        await conn.fetchval(
            """
            INSERT INTO exams (
                title, creator_id, duration_minutes, start_time, end_time, max_attempts,
                shuffle_questions, shuffle_options, show_results, passing_score, seb_config_key,
                is_published, subject, exam_type, show_teacher_name, access_token,
                is_deleted, has_ever_had_results
            ) VALUES (
                $1,$2,90,$3,$4,3,false,false,true,70,$5,true,'MTK','UTS',true,'REM000',false,false
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
            "INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings) VALUES ($1,'MC','multiple_choice','easy',1,0,'{}'::jsonb) RETURNING id",
            exam_id,
        )
    )
    oid = int(
        await conn.fetchval(
            "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'A',true,0) RETURNING id",
            qid,
        )
    )
    students, sessions, names = [], [], []
    for i in range(count):
        name = f"{PREFIX}_s{i:03d}"
        uid = int(
            await conn.fetchval(
                "INSERT INTO users (username, password_hash, full_name, role, student_class, is_active) VALUES ($1,'x',$1,'student',$2,true) RETURNING id",
                name,
                CLASS_NAME,
            )
        )
        sid = int(
            await conn.fetchval(
                "INSERT INTO exam_sessions (user_id, exam_id, status, start_time) VALUES ($1,$2,'in_progress',$3) RETURNING id",
                uid,
                exam_id,
                now,
            )
        )
        if kind == "submit":
            await conn.execute(
                "INSERT INTO answers (session_id, question_id, selected_option_id, answered_at) VALUES ($1,$2,$3,$4)",
                sid,
                qid,
                oid,
                now,
            )
        students.append(uid)
        sessions.append(sid)
        names.append(name)
    return {"question_id": qid, "option_id": oid, "student_ids": students, "session_ids": sessions, "usernames": names}


async def amain() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("autosave", "batch", "submit"), required=True)
    parser.add_argument("--go-url", default=os.getenv("GO_REMAIN_URL", "http://go_server:8000"))
    parser.add_argument("--http-url", default=os.getenv("GO_REMAIN_HTTP_URL", ""))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://redis:6379/0"))
    parser.add_argument("--jwt-secret", default=os.getenv("JWT_SECRET_KEY", ""))
    parser.add_argument("--phases", default=",".join(str(item) for item in PHASES))
    parser.add_argument("--allow-mixed-replica", action="store_true")
    args = parser.parse_args()
    if not args.database_url or not args.jwt_secret:
        raise SystemExit("DATABASE_URL and JWT_SECRET_KEY are required")
    phases = [int(item) for item in args.phases.split(",") if item.strip()]
    http_url = (args.http_url or args.go_url).rstrip("/")
    rds = redis.Redis.from_url(args.redis_url, decode_responses=True)
    conn = await asyncpg.connect(postgres_dsn(args.database_url), statement_cache_size=0)
    report: dict[str, Any] = {"kind": args.kind, "phases": [], "errors": [], "http_url": http_url}
    try:
        await cleanup(conn, rds)
        fixture = await seed(conn, sum(phases), args.kind)
        tokens = [mint_token(uid, name, args.jwt_secret) for uid, name in zip(fixture["student_ids"], fixture["usernames"])]
        health = httpx.get(f"{args.go_url.rstrip('/')}/health", timeout=5.0)
        if health.status_code != 200:
            raise RuntimeError(f"go health {health.status_code}")
        cursor = 0
        for count in phases:
            slice_tokens = tokens[cursor : cursor + count]
            slice_sessions = fixture["session_ids"][cursor : cursor + count]
            cursor += count
            with ThreadPoolExecutor(max_workers=count) as pool:
                results = list(
                    pool.map(
                        lambda pair: call_one(
                            args.kind, http_url, pair[0], pair[1], fixture["question_id"], fixture["option_id"]
                        ),
                        zip(slice_tokens, slice_sessions),
                    )
                )
            errors: list[str] = []
            success = sum(item["status"] == 200 for item in results)
            if success != count:
                errors.append(f"http_success={success}/{count}")
            go_count = sum(item["replica"] == "go-start" for item in results)
            if not args.allow_mixed_replica and go_count != count:
                errors.append(f"replica={sorted({item['replica'] for item in results})}")
            if args.kind == "autosave":
                cached = sum(1 for sid in slice_sessions if rds.get(f"exam_answers:{sid}"))
                if cached != count:
                    errors.append(f"redis_saved={cached} expected={count}")
            elif args.kind in {"batch", "submit"}:
                saved = int(await conn.fetchval("SELECT count(*) FROM answers WHERE session_id = ANY($1::int[])", slice_sessions) or 0)
                if saved != count:
                    errors.append(f"lost_answers saved={saved} expected={count}")
            if args.kind == "submit":
                submitted = int(
                    await conn.fetchval(
                        "SELECT count(*) FROM exam_sessions WHERE id = ANY($1::int[]) AND status='submitted'",
                        slice_sessions,
                    )
                    or 0
                )
                if submitted != count:
                    errors.append(f"submitted={submitted} expected={count}")
            elapsed = sorted(item["elapsed_ms"] for item in results)

            def pct(p: float) -> float:
                if not elapsed:
                    return 0.0
                idx = min(len(elapsed) - 1, max(0, int(round((p / 100) * (len(elapsed) - 1)))))
                return round(elapsed[idx], 2)

            report["phases"].append(
                {"users": count, "success": success, "go": go_count, "p95_ms": pct(95), "errors": errors}
            )
            report["errors"].extend(errors)
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
