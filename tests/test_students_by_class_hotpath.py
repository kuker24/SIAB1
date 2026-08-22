from pathlib import Path


USERS_SOURCE = Path("app/api/users.py").read_text(encoding="utf-8")


def test_students_by_class_uses_cache_and_column_projection() -> None:
    assert 'cache_key = ("students_by_class", current_user.role.lower(), normalized_class.lower())' in USERS_SOURCE
    assert "redis_cached_users = await _get_cached_users_list_redis(cache_key)" in USERS_SOURCE
    assert "students = [dict(row) for row in result.mappings().all()]" in USERS_SOURCE
