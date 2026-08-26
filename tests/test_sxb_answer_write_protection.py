from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core import cache
from app.core import request_security_memo
from app.middleware.seb_validation import validate_seb_headers
from app.middleware.sxb_enforcer import SXBEnforcerMiddleware

SXB_ENFORCER_SOURCE = Path("app/middleware/sxb_enforcer.py").read_text(encoding="utf-8")


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


@pytest.mark.parametrize(
    "path",
    [
        "/api/exams/auto-save",
        "/api/exams/auto-save-batch",
        "/api/exams/answer-journal/sync",
        "/api/exams/1/start",
        "/api/exams/submit-answer",
        "/api/exams/submit",
    ],
)
def test_secure_exam_client_passes_sxb_middleware(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    app = FastAPI()
    app.add_middleware(SXBEnforcerMiddleware, enforce_sxb=True)

    @app.post(path)
    @app.get(path)
    async def exam_route() -> dict[str, bool]:
        return {"ok": True}

    monkeypatch.setattr(
        cache,
        "is_developer_mode_enabled",
        AsyncMock(return_value=False),
    )

    response = TestClient(app).post(path, headers={"User-Agent": "SXB-Client/2.0"})
    assert response.status_code == 200


def test_sxb_enforcer_drops_unreachable_auth_strict_paths() -> None:
    assert "strict_endpoints" not in SXB_ENFORCER_SOURCE
    assert '"/api/auth/login"' not in SXB_ENFORCER_SOURCE


def _http_request() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/exams/1/start",
            "raw_path": b"/api/exams/1/start",
            "query_string": b"",
            "headers": [(b"user-agent", b"SXB-Client/2.0")],
            "client": ("127.0.0.1", 123),
            "server": ("test", 80),
        }
    )


@pytest.mark.asyncio
async def test_developer_mode_and_signatures_are_memoized_per_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _http_request()
    developer_mode = AsyncMock(return_value=True)
    signatures = AsyncMock(return_value=["abc"])
    monkeypatch.setattr(cache, "is_developer_mode_enabled", developer_mode)
    monkeypatch.setattr(cache, "get_allowed_signatures", signatures)

    assert await request_security_memo.developer_mode_enabled(request) is True
    assert await request_security_memo.developer_mode_enabled(request) is True
    assert await request_security_memo.allowed_signatures(request) == ["abc"]
    assert await request_security_memo.allowed_signatures(request) == ["abc"]
    assert developer_mode.await_count == 1
    assert signatures.await_count == 1


@pytest.mark.asyncio
async def test_validate_seb_headers_reuses_developer_mode_memo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _http_request()
    developer_mode = AsyncMock(return_value=True)
    monkeypatch.setattr(cache, "is_developer_mode_enabled", developer_mode)
    monkeypatch.setattr(
        "app.middleware.seb_validation._log_security_event",
        AsyncMock(return_value=None),
    )

    assert await validate_seb_headers(request, 1, db=None, require_seb=True) is True
    assert await validate_seb_headers(request, 1, db=None, require_seb=True) is True
    assert developer_mode.await_count == 1
