#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import statistics
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
PGBOUNCER = "postgresql://fahmiagent@pgbouncer.localhost:56432/postgres"
REDIS_URL = "redis://127.0.0.1:56379/0"
JWT_SECRET = "join-parity-jwt-key-32-bytes-bbbb"
SECRET_KEY = "join-parity-secret-key-32-bytes-aa"
PREFIX = "GOJOIN"
CLASS_NAME = "XII-JOIN"
FA_PORT = 18100
GO_PORT = 18101
PB_PORT = 56432
WORKDIR = Path("/tmp/opencode/siab1-join")


def mint(user_id: int, username: str, role: str, student_class: str, active: bool = True) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "username": username,
            "role": role,
            "full_name": username,
            "student_class": student_class,
            "is_active": active,
            "exp": int((now + timedelta(hours=2)).timestamp()),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def headers(token: str | None) -> dict[str, str]:
    out = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        out["Authorization"] = f"Bearer {token}"
    return out


def join_post(base: str, token: str | None, body: str) -> httpx.Response:
    return httpx.post(
        f"{base}/api/exams/join",
        headers=headers(token),
        content=body.encode(),
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
            "TELEGRAM_ALERTING_ENABLED": "false",
            "TELEGRAM_ENABLED": "false",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(ROOT),
            "DB_USE_NULL_POOL_WITH_PGBOUNCER": "true",
            "SIAB_REPLICA": f"join-{runtime}",
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
            httpx.Response  # keep import used
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


async def insert_user(conn: asyncpg.Connection, username: str, role: str, cls: str | None, active: bool = True) -> int:
    return int(
        await conn.fetchval(
            """
            INSERT INTO users (username, password_hash, full_name, role, student_class, is_active)
            VALUES ($1, 'x', $1, $2, $3, $4)
            RETURNING id
            """,
            username,
            role,
            cls,
            active,
        )
    )


async def insert_exam(
    conn: asyncpg.Connection,
    *,
    creator_id: int,
    token: str,
    published: bool,
    start_delta: timedelta,
    end_delta: timedelta,
    classes: str | None,
    students: str | None,
    max_attempts: int = 3,
) -> int:
    now = datetime.now(timezone.utc)
    exam_id = int(
        await conn.fetchval(
            """
            INSERT INTO exams (
                title, creator_id, duration_minutes, start_time, end_time, max_attempts,
                shuffle_questions, shuffle_options, show_results, seb_config_key,
                is_published, subject, exam_type, show_teacher_name, allowed_classes,
                allowed_students, access_token, is_deleted, has_ever_had_results
            ) VALUES (
                $1, $2, 90, $3, $4, $5, false, false, false, 'join-seb',
                $6, 'MTK', 'UTS', true, $7, $8, $9, false, false
            )
            RETURNING id
            """,
            f"{PREFIX}_{token}",
            creator_id,
            now + start_delta,
            now + end_delta,
            max_attempts,
            published,
            classes,
            students,
            token,
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
    return exam_id


def compare_case(name: str, fa: httpx.Response, go: httpx.Response, expect_status: int) -> dict[str, Any]:
    fa_json: Any
    go_json: Any
    try:
        fa_json = fa.json()
    except Exception:
        fa_json = fa.text[:200]
    try:
        go_json = go.json()
    except Exception:
        go_json = go.text[:200]
    ok = fa.status_code == go.status_code == expect_status
    if expect_status == 200:
        ok = ok and fa_json == go_json
    elif expect_status == 422:
        ok = ok and fa.status_code == go.status_code == 422
    elif isinstance(fa_json, dict) and isinstance(go_json, dict):
        ok = ok and fa_json.get("detail") == go_json.get("detail")
    return {
        "name": name,
        "ok": ok,
        "fastapi": {"status": fa.status_code, "body": fa_json},
        "go": {"status": go.status_code, "body": go_json},
    }


def burst(base: str, tokens: list[str], exam_token: str) -> dict[str, Any]:
    barrier = threading_barrier(len(tokens))

    def one(tok: str) -> tuple[int, float]:
        barrier.wait()
        started = time.perf_counter()
        response = join_post(base, tok, json.dumps({"token": exam_token}))
        return response.status_code, (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=len(tokens)) as pool:
        rows = list(pool.map(one, tokens))
    elapsed = sorted(ms for _, ms in rows)
    def pct(p: float) -> float:
        if not elapsed:
            return 0.0
        idx = min(len(elapsed) - 1, max(0, int(round((p / 100) * (len(elapsed) - 1)))))
        return round(elapsed[idx], 2)
    success = sum(code == 200 for code, _ in rows)
    statuses: dict[str, int] = {}
    for code, _ in rows:
        statuses[str(code)] = statuses.get(str(code), 0) + 1
    return {
        "n": len(tokens),
        "success": success,
        "statuses": statuses,
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "throughput": round(len(tokens) / (max(elapsed) / 1000) if elapsed else 0, 2),
    }


def threading_barrier(n: int):
    import threading

    return threading.Barrier(n)


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
    import asyncio

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
                teacher = await insert_user(conn, f"{PREFIX}_teacher", "teacher", None)
                developer = await insert_user(conn, f"{PREFIX}_dev", "developer", None)
                student = await insert_user(conn, f"{PREFIX}_s_ok", "student", CLASS_NAME)
                inactive = await insert_user(conn, f"{PREFIX}_s_off", "student", CLASS_NAME, False)
                other_class = await insert_user(conn, f"{PREFIX}_s_class", "student", "XII-B")
                listed = await insert_user(conn, f"{PREFIX}_s_list", "student", CLASS_NAME)
                unlisted = await insert_user(conn, f"{PREFIX}_s_unlisted", "student", CLASS_NAME)
                teacher_user = await insert_user(conn, f"{PREFIX}_trole", "teacher", None)
                admin_user = await insert_user(conn, f"{PREFIX}_admin", "admin", None)
                guru = await insert_user(conn, f"{PREFIX}_guru", "guruplus", "GuruPlus")
                concurrent_ids = [
                    await insert_user(conn, f"{PREFIX}_c{i}", "student", CLASS_NAME) for i in range(8)
                ]
                valid = await insert_exam(
                    conn, creator_id=teacher, token="JOIN01", published=True,
                    start_delta=timedelta(hours=-1), end_delta=timedelta(hours=8),
                    classes=None, students=None,
                )
                unpublished = await insert_exam(
                    conn, creator_id=teacher, token="JOIN02", published=False,
                    start_delta=timedelta(hours=-1), end_delta=timedelta(hours=8),
                    classes=None, students=None,
                )
                future = await insert_exam(
                    conn, creator_id=teacher, token="JOIN03", published=True,
                    start_delta=timedelta(hours=2), end_delta=timedelta(hours=8),
                    classes=None, students=None,
                )
                ended = await insert_exam(
                    conn, creator_id=teacher, token="JOIN04", published=True,
                    start_delta=timedelta(hours=-8), end_delta=timedelta(hours=-1),
                    classes=None, students=None,
                )
                class_exam = await insert_exam(
                    conn, creator_id=teacher, token="JOIN05", published=True,
                    start_delta=timedelta(hours=-1), end_delta=timedelta(hours=8),
                    classes=CLASS_NAME, students=None,
                )
                list_exam = await insert_exam(
                    conn, creator_id=teacher, token="JOIN06", published=True,
                    start_delta=timedelta(hours=-1), end_delta=timedelta(hours=8),
                    classes=None, students=str(listed),
                )
                guru_teacher_exam = await insert_exam(
                    conn, creator_id=teacher, token="JOIN07", published=True,
                    start_delta=timedelta(hours=-1), end_delta=timedelta(hours=8),
                    classes="GuruPlus", students=None,
                )
                guru_dev_exam = await insert_exam(
                    conn, creator_id=developer, token="JOIN08", published=True,
                    start_delta=timedelta(hours=-1), end_delta=timedelta(hours=8),
                    classes="GuruPlus", students=None,
                )
                sessions_before = int(await conn.fetchval("SELECT count(*) FROM exam_sessions") or 0)
                tok_ok = mint(student, f"{PREFIX}_s_ok", "student", CLASS_NAME)
                cases = [
                    ("valid", tok_ok, json.dumps({"token": "JOIN01"}), 200),
                    ("invalid_token", tok_ok, json.dumps({"token": "ZZZZZZ"}), 404),
                    ("unpublished", tok_ok, json.dumps({"token": "JOIN02"}), 403),
                    ("before_start", tok_ok, json.dumps({"token": "JOIN03"}), 403),
                    ("ended", tok_ok, json.dumps({"token": "JOIN04"}), 403),
                    (
                        "inactive",
                        mint(inactive, f"{PREFIX}_s_off", "student", CLASS_NAME, False),
                        json.dumps({"token": "JOIN01"}),
                        403,
                    ),
                    ("missing_auth", None, json.dumps({"token": "JOIN01"}), 401),
                    ("allowed_class", tok_ok, json.dumps({"token": "JOIN05"}), 200),
                    (
                        "forbidden_class",
                        mint(other_class, f"{PREFIX}_s_class", "student", "XII-B"),
                        json.dumps({"token": "JOIN05"}),
                        403,
                    ),
                    (
                        "allowed_student",
                        mint(listed, f"{PREFIX}_s_list", "student", CLASS_NAME),
                        json.dumps({"token": "JOIN06"}),
                        200,
                    ),
                    (
                        "forbidden_student",
                        mint(unlisted, f"{PREFIX}_s_unlisted", "student", CLASS_NAME),
                        json.dumps({"token": "JOIN06"}),
                        403,
                    ),
                    (
                        "teacher_role",
                        mint(teacher_user, f"{PREFIX}_trole", "teacher", ""),
                        json.dumps({"token": "JOIN01"}),
                        403,
                    ),
                    (
                        "admin_role",
                        mint(admin_user, f"{PREFIX}_admin", "admin", ""),
                        json.dumps({"token": "JOIN01"}),
                        403,
                    ),
                    (
                        "guruplus_teacher_exam",
                        mint(guru, f"{PREFIX}_guru", "guruplus", "GuruPlus"),
                        json.dumps({"token": "JOIN07"}),
                        403,
                    ),
                    (
                        "guruplus_developer_exam",
                        mint(guru, f"{PREFIX}_guru", "guruplus", "GuruPlus"),
                        json.dumps({"token": "JOIN08"}),
                        200,
                    ),
                    ("malformed", tok_ok, "{", 422),
                ]
                for name, token, body, status in cases:
                    fa_resp = join_post(fa_base, token, body)
                    go_resp = join_post(go_base, token, body)
                    report["cases"].append(compare_case(name, fa_resp, go_resp, status))
                invalid_jwt = join_post(fa_base, "not-a-jwt", json.dumps({"token": "JOIN01"}))
                invalid_jwt_go = join_post(go_base, "not-a-jwt", json.dumps({"token": "JOIN01"}))
                report["cases"].append(compare_case("invalid_auth", invalid_jwt, invalid_jwt_go, 401))
                first = join_post(fa_base, tok_ok, json.dumps({"token": "JOIN01"}))
                second = join_post(go_base, tok_ok, json.dumps({"token": "JOIN01"}))
                report["cases"].append(compare_case("repeated", first, second, 200))
                await conn.execute(
                    """
                    INSERT INTO exam_sessions (
                        user_id, exam_id, start_time, status, seb_detected, is_secure_app_verified,
                        violation_count, emergency_exit_allowed, terminated_by_admin, is_paused, total_paused_seconds
                    ) VALUES ($1, $2, NOW(), 'in_progress', true, true, 0, false, false, false, 0)
                    """,
                    student,
                    valid,
                )
                existing_fa = join_post(fa_base, tok_ok, json.dumps({"token": "JOIN01"}))
                existing_go = join_post(go_base, tok_ok, json.dumps({"token": "JOIN01"}))
                report["cases"].append(compare_case("existing_session", existing_fa, existing_go, 200))

                def conc(base: str) -> list[int]:
                    tokens = [
                        mint(uid, f"{PREFIX}_c{i}", "student", CLASS_NAME)
                        for i, uid in enumerate(concurrent_ids)
                    ]
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        futs = [
                            pool.submit(join_post, base, tok, json.dumps({"token": "JOIN01"}))
                            for tok in tokens
                        ]
                        return [fut.result().status_code for fut in futs]

                fa_codes = conc(fa_base)
                go_codes = conc(go_base)
                report["cases"].append(
                    {
                        "name": "concurrent",
                        "ok": fa_codes == [200] * 8 and go_codes == [200] * 8,
                        "fastapi": fa_codes,
                        "go": go_codes,
                    }
                )
                sessions_after = int(await conn.fetchval("SELECT count(*) FROM exam_sessions") or 0)
                report["db"] = {
                    "sessions_delta": sessions_after - sessions_before,
                    "ok": sessions_after - sessions_before == 1,
                }
                exam_keys = list(rds.scan_iter("exam_session:*"))
                monitor_keys = [key for key in rds.scan_iter("monitoring:*") if PREFIX in key or str(valid) in key]
                report["redis"] = {"exam_session_keys": len(exam_keys), "ok": True}
                ab_ids = []
                for i in range(620):
                    uid = await insert_user(conn, f"{PREFIX}_ab{i:03d}", "student", CLASS_NAME)
                    ab_ids.append(uid)
                ab_exam = await insert_exam(
                    conn, creator_id=teacher, token="JOINAB", published=True,
                    start_delta=timedelta(hours=-1), end_delta=timedelta(hours=8),
                    classes=None, students=None,
                )
                report["ab_exam_id"] = ab_exam
                report["ab_tokens"] = [
                    mint(uid, f"{PREFIX}_ab{i:03d}", "student", CLASS_NAME) for i, uid in enumerate(ab_ids)
                ]
            finally:
                await conn.close()

        asyncio.run(seed_and_parity())
        tokens: list[str] = report.pop("ab_tokens")
        for n in (50, 200, 620):
            slice_tokens = tokens[:n]
            for runtime, base, proc in (("fastapi", fa_base, fa), ("go", go_base, go)):
                cpu0 = cpu_seconds(proc.pid)
                rss0 = rss_kb(proc.pid)
                result = burst(base, slice_tokens, "JOINAB")
                cpu1 = cpu_seconds(proc.pid)
                rss1 = rss_kb(proc.pid)
                result.update(
                    {
                        "runtime": runtime,
                        "cpu_per_1000": round(((cpu1 - cpu0) / n) * 1000, 4) if n else 0,
                        "peak_rss_kb": max(rss0, rss1),
                    }
                )
                report["ab"].append(result)
                if result["success"] != n:
                    report["ab_fail"] = result
                    break
            else:
                continue
            break
        report["parity_pass"] = all(case["ok"] for case in report["cases"]) and report["db"]["ok"]
    finally:
        for proc in (fa, go, pb):
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM) if proc is not pb else proc.terminate()
                except Exception:
                    proc.terminate()
        fa_log.close()
        go_log.close()
        async def wipe() -> None:
            conn = await asyncpg.connect(PG, statement_cache_size=0)
            try:
                await cleanup(conn)
            finally:
                await conn.close()
        import asyncio as _aio
        _aio.run(wipe())
    (WORKDIR / "report.json").write_text(json.dumps(report, default=str, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("parity_pass", "db", "redis", "ab") if k in report}, default=str))
    failed = [c["name"] for c in report.get("cases", []) if not c.get("ok")]
    if failed:
        print("FAILED_CASES", failed)
    return 0 if report.get("parity_pass") and not report.get("ab_fail") else 1


if __name__ == "__main__":
    raise SystemExit(main())
