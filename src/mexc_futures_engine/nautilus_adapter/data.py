from __future__ import annotations

import time
from typing import Any

from ..market_data import MarketDataParser
from ..settings import MexcSettings
from ..ws import MexcWebSocketClient
from ..ws import deal_subscription
from ..ws import depth_subscription
from ..ws import ticker_subscription
from .config import MexcFuturesAdapterConfig


PUBLIC_SUBSCRIPTIONS = {
    "ticker": ticker_subscription,
    "deal": deal_subscription,
    "depth": depth_subscription,
}


class MexcFuturesDataClientBoundary:
    """Read-only market data boundary for Nautilus-style Quote/Trade/Book specs."""

    def __init__(
        self,
        settings: MexcSettings,
        config: MexcFuturesAdapterConfig | None = None,
    ):
        self.settings = settings
        self.config = config or MexcFuturesAdapterConfig()
        self.config.assert_read_only_safe()

    def stream_public(
        self,
        *,
        channel: str,
        symbol: str,
        messages: int | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        if channel not in PUBLIC_SUBSCRIPTIONS:
            allowed = ", ".join(sorted(PUBLIC_SUBSCRIPTIONS))
            raise ValueError(f"unsupported public channel {channel!r}; allowed: {allowed}")

        requested_messages = messages or self.config.default_market_messages
        if requested_messages <= 0:
            raise ValueError("messages must be positive")

        raw_messages: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        ws_client = MexcWebSocketClient(self.settings)
        parser = MarketDataParser()
        for message in ws_client.stream_public(PUBLIC_SUBSCRIPTIONS[channel](symbol), messages=requested_messages):
            raw_messages.append(message)
            events.extend(event.to_dict() for event in parser.parse_public_ws_message(message))

        event_counts: dict[str, int] = {}
        for event in events:
            event_type = str(event.get("eventType"))
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        payload: dict[str, Any] = {
            "timestamp": int(time.time() * 1000),
            "boundary": "MexcFuturesDataClientBoundary",
            "symbol": symbol.upper(),
            "channel": channel,
            "requestedMessages": requested_messages,
            "rawMessageCount": len(raw_messages),
            "eventCount": len(events),
            "eventCounts": event_counts,
            "events": events,
        }
        if include_raw:
            payload["rawMessages"] = raw_messages
        return payload
