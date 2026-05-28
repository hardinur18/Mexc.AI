from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib.parse import quote


def compact_json(data: dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def canonical_query(params: dict[str, Any] | None) -> str:
    if not params:
        return ""

    parts: list[str] = []
    for key in sorted(params):
        value = params[key]
        if value is None:
            continue
        encoded = quote(str(value), safe="")
        parts.append(f"{key}={encoded}")
    return "&".join(parts)


def sign(access_key: str, secret_key: str, request_time: str, parameter_string: str = "") -> str:
    payload = f"{access_key}{request_time}{parameter_string}"
    return hmac.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

