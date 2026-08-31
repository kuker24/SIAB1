import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from app.api import exams
from app.api.exam_crud import regenerate_exam_token, toggle_publish_exam
from app.main import not_found_handler


ROOT = Path(__file__).resolve().parents[1]


class _DatabaseMustNotBeUsed:
    async def execute(self, _statement):
        raise AssertionError("authorization must be checked before database access")


class _EmptyExamDatabase:
    async def execute(self, _statement):
        return SimpleNamespace(first=lambda: None)


def _pengawas() -> SimpleNamespace:
    return SimpleNamespace(id=41, role="gurupengawas", job_title="Pengawas")


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [toggle_publish_exam, regenerate_exam_token])
async def test_pengawas_cannot_mutate_exam_publication_or_token(endpoint) -> None:
    with pytest.raises(HTTPException) as exc:
        await endpoint(
            exam_id=7,
            current_user=_pengawas(),
            db=_DatabaseMustNotBeUsed(),
        )

    assert exc.value.status_code == 403
    assert "Pengawas" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_unknown_six_character_exam_token_returns_domain_error(monkeypatch) -> None:
    async def allow_attempt(_limiter, _key):
        return True, 4

    monkeypatch.setattr(exams, "check_rate_limit", allow_attempt)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/exams/join",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )

    with pytest.raises(HTTPException) as exc:
        await exams.join_exam_by_token(
            request=exams.JoinExamRequest(token="ZZZZZZ"),
            raw_request=request,
            current_user=SimpleNamespace(id=51, role="student"),
            db=_EmptyExamDatabase(),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Token ujian tidak valid"


@pytest.mark.asyncio
async def test_api_not_found_handler_preserves_domain_error() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/exams/join",
            "query_string": b"",
            "headers": [],
        }
    )

    response = await not_found_handler(
        request,
        HTTPException(status_code=404, detail="Token ujian tidak valid"),
    )

    assert response.status_code == 404
    assert json.loads(response.body) == {"detail": "Token ujian tidak valid"}


@pytest.mark.asyncio
async def test_page_not_found_handler_stays_generic() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/control/dashboard",
            "query_string": b"",
            "headers": [],
        }
    )

    response = await not_found_handler(
        request,
        HTTPException(status_code=404, detail="Internal template name"),
    )

    assert json.loads(response.body) == {"detail": "Halaman tidak ditemukan"}


def test_pengawas_exam_table_has_no_mutation_controls() -> None:
    template = (ROOT / "templates/admin/exams.html").read_text(encoding="utf-8")

    assert "unpublishExamForPengawas" not in template
    assert 'data-pengawas-readonly="true"' in template
