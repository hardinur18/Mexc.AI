"""
MEXC Futures WebSocket realtime ticker client.

Subscribes to `push.tickers` push channel (all tickers in one stream)
and maintains an in-process price cache. Used by cascade orchestrator
for instant SL/TP triggering instead of 6s REST polling.

Endpoint: wss://contract.mexc.com/edge
Sub message: {"method":"sub.tickers","param":{}}
Push message: {"channel":"push.tickers","data":[{"symbol":"BTC_USDT","fairPrice":..., "lastPrice":..., ...}, ...]}

Reconnects on disconnect with exponential backoff.
Uses DoH override for ISP DNS bypass (same as REST client).
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from typing import Any

# Phase 16: WS disabled by default — global socket.getaddrinfo patch caused
# race conditions with concurrent REST calls. Set MEXC_WS_ENABLED=1 to opt in.
# Cascade orchestrator gracefully falls back to REST tickers (cached 30s).
MEXC_WS_ENABLED = os.environ.get("MEXC_WS_ENABLED", "0") == "1"

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore

try:
    from mexc_futures_engine.dns import resolve_a_records_doh
except ImportError:
    resolve_a_records_doh = None  # type: ignore


WS_URL = "wss://contract.mexc.com/edge"
WS_HOST = "contract.mexc.com"
DOH_URL = "https://1.1.1.1/dns-query"
PING_INTERVAL_SEC = 15
RECONNECT_MIN_SEC = 2
RECONNECT_MAX_SEC = 60


class MexcWsClient:
    """Singleton MEXC WS ticker client with in-process price cache."""

    def __init__(self):
        # cache: symbol -> {fair_price, last_price, ts_ms, volume_24h}
        self._cache: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = False
        self._last_message_ts: float = 0
        self._resolved_ip: str | None = None
        self._stats = {"messages": 0, "connects": 0, "errors": 0}

    # ─── Public API ───
    def start(self) -> None:
        if self._running or websockets is None or not MEXC_WS_ENABLED:
            return
        self._running = True
        self._thread = threading.Thread(target=self._thread_runner, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def get_price(self, symbol: str) -> float | None:
        """Get latest fair price for symbol, or None if not cached."""
        with self._lock:
            entry = self._cache.get(symbol)
            if not entry:
                return None
            # Stale check: if no update >30s, treat as stale
            if (time.time() * 1000 - entry.get("ts_ms", 0)) > 30000:
                return None
            return entry.get("fair_price") or entry.get("last_price")

    def get_ticker(self, symbol: str) -> dict | None:
        """Full ticker info or None."""
        with self._lock:
            return self._cache.get(symbol)

    def status(self) -> dict:
        with self._lock:
            cache_size = len(self._cache)
        return {
            "connected": self._connected,
            "cache_size": cache_size,
            "last_message_age_sec": (
                round(time.time() - self._last_message_ts, 1)
                if self._last_message_ts else None
            ),
            "stats": dict(self._stats),
        }

    # ─── Internal ───
    def _thread_runner(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception as e:
            print(f"[ws_client] thread exited: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass

    async def _main(self) -> None:
        backoff = RECONNECT_MIN_SEC
        while self._running:
            try:
                await self._run_once()
                backoff = RECONNECT_MIN_SEC  # reset on clean close
            except Exception as e:
                self._stats["errors"] += 1
                print(f"[ws_client] connection error: {type(e).__name__}: {e}")
                self._connected = False
            if not self._running:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_SEC)

    async def _run_once(self) -> None:
        # Resolve via DoH (ISP DNS hijack bypass)
        if not self._resolved_ip and resolve_a_records_doh:
            try:
                ips = resolve_a_records_doh(WS_HOST, DOH_URL)
                if ips:
                    self._resolved_ip = ips[0]
            except Exception as e:
                print(f"[ws_client] DoH resolve failed: {e}")

        # Patch socket.getaddrinfo to use resolved IP if available
        original_getaddrinfo = socket.getaddrinfo

        def patched_getaddrinfo(host, port, *args, **kwargs):
            if host == WS_HOST and self._resolved_ip:
                return original_getaddrinfo(self._resolved_ip, port, *args, **kwargs)
            return original_getaddrinfo(host, port, *args, **kwargs)

        socket.getaddrinfo = patched_getaddrinfo
        try:
            async with websockets.connect(
                WS_URL,
                server_hostname=WS_HOST,
                ping_interval=PING_INTERVAL_SEC,
                ping_timeout=10,
                close_timeout=5,
                open_timeout=10,
            ) as ws:
                self._connected = True
                self._stats["connects"] += 1
                # Subscribe to all tickers stream
                await ws.send(json.dumps({"method": "sub.tickers", "param": {}}))
                async for raw in ws:
                    if not self._running:
                        break
                    try:
                        self._handle_message(raw)
                    except Exception as e:
                        self._stats["errors"] += 1
                        print(f"[ws_client] message parse error: {e}")
        finally:
            socket.getaddrinfo = original_getaddrinfo
            self._connected = False

    def _handle_message(self, raw: Any) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            msg = json.loads(raw)
        except Exception:
            return
        self._last_message_ts = time.time()
        self._stats["messages"] += 1

        channel = msg.get("channel") or msg.get("c")
        data = msg.get("data") or msg.get("d")
        if not data:
            return

        # push.tickers: data is a LIST of ticker dicts
        # push.ticker: data is a SINGLE ticker dict
        items: list[dict]
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            return

        now_ms = int(time.time() * 1000)
        with self._lock:
            for t in items:
                if not isinstance(t, dict):
                    continue
                sym = t.get("symbol") or t.get("s")
                if not sym:
                    continue
                try:
                    fair = float(t.get("fairPrice") or t.get("fp") or 0) or None
                except Exception:
                    fair = None
                try:
                    last = float(t.get("lastPrice") or t.get("lp") or 0) or None
                except Exception:
                    last = None
                try:
                    vol24 = float(t.get("amount24") or t.get("a24") or 0)
                except Exception:
                    vol24 = 0
                if fair is None and last is None:
                    continue
                self._cache[sym] = {
                    "fair_price": fair,
                    "last_price": last,
                    "volume_24h": vol24,
                    "ts_ms": now_ms,
                }


# Module-level singleton
WS_CLIENT = MexcWsClient()
