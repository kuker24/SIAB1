from pathlib import Path


SECURITY_MIDDLEWARE_SOURCE = Path("app/middleware/security.py").read_text(encoding="utf-8")
MAIN_SOURCE = Path("app/main.py").read_text(encoding="utf-8")


def test_range_header_guard_middleware_exists_and_strips_invalid_range() -> None:
    assert "class RangeHeaderGuardMiddleware" in SECURITY_MIDDLEWARE_SOURCE
    assert "_SIMPLE_BYTE_RANGE_RE" in SECURITY_MIDDLEWARE_SOURCE
    assert "if key != b\"range\"" in SECURITY_MIDDLEWARE_SOURCE


def test_main_registers_range_header_guard_before_security_headers() -> None:
    range_guard_call = "app.add_middleware(RangeHeaderGuardMiddleware)"
    security_headers_call = "app.add_middleware(SecurityHeadersMiddleware)"
    assert range_guard_call in MAIN_SOURCE
    assert security_headers_call in MAIN_SOURCE
    assert MAIN_SOURCE.index(range_guard_call) < MAIN_SOURCE.index(security_headers_call)
