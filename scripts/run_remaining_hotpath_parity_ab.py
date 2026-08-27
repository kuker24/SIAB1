#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import jwt
import redis as redislib

ROOT = Path(__file__).resolve().parents[1]
PYTHON = "/tmp/opencode/siab1-venv/bin/python"
GO = "/tmp/opencode/go/bin/go"
PG = "postgresql://fahmiagent@127.0.0.1:55432/postgres"
REDIS_URL = "redis://127.0.0.1:56379/0"
JWT_SECRET = "remain-parity-jwt-key-32-bytes-bb"
SECRET_KEY = "remain-parity-secret-key-32-bytes-aa"
PREFIX = "GOREM"
CLASS_NAME = "XII-REM"
FA_PORT = 18300
GO_PORT = 18301
WORKDIR = Path("/tmp/opencode/siab1-remain")
SEB_KEY = "rem-seb"
SEB_HASH = hashlib.sha256(SEB_KEY.encode()).hexdigest()


def mint(user_id: int, username: str) -> str:
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
        JWT_SECRET,
        algorithm="HS256",
    )


def headers(token: str | None, seb: bool = False) -> dict[str, str]:
    out = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SEB/3.6 (Safe Exam Browser)" if seb else "Mozilla/5.0",
    }
    if seb:
        out["X-SafeExamBrowser-ConfigKeyHash"] = SEB_HASH
    if token:
        out["Authorization"] = f"Bearer {token}"
    return out


def wait_http(url: str, timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=1.0).status_code == 200:
                return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"timeout {url}")


def env_for(runtime: str) -> dict[str, str]:
    env = os.environ.copy()
    db = (
        PG.replace("postgresql://", "postgresql+asyncpg://", 1)
        if runtime == "fastapi"
        else PG + "?pool_max_conns=4&default_query_exec_mode=simple_protocol&statement_cache_capacity=0"
    )
    env.update(
        {
            "APP_ENV": "development",
            "DEBUG": "false",
            "DATABASE_URL": db,
            "REDIS_URL": REDIS_URL,
            "SECRET_KEY": SECRET_KEY,
            "JWT_SECRET_KEY": JWT_SECRET,
            "DISABLE_RATE_LIMIT": "true",
            "ENFORCE_SXB": "false",
            "EXAM_PEAK_MODE": "true",
            "ANSWER_WRITE_MODE": "direct",
            "TELEGRAM_ALERTING_ENABLED": "false",
            "TELEGRAM_ENABLED": "false",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(ROOT),
            "SIAB_REPLICA": f"remain-{runtime}",
            "PYTHON_UPSTREAM": "",
            "PORT": str(GO_PORT if runtime == "go" else FA_PORT),
        }
    )
    return env


async def cleanup(conn: asyncpg.Connection) -> None:
    user_ids = [int(r["id"]) for r in await conn.fetch("SELECT id FROM users WHERE username LIKE $1", f"{PREFIX}_%")]
    exam_ids = [int(r["id"]) for r in await conn.fetch("SELECT id FROM exams WHERE title LIKE $1", f"{PREFIX}_%")]
    sids: list[int] = []
    if user_ids or exam_ids:
        sessions = await conn.fetch(
            """
            SELECT id FROM exam_sessions
             WHERE ($1::int[] = '{}'::int[] OR user_id = ANY($1::int[]))
                OR ($2::int[] = '{}'::int[] OR exam_id = ANY($2::int[]))
            """,
            user_ids or [],
            exam_ids or [],
        )
        sids = [int(r["id"]) for r in sessions]
        if sids:
            await conn.execute("DELETE FROM answers WHERE session_id = ANY($1::int[])", sids)
            await conn.execute("DELETE FROM exam_logs WHERE session_id = ANY($1::int[])", sids)
            await conn.execute("DELETE FROM exam_sessions WHERE id = ANY($1::int[])", sids)
    for eid in exam_ids:
        await conn.execute(
            "DELETE FROM question_options WHERE question_id IN (SELECT id FROM questions WHERE exam_id=$1)", eid
        )
        await conn.execute("DELETE FROM questions WHERE exam_id=$1", eid)
        await conn.execute("DELETE FROM exams WHERE id=$1", eid)
    if user_ids:
        await conn.execute("DELETE FROM users WHERE id = ANY($1::int[])", user_ids)


async def insert_user(conn: asyncpg.Connection, username: str) -> int:
    return int(
        await conn.fetchval(
            """
            INSERT INTO users (username, password_hash, full_name, role, student_class, is_active)
            VALUES ($1, 'x', $1, 'student', $2, true) RETURNING id
            """,
            username,
            CLASS_NAME,
        )
    )


def post(base: str, path: str, token: str | None, body: Any, raw: bytes | None = None, seb: bool = False) -> httpx.Response:
    if raw is not None:
        return httpx.post(f"{base}{path}", headers=headers(token, seb=seb), content=raw, timeout=30.0)
    return httpx.post(f"{base}{path}", headers=headers(token, seb=seb), json=body, timeout=180.0)


def compare_status(name: str, fa: httpx.Response, go: httpx.Response, expect: int) -> dict[str, Any]:
    try:
        fa_json = fa.json()
    except Exception:
        fa_json = fa.text[:200]
    try:
        go_json = go.json()
    except Exception:
        go_json = go.text[:200]
    ok = fa.status_code == go.status_code == expect
    if expect in {401, 403, 404, 400} and isinstance(fa_json, dict) and isinstance(go_json, dict):
        ok = ok and fa_json.get("detail") == go_json.get("detail")
    elif expect == 200 and isinstance(fa_json, dict) and isinstance(go_json, dict):
        skip = {"timestamp", "queue_id", "session_id"}

        def canon(value: Any) -> Any:
            if isinstance(value, bool) or value is None:
                return value
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, dict):
                return {k: canon(v) for k, v in value.items() if k not in skip}
            return value

        ok = ok and canon(fa_json) == canon(go_json)
    elif expect == 422:
        ok = fa.status_code == go.status_code == 422
    return {"name": name, "ok": ok, "fastapi": {"status": fa.status_code, "body": fa_json}, "go": {"status": go.status_code, "body": go_json}}


def burst(base: str, path: str, jobs: list[tuple[str, dict[str, Any]]], seb: bool = False) -> dict[str, Any]:
    import threading

    barrier = threading.Barrier(len(jobs))

    def one(job: tuple[str, dict[str, Any]]) -> tuple[int, float]:
        barrier.wait()
        started = time.perf_counter()
        try:
            response = post(base, path, job[0], job[1], seb=seb)
            return response.status_code, (time.perf_counter() - started) * 1000
        except Exception:
            return 0, (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        rows = list(pool.map(one, jobs))
    elapsed = sorted(ms for _, ms in rows)

    def pct(p: float) -> float:
        if not elapsed:
            return 0.0
        idx = min(len(elapsed) - 1, max(0, int(round((p / 100) * (len(elapsed) - 1)))))
        return round(elapsed[idx], 2)

    return {
        "n": len(jobs),
        "success": sum(code == 200 for code, _ in rows),
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "throughput": round(len(jobs) / (max(elapsed) / 1000) if elapsed else 0, 2),
    }


def rss_kb(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except Exception:
        return 0
    return 0


def cpu_seconds(pid: int) -> float:
    try:
        parts = Path(f"/proc/{pid}/stat").read_text().split()
        return (int(parts[13]) + int(parts[14])) / os.sysconf("SC_CLK_TCK")
    except Exception:
        return 0.0


def main() -> int:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    fa_log = open(WORKDIR / "fastapi.log", "w")
    go_log = open(WORKDIR / "go.log", "w")
    go_bin = WORKDIR / "go-server"
    subprocess.check_call(
        [GO, "build", "-o", str(go_bin), "./cmd/server"],
        cwd=str(ROOT / "go"),
        env={**os.environ, "CGO_ENABLED": "0", "PATH": os.environ.get("PATH", "")},
    )
    fa_proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(FA_PORT), "--log-level", "warning"],
        cwd=str(ROOT),
        env=env_for("fastapi"),
        stdout=fa_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    go_proc = subprocess.Popen(
        [str(go_bin)],
        cwd=str(ROOT),
        env=env_for("go"),
        stdout=go_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    report: dict[str, Any] = {"autosave": {"cases": []}, "batch": {"cases": []}, "submit": {"cases": []}, "ab": []}
    rds = redislib.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        wait_http(f"http://127.0.0.1:{FA_PORT}/health")
        wait_http(f"http://127.0.0.1:{GO_PORT}/health")
        fa_base = f"http://127.0.0.1:{FA_PORT}"
        go_base = f"http://127.0.0.1:{GO_PORT}"

        async def seed() -> dict[str, Any]:
            conn = await asyncpg.connect(PG, statement_cache_size=0)
            try:
                await cleanup(conn)
                await conn.execute("UPDATE system_settings SET allow_browser_testing = true")
                await conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS answers_session_question_uidx ON answers (session_id, question_id)"
                )
                teacher = int(
                    await conn.fetchval(
                        "INSERT INTO users (username, password_hash, full_name, role, is_active) VALUES ($1,'x',$1,'teacher',true) RETURNING id",
                        f"{PREFIX}_teacher",
                    )
                )
                now = datetime.now(timezone.utc)
                exam_id = int(
                    await conn.fetchval(
                        """
                        INSERT INTO exams (
                            title, creator_id, duration_minutes, start_time, end_time, max_attempts,
                            shuffle_questions, shuffle_options, show_results, passing_score, seb_config_key,
                            is_published, subject, exam_type, show_teacher_name, access_token,
                            is_deleted, has_ever_had_results
                        ) VALUES (
                            $1,$2,90,$3,$4,3,false,false,true,70,$5,true,'MTK','UTS',true,'REM001',false,false
                        ) RETURNING id
                        """,
                        f"{PREFIX}_exam",
                        teacher,
                        now - timedelta(hours=1),
                        now + timedelta(hours=3),
                        SEB_KEY,
                    )
                )
                q_mc = int(
                    await conn.fetchval(
                        "INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings) VALUES ($1,'MC','multiple_choice','easy',1,0,'{}'::jsonb) RETURNING id",
                        exam_id,
                    )
                )
                opt_ok = int(
                    await conn.fetchval(
                        "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'A',true,0) RETURNING id",
                        q_mc,
                    )
                )
                q_cx = int(
                    await conn.fetchval(
                        "INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings) VALUES ($1,'CX','multiple_choice_complex','easy',2,1,'{\"pgk_type\":\"checkbox\"}'::jsonb) RETURNING id",
                        exam_id,
                    )
                )
                cx1 = int(
                    await conn.fetchval(
                        "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'C1',true,0) RETURNING id",
                        q_cx,
                    )
                )
                q_table = int(
                    await conn.fetchval(
                        """
                        INSERT INTO questions (exam_id, question_text, question_type, pgk_type, difficulty_level, points, order_index, question_settings)
                        VALUES ($1,'TB','multiple_choice_complex','table_validation','easy',2,2,'{"pgk_type":"table_validation","statement_answers":[true,false]}'::jsonb)
                        RETURNING id
                        """,
                        exam_id,
                    )
                )
                q_essay = int(
                    await conn.fetchval(
                        "INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings) VALUES ($1,'ES','essay','easy',5,3,'{}'::jsonb) RETURNING id",
                        exam_id,
                    )
                )
                student = await insert_user(conn, f"{PREFIX}_s")
                student_fa = await insert_user(conn, f"{PREFIX}_sfa")
                student_go = await insert_user(conn, f"{PREFIX}_sgo")
                other = await insert_user(conn, f"{PREFIX}_o")
                session = int(
                    await conn.fetchval(
                        "INSERT INTO exam_sessions (user_id, exam_id, status, start_time) VALUES ($1,$2,'in_progress',$3) RETURNING id",
                        student,
                        exam_id,
                        now,
                    )
                )
                session_fa = int(
                    await conn.fetchval(
                        "INSERT INTO exam_sessions (user_id, exam_id, status, start_time) VALUES ($1,$2,'in_progress',$3) RETURNING id",
                        student_fa,
                        exam_id,
                        now,
                    )
                )
                session_go = int(
                    await conn.fetchval(
                        "INSERT INTO exam_sessions (user_id, exam_id, status, start_time) VALUES ($1,$2,'in_progress',$3) RETURNING id",
                        student_go,
                        exam_id,
                        now,
                    )
                )
                submitted = int(
                    await conn.fetchval(
                        "INSERT INTO exam_sessions (user_id, exam_id, status, start_time, end_time, score) VALUES ($1,$2,'submitted',$3,$3,80) RETURNING id",
                        student,
                        exam_id,
                        now,
                    )
                )
                paused = int(
                    await conn.fetchval(
                        "INSERT INTO exam_sessions (user_id, exam_id, status, start_time) VALUES ($1,$2,'paused',$3) RETURNING id",
                        student,
                        exam_id,
                        now,
                    )
                )
                other_session = int(
                    await conn.fetchval(
                        "INSERT INTO exam_sessions (user_id, exam_id, status, start_time) VALUES ($1,$2,'in_progress',$3) RETURNING id",
                        other,
                        exam_id,
                        now,
                    )
                )
                return {
                    "exam_id": exam_id,
                    "q_mc": q_mc,
                    "opt_ok": opt_ok,
                    "q_cx": q_cx,
                    "cx1": cx1,
                    "q_table": q_table,
                    "q_essay": q_essay,
                    "student": student,
                    "student_fa": student_fa,
                    "student_go": student_go,
                    "other": other,
                    "session": session,
                    "session_fa": session_fa,
                    "session_go": session_go,
                    "submitted": submitted,
                    "paused": paused,
                    "other_session": other_session,
                }
            finally:
                await conn.close()

        ids = asyncio.run(seed())
        tok = mint(ids["student"], f"{PREFIX}_s")
        tok_fa = mint(ids["student_fa"], f"{PREFIX}_sfa")
        tok_go = mint(ids["student_go"], f"{PREFIX}_sgo")
        other_tok = mint(ids["other"], f"{PREFIX}_o")
        ts = datetime.now(timezone.utc).isoformat()
        auto_ok = {"session_id": ids["session"], "answers": {str(ids["q_mc"]): ids["opt_ok"]}, "timestamp": ts}

        autosave_cases = [
            ("valid", tok, auto_ok, 200),
            ("repeat", tok, auto_ok, 200),
            ("invalid_session", tok, {"session_id": 999999, "answers": {"1": 1}, "timestamp": ts}, 404),
            ("ownership", other_tok, {"session_id": ids["session"], "answers": {str(ids["q_mc"]): ids["opt_ok"]}, "timestamp": ts}, 404),
            ("submitted", tok, {"session_id": ids["submitted"], "answers": {str(ids["q_mc"]): ids["opt_ok"]}, "timestamp": ts}, 404),
            ("expired", tok, {"session_id": ids["paused"], "answers": {str(ids["q_mc"]): ids["opt_ok"]}, "timestamp": ts}, 404),
            ("malformed", tok, None, 422),
            ("missing_auth", None, auto_ok, 401),
            ("seb_whitelist", tok, auto_ok, 200),
        ]
        answers_before = None
        conn_sync = None
        for name, token, body, expect in autosave_cases:
            if body is None:
                fa = post(fa_base, "/api/exams/auto-save", token, None, raw=b"{")
                go = post(go_base, "/api/exams/auto-save", token, None, raw=b"{")
            else:
                fa = post(fa_base, "/api/exams/auto-save", token, body)
                go = post(go_base, "/api/exams/auto-save", token, body)
            report["autosave"]["cases"].append(compare_status(name, fa, go, expect))
        fa_redis = json.loads(rds.get(f"exam_answers:{ids['session']}") or "null")
        go_ttl = rds.ttl(f"exam_answers:{ids['session']}")
        report["autosave"]["redis"] = {"payload": fa_redis, "ttl": go_ttl, "ok": fa_redis is not None and go_ttl > 0}

        async def count_answers() -> int:
            conn = await asyncpg.connect(PG, statement_cache_size=0)
            try:
                return int(await conn.fetchval("SELECT count(*) FROM answers WHERE session_id=$1", ids["session"]) or 0)
            finally:
                await conn.close()

        answers_before = asyncio.run(count_answers())
        report["autosave"]["db_unchanged"] = {"count": answers_before, "ok": answers_before == 0}

        def batch_body_for(session_id: int) -> dict[str, Any]:
            return {
                "session_id": session_id,
                "answers": [
                    {"question_id": ids["q_mc"], "selected_option_id": ids["opt_ok"]},
                    {"question_id": ids["q_cx"], "selected_option_ids": [ids["cx1"]]},
                ],
            }

        write_batch = [
            ("single", {"answers": [{"question_id": ids["q_mc"], "selected_option_id": ids["opt_ok"]}]}),
            ("multiple", {"answers": batch_body_for(0)["answers"]}),
            ("essay", {"answers": [{"question_id": ids["q_essay"], "answer_text": "esai"}]}),
            ("table", {"answers": [{"question_id": ids["q_table"], "statement_answers": {"0": True, "1": False}}]}),
            ("duplicate_items", {"answers": [{"question_id": ids["q_mc"], "selected_option_id": ids["opt_ok"]}, {"question_id": ids["q_mc"], "selected_option_id": ids["opt_ok"]}]}),
        ]
        for name, payload in write_batch:
            fa_body = {"session_id": ids["session_fa"], **payload}
            go_body = {"session_id": ids["session_go"], **payload}
            fa_resp = post(fa_base, "/api/exams/auto-save-batch", tok_fa, fa_body)
            go_resp = post(go_base, "/api/exams/auto-save-batch", tok_go, go_body)
            report["batch"]["cases"].append(compare_status(name, fa_resp, go_resp, 200))
        fa_repeat = post(fa_base, "/api/exams/auto-save-batch", tok_fa, {"session_id": ids["session_fa"], **write_batch[1][1]})
        go_repeat = post(go_base, "/api/exams/auto-save-batch", tok_go, {"session_id": ids["session_go"], **write_batch[1][1]})
        report["batch"]["cases"].append(compare_status("repeat", fa_repeat, go_repeat, 200))
        error_batch = [
            ("invalid_question", tok, {"session_id": ids["session"], "answers": [{"question_id": 999999, "selected_option_id": 1}]}, 200),
            ("ownership", other_tok, {"session_id": ids["session"], "answers": [{"question_id": ids["q_mc"], "selected_option_id": ids["opt_ok"]}]}, 404),
            ("submitted", tok, {"session_id": ids["submitted"], "answers": [{"question_id": ids["q_mc"], "selected_option_id": ids["opt_ok"]}]}, 404),
            ("malformed", tok, None, 422),
            ("missing_auth", None, batch_body_for(ids["session"]), 401),
        ]
        for name, token, body, expect in error_batch:
            if body is None:
                fa_resp = post(fa_base, "/api/exams/auto-save-batch", token, None, raw=b"{")
                go_resp = post(go_base, "/api/exams/auto-save-batch", token, None, raw=b"{")
            else:
                fa_resp = post(fa_base, "/api/exams/auto-save-batch", token, body)
                go_resp = post(go_base, "/api/exams/auto-save-batch", token, body)
            report["batch"]["cases"].append(compare_status(name, fa_resp, go_resp, expect))

        def conc_batch(base: str) -> list[int]:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futs = [
                    pool.submit(post, base, "/api/exams/auto-save-batch", tok, {"session_id": ids["session"], "answers": [{"question_id": ids["q_mc"], "selected_option_id": ids["opt_ok"]}]})
                    for _ in range(8)
                ]
                return [fut.result().status_code for fut in futs]

        fa_c = conc_batch(fa_base)
        go_c = conc_batch(go_base)
        report["batch"]["cases"].append(
            {"name": "concurrent", "ok": all(code == 200 for code in fa_c + go_c), "fastapi": fa_c, "go": go_c}
        )
        after = asyncio.run(count_answers())
        report["batch"]["db"] = {"answers": after, "ok": after >= 1, "lost": after == 0}

        fa_seb = post(fa_base, "/api/exams/submit", tok_fa, {"session_id": ids["session_fa"]}, seb=False)
        go_seb = post(go_base, "/api/exams/submit", tok_go, {"session_id": ids["session_go"]}, seb=False)
        report["submit"]["cases"].append({
            "name": "seb_reject",
            "ok": fa_seb.status_code == go_seb.status_code == 403,
            "fastapi": {"status": fa_seb.status_code},
            "go": {"status": go_seb.status_code},
        })
        fa_normal = post(fa_base, "/api/exams/submit", tok_fa, {"session_id": ids["session_fa"]}, seb=True)
        go_normal = post(go_base, "/api/exams/submit", tok_go, {"session_id": ids["session_go"]}, seb=True)
        report["submit"]["cases"].append(compare_status("normal", fa_normal, go_normal, 200))
        fa_rep = post(fa_base, "/api/exams/submit", tok_fa, {"session_id": ids["session_fa"]}, seb=True)
        go_rep = post(go_base, "/api/exams/submit", tok_go, {"session_id": ids["session_go"]}, seb=True)
        report["submit"]["cases"].append(compare_status("repeat", fa_rep, go_rep, 200))
        submit_cases = [
            ("paused", tok, {"session_id": ids["paused"]}, 400, True),
            ("ownership", other_tok, {"session_id": ids["session_fa"]}, 404, True),
            ("invalid_status_already", tok, {"session_id": ids["submitted"]}, 200, True),
            ("missing_auth", None, {"session_id": ids["session"]}, 401, False),
            ("malformed", tok, None, 422, False),
        ]
        for name, token, body, expect, seb in submit_cases:
            if body is None:
                fa_resp = post(fa_base, "/api/exams/submit", token, None, raw=b"{", seb=seb)
                go_resp = post(go_base, "/api/exams/submit", token, None, raw=b"{", seb=seb)
            else:
                fa_resp = post(fa_base, "/api/exams/submit", token, body, seb=seb)
                go_resp = post(go_base, "/api/exams/submit", token, body, seb=seb)
            report["submit"]["cases"].append(compare_status(name, fa_resp, go_resp, expect))

        async def db_submit_state() -> dict[str, Any]:
            conn = await asyncpg.connect(PG, statement_cache_size=0)
            try:
                row = await conn.fetchrow("SELECT status, score FROM exam_sessions WHERE id=$1", ids["session_fa"])
                logs = int(await conn.fetchval("SELECT count(*) FROM exam_logs WHERE session_id=$1 AND event_type=ANY($2::text[])", ids["session_fa"], ["EXAM_SUBMITTED", "SCORE_BREAKDOWN"]) or 0)
                return {"status": row["status"] if row else None, "score": float(row["score"]) if row and row["score"] is not None else None, "logs": logs}
            finally:
                await conn.close()

        report["submit"]["db"] = asyncio.run(db_submit_state())
        report["submit"]["db"]["ok"] = report["submit"]["db"]["status"] == "submitted" and report["submit"]["db"]["logs"] >= 2

        def failed(section: str) -> list[dict[str, Any]]:
            return [item for item in report[section]["cases"] if not item.get("ok")]

        report["autosave"]["parity_pass"] = not failed("autosave") and report["autosave"]["redis"]["ok"] and report["autosave"]["db_unchanged"]["ok"]
        report["batch"]["parity_pass"] = not failed("batch") and report["batch"]["db"]["ok"]
        report["submit"]["parity_pass"] = not failed("submit") and report["submit"]["db"]["ok"]
        if not (report["autosave"]["parity_pass"] and report["batch"]["parity_pass"] and report["submit"]["parity_pass"]):
            report["failed"] = {"autosave": failed("autosave"), "batch": failed("batch"), "submit": failed("submit")}
            print(json.dumps(report, default=str))
            return 1

        async def seed_jobs(n: int, runtime: str, kind: str) -> list[tuple[str, dict[str, Any]]]:
            conn = await asyncpg.connect(PG, statement_cache_size=0)
            try:
                now = datetime.now(timezone.utc)
                jobs: list[tuple[str, dict[str, Any]]] = []
                for i in range(n):
                    uid = await insert_user(conn, f"{PREFIX}_{kind}{n}_{runtime}_{i}")
                    sid = int(
                        await conn.fetchval(
                            "INSERT INTO exam_sessions (user_id, exam_id, status, start_time) VALUES ($1,$2,'in_progress',$3) RETURNING id",
                            uid,
                            ids["exam_id"],
                            now,
                        )
                    )
                    token = mint(uid, f"{PREFIX}_{kind}{n}_{runtime}_{i}")
                    if kind == "autosave":
                        jobs.append((token, {"session_id": sid, "answers": {str(ids["q_mc"]): ids["opt_ok"]}, "timestamp": now.isoformat()}))
                    elif kind == "batch":
                        jobs.append((token, {"session_id": sid, "answers": [{"question_id": ids["q_mc"], "selected_option_id": ids["opt_ok"]}]}))
                    else:
                        await conn.execute(
                            "INSERT INTO answers (session_id, question_id, selected_option_id, answered_at) VALUES ($1,$2,$3,$4)",
                            sid,
                            ids["q_mc"],
                            ids["opt_ok"],
                            now,
                        )
                        jobs.append((token, {"session_id": sid}))
                return jobs
            finally:
                await conn.close()

        paths = {"autosave": "/api/exams/auto-save", "batch": "/api/exams/auto-save-batch", "submit": "/api/exams/submit"}
        for kind in ("autosave", "batch", "submit"):
            for n in (50, 200, 620):
                for runtime, base, proc in (("fastapi", fa_base, fa_proc), ("go", go_base, go_proc)):
                    jobs = asyncio.run(seed_jobs(n, runtime, kind))
                    cpu0 = cpu_seconds(proc.pid)
                    rss0 = rss_kb(proc.pid)
                    result = burst(base, paths[kind], jobs, seb=(kind == "submit"))
                    result.update(
                        {
                            "kind": kind,
                            "runtime": runtime,
                            "cpu_per_1000": round((cpu_seconds(proc.pid) - cpu0) / max(n, 1) * 1000, 4),
                            "peak_rss_kb": max(rss0, rss_kb(proc.pid)),
                        }
                    )
                    report["ab"].append(result)
                    if result["success"] != n:
                        print(json.dumps(report, default=str))
                        return 1
        print(json.dumps(report, default=str))
        return 0
    finally:
        for proc in (fa_proc, go_proc):
            try:
                os.killpg(proc.pid, 15)
            except Exception:
                proc.terminate()
        fa_log.close()
        go_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
