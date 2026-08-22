"""
Backup and Restore API endpoints.
Export and import data with filtering options.
"""
import asyncio
import io
import json
import os  # FIX: For environment variables
import subprocess  # FIX: For GPG encryption
import logging  # FIX: For logger
import secrets
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.config import settings
from app.core.feature_flags import require_feature_enabled
from app.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question, QuestionOption
from app.models.session import ExamSession
from app.models.activity_log import UserActivityLog
from app.core.security import get_current_active_admin

# Initialize logger
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backup", tags=["Backup & Restore"])

# Admin Audit Logging Helper
async def log_admin_backup_action(
    db: AsyncSession,
    admin_user: User,
    action: str,
    target_type: str,
    target_id: int,
    target_name: str,
    details: dict = None
):
    """Log admin actions for audit trail."""
    log_entry = UserActivityLog(
        user_id=admin_user.id,
        event_type=f"admin_{action}",
        event_data={
            "admin_username": admin_user.username,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "target_name": target_name,
            "details": details or {}
        }
    )
    db.add(log_entry)
    await db.commit()
    logger.warning(f"🚨 ADMIN BACKUP ACTION: {admin_user.username} {action} {target_type} '{target_name}' (ID: {target_id})")


class ExportRequest(BaseModel):
    """Export request with filter options."""
    export_type: str  # all, teachers, students, exams, results
    exam_id: Optional[int] = None  # For results export


class ImportPreview(BaseModel):
    """Preview of import data."""
    users_count: int = 0
    exams_count: int = 0
    questions_count: int = 0
    sessions_count: int = 0
    can_import: bool = True
    warnings: List[str] = []


def _serialize_exam_for_backup(exam: Exam) -> dict:
    return {
        "id": exam.id,
        "title": exam.title,
        "description": exam.description,
        "duration_minutes": exam.duration_minutes,
        "passing_score": float(exam.passing_score) if exam.passing_score else None,
        "shuffle_questions": exam.shuffle_questions,
        "shuffle_options": exam.shuffle_options,
        "is_published": exam.is_published,
        "subject": exam.subject,
        "exam_type": exam.exam_type,
        "questions": [
            {
                "id": question.id,
                "question_type": question.question_type,
                "question_text": question.question_text,
                "points": float(question.points) if question.points else 1,
                "order_index": question.order_index,
                "options": [
                    {
                        "id": option.id,
                        "option_text": option.option_text,
                        "is_correct": option.is_correct,
                        "order_index": option.order_index,
                    }
                    for option in sorted(question.options, key=lambda item: item.order_index)
                ],
            }
            for question in sorted(exam.questions, key=lambda item: item.order_index)
        ],
    }


def _run_gpg_encrypt(json_data: str, gpg_recipient: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gpg", "--encrypt", "--armor", "--recipient", gpg_recipient],
        input=json_data.encode("utf-8"),
        capture_output=True,
        timeout=30,
        check=False,
    )


@router.post("/export")
async def export_data(
    request: ExportRequest,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Export data based on filter type.

    Types:
    - all: All users, exams, questions, results
    - teachers: Only teacher accounts
    - students: Only student accounts
    - exams: All exams with questions
    - results: Exam results (requires exam_id)
    """
    require_feature_enabled(
        settings.heavy_exports_active,
        "heavy_export",
        status_code=503,
        message="Backup/export data sedang dinonaktifkan selama mode ujian/puncak.",
    )
    export_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": current_user.username,
        "export_type": request.export_type,
        "version": "1.0"
    }

    if request.export_type == "all":
        # Export all users
        result = await db.execute(select(User))
        users = result.scalars().all()
        export_data["users"] = [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "role": u.role,
                "student_class": u.student_class,
                "job_title": u.job_title,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]

        # Export all exams with questions
        result = await db.execute(
            select(Exam).options(
                selectinload(Exam.questions).selectinload(Question.options)
            )
        )
        exams = result.scalars().all()
        export_data["exams"] = [_serialize_exam_for_backup(exam) for exam in exams]

    elif request.export_type == "teachers":
        result = await db.execute(select(User).where(User.role == "teacher"))
        users = result.scalars().all()
        export_data["users"] = [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "role": u.role,
                "job_title": u.job_title,
                "is_active": u.is_active
            }
            for u in users
        ]

    elif request.export_type == "students":
        result = await db.execute(select(User).where(User.role == "student"))
        users = result.scalars().all()
        export_data["users"] = [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "role": u.role,
                "student_class": u.student_class,
                "is_active": u.is_active
            }
            for u in users
        ]

    elif request.export_type == "exams":
        result = await db.execute(select(Exam))
        exams = result.scalars().all()
        export_data["exams"] = [
            {
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "duration_minutes": e.duration_minutes,
                "is_published": e.is_published,
                "subject": e.subject,
                "exam_type": e.exam_type
            }
            for e in exams
        ]

    elif request.export_type == "results":
        if not request.exam_id:
            raise HTTPException(400, "exam_id required for results export")

        # Get exam info for metadata with creator
        exam_result = await db.execute(
            select(Exam)
            .options(selectinload(Exam.creator))
            .where(Exam.id == request.exam_id)
        )
        exam = exam_result.scalar_one_or_none()
        if not exam:
            raise HTTPException(404, "Exam not found")

        # Generate creator name with role prefix
        creator_name = None
        if exam.creator:
            role_prefix = ""
            if exam.creator.role == "teacher":
                role_prefix = "Guru "
            elif exam.creator.role == "admin":
                role_prefix = "Admin "
            creator_name = f"{role_prefix}{exam.creator.full_name or exam.creator.username}"

        # Add exam metadata to export
        export_data["exam_info"] = {
            "title": exam.title,
            "subject": exam.subject,
            "exam_type": exam.exam_type,
            "duration_minutes": exam.duration_minutes,
            "passing_score": float(exam.passing_score) if exam.passing_score else None,
            "pelaksana": creator_name
        }

        result = await db.execute(
            select(ExamSession)
            .options(selectinload(ExamSession.user))
            .where(ExamSession.exam_id == request.exam_id)
            .where(ExamSession.status.in_(["completed", "submitted"]))
        )
        sessions = result.scalars().all()

        export_data["results"] = []
        for s in sessions:
            user = s.user

            export_data["results"].append({
                "session_id": s.id,
                "user_id": s.user_id,
                "username": user.username if user else "unknown",
                "full_name": user.full_name if user else "Unknown",
                "student_class": user.student_class if user else None,
                "score": float(s.score) if s.score else 0,
                "status": s.status,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None
            })
    else:
        raise HTTPException(400, f"Invalid export_type: {request.export_type}")

    # Convert to JSON
    json_data = json.dumps(export_data, ensure_ascii=False, indent=2)

    # ✅ SECURITY FIX: Encrypt backup if GPG_ENCRYPT=true
    encrypt_backup = os.getenv("GPG_ENCRYPT", "false").lower() == "true"

    if encrypt_backup:
        try:
            # Try to encrypt with GPG
            gpg_recipient = os.getenv("GPG_RECIPIENT", "admin@example.com")

            # Validasi format email sederhana untuk mencegah input aneh
            import re
            if not re.match(r"[^@]+@[^@]+\.[^@]+", gpg_recipient):
                logger.warning(f"Invalid GPG recipient format: {gpg_recipient}. Fallback to unencrypted.")
                encrypt_backup = False
            else:
                # Encrypt using GPG
                # subprocess.run dengan list argument AMAN dari shell injection
                result = await asyncio.to_thread(
                    _run_gpg_encrypt,
                    json_data,
                    gpg_recipient,
                )

                if result.returncode == 0:
                    # Encryption successful
                    encrypted_data = result.stdout
                    filename = f"backup_{request.export_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json.gpg"

                    return StreamingResponse(
                        io.BytesIO(encrypted_data),
                        media_type="application/pgp-encrypted",
                        headers={"Content-Disposition": f"attachment; filename={filename}"}
                    )
                else:
                    # GPG failed, log warning and continue unencrypted
                    logger.warning(f"GPG encryption failed: {result.stderr.decode()}")
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            # GPG not available or error, log and continue unencrypted
            logger.warning(f"Backup encryption error: {e}")

    # Return unencrypted (if GPG disabled or failed)
    filename = f"backup_{request.export_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    return StreamingResponse(
        io.BytesIO(json_data.encode('utf-8')),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/import/preview", response_model=ImportPreview)
async def preview_import(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_admin)
):
    """Preview backup file before importing."""
    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))

        preview = ImportPreview()

        if "users" in data:
            preview.users_count = len(data["users"])
        if "exams" in data:
            preview.exams_count = len(data["exams"])
            preview.questions_count = sum(
                len(e.get("questions", [])) for e in data["exams"]
            )
        if "results" in data:
            preview.sessions_count = len(data["results"])

        # Add warnings
        if preview.users_count > 0:
            preview.warnings.append(f"⚠️ {preview.users_count} akun pengguna akan ditambahkan")
        if preview.exams_count > 0:
            preview.warnings.append(f"⚠️ {preview.exams_count} ujian dengan {preview.questions_count} soal")

        return preview

    except json.JSONDecodeError:
        raise HTTPException(400, "File bukan format JSON yang valid")


@router.post("/import")
async def import_data(
    file: UploadFile = File(...),
    import_users: bool = Form(True),
    import_exams: bool = Form(True),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Import data from backup file.

    Note: This creates new records, does not overwrite existing.
    """
    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))

        imported = {
            "users": 0,
            "exams": 0,
            "questions": 0
        }
        imported_user_credentials: List[dict] = []

        # Import users
        if import_users and "users" in data:
            from app.core.security import get_password_hash

            for user_data in data["users"]:
                # Check if user exists
                existing = await db.execute(
                    select(User).where(User.username == user_data["username"])
                )
                if existing.scalar_one_or_none():
                    continue

                temp_password = secrets.token_urlsafe(10)
                user = User(
                    username=user_data["username"],
                    password_hash=get_password_hash(temp_password),
                    full_name=user_data.get("full_name", user_data["username"]),
                    role=user_data.get("role", "student"),
                    student_class=user_data.get("student_class"),
                    job_title=user_data.get("job_title"),
                    is_active=user_data.get("is_active", True)
                )
                db.add(user)
                imported["users"] += 1
                imported_user_credentials.append(
                    {
                        "username": user.username,
                        "temporary_password": temp_password,
                        "must_change_password": True,
                    }
                )

        # Import exams
        if import_exams and "exams" in data:
            for exam_data in data["exams"]:
                exam = Exam(
                    title=exam_data["title"] + " (Imported)",
                    description=exam_data.get("description"),
                    creator_id=current_user.id,
                    duration_minutes=exam_data.get("duration_minutes", 60),
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    passing_score=exam_data.get("passing_score"),
                    shuffle_questions=exam_data.get("shuffle_questions", False),
                    shuffle_options=exam_data.get("shuffle_options", False),
                    is_published=False,  # Always import as draft
                    subject=exam_data.get("subject"),
                    exam_type=exam_data.get("exam_type"),
                    seb_config_key="imported"
                )
                db.add(exam)
                await db.flush()  # Get exam ID

                # Import questions
                for q_data in exam_data.get("questions", []):
                    question = Question(
                        exam_id=exam.id,
                        question_type=q_data.get("question_type", "multiple_choice"),
                        question_text=q_data["question_text"],
                        points=q_data.get("points", 1),
                        order_index=q_data.get("order_index", 0)  # FIX: Correct field name
                    )
                    db.add(question)
                    await db.flush()

                    # Import options
                    for opt_data in q_data.get("options", []):
                        option = QuestionOption(
                            question_id=question.id,
                            option_text=opt_data["option_text"],
                            is_correct=opt_data.get("is_correct", False),
                            order_index=opt_data.get("order_index", 0)  # FIX: Correct field name
                        )
                        db.add(option)

                    imported["questions"] += 1

                imported["exams"] += 1

        await db.commit()

        return {
            "success": True,
            "message": f"Import berhasil: {imported['users']} users, {imported['exams']} exams, {imported['questions']} questions",
            "imported": imported,
            "temporary_credentials": imported_user_credentials,
            "security_notice": (
                "Password user import dibuat acak per akun. "
                "Wajib minta user mengganti password setelah login pertama."
            ),
        }

    except json.JSONDecodeError:
        raise HTTPException(400, "File bukan format JSON yang valid")
    except Exception:
        await db.rollback()
        logger.exception("Import backup failed")
        raise HTTPException(500, "Import gagal")


@router.delete("/results/{exam_id}")
async def delete_exam_results(
    exam_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete all results for an exam."""
    # Verify exam exists
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(404, "Ujian tidak ditemukan")

    # Get sessions to delete
    sessions_result = await db.execute(
        select(ExamSession).where(ExamSession.exam_id == exam_id)
    )
    sessions = sessions_result.scalars().all()

    count = len(sessions)

    # Delete all sessions (cascades to answers)
    for session in sessions:
        await db.delete(session)

    await db.commit()

    # Log admin action
    await log_admin_backup_action(
        db, current_user, "delete_results", "exam", exam_id, exam.title,
        {"deleted_count": count, "exam_creator_id": exam.creator_id}
    )

    return {
        "success": True,
        "message": f"{count} hasil ujian berhasil dihapus",
        "deleted_count": count
    }


@router.delete("/results/{exam_id}/{session_id}")
async def delete_single_result(
    exam_id: int,
    session_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a single exam result."""
    # Get exam info first
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = exam_result.scalar_one_or_none()

    result = await db.execute(
        select(ExamSession)
        .where(ExamSession.id == session_id)
        .where(ExamSession.exam_id == exam_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "Hasil ujian tidak ditemukan")

    await db.delete(session)
    await db.commit()

    # Log admin action
    await log_admin_backup_action(
        db, current_user, "delete_single_result", "session", session_id,
        f"Session-{session_id}",
        {"exam_id": exam_id, "exam_title": exam.title if exam else "Unknown", "user_id": session.user_id}
    )

    return {
        "success": True,
        "message": "Hasil ujian berhasil dihapus"
    }
