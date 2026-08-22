"""
Subjects (Bidang Studi) API endpoints.
"""
import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
import logging

from app.database import get_db_read, get_db_write
from app.models.user import User
from app.models.subject import Subject
from app.core.security import get_current_user, get_current_teacher
from app.core.roles import is_admin_scope_role

router = APIRouter(prefix="/api/subjects", tags=["Subjects"])
logger = logging.getLogger(__name__)

SUBJECTS_CACHE_TTL_SECONDS = 300
_subjects_cache: dict = {
    "expires_at": 0.0,
    "data": None
}


# Schemas
class SubjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class SubjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


def _get_cached_subjects() -> Optional[List[dict]]:
    cache_data = _subjects_cache.get("data")
    expires_at = _subjects_cache.get("expires_at", 0.0)
    if cache_data is None:
        return None
    if time.monotonic() >= expires_at:
        _subjects_cache["data"] = None
        _subjects_cache["expires_at"] = 0.0
        return None
    return cache_data


def _set_cached_subjects(subjects: List[dict]) -> None:
    _subjects_cache["data"] = subjects
    _subjects_cache["expires_at"] = time.monotonic() + SUBJECTS_CACHE_TTL_SECONDS


def _invalidate_subjects_cache() -> None:
    _subjects_cache["data"] = None
    _subjects_cache["expires_at"] = 0.0


# Helper function to seed default subjects
async def seed_default_subjects(db: AsyncSession):
    """Seed database with default subjects (replace existing)."""
    # Delete all existing subjects to ensure full sync with the new list
    await db.execute(delete(Subject))
    await db.commit()

    logger.info("📚 Seeding new subject list (total replacement)...")

    default_subjects = [
        ("Al-Qur'an Hadis", "Mata Pelajaran Al-Qur'an Hadis"),
        ("Akidah Akhlak", "Mata Pelajaran Akidah Akhlak"),
        ("Fikih", "Mata Pelajaran Fikih"),
        ("Sejarah Kebudayaan Islam (SKI)", "Sejarah Kebudayaan Islam"),
        ("Pendidikan Pancasila", "Pendidikan Pancasila"),
        ("Bahasa Indonesia", "Bahasa Indonesia"),
        ("Bahasa Arab", "Bahasa Arab"),
        ("Matematika", "Matematika"),
        ("Bahasa Inggris", "Bahasa Inggris"),
        ("Sejarah", "Sejarah"),
        ("Pendidikan Jasmani, Olahraga, dan Kesehatan (PJOK)", "PJOK"),
        ("Seni Budaya", "Seni Budaya"),
        ("Informatika", "Informatika"),
        ("Prakarya", "Prakarya"),
        ("Biologi", "Biologi"),
        ("Fisika", "Fisika"),
        ("Kimia", "Kimia"),
        ("Ekonomi", "Ekonomi"),
        ("Sosiologi", "Sosiologi"),
        ("Geografi", "Geografi"),
        ("Antropologi", "Antropologi"),
        ("Matematika Lanjutan", "Matematika Lanjutan"),
        ("Bahasa Arab Tingkat Lanjut", "Bahasa Arab Tingkat Lanjut"),
        ("Tafsir", "Tafsir"),
        ("Ushul Fikih", "Ushul Fikih"),
        ("Ilmu Hadist", "Ilmu Hadist"),
        ("Budaya Melayu Riau (BMR)", "Budaya Melayu Riau"),
    ]

    for name, desc in default_subjects:
        subject = Subject(name=name, description=desc, creator_id=1)
        db.add(subject)

    await db.commit()
    logger.info(f"✅ Seeded {len(default_subjects)} default subjects")


# Endpoints
@router.get("", response_model=List[SubjectResponse])
async def list_subjects(
    db: AsyncSession = Depends(get_db_read),
    current_user: User = Depends(get_current_user)
):
    """Get all subjects (available to all authenticated users)."""
    cached_subjects = _get_cached_subjects()
    if cached_subjects is not None:
        return cached_subjects

    result = await db.execute(
        select(Subject.id, Subject.name, Subject.description)
        .order_by(Subject.name)
    )
    subjects = result.all()

    response_payload = [
        {
            "id": subject.id,
            "name": subject.name,
            "description": subject.description
        }
        for subject in subjects
    ]

    _set_cached_subjects(response_payload)

    logger.info(f"📚 Returning {len(response_payload)} subjects to user {current_user.username}")
    return response_payload


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    subject_data: SubjectCreate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_write)
):
    """Create a new subject (teacher/admin only)."""
    # Check if subject already exists (case insensitive)
    existing = await db.execute(
        select(Subject).where(func.lower(Subject.name) == func.lower(subject_data.name))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Bidang studi dengan nama ini sudah ada"
        )

    subject = Subject(
        name=subject_data.name,
        description=subject_data.description,
        creator_id=current_user.id
    )
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    _invalidate_subjects_cache()

    return subject


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
    subject_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db_write)
):
    """Delete a subject (admin only or creator)."""
    result = await db.execute(
        select(Subject).where(Subject.id == subject_id)
    )
    subject = result.scalar_one_or_none()

    if not subject:
        raise HTTPException(status_code=404, detail="Bidang studi tidak ditemukan")

    # Only admin or creator can delete
    if not is_admin_scope_role(current_user.role) and subject.creator_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Anda tidak memiliki akses untuk menghapus bidang studi ini"
        )

    await db.delete(subject)
    await db.commit()
    _invalidate_subjects_cache()

    return None
