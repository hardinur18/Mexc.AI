from __future__ import annotations

import gzip
import json
import time
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

from .candles import mexc_candle_interval
from .dns import override_getaddrinfo, resolve_a_records_doh
from .settings import MexcSettings
from .signing import sign


DEFAULT_WS_URL = "wss://contract.mexc.com/edge"


class MexcWebSocketError(RuntimeError):
    pass


@dataclass(frozen=True)
class WsSubscription:
    method: str
    param: dict[str, Any]
    gzip: bool = False

    def to_message(self) -> dict[str, Any]:
        return {"method": self.method, "param": self.param, "gzip": self.gzip}


def ticker_subscription(symbol: str) -> WsSubscription:
    return WsSubscription("sub.ticker", {"symbol": symbol.upper()})


def deal_subscription(symbol: str) -> WsSubscription:
    return WsSubscription("sub.deal", {"symbol": symbol.upper(), "compress": False})


def depth_subscription(symbol: str) -> WsSubscription:
    return WsSubscription("sub.depth", {"symbol": symbol.upper()})


def kline_subscription(symbol: str, interval: str) -> WsSubscription:
    return WsSubscription("sub.kline", {"symbol": symbol.upper(), "interval": mexc_candle_interval(interval)})


def build_ping_message() -> dict[str, str]:
    return {"method": "ping"}


def build_private_login_message(settings: MexcSettings) -> dict[str, Any]:
    if not settings.access_key or not settings.secret_key:
        raise MexcWebSocketError("MEXC_ACCESS_KEY and MEXC_SECRET_KEY are required for private WebSocket login")

    req_time = str(int(time.time() * 1000))
    return {
        "method": "login",
        "param": {
            "apiKey": settings.access_key,
            "reqTime": req_time,
            "signature": sign(settings.access_key, settings.secret_key, req_time, ""),
        },
    }


def build_private_filter_message(filters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"method": "personal.filter", "param": {"filters": filters or []}}


def decode_ws_payload(payload: str | bytes) -> dict[str, Any]:
    if isinstance(payload, bytes):
        try:
            payload = gzip.decompress(payload).decode("utf-8")
        except OSError:
            payload = payload.decode("utf-8")
    return json.loads(payload)


class MexcWebSocketClient:
    def __init__(self, settings: MexcSettings, url: str = DEFAULT_WS_URL):
        self.settings = settings
        self.url = url
        self._dns_cache: dict[str, str] = {}

    def stream_public(self, subscription: WsSubscription, *, messages: int = 5) -> Iterable[dict[str, Any]]:
        ws = self._connect()
        try:
            ws.send(json.dumps(subscription.to_message(), separators=(",", ":")))
            yield from self._read_messages(ws, messages=messages)
        finally:
            ws.close()

    def stream_private(self, *, messages: int = 5) -> Iterable[dict[str, Any]]:
        ws = self._connect()
        try:
            ws.send(json.dumps(build_private_login_message(self.settings), separators=(",", ":")))
            ws.send(json.dumps(build_private_filter_message(), separators=(",", ":")))
            yield from self._read_messages(ws, messages=messages)
        finally:
            ws.close()

    def _connect(self):
        try:
            import websocket
        except ImportError as exc:
            raise MexcWebSocketError(
                "Missing dependency websocket-client. Run: python -m pip install -e ."
            ) from exc

        try:
            with self._dns_context():
                return websocket.create_connection(self.url, timeout=15)
        except Exception as exc:
            raise MexcWebSocketError(f"WebSocket connection failed: {exc}") from exc

    def _read_messages(self, ws, *, messages: int) -> Iterable[dict[str, Any]]:
        seen = 0
        last_ping = time.monotonic()
        while seen < messages:
            if time.monotonic() - last_ping > 15:
                ws.send(json.dumps(build_ping_message(), separators=(",", ":")))
                last_ping = time.monotonic()

            try:
                raw = ws.recv()
                decoded = decode_ws_payload(raw)
            except Exception as exc:
                if seen > 0 and "timed out" in str(exc).lower():
                    return
                raise MexcWebSocketError(f"WebSocket receive failed: {exc}") from exc

            seen += 1
            yield decoded

    def _dns_context(self):
        host = urlparse(self.url).hostname
        if not self.settings.use_doh_dns or not host or not host.endswith("mexc.com"):
            return override_getaddrinfo({})
        cached = self._dns_cache.get(host)
        if not cached:
            cached = resolve_a_records_doh(host, self.settings.doh_url)[0]
            self._dns_cache[host] = cached
        return override_getaddrinfo({host: cached})
