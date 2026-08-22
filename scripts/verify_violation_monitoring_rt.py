#!/usr/bin/env python3
"""
Verify violation logging + monitoring real-time broadcast consistency.

This script is intended to run inside the API container where app modules and
dependencies are already available.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple
from uuid import uuid4

import httpx
import websockets
from sqlalchemy import delete, select

from app.core.security import create_access_token, get_password_hash
from app.config import settings
from app.database import async_session_write
from app.models.exam import Exam
from app.models.question import Question, QuestionOption
from app.models.session import ExamLog, ExamSession
from app.models.user import User


@dataclass
class Fixture:
    teacher_id: int
    student_id: int
    exam_id: int
    session_id: int
    teacher_token: str
    student_token: str


VIOLATION_CASES: List[Tuple[str, Dict[str, str], str]] = [
    ("tab_switch", {}, "tab_switch"),
    ("window_blur", {}, "focus_lost"),
    ("copy_paste_attempt", {"action": "keyboard_ctrl_v"}, "paste"),
    ("devtools_attempt", {}, "devtools_open"),
    ("screenshot", {}, "screenshot_attempt"),
    ("overlay_apps", {}, "overlay_app"),
    ("screen_recording", {}, "screen_recording"),
    ("external_display", {}, "external_display"),
    ("accessibility_risk", {}, "accessibility_risk"),
    ("apk_tampering", {}, "apk_tampering"),
    ("security_warning", {}, "security_warning"),
    ("violation_copy", {}, "copy"),
    ("clipboard_violation", {"action": "cut"}, "cut"),
]


async def prepare_fixture() -> Fixture:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:8]
    teacher_username = f"rt_teacher_{stamp}_{suffix}"
    student_username = f"rt_student_{stamp}_{suffix}"
    pwd_hash = get_password_hash("TempPass!123")
    now = datetime.now(timezone.utc)

    async with async_session_write() as db:
        teacher = User(
            username=teacher_username,
            password_hash=pwd_hash,
            full_name="RT Teacher",
            role="teacher",
            is_active=True,
        )
        student = User(
            username=student_username,
            password_hash=pwd_hash,
            full_name="RT Student",
            role="student",
            student_class="RT_CLASS",
            is_active=True,
        )
        db.add(teacher)
        db.add(student)
        await db.flush()

        exam = Exam(
            title=f"RT Violation Verification {stamp}",
            description="Real-time violation verification",
            creator_id=teacher.id,
            duration_minutes=30,
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(minutes=60),
            is_published=True,
            access_token=suffix[:6].upper(),
            allowed_classes="RT_CLASS",
            show_results=True,
            shuffle_questions=False,
            shuffle_options=False,
            max_attempts=1,
            seb_config_key=settings.seb_default_config_key,
            seb_browser_exam_key=settings.seb_default_browser_exam_key,
        )
        db.add(exam)
        await db.flush()

        question = Question(
            exam_id=exam.id,
            question_text="RT question",
            question_type="multiple_choice",
            difficulty_level="easy",
            points=1,
            order_index=1,
        )
        db.add(question)
        await db.flush()
        db.add_all(
            [
                QuestionOption(
                    question_id=question.id,
                    option_text="A",
                    is_correct=True,
                    order_index=1,
                ),
                QuestionOption(
                    question_id=question.id,
                    option_text="B",
                    is_correct=False,
                    order_index=2,
                ),
            ]
        )

        session = ExamSession(
            user_id=student.id,
            exam_id=exam.id,
            start_time=now,
            status="in_progress",
            violation_count=0,
        )
        db.add(session)
        await db.commit()
        await db.refresh(teacher)
        await db.refresh(student)
        await db.refresh(exam)
        await db.refresh(session)

    teacher_token = create_access_token(
        {"sub": str(teacher.id), "username": teacher.username, "role": teacher.role}
    )
    student_token = create_access_token(
        {"sub": str(student.id), "username": student.username, "role": student.role}
    )
    return Fixture(
        teacher_id=teacher.id,
        student_id=student.id,
        exam_id=exam.id,
        session_id=session.id,
        teacher_token=teacher_token,
        student_token=student_token,
    )


async def cleanup_fixture(fixture: Fixture) -> None:
    async with async_session_write() as db:
        await db.execute(delete(ExamLog).where(ExamLog.session_id == fixture.session_id))
        await db.execute(delete(ExamSession).where(ExamSession.id == fixture.session_id))
        await db.execute(delete(QuestionOption).where(QuestionOption.question.has(exam_id=fixture.exam_id)))
        await db.execute(delete(Question).where(Question.exam_id == fixture.exam_id))
        await db.execute(delete(Exam).where(Exam.id == fixture.exam_id))
        await db.execute(delete(User).where(User.id.in_([fixture.teacher_id, fixture.student_id])))
        await db.commit()


async def run_verification(base_url: str) -> Dict[str, object]:
    fixture = await prepare_fixture()
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_endpoint = f"{ws_url}/ws/monitor/{fixture.exam_id}?token={fixture.teacher_token}"

    websocket_payloads: List[Dict[str, object]] = []
    violations_api: Dict[str, object] = {}
    errors: List[str] = []

    headers_teacher = {"Authorization": f"Bearer {fixture.teacher_token}"}
    headers_student = {"Authorization": f"Bearer {fixture.student_token}"}

    try:
        async with websockets.connect(ws_endpoint, ping_interval=None, close_timeout=1) as ws, httpx.AsyncClient(
            base_url=base_url,
            timeout=10.0,
        ) as api:
            for raw_event_type, event_data, expected_key in VIOLATION_CASES:
                payload = {
                    "session_id": fixture.session_id,
                    "exam_id": 0,  # enforce fallback-to-session exam_id path
                    "event_type": raw_event_type,
                    "event_data": event_data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "user_agent": "SXB-Client/1.0",
                    "screen_resolution": "1080x1920",
                }
                response = await api.post(
                    "/api/exams/log-violation",
                    headers=headers_student,
                    json=payload,
                )
                if response.status_code != 200:
                    errors.append(
                        f"log-violation failed for {raw_event_type}: "
                        f"{response.status_code} {response.text}"
                    )
                    continue

                try:
                    ws_message = await asyncio.wait_for(ws.recv(), timeout=4.0)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"websocket timeout for {raw_event_type}: {exc}")
                    continue

                ws_payload = json.loads(ws_message)
                websocket_payloads.append(ws_payload)
                got_type = ws_payload.get("violation_type")
                if ws_payload.get("type") != "violation_detected":
                    errors.append(
                        f"unexpected ws type for {raw_event_type}: {ws_payload.get('type')}"
                    )
                if got_type != expected_key:
                    errors.append(
                        f"violation key mismatch for {raw_event_type}: expected {expected_key}, got {got_type}"
                    )
                if not ws_payload.get("violation_label"):
                    errors.append(f"missing violation_label for {raw_event_type}")
                if not ws_payload.get("violation_category"):
                    errors.append(f"missing violation_category for {raw_event_type}")

            violations_resp = await api.get(
                "/api/monitoring/violations",
                headers=headers_teacher,
                params={"exam_id": fixture.exam_id},
            )
            if violations_resp.status_code != 200:
                errors.append(
                    f"monitoring violations endpoint failed: "
                    f"{violations_resp.status_code} {violations_resp.text}"
                )
            else:
                violations_api = violations_resp.json()

    finally:
        await cleanup_fixture(fixture)

    by_type = dict((violations_api or {}).get("by_type") or {})
    type_details = dict((violations_api or {}).get("type_details") or {})

    missing_from_api = [
        expected
        for _, _, expected in VIOLATION_CASES
        if by_type.get(expected, 0) < 1
    ]
    if missing_from_api:
        errors.append(f"missing types in monitoring API: {missing_from_api}")

    detail_missing = [
        key
        for key in by_type.keys()
        if not (type_details.get(key) or {}).get("label")
        or not (type_details.get(key) or {}).get("category")
    ]
    if detail_missing:
        errors.append(f"type_details missing label/category: {detail_missing}")

    return {
        "ok": not errors,
        "total_cases": len(VIOLATION_CASES),
        "websocket_events": len(websocket_payloads),
        "monitoring_total_violations": int((violations_api or {}).get("total_violations", 0)),
        "monitoring_by_type": by_type,
        "errors": errors,
        "sample_ws": websocket_payloads[:5],
    }


def main() -> None:
    base_url = os.getenv("VERIFY_BASE_URL", "http://127.0.0.1:8000")
    result = asyncio.run(run_verification(base_url=base_url))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
