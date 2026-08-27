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
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_post_lock = threading.Lock()
_last_post = 0.0
_post_gap = 0.22
_count_lock = threading.Lock()
_429_count = 0


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


def note_429() -> None:
    global _429_count
    with _count_lock:
        _429_count += 1


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, int(round(p / 100.0 * (len(values) - 1)))))
    return round(values[idx], 3)


def is_go(replica: str) -> bool:
    marker = (replica or "").lower()
    return marker.startswith("go")


def parse_json(raw: Any) -> Any | None:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode()
    try:
        return json.loads(raw)
    except Exception:
        return None


def cache_has_question(payload: Any, question_id: int) -> bool:
    if not isinstance(payload, dict):
        return False
    return str(question_id) in payload or question_id in payload


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


def redis_before(rds: redis.Redis, session_id: int, qid: int, qid2: int) -> list[str]:
    errors: list[str] = []
    answers_raw = rds.get(f"exam_answers:{session_id}")
    answers_ttl = int(rds.ttl(f"exam_answers:{session_id}"))
    payload = parse_json(answers_raw)
    if payload is None:
        errors.append("pre-submit exam_answers missing/invalid json")
    else:
        if not cache_has_question(payload, qid) or not cache_has_question(payload, qid2):
            errors.append("pre-submit exam_answers missing Q1/Q2")
        if answers_ttl <= 0:
            errors.append(f"pre-submit exam_answers ttl={answers_ttl}")
    session_raw = rds.get(f"exam_session:{session_id}")
    session_ttl = int(rds.ttl(f"exam_session:{session_id}"))
    session_payload = parse_json(session_raw)
    if session_payload is None:
        errors.append("pre-submit exam_session missing/invalid json")
    elif session_ttl <= 0:
        errors.append(f"pre-submit exam_session ttl={session_ttl}")
    members = {str(item) for item in rds.smembers(f"exam_answered_questions:{session_id}")}
    if str(qid) not in members or str(qid2) not in members:
        errors.append("pre-submit exam_answered_questions missing Q1/Q2")
    aq_ttl = int(rds.ttl(f"exam_answered_questions:{session_id}"))
    if aq_ttl <= 0:
        errors.append(f"pre-submit exam_answered_questions ttl={aq_ttl}")
    return errors


def redis_after(rds: redis.Redis, session_id: int) -> list[str]:
    errors: list[str] = []
    session_raw = rds.get(f"exam_session:{session_id}")
    session_ttl = int(rds.ttl(f"exam_session:{session_id}"))
    payload = parse_json(session_raw)
    if payload is None:
        errors.append("post-submit exam_session missing/invalid json")
        return errors
    if str(payload.get("status") or "").lower() != "submitted":
        errors.append(f"post-submit exam_session status={payload.get('status')}")
    if "end_time" not in payload:
        errors.append("post-submit exam_session missing end_time")
    if session_ttl <= 0:
        errors.append(f"post-submit exam_session ttl={session_ttl}")
    answers_raw = rds.get(f"exam_answers:{session_id}")
    if answers_raw is not None:
        if parse_json(answers_raw) is None:
            errors.append("post-submit exam_answers invalid json")
        answers_ttl = int(rds.ttl(f"exam_answers:{session_id}"))
        if answers_ttl <= 0:
            errors.append(f"post-submit exam_answers ttl={answers_ttl}")
    return errors


def one_lifecycle(
    token: str,
    exam_token: str,
    exam_id: int,
    qid: int,
    oid: int,
    oid_wrong: int,
    qid2: int,
    oid2: int,
) -> dict[str, Any]:
    errors: list[str] = []
    service_ms = 0.0
    client = httpx.Client(timeout=30.0)
    rds = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    def timed_get(path: str) -> httpx.Response:
        nonlocal service_ms
        t0 = time.perf_counter()
        response = client.get(f"{BASE}{path}", headers=hdr(token))
        service_ms += (time.perf_counter() - t0) * 1000
        return response

    def post_retry(path: str, body: dict[str, Any]) -> httpx.Response:
        nonlocal service_ms
        last = httpx.Response(599)
        for attempt in range(10):
            pace_post()
            t0 = time.perf_counter()
            last = client.post(f"{BASE}{path}", headers=hdr(token), json=body)
            service_ms += (time.perf_counter() - t0) * 1000
            if last.status_code != 429:
                return last
            note_429()
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

    wall0 = time.perf_counter()
    join = post_retry("/api/exams/join", {"token": exam_token})
    if join.status_code != 200:
        return {
            "ok": False,
            "errors": [f"join {join.status_code}"],
            "service_ms": round(service_ms, 3),
            "wall_ms": round((time.perf_counter() - wall0) * 1000, 3),
            "session_id": 0,
        }
    start = post_retry(f"/api/exams/{exam_id}/start", {})
    if start.status_code != 200:
        return {
            "ok": False,
            "errors": [f"start {start.status_code} {start.text[:120]}"],
            "service_ms": round(service_ms, 3),
            "wall_ms": round((time.perf_counter() - wall0) * 1000, 3),
            "session_id": 0,
        }
    session_id = int(start.json()["session_id"])
    ans = post_retry(
        "/api/exams/submit-answer",
        {"session_id": session_id, "question_id": qid, "selected_option_id": oid_wrong},
    )
    if ans.status_code != 200:
        errors.append(f"answer {ans.status_code}")
    auto = post_retry(
        "/api/exams/auto-save",
        {
            "session_id": session_id,
            "answers": {str(qid): oid_wrong},
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
                {"question_id": qid, "selected_option_id": oid_wrong},
                {"question_id": qid2, "selected_option_id": oid2},
            ],
        },
    )
    if batch.status_code != 200:
        errors.append(f"batch {batch.status_code}")
    errors.extend(redis_before(rds, session_id, qid, qid2))
    resume = timed_get(f"/api/exams/session/{session_id}/resume")
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
    errors.extend(redis_after(rds, session_id))
    score = None
    try:
        score = sub.json().get("score")
    except Exception:
        pass
    replicas = {
        "join": join.headers.get("x-siab-replica", ""),
        "start": start.headers.get("x-siab-replica", ""),
        "answer": ans.headers.get("x-siab-replica", ""),
        "autosave": auto.headers.get("x-siab-replica", ""),
        "answer2": ans2.headers.get("x-siab-replica", ""),
        "batch": batch.headers.get("x-siab-replica", ""),
        "update": upd.headers.get("x-siab-replica", ""),
        "submit": sub.headers.get("x-siab-replica", ""),
    }
    if any(not is_go(value) for value in replicas.values()):
        errors.append(f"non-go replica {replicas}")
    return {
        "ok": not errors,
        "errors": errors,
        "service_ms": round(service_ms, 3),
        "wall_ms": round((time.perf_counter() - wall0) * 1000, 3),
        "session_id": session_id,
        "score": score,
        "replicas": replicas,
        "join_replica": replicas["join"],
        "start_replica": replicas["start"],
        "answer_replica": replicas["answer"],
        "autosave_replica": replicas["autosave"],
        "answer2_replica": replicas["answer2"],
        "batch_replica": replicas["batch"],
        "update_replica": replicas["update"],
        "submit_replica": replicas["submit"],
    }


async def assert_sessions(
    conn: asyncpg.Connection,
    session_ids: list[int],
    qid: int,
    qid2: int,
    oid: int,
    oid2: int,
    exam_id: int,
) -> dict[str, Any]:
    out = {
        "errors": [],
        "lost": 0,
        "dups": 0,
        "live": 0,
        "wrong_scores": 0,
        "missing_audit": 0,
        "stale_update": 0,
    }
    if not session_ids:
        out["errors"].append("no sessions")
        return out
    rows = await conn.fetch(
        "SELECT id, status, score FROM exam_sessions WHERE id = ANY($1::int[])",
        session_ids,
    )
    by_id = {int(r["id"]): r for r in rows}
    for sid in session_ids:
        row = by_id.get(sid)
        if row is None:
            out["errors"].append(f"missing session {sid}")
            continue
        if row["status"] != "submitted":
            out["errors"].append(f"status {sid}={row['status']}")
        score = float(row["score"] or -1)
        if abs(score - 100.0) > 0.01:
            out["wrong_scores"] += 1
    answers = await conn.fetch(
        """
        SELECT session_id, question_id, selected_option_id, count(*) AS n
          FROM answers WHERE session_id = ANY($1::int[])
         GROUP BY session_id, question_id, selected_option_id
        """,
        session_ids,
    )
    seen: dict[int, dict[int, int]] = {}
    pair_counts: dict[tuple[int, int], int] = {}
    for row in answers:
        sid = int(row["session_id"])
        q = int(row["question_id"])
        opt = int(row["selected_option_id"] or 0)
        n = int(row["n"])
        pair_counts[(sid, q)] = pair_counts.get((sid, q), 0) + n
        seen.setdefault(sid, {})[q] = opt
    out["dups"] = sum(1 for count in pair_counts.values() if count > 1)
    for sid in session_ids:
        got = seen.get(sid, {})
        if qid not in got or qid2 not in got:
            out["lost"] += 1
            continue
        if got[qid] != oid or got[qid2] != oid2:
            out["stale_update"] += 1
    out["live"] = int(
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
    for sid in session_ids:
        got = logmap.get(sid, {})
        if got.get("SESSION_START", 0) < 1 or got.get("EXAM_SUBMITTED", 0) < 1 or got.get("SCORE_BREAKDOWN", 0) < 1:
            out["missing_audit"] += 1
    if out["wrong_scores"]:
        out["errors"].append(f"wrong scores={out['wrong_scores']}")
    if out["dups"]:
        out["errors"].append(f"duplicate answers={out['dups']}")
    if out["lost"]:
        out["errors"].append(f"lost answers sessions={out['lost']}")
    if out["stale_update"]:
        out["errors"].append(f"stale update sessions={out['stale_update']}")
    if out["live"]:
        out["errors"].append(f"duplicate live sessions={out['live']}")
    if out["missing_audit"]:
        out["errors"].append(f"missing audit logs sessions={out['missing_audit']}")
    return out


async def leftover_count(conn: asyncpg.Connection) -> int:
    users = int(await conn.fetchval("SELECT count(*) FROM users WHERE username LIKE $1", f"{PREFIX}_%") or 0)
    exams = int(await conn.fetchval("SELECT count(*) FROM exams WHERE title LIKE $1", f"{PREFIX}_%") or 0)
    return users + exams


async def amain() -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL", "")
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    mixed = int(os.getenv("HOTPATH_MIXED", "0"))
    if not database_url or not jwt_secret:
        raise SystemExit("DATABASE_URL and JWT_SECRET_KEY are required")
    rds = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    conn = await asyncpg.connect(postgres_dsn(database_url), statement_cache_size=0)
    report: dict[str, Any] = {"errors": [], "redis": "PASS", "429": 0}
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
        oid_wrong = int(
            await conn.fetchval(
                "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'C',false,1) RETURNING id",
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
        args = (ACCESS, exam_id, qid, oid, oid_wrong, qid2, oid2)
        if mixed <= 0:
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
            life = one_lifecycle(mint(uid, f"{PREFIX}_s", jwt_secret), *args)
            report["lifecycle"] = life
            if not life["ok"]:
                report["errors"].extend(life["errors"])
            session_id = int(life.get("session_id") or 0)
            db = await assert_sessions(conn, [session_id] if session_id else [], qid, qid2, oid, oid2, exam_id)
            report["lifecycle_db"] = "PASS" if not db["errors"] else db
            report["errors"].extend(db["errors"])
            if any("exam_answers" in err or "exam_session" in err or "exam_answered" in err for err in life["errors"]):
                report["redis"] = "FAIL"
        else:
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
            wall0 = time.time()
            workers = max(1, min(4, mixed))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                mixed_rows = list(pool.map(lambda item: one_lifecycle(item, *args), tokens))
            wall = max(0.001, time.time() - wall0)
            service = sorted(float(item["service_ms"]) for item in mixed_rows if item.get("service_ms") is not None)
            success = sum(1 for item in mixed_rows if item["ok"])
            mixed_sids = [int(item["session_id"]) for item in mixed_rows if item.get("session_id")]
            db = await assert_sessions(conn, mixed_sids, qid, qid2, oid, oid2, exam_id)
            redis_fail = sum(
                1
                for item in mixed_rows
                if any("exam_answers" in err or "exam_session" in err or "exam_answered" in err for err in item["errors"])
            )
            if redis_fail:
                report["redis"] = "FAIL"
            report["mixed"] = {
                "n": mixed,
                "success": success,
                "correctness": round(100.0 * success / mixed, 2) if mixed else 0,
                "p50": pct(service, 50),
                "p95": pct(service, 95),
                "p99": pct(service, 99),
                "max": round(service[-1], 3) if service else 0,
                "wall_s": round(wall, 3),
                "errors": [item["errors"] for item in mixed_rows if not item["ok"]][:5],
                "db": "PASS" if not db["errors"] else db,
                "lost": db["lost"],
                "dups": db["dups"],
                "live": db["live"],
                "wrong_scores": db["wrong_scores"],
                "missing_audit": db["missing_audit"],
            }
            if success != mixed:
                report["errors"].append(f"mixed {success}/{mixed}")
            report["errors"].extend(db["errors"])
        origin = httpx.get("http://nginx/health", timeout=5).status_code
        report["origin"] = origin
        await cleanup(conn, rds)
        leftover = await leftover_count(conn)
        report["cleanup"] = "PASS" if leftover == 0 else "FAIL"
        if leftover:
            report["errors"].append(f"leftovers={leftover}")
    finally:
        await conn.close()
    report["429"] = _429_count
    report["verdict"] = "PASS" if not report["errors"] else "FAIL"
    print(json.dumps(report, default=str))
    return report


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(amain()).get("verdict") == "PASS" else 1)
