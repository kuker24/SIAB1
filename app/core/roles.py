"""
Shared role constants and authorization helpers.
"""
from __future__ import annotations

from typing import Optional

ROLE_DEVELOPER = "developer"
ROLE_ADMIN = "admin"
ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ROLE_GURUPLUS = "guruplus"

ADMIN_SCOPE_ROLES = {ROLE_DEVELOPER, ROLE_ADMIN}
TEACHER_SCOPE_ROLES = {ROLE_DEVELOPER, ROLE_ADMIN, ROLE_TEACHER}
PARTICIPANT_ROLES = {ROLE_STUDENT, ROLE_GURUPLUS}


def normalize_role(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def is_developer_role(value: Optional[str]) -> bool:
    return normalize_role(value) == ROLE_DEVELOPER


def is_admin_scope_role(value: Optional[str]) -> bool:
    return normalize_role(value) in ADMIN_SCOPE_ROLES


def is_teacher_scope_role(value: Optional[str]) -> bool:
    return normalize_role(value) in TEACHER_SCOPE_ROLES


def is_participant_role(value: Optional[str]) -> bool:
    return normalize_role(value) in PARTICIPANT_ROLES


def can_assign_role(actor_role: Optional[str], target_role: Optional[str]) -> bool:
    actor = normalize_role(actor_role)
    target = normalize_role(target_role)
    if not target:
        return True
    if target in {ROLE_DEVELOPER, ROLE_GURUPLUS} and actor != ROLE_DEVELOPER:
        return False
    return actor in ADMIN_SCOPE_ROLES


def can_manage_user_account(actor_role: Optional[str], target_role: Optional[str]) -> bool:
    actor = normalize_role(actor_role)
    target = normalize_role(target_role)
    if actor not in ADMIN_SCOPE_ROLES:
        return False
    if target == ROLE_DEVELOPER and actor != ROLE_DEVELOPER:
        return False
    return True


def is_developer_exam_hidden_for_viewer(
    viewer_role: Optional[str],
    creator_role: Optional[str],
) -> bool:
    """
    Developer-authored exams are hidden from non-developer control-plane roles.
    """
    return normalize_role(creator_role) == ROLE_DEVELOPER and not is_developer_role(viewer_role)
