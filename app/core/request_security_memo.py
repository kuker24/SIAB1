from typing import Any, Optional

from app.core import cache

_MEMO_ATTR = "_siab1_security_memo"


def _memo(request: Any) -> Optional[dict[str, Any]]:
    state = getattr(request, "state", None)
    if state is None:
        return None
    memo = getattr(state, _MEMO_ATTR, None)
    if memo is None:
        memo = {}
        setattr(state, _MEMO_ATTR, memo)
    return memo


async def developer_mode_enabled(request: Any = None) -> bool:
    memo = _memo(request)
    if memo is not None and "developer_mode" in memo:
        return bool(memo["developer_mode"])
    enabled = await cache.is_developer_mode_enabled()
    if memo is not None:
        memo["developer_mode"] = enabled
    return enabled


async def allowed_signatures(request: Any = None) -> list[str]:
    memo = _memo(request)
    if memo is not None and "allowed_signatures" in memo:
        cached = memo["allowed_signatures"]
        return list(cached) if isinstance(cached, list) else []
    signatures = await cache.get_allowed_signatures()
    if memo is not None:
        memo["allowed_signatures"] = signatures
    return signatures
