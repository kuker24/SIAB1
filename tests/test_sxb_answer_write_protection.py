from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import cache
from app.middleware.sxb_enforcer import SXBEnforcerMiddleware


@pytest.mark.parametrize(
    "path",
    [
        "/api/exams/auto-save",
        "/api/exams/auto-save-batch",
        "/api/exams/answer-journal/sync",
    ],
)
def test_answer_write_routes_require_secure_exam_client(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    app = FastAPI()
    app.add_middleware(SXBEnforcerMiddleware, enforce_sxb=True)

    @app.post(path)
    async def answer_write() -> dict[str, bool]:
        return {"ok": True}

    monkeypatch.setattr(
        cache,
        "is_developer_mode_enabled",
        AsyncMock(return_value=False),
    )

    response = TestClient(app).post(path, headers={"User-Agent": "Mozilla/5.0"})

    assert response.status_code == 403
