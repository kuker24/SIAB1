#!/usr/bin/env python3
"""Create the first admin account from explicit one-time environment input."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.dialects.postgresql import insert

from app.core.security import get_password_hash
from app.database import async_session_write
from app.models.user import User


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,100}$")


def load_bootstrap_input(environ: Mapping[str, str]) -> tuple[str, str, str]:
    username = environ.get("SIAB1_BOOTSTRAP_ADMIN_USERNAME", "admin").strip()
    password = environ.get("SIAB1_BOOTSTRAP_ADMIN_PASSWORD", "")
    full_name = environ.get("SIAB1_BOOTSTRAP_ADMIN_FULL_NAME", "System Administrator").strip()

    if not password:
        raise ValueError("SIAB1_BOOTSTRAP_ADMIN_PASSWORD is required")
    if len(password) < 12:
        raise ValueError("SIAB1_BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("SIAB1_BOOTSTRAP_ADMIN_PASSWORD must be at most 72 UTF-8 bytes")
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("SIAB1_BOOTSTRAP_ADMIN_USERNAME has an invalid format")
    if not full_name or len(full_name) > 255:
        raise ValueError("SIAB1_BOOTSTRAP_ADMIN_FULL_NAME must contain 1-255 characters")
    return username, password, full_name


async def create_admin(username: str, password: str, full_name: str) -> bool:
    statement = (
        insert(User)
        .values(
            username=username,
            password_hash=get_password_hash(password),
            full_name=full_name,
            role="admin",
            student_class=None,
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=[User.username])
        .returning(User.id)
    )
    async with async_session_write() as db:
        result = await db.execute(statement)
        created_id = result.scalar_one_or_none()
        await db.commit()
    return created_id is not None


def main() -> int:
    try:
        username, password, full_name = load_bootstrap_input(os.environ)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        created = asyncio.run(create_admin(username, password, full_name))
    except Exception:
        print("Admin bootstrap failed; inspect application logs and database health.", file=sys.stderr)
        return 1

    if created:
        print(f"Admin account created: {username}")
    else:
        print(f"Admin account already exists: {username}; no credentials changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
