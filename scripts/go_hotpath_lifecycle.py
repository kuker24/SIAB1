#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
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
ACCESS = os.getenv("GOLIFE_TOKEN", f"L{int(time.time()) % 100000:05d}")

_post_lock = threading.Lock()
_last_post = 0.0
_post_gap = 0.22


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


def pace_post() -> None:
    global _last_post
    with _post_lock:
        wait = _post_gap - (time.time() - _last_post)
        if wait > 0:
            time.sleep(wait)
        _last_post = time.time()


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, int(round(p / 100.0 * (len(values) - 1)))))
    return round(values[idx], 3)


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


def one_lifecycle(token: str, exam_token: str, exam_id: int, qid: int, oid: int, qid2: int, oid2: int) -> dict[str, Any]:
    errors: list[str] = []
    client = httpx.Client(timeout=30.0)

    def post_retry(path: str, body: dict[str, Any]) -> httpx.Response:
        last = httpx.Response(599)
        for attempt in range(10):
            pace_post()
            last = client.post(f"{BASE}{path}", headers=hdr(token), json=body)
            if last.status_code != 429:
                return last
            wait = 2.0 * (attempt + 1)
            raw = last.headers.get("Retry-After")
            if raw:
                try:
                    wait = float(raw)
                except ValueError:
                    pass
            else:
                try:
                    wait = float(last.json().get("retry_after") or wait)
                except Exception:
                    pass
            time.sleep(min(65.0, wait))
        return last

    join = post_retry("/api/exams/join", {"token": exam_token})
    if join.status_code != 200:
        return {"ok": False, "errors": [f"join {join.status_code}"], "elapsed_ms": 0, "session_id": 0}
    started = datetime.now(timezone.utc)
    start = post_retry(f"/api/exams/{exam_id}/start", {})
    if start.status_code != 200:
        return {
            "ok": False,
            "errors": [f"start {start.status_code} {start.text[:120]}"],
            "elapsed_ms": 0,
            "session_id": 0,
        }
    session_id = int(start.json()["session_id"])
    ans = post_retry(
        "/api/exams/submit-answer",
        {"session_id": session_id, "question_id": qid, "selected_option_id": oid},
    )
    if ans.status_code != 200:
        errors.append(f"answer {ans.status_code}")
    auto = post_retry(
        "/api/exams/auto-save",
        {
            "session_id": session_id,
            "answers": {str(qid): oid},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    if auto.status_code != 200:
        errors.append(f"autosave {auto.status_code}")
    ans2 = post_retry(
        "/api/exams/submit-answer",
        {"session_id": session_id, "question_id": qid2, "selected_option_id": oid2},
    )
    if ans2.status_code != 200:
        errors.append(f"answer2 {ans2.status_code}")
    batch = post_retry(
        "/api/exams/auto-save-batch",
        {
            "session_id": session_id,
            "answers": [
                {"question_id": qid, "selected_option_id": oid},
                {"question_id": qid2, "selected_option_id": oid2},
            ],
        },
    )
    if batch.status_code != 200:
        errors.append(f"batch {batch.status_code}")
    resume = client.get(f"{BASE}/api/exams/session/{session_id}/resume", headers=hdr(token))
    if resume.status_code != 200:
        errors.append(f"resume {resume.status_code}")
    upd = post_retry(
        "/api/exams/submit-answer",
        {"session_id": session_id, "question_id": qid, "selected_option_id": oid},
    )
    if upd.status_code != 200:
        errors.append(f"update {upd.status_code}")
    sub = post_retry("/api/exams/submit", {"session_id": session_id})
    if sub.status_code != 200:
        errors.append(f"submit {sub.status_code} {sub.text[:120]}")
    score = None
    try:
        score = sub.json().get("score")
    except Exception:
        pass
    elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    return {
        "ok": not errors,
        "errors": errors,
        "elapsed_ms": elapsed,
        "session_id": session_id,
        "score": score,
        "join_replica": join.headers.get("x-siab-replica", ""),
        "start_replica": start.headers.get("x-siab-replica", ""),
        "answer_replica": ans.headers.get("x-siab-replica", ""),
        "autosave_replica": auto.headers.get("x-siab-replica", ""),
        "batch_replica": batch.headers.get("x-siab-replica", ""),
        "submit_replica": sub.headers.get("x-siab-replica", ""),
    }


async def assert_sessions(
    conn: asyncpg.Connection,
    rds: redis.Redis,
    session_ids: list[int],
    qid: int,
    qid2: int,
    exam_id: int,
    check_redis_sid: int | None,
) -> list[str]:
    errors: list[str] = []
    if not session_ids:
        return ["no sessions"]
    rows = await conn.fetch(
        "SELECT id, status, score FROM exam_sessions WHERE id = ANY($1::int[])",
        session_ids,
    )
    by_id = {int(r["id"]): r for r in rows}
    for sid in session_ids:
        row = by_id.get(sid)
        if row is None:
            errors.append(f"missing session {sid}")
            continue
        if row["status"] != "submitted":
            errors.append(f"status {sid}={row['status']}")
        score = float(row["score"] or -1)
        if abs(score - 100.0) > 0.01:
            errors.append(f"wrong score {sid}={score}")
    answers = await conn.fetch(
        """
        SELECT session_id, question_id, count(*) AS n
          FROM answers WHERE session_id = ANY($1::int[])
         GROUP BY session_id, question_id
        """,
        session_ids,
    )
    seen: dict[int, set[int]] = {}
    dups = 0
    for row in answers:
        sid = int(row["session_id"])
        q = int(row["question_id"])
        n = int(row["n"])
        if n > 1:
            dups += 1
        seen.setdefault(sid, set()).add(q)
    if dups:
        errors.append(f"duplicate answers={dups}")
    lost = 0
    for sid in session_ids:
        got = seen.get(sid, set())
        if qid not in got or qid2 not in got:
            lost += 1
    if lost:
        errors.append(f"lost answers sessions={lost}")
    live = int(
        await conn.fetchval(
            """
            SELECT count(*) FROM (
                SELECT user_id FROM exam_sessions
                 WHERE exam_id=$1 AND status='in_progress'
                 GROUP BY user_id HAVING count(*) > 1
            ) t
            """,
            exam_id,
        )
        or 0
    )
    if live:
        errors.append(f"duplicate live sessions={live}")
    logs = await conn.fetch(
        """
        SELECT session_id, event_type, count(*) AS n
          FROM exam_logs
         WHERE session_id = ANY($1::int[])
           AND event_type = ANY($2::text[])
         GROUP BY session_id, event_type
        """,
        session_ids,
        ["SESSION_START", "EXAM_SUBMITTED", "SCORE_BREAKDOWN"],
    )
    logmap: dict[int, dict[str, int]] = {}
    for row in logs:
        logmap.setdefault(int(row["session_id"]), {})[str(row["event_type"])] = int(row["n"])
    missing = 0
    for sid in session_ids:
        got = logmap.get(sid, {})
        if got.get("SESSION_START", 0) != 1 or got.get("EXAM_SUBMITTED", 0) != 1 or got.get("SCORE_BREAKDOWN", 0) != 1:
            missing += 1
    if missing:
        errors.append(f"missing audit logs sessions={missing}")
    if check_redis_sid:
        raw = rds.get(f"exam_answers:{check_redis_sid}")
        ttl = int(rds.ttl(f"exam_answers:{check_redis_sid}"))
        if raw:
            try:
                json.loads(raw)
            except Exception:
                errors.append("malformed exam_answers json")
            if ttl == 0:
                errors.append("exam_answers ttl=0")
    return errors


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
                    $1,$2,90,$3,$4,3,false,false,true,$5,true,'MTK','UTS',true,$6,false,false
                ) RETURNING id
                """,
                f"{PREFIX}_exam",
                teacher,
                now - timedelta(hours=1),
                now + timedelta(hours=3),
                SEB_KEY,
                ACCESS,
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
        qid2 = int(
            await conn.fetchval(
                """
                INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings)
                VALUES ($1,'MC2','multiple_choice','easy',1,1,'{}'::jsonb) RETURNING id
                """,
                exam_id,
            )
        )
        oid2 = int(
            await conn.fetchval(
                "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'B',true,0) RETURNING id",
                qid2,
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
        life = one_lifecycle(tok, ACCESS, exam_id, qid, oid, qid2, oid2)
        report["lifecycle"] = life
        if not life["ok"]:
            report["errors"].extend(life["errors"])
        session_id = int(life.get("session_id") or 0)
        life_errors = await assert_sessions(conn, rds, [session_id] if session_id else [], qid, qid2, exam_id, session_id)
        report["lifecycle_db"] = "PASS" if not life_errors else life_errors
        report["errors"].extend(life_errors)
        mixed_rows: list[dict[str, Any]] = []
        wall0 = time.time()
        if mixed > 0 and not report["errors"]:
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
                tokens.append(mint(mid, name, jwt_secret))
            with ThreadPoolExecutor(max_workers=mixed) as pool:
                mixed_rows = list(
                    pool.map(lambda item: one_lifecycle(item, ACCESS, exam_id, qid, oid, qid2, oid2), tokens)
                )
        wall = max(0.001, time.time() - wall0)
        elapsed = sorted(float(item["elapsed_ms"]) for item in mixed_rows if item.get("elapsed_ms"))
        success = sum(1 for item in mixed_rows if item["ok"])
        mixed_sids = [int(item["session_id"]) for item in mixed_rows if item.get("session_id")]
        mixed_db = await assert_sessions(conn, rds, mixed_sids, qid, qid2, exam_id, None) if mixed_sids else []
        report["mixed"] = {
            "n": mixed,
            "success": success,
            "correctness": round(100.0 * success / mixed, 2) if mixed else 0,
            "p50": pct(elapsed, 50),
            "p95": pct(elapsed, 95),
            "p99": pct(elapsed, 99),
            "max": round(elapsed[-1], 3) if elapsed else 0,
            "throughput": round(success / wall, 3) if mixed else 0,
            "errors": [item["errors"] for item in mixed_rows if not item["ok"]][:5],
            "db": "PASS" if not mixed_db else mixed_db,
        }
        if mixed and success != mixed:
            report["errors"].append(f"mixed {success}/{mixed}")
        report["errors"].extend(mixed_db)
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
