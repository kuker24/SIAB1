from pathlib import Path


USERS_SOURCE = Path("app/api/users.py").read_text(encoding="utf-8")


def test_user_id_routes_use_int_converter_to_avoid_batch_delete_shadowing() -> None:
    assert '@router.get("/{user_id:int}", response_model=UserResponse)' in USERS_SOURCE
    assert '@router.put("/{user_id:int}", response_model=UserResponse)' in USERS_SOURCE
    assert '@router.delete("/{user_id:int}", status_code=status.HTTP_204_NO_CONTENT)' in USERS_SOURCE


def test_batch_delete_route_still_defined() -> None:
    assert '@router.delete("/batch-delete")' in USERS_SOURCE
