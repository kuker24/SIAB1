"""Exam PDF/export routes.

Routes stay under ``/api/exams`` but are separated from the large exam module.
"""

import hashlib
import re
from datetime import datetime
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exam_access_policy import (
    is_exam_participant_role as _is_exam_participant_role,
)
from app.core.feature_flags import require_feature_enabled
from app.core.roles import ROLE_DEVELOPER, is_developer_exam_hidden_for_viewer
from app.core.security import get_current_teacher, get_current_user, is_pengawas_user
from app.database import get_db, get_db_read
from app.models.exam import Exam
from app.models.session import ExamSession
from app.models.user import User

router = APIRouter(prefix="/api/exams", tags=["Exam Exports"])


async def _get_exam_creator_role(db: AsyncSession, creator_id: Optional[int]) -> Optional[str]:
    if not creator_id:
        return None

    creator_role_result = await db.execute(select(User.role).where(User.id == creator_id))
    return creator_role_result.scalar_one_or_none()


def _raise_hidden_exam_error() -> None:
    raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")


def _enforce_developer_exam_visibility(
    current_user: User,
    exam_creator_role: Optional[str],
) -> None:
    if is_developer_exam_hidden_for_viewer(current_user.role, exam_creator_role):
        _raise_hidden_exam_error()


async def _enforce_exam_owner_or_admin_access(
    db: AsyncSession,
    current_user: User,
    exam_creator_id: int,
    *,
    allow_pengawas: bool = False,
) -> str:
    creator_role = await _get_exam_creator_role(db, exam_creator_id)
    _enforce_developer_exam_visibility(current_user, creator_role)

    if exam_creator_id == current_user.id:
        return str(creator_role or "")

    if bool(getattr(current_user, "is_admin", False)):
        return str(creator_role or "")

    if allow_pengawas and is_pengawas_user(current_user):
        return str(creator_role or "")

    raise HTTPException(status_code=403, detail="Tidak memiliki akses")


@router.get("/{exam_id}/analytics/pdf")
async def get_exam_analytics_pdf(
    exam_id: int,
    class_name: Optional[str] = Query(
        default=None,
        description="Nama kelas dari tab performa siswa (opsional)",
    ),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_read),
):
    """Export exam analytics as formal PDF."""
    require_feature_enabled(
        settings.heavy_exports_active,
        "heavy_export",
        status_code=503,
        message="PDF analytics sedang dinonaktifkan selama mode ujian/puncak.",
    )
    from app.api.analytics import (
        _build_class_performance_payload,
        get_question_difficulty_analysis,
    )
    from app.api.exams import get_exam_analytics
    from app.core.pdf_generator import (
        REPORTLAB_AVAILABLE,
        generate_exam_analytics_pdf,
    )

    if not REPORTLAB_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="PDF export tidak tersedia. Install ReportLab: pip install reportlab",
        )

    exam_result = await db.execute(
        select(Exam)
        .options(selectinload(Exam.creator))
        .where(
            Exam.id == exam_id,
            Exam.is_deleted == False,
        )
    )
    exam = exam_result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
    )

    overview_obj = await get_exam_analytics(exam_id=exam_id, current_user=current_user, db=db)
    overview_payload = (
        overview_obj.model_dump()
        if hasattr(overview_obj, "model_dump")
        else dict(overview_obj)
    )

    question_payload = await get_question_difficulty_analysis(
        exam_id=exam_id,
        current_user=current_user,
        db=db,
    )
    question_rows = question_payload.get("questions", [])

    class_filter = (class_name or "").strip()
    class_payload = None
    if class_filter:
        class_obj = await _build_class_performance_payload(
            class_filter,
            current_user,
            db,
            exam_id=exam_id,
        )
        class_payload = (
            class_obj.model_dump()
            if hasattr(class_obj, "model_dump")
            else dict(class_obj)
        )

    creator_name = "-"
    if exam.creator:
        role_prefix = ""
        if exam.creator.role == "teacher":
            role_prefix = "Guru "
        elif exam.creator.role == ROLE_DEVELOPER:
            role_prefix = "Developer "
        elif exam.creator.role == "admin":
            role_prefix = "Admin "
        creator_name = f"{role_prefix}{exam.creator.full_name or exam.creator.username}"

    exported_at = datetime.now(pytz.timezone("Asia/Jakarta")).strftime(
        "%A, %d %B %Y %H:%M WIB"
    )

    payload = {
        "exam": {
            "id": exam.id,
            "title": exam.title,
            "subject": exam.subject or "-",
            "teacher_name": creator_name,
            "passing_score": float(exam.passing_score or 70),
        },
        "overview": overview_payload,
        "score_distribution": overview_payload.get("score_distribution") or {},
        "question_analysis": question_rows,
        "class_performance": class_payload,
        "class_filter": class_filter or "Belum dipilih",
        "generated_at": exported_at,
    }

    pdf_bytes = generate_exam_analytics_pdf(payload)

    safe_title = re.sub(r"[^\w\s-]", "", exam.title or "ujian").strip()
    safe_title = re.sub(r"\s+", "_", safe_title) or "ujian"
    filename = f"analitik_ujian_{safe_title}_{datetime.now().strftime('%Y%m%d')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{exam_id}/results/pdf")
async def get_exam_results_pdf(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    """Export exam results as PDF document."""
    require_feature_enabled(
        settings.heavy_exports_active,
        "heavy_export",
        status_code=503,
        message="PDF hasil ujian sedang dinonaktifkan selama mode ujian/puncak.",
    )
    from app.core.pdf_generator import REPORTLAB_AVAILABLE, generate_exam_results_pdf

    if not REPORTLAB_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="PDF export tidak tersedia. Install ReportLab: pip install reportlab",
        )

    result = await db.execute(
        select(Exam)
        .options(selectinload(Exam.creator))
        .where(Exam.id == exam_id)
    )
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
    )

    creator_name = None
    if exam.creator:
        role_prefix = ""
        if exam.creator.role == "teacher":
            role_prefix = "Guru "
        elif exam.creator.role == ROLE_DEVELOPER:
            role_prefix = "Developer "
        elif exam.creator.role == "admin":
            role_prefix = "Admin "
        creator_name = f"{role_prefix}{exam.creator.full_name or exam.creator.username}"

    stmt = (
        select(ExamSession)
        .where(ExamSession.exam_id == exam_id)
        .where(ExamSession.status.in_(["submitted", "completed"]))
        .options(selectinload(ExamSession.user))
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    if not sessions:
        raise HTTPException(status_code=404, detail="Belum ada hasil ujian")

    results = []
    scores = []
    passed_count = 0

    for session in sessions:
        score = float(session.score or 0)
        passed = score >= float(exam.passing_score or 70)

        if passed:
            passed_count += 1
        scores.append(score)

        results.append({
            "student_name": session.user.full_name or session.user.username,
            "student_class": getattr(session.user, "student_class", "-") or "-",
            "score": score,
            "passed": passed,
        })

    summary = {
        "average": sum(scores) / len(scores) if scores else 0,
        "highest": max(scores) if scores else 0,
        "lowest": min(scores) if scores else 0,
        "passed": passed_count,
        "failed": len(sessions) - passed_count,
        "pass_rate": (passed_count / len(sessions) * 100) if sessions else 0,
    }

    exam_date = exam.start_time.strftime("%d %B %Y") if exam.start_time else "N/A"
    pdf_bytes = generate_exam_results_pdf(
        exam_title=exam.title,
        exam_date=exam_date,
        results=results,
        summary=summary,
        creator_name=creator_name,
    )

    filename = f"hasil_ujian_{exam.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{exam_id}/sessions/{session_id}/certificate")
async def get_session_certificate(
    exam_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate completion certificate PDF for a passed exam session."""
    require_feature_enabled(
        settings.heavy_exports_active,
        "heavy_export",
        status_code=503,
        message="Sertifikat PDF sedang dinonaktifkan selama mode ujian/puncak.",
    )
    from app.core.pdf_generator import REPORTLAB_AVAILABLE, generate_certificate_pdf

    if not REPORTLAB_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="PDF export tidak tersedia. Install ReportLab: pip install reportlab",
        )

    stmt = (
        select(ExamSession)
        .where(ExamSession.id == session_id, ExamSession.exam_id == exam_id)
        .options(selectinload(ExamSession.user), selectinload(ExamSession.exam))
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

    if _is_exam_participant_role(current_user.role) and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tidak memiliki akses")
    elif not _is_exam_participant_role(current_user.role):
        await _enforce_exam_owner_or_admin_access(
            db,
            current_user,
            session.exam.creator_id,
            allow_pengawas=True,
        )

    passing_score = float(session.exam.passing_score or 70)
    score = float(session.score or 0)

    if score < passing_score:
        raise HTTPException(
            status_code=400,
            detail=f"Sertifikat hanya tersedia untuk yang lulus (skor >= {passing_score})",
        )

    cert_data = f"{session.id}-{session.user_id}-{session.exam_id}"
    certificate_id = hashlib.sha256(cert_data.encode()).hexdigest()[:12].upper()

    completion_date = session.end_time.strftime("%d %B %Y") if session.end_time else "N/A"

    pdf_bytes = generate_certificate_pdf(
        student_name=session.user.full_name or session.user.username,
        exam_title=session.exam.title,
        score=score,
        completion_date=completion_date,
        certificate_id=f"CERT-{certificate_id}",
    )

    filename = f"sertifikat_{session.user.username}_{session.exam.title.replace(' ', '_')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
