from pathlib import Path

from app.core.roles import can_manage_user_account


USERS_API_SOURCE = Path("app/api/users.py").read_text(encoding="utf-8")
USERS_UI_SOURCE = Path("templates/admin/users.html").read_text(encoding="utf-8")


def test_can_manage_user_account_enforces_developer_only_for_developer_targets() -> None:
    assert can_manage_user_account("developer", "developer") is True
    assert can_manage_user_account("admin", "developer") is False
    assert can_manage_user_account("admin", "teacher") is True


def test_update_user_checks_developer_target_before_mutating_profile_fields() -> None:
    fn = USERS_API_SOURCE.split("async def update_user(", 1)[1].split(
        "@router.delete",
        1,
    )[0]
    guard = "_assert_target_user_manageable(current_user.role, user.role)"
    assert guard in fn
    guard_idx = fn.index(guard)
    username_update_idx = fn.index("user.username = user_data.username")
    full_name_update_idx = fn.index("if user_data.full_name: user.full_name = user_data.full_name")
    password_update_idx = fn.index("user.password_hash = get_password_hash(user_data.password)")
    assert guard_idx < username_update_idx
    assert guard_idx < full_name_update_idx
    assert guard_idx < password_update_idx


def test_users_ui_hides_and_guards_developer_rows_for_non_developer_actor() -> None:
    assert "const canManageDeveloperAccount = u.role !== DEVELOPER_ROLE || isDeveloperActor();" in USERS_UI_SOURCE
    assert "if (user.role === DEVELOPER_ROLE && !isDeveloperActor()) {" in USERS_UI_SOURCE
    assert "Akun developer hanya dapat dikelola developer" in USERS_UI_SOURCE
