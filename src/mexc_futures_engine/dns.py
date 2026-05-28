from __future__ import annotations

from contextlib import contextmanager
import json
import socket
from typing import Any, Iterator
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class DnsError(RuntimeError):
    pass


def resolve_a_records_doh(hostname: str, doh_url: str) -> list[str]:
    query = urlencode({"name": hostname, "type": "A"})
    url = f"{doh_url}?{query}"
    request = Request(url, headers={"accept": "application/dns-json"}, method="GET")
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:
        raise DnsError(f"DoH lookup failed for {hostname}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DnsError(f"DoH lookup returned non-JSON for {hostname}: {raw[:300]}") from exc

    answers = payload.get("Answer") or []
    records = [item.get("data") for item in answers if item.get("type") == 1 and item.get("data")]
    if not records:
        raise DnsError(f"DoH lookup returned no A records for {hostname}: {payload}")
    return records


@contextmanager
def override_getaddrinfo(overrides: dict[str, str]) -> Iterator[None]:
    original_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any):
        replacement = overrides.get(host)
        if replacement:
            return original_getaddrinfo(replacement, port, *args, **kwargs)
        return original_getaddrinfo(host, port, *args, **kwargs)

    socket.getaddrinfo = patched_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo

