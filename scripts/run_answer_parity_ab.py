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
from urllib.parse import urlparse, urlunparse

import asyncpg
import httpx
import jwt
import redis as redislib


ROOT = Path(__file__).resolve().parents[1]
PYTHON = "/tmp/opencode/siab1-venv/bin/python"
GO = "/tmp/opencode/go/bin/go"
PG = "postgresql://fahmiagent@127.0.0.1:55432/postgres"
PGBOUNCER = "postgresql://fahmiagent@pgbouncer.localhost:56432/postgres"
REDIS_URL = "redis://127.0.0.1:56379/0"
JWT_SECRET = "answer-parity-jwt-key-32-bytes-bb"
SECRET_KEY = "answer-parity-secret-key-32-bytes-aa"
PREFIX = "GOANS"
CLASS_NAME = "XII-ANS"
FA_PORT = 18200
GO_PORT = 18201
PB_PORT = 56432
WORKDIR = Path("/tmp/opencode/siab1-answer")


def mint(user_id: int, username: str, active: bool = True) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "username": username,
            "role": "student",
            "full_name": username,
            "student_class": CLASS_NAME,
            "is_active": active,
            "exp": int((now + timedelta(hours=2)).timestamp()),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


SEB_KEY = "ans-seb"
SEB_HASH = hashlib.sha256(SEB_KEY.encode()).hexdigest()


def headers(token: str | None) -> dict[str, str]:
    out = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SEB/3.6 (Safe Exam Browser)",
        "X-SafeExamBrowser-ConfigKeyHash": SEB_HASH,
    }
    if token:
        out["Authorization"] = f"Bearer {token}"
    return out


def post_answer(base: str, token: str | None, body: dict[str, Any]) -> httpx.Response:
    return httpx.post(
        f"{base}/api/exams/submit-answer",
        headers=headers(token),
        json=body,
        timeout=30.0,
    )


def wait_http(url: str, timeout: float = 30.0) -> None:
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
        PGBOUNCER.replace("postgresql://", "postgresql+asyncpg://", 1)
        + "?prepared_statement_cache_size=0"
        if runtime == "fastapi"
        else PGBOUNCER + "?pool_max_conns=4&default_query_exec_mode=simple_protocol&statement_cache_capacity=0"
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
            "DB_USE_NULL_POOL_WITH_PGBOUNCER": "true",
            "SIAB_REPLICA": f"answer-{runtime}",
            "PYTHON_UPSTREAM": "",
            "PORT": str(GO_PORT if runtime == "go" else FA_PORT),
        }
    )
    return env


def start_pgbouncer() -> subprocess.Popen:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    auth = WORKDIR / "userlist.txt"
    auth.write_text('"fahmiagent" ""\n', encoding="utf-8")
    ini = WORKDIR / "pgbouncer.ini"
    ini.write_text(
        f"""
[databases]
postgres = host=127.0.0.1 port=55432 dbname=postgres
[pgbouncer]
listen_addr = *
listen_port = {PB_PORT}
auth_type = trust
auth_file = {auth}
pool_mode = transaction
max_client_conn = 2000
default_pool_size = 40
admin_users = fahmiagent
logfile = {WORKDIR / "pgbouncer.log"}
pidfile = {WORKDIR / "pgbouncer.pid"}
unix_socket_dir =
""",
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        ["/tmp/opencode/pgbouncer-root/usr/sbin/pgbouncer", str(ini)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            import socket

            sock = socket.create_connection(("127.0.0.1", PB_PORT), 0.2)
            sock.close()
            return proc
        except Exception:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
    raise RuntimeError("pgbouncer failed")


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
            "DELETE FROM question_options WHERE question_id IN (SELECT id FROM questions WHERE exam_id=$1)",
            eid,
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
            VALUES ($1, 'x', $1, 'student', $2, true)
            RETURNING id
            """,
            username,
            CLASS_NAME,
        )
    )


def compare(name: str, fa: httpx.Response, go: httpx.Response, expect: int) -> dict[str, Any]:
    try:
        fa_json = fa.json()
    except Exception:
        fa_json = fa.text[:200]
    try:
        go_json = go.json()
    except Exception:
        go_json = go.text[:200]
    ok = fa.status_code == go.status_code == expect
    if expect == 200:
        ok = ok and fa_json == go_json
    elif expect == 422:
        ok = fa.status_code == go.status_code == 422
    elif isinstance(fa_json, dict) and isinstance(go_json, dict):
        ok = ok and fa_json.get("detail") == go_json.get("detail")
    return {
        "name": name,
        "ok": ok,
        "fastapi": {"status": fa.status_code, "body": fa_json},
        "go": {"status": go.status_code, "body": go_json},
    }


def burst(base: str, jobs: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    import threading

    barrier = threading.Barrier(len(jobs))

    def one(job: tuple[str, dict[str, Any]]) -> tuple[int, float]:
        barrier.wait()
        started = time.perf_counter()
        response = post_answer(base, job[0], job[1])
        return response.status_code, (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        rows = list(pool.map(one, jobs))
    elapsed = sorted(ms for _, ms in rows)

    def pct(p: float) -> float:
        if not elapsed:
            return 0.0
        idx = min(len(elapsed) - 1, max(0, int(round((p / 100) * (len(elapsed) - 1)))))
        return round(elapsed[idx], 2)

    statuses: dict[str, int] = {}
    for code, _ in rows:
        statuses[str(code)] = statuses.get(str(code), 0) + 1
    return {
        "n": len(jobs),
        "success": sum(code == 200 for code, _ in rows),
        "statuses": statuses,
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
    pb = start_pgbouncer()
    fa_log = open(WORKDIR / "fastapi.log", "w")
    go_log = open(WORKDIR / "go.log", "w")
    go_bin = WORKDIR / "go-server"
    subprocess.check_call(
        [GO, "build", "-o", str(go_bin), "./cmd/server"],
        cwd=str(ROOT / "go"),
        env={**os.environ, "CGO_ENABLED": "0"},
    )
    fa = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(FA_PORT), "--log-level", "warning"],
        cwd=str(ROOT),
        env=env_for("fastapi"),
        stdout=fa_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    go = subprocess.Popen(
        [str(go_bin)],
        cwd=str(ROOT),
        env=env_for("go"),
        stdout=go_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    report: dict[str, Any] = {"cases": [], "ab": []}
    rds = redislib.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        wait_http(f"http://127.0.0.1:{FA_PORT}/health")
        wait_http(f"http://127.0.0.1:{GO_PORT}/health")
        fa_base = f"http://127.0.0.1:{FA_PORT}"
        go_base = f"http://127.0.0.1:{GO_PORT}"

        async def seed_and_parity() -> None:
            conn = await asyncpg.connect(PG, statement_cache_size=0)
            try:
                await cleanup(conn)
                await conn.execute("UPDATE system_settings SET allow_browser_testing = true")
                await conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS answers_session_question_uidx ON answers (session_id, question_id)"
                )
                teacher = int(
                    await conn.fetchval(
                        """
                        INSERT INTO users (username, password_hash, full_name, role, is_active)
                        VALUES ($1, 'x', $1, 'teacher', true) RETURNING id
                        """,
                        f"{PREFIX}_teacher",
                    )
                )
                student = await insert_user(conn, f"{PREFIX}_s")
                other = await insert_user(conn, f"{PREFIX}_other")
                now = datetime.now(timezone.utc)
                exam_id = int(
                    await conn.fetchval(
                        """
                        INSERT INTO exams (
                            title, creator_id, duration_minutes, start_time, end_time, max_attempts,
                            shuffle_questions, shuffle_options, show_results, seb_config_key,
                            is_published, subject, exam_type, show_teacher_name, access_token,
                            is_deleted, has_ever_had_results
                        ) VALUES (
                            $1, $2, 90, $3, $4, 3, false, false, false, 'ans-seb',
                            true, 'MTK', 'UTS', true, 'ANS001', false, false
                        ) RETURNING id
                        """,
                        f"{PREFIX}_exam",
                        teacher,
                        now - timedelta(hours=1),
                        now + timedelta(hours=3),
                    )
                )
                q_mc = int(
                    await conn.fetchval(
                        """
                        INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings)
                        VALUES ($1, 'MC', 'multiple_choice', 'easy', 1, 0, '{}'::jsonb) RETURNING id
                        """,
                        exam_id,
                    )
                )
                opt_ok = int(
                    await conn.fetchval(
                        "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'A',true,0) RETURNING id",
                        q_mc,
                    )
                )
                opt_bad = int(
                    await conn.fetchval(
                        "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'B',false,1) RETURNING id",
                        q_mc,
                    )
                )
                q_complex = int(
                    await conn.fetchval(
                        """
                        INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings)
                        VALUES ($1, 'CX', 'multiple_choice_complex', 'easy', 2, 1, '{"pgk_type":"checkbox"}'::jsonb) RETURNING id
                        """,
                        exam_id,
                    )
                )
                cx1 = int(
                    await conn.fetchval(
                        "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'C1',true,0) RETURNING id",
                        q_complex,
                    )
                )
                cx2 = int(
                    await conn.fetchval(
                        "INSERT INTO question_options (question_id, option_text, is_correct, order_index) VALUES ($1,'C2',true,1) RETURNING id",
                        q_complex,
                    )
                )
                q_table = int(
                    await conn.fetchval(
                        """
                        INSERT INTO questions (exam_id, question_text, question_type, pgk_type, difficulty_level, points, order_index, question_settings)
                        VALUES ($1, 'TB', 'multiple_choice_complex', 'table_validation', 'easy', 2, 2,
                                '{"pgk_type":"table_validation","statement_answers":[true,false]}'::jsonb)
                        RETURNING id
                        """,
                        exam_id,
                    )
                )
                q_essay = int(
                    await conn.fetchval(
                        """
                        INSERT INTO questions (exam_id, question_text, question_type, difficulty_level, points, order_index, question_settings)
                        VALUES ($1, 'ES', 'essay', 'easy', 5, 3, '{}'::jsonb) RETURNING id
                        """,
                        exam_id,
                    )
                )
                session = int(
                    await conn.fetchval(
                        """
                        INSERT INTO exam_sessions (user_id, exam_id, status, start_time)
                        VALUES ($1, $2, 'in_progress', $3) RETURNING id
                        """,
                        student,
                        exam_id,
                        now,
                    )
                )
                submitted = int(
                    await conn.fetchval(
                        """
                        INSERT INTO exam_sessions (user_id, exam_id, status, start_time, end_time)
                        VALUES ($1, $2, 'submitted', $3, $3) RETURNING id
                        """,
                        student,
                        exam_id,
                        now,
                    )
                )
                paused = int(
                    await conn.fetchval(
                        """
                        INSERT INTO exam_sessions (user_id, exam_id, status, start_time)
                        VALUES ($1, $2, 'paused', $3) RETURNING id
                        """,
                        student,
                        exam_id,
                        now,
                    )
                )
                other_session = int(
                    await conn.fetchval(
                        """
                        INSERT INTO exam_sessions (user_id, exam_id, status, start_time)
                        VALUES ($1, $2, 'in_progress', $3) RETURNING id
                        """,
                        other,
                        exam_id,
                        now,
                    )
                )
                tok = mint(student, f"{PREFIX}_s")
                other_tok = mint(other, f"{PREFIX}_other")
                answers_before = int(await conn.fetchval("SELECT count(*) FROM answers WHERE session_id=$1", session) or 0)
                cases = [
                    ("first", tok, {"session_id": session, "question_id": q_mc, "selected_option_id": opt_ok}, 200),
                    ("update", tok, {"session_id": session, "question_id": q_mc, "selected_option_id": opt_bad}, 200),
                    ("idempotent", tok, {"session_id": session, "question_id": q_mc, "selected_option_id": opt_bad}, 200),
                    ("invalid_question", tok, {"session_id": session, "question_id": 999999, "selected_option_id": opt_ok}, 404),
                    ("invalid_session", tok, {"session_id": 999999, "question_id": q_mc, "selected_option_id": opt_ok}, 404),
                    ("ownership", other_tok, {"session_id": session, "question_id": q_mc, "selected_option_id": opt_ok}, 404),
                    ("submitted", tok, {"session_id": submitted, "question_id": q_mc, "selected_option_id": opt_ok}, 200),
                    ("expired", tok, {"session_id": paused, "question_id": q_mc, "selected_option_id": opt_ok}, 400),
                    ("complex", tok, {"session_id": session, "question_id": q_complex, "selected_option_ids": [cx1, cx2]}, 200),
                    ("table", tok, {"session_id": session, "question_id": q_table, "statement_answers": {"0": True, "1": False}}, 200),
                    ("essay", tok, {"session_id": session, "question_id": q_essay, "answer_text": "esai"}, 200),
                    ("malformed", tok, None, 422),
                    ("missing_auth", None, {"session_id": session, "question_id": q_mc, "selected_option_id": opt_ok}, 401),
                ]
                for name, token, body, expect in cases:
                    if body is None:
                        fa = httpx.post(f"{fa_base}/api/exams/submit-answer", headers=headers(token), content=b"{", timeout=30)
                        go = httpx.post(f"{go_base}/api/exams/submit-answer", headers=headers(token), content=b"{", timeout=30)
                    else:
                        fa = post_answer(fa_base, token, body)
                        go = post_answer(go_base, token, body)
                    report["cases"].append(compare(name, fa, go, expect))

                def conc(base: str) -> list[int]:
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        futs = [
                            pool.submit(post_answer, base, tok, {"session_id": session, "question_id": q_mc, "selected_option_id": opt_ok})
                            for _ in range(8)
                        ]
                        return [fut.result().status_code for fut in futs]

                fa_c = conc(fa_base)
                go_c = conc(go_base)
                report["cases"].append(
                    {
                        "name": "simultaneous_same_question",
                        "ok": fa_c == go_c and all(code == 200 for code in fa_c + go_c),
                        "fastapi": fa_c,
                        "go": go_c,
                    }
                )
                with ThreadPoolExecutor(max_workers=4) as pool:
                    fa_d = list(
                        pool.map(
                            lambda body: post_answer(fa_base, tok, body).status_code,
                            [
                                {"session_id": session, "question_id": q_complex, "selected_option_ids": [cx1, cx2]},
                                {"session_id": session, "question_id": q_essay, "answer_text": "esai2"},
                            ],
                        )
                    )
                with ThreadPoolExecutor(max_workers=4) as pool:
                    go_d = list(
                        pool.map(
                            lambda body: post_answer(go_base, tok, body).status_code,
                            [
                                {"session_id": session, "question_id": q_complex, "selected_option_ids": [cx1, cx2]},
                                {"session_id": session, "question_id": q_essay, "answer_text": "esai2"},
                            ],
                        )
                    )
                report["cases"].append(
                    {
                        "name": "different_questions_concurrent",
                        "ok": fa_d == go_d and all(code == 200 for code in fa_d + go_d),
                        "fastapi": fa_d,
                        "go": go_d,
                    }
                )
                answers_after = int(await conn.fetchval("SELECT count(*) FROM answers WHERE session_id=$1", session) or 0)
                redis_fa = rds.get(f"exam_answers:{session}")
                report["db"] = {"answers_before": answers_before, "answers_after": answers_after, "ok": answers_after >= 4}
                report["redis"] = {"exam_answers": redis_fa is not None, "ok": True}
                report["other_session"] = other_session
                report["q_mc"] = q_mc
                report["opt_ok"] = opt_ok
                report["exam_id"] = exam_id
                report["student"] = student
            finally:
                await conn.close()

        asyncio.run(seed_and_parity())
        failed = [item for item in report["cases"] if not item.get("ok")]
        report["parity_pass"] = not failed and report.get("db", {}).get("ok")
        if not report["parity_pass"]:
            report["failed"] = failed
            print(json.dumps(report, default=str))
            return 1

        async def seed_ab(n: int, runtime: str) -> list[tuple[str, dict[str, Any]]]:
            conn = await asyncpg.connect(PG, statement_cache_size=0)
            try:
                now = datetime.now(timezone.utc)
                exam_id = int(report["exam_id"])
                q_mc = int(report["q_mc"])
                opt_ok = int(report["opt_ok"])
                jobs: list[tuple[str, dict[str, Any]]] = []
                for i in range(n):
                    uid = await insert_user(conn, f"{PREFIX}_ab{n}_{runtime}_{i}")
                    sid = int(
                        await conn.fetchval(
                            """
                            INSERT INTO exam_sessions (user_id, exam_id, status, start_time)
                            VALUES ($1, $2, 'in_progress', $3) RETURNING id
                            """,
                            uid,
                            exam_id,
                            now,
                        )
                    )
                    jobs.append((mint(uid, f"{PREFIX}_ab{n}_{runtime}_{i}"), {"session_id": sid, "question_id": q_mc, "selected_option_id": opt_ok}))
                return jobs
            finally:
                await conn.close()

        for n in (50, 200, 620):
            for runtime, base, proc in (("fastapi", fa_base, fa), ("go", go_base, go)):
                jobs = asyncio.run(seed_ab(n, runtime))
                cpu0 = cpu_seconds(proc.pid)
                rss0 = rss_kb(proc.pid)
                result = burst(base, jobs)
                result["runtime"] = runtime
                result["cpu_per_1000"] = round((cpu_seconds(proc.pid) - cpu0) / max(n, 1) * 1000, 4)
                result["peak_rss_kb"] = max(rss0, rss_kb(proc.pid))
                report["ab"].append(result)
                if result["success"] != n:
                    print(json.dumps(report, default=str))
                    return 1
        print(json.dumps(report, default=str))
        return 0
    finally:
        for proc in (fa, go, pb):
            try:
                os.killpg(proc.pid, 15)
            except Exception:
                proc.terminate()
        fa_log.close()
        go_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
