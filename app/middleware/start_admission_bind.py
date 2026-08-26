from typing import Callable

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.start_db_admission import bind_start_admission, is_exam_start_path


class StartAdmissionBindMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "POST" and is_exam_start_path(request.url.path):
            async with bind_start_admission(request):
                return await call_next(request)
        return await call_next(request)
