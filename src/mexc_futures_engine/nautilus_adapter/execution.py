from __future__ import annotations

import time
from typing import Any

from ..client import MexcFuturesClient
from ..execution_reports import build_execution_report_bundle
from ..private_stream import parse_private_ws_message
from ..reconciliation import build_reconciliation_report
from ..settings import MexcSettings
from ..ws import MexcWebSocketClient
from .config import MexcFuturesAdapterConfig


class LiveMutationUnavailable(RuntimeError):
    pass


class MexcFuturesExecutionClientBoundary:
    """Read-only execution boundary for reports, private stream, and reconciliation."""

    def __init__(
        self,
        client: MexcFuturesClient,
        settings: MexcSettings,
        config: MexcFuturesAdapterConfig | None = None,
    ):
        self.client = client
        self.settings = settings
        self.config = config or MexcFuturesAdapterConfig()
        self.config.assert_read_only_safe()

    def generate_execution_reports(
        self,
        *,
        symbol: str,
        currency: str | None = None,
        history_limit: int | None = None,
        deals_limit: int | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        currency = (currency or self.config.default_currency).upper()
        history_limit = history_limit or self.config.default_history_limit
        deals_limit = deals_limit or self.config.default_deals_limit
        snapshot = self._rest_snapshot(symbol=symbol, currency=currency, history_limit=history_limit)
        return build_execution_report_bundle(
            asset_response=snapshot["singleAsset"],
            positions_response=snapshot["positions"],
            open_orders_response=snapshot["openOrders"],
            history_orders_response=snapshot["recentOrders"],
            order_deals_response=self.client.order_deals(symbol, page_num=1, page_size=deals_limit),
            symbol=symbol,
            currency=currency,
            include_raw=include_raw,
        )

    def stream_private(
        self,
        *,
        messages: int | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        requested_messages = messages or self.config.default_private_ws_messages
        if requested_messages <= 0:
            raise ValueError("messages must be positive")

        raw_messages: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        ws_client = MexcWebSocketClient(self.settings)
        for message in ws_client.stream_private(messages=requested_messages):
            raw_messages.append(message)
            events.append(parse_private_ws_message(message).to_dict(include_raw=include_raw))

        event_counts: dict[str, int] = {}
        for event in events:
            event_type = str(event.get("eventType"))
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        return {
            "timestamp": int(time.time() * 1000),
            "boundary": "MexcFuturesExecutionClientBoundary",
            "requestedMessages": requested_messages,
            "rawMessageCount": len(raw_messages),
            "eventCount": len(events),
            "eventCounts": event_counts,
            "events": events,
        }

    def reconcile_startup(
        self,
        *,
        symbol: str,
        currency: str | None = None,
        history_limit: int | None = None,
        deals_limit: int | None = None,
        private_ws_messages: int | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        currency = (currency or self.config.default_currency).upper()
        history_limit = history_limit or self.config.default_history_limit
        deals_limit = deals_limit or self.config.default_deals_limit
        snapshot = self._rest_snapshot(symbol=symbol, currency=currency, history_limit=history_limit)
        execution_bundle = build_execution_report_bundle(
            asset_response=snapshot["singleAsset"],
            positions_response=snapshot["positions"],
            open_orders_response=snapshot["openOrders"],
            history_orders_response=snapshot["recentOrders"],
            order_deals_response=self.client.order_deals(symbol, page_num=1, page_size=deals_limit),
            symbol=symbol,
            currency=currency,
            include_raw=include_raw,
        )
        private_ws_payload = self.stream_private(messages=private_ws_messages, include_raw=include_raw)
        return build_reconciliation_report(
            rest_snapshot=snapshot,
            execution_bundle=execution_bundle,
            private_ws_payload=private_ws_payload,
            symbol=symbol,
            currency=currency,
            include_raw=include_raw,
        )

    def submit_order(self, *_args: Any, **_kwargs: Any) -> None:
        raise LiveMutationUnavailable("live submit_order is intentionally unavailable in this adapter phase")

    def cancel_order(self, *_args: Any, **_kwargs: Any) -> None:
        raise LiveMutationUnavailable("live cancel_order is intentionally unavailable in this adapter phase")

    def cancel_all_orders(self, *_args: Any, **_kwargs: Any) -> None:
        raise LiveMutationUnavailable("live cancel_all_orders is intentionally unavailable in this adapter phase")

    def _rest_snapshot(
        self,
        *,
        symbol: str,
        currency: str,
        history_limit: int,
    ) -> dict[str, Any]:
        assets = self.client.all_assets()
        single_asset = self.client.asset(currency)
        global_positions = self.client.open_positions()
        positions = self.client.open_positions(symbol)
        open_orders = self.client.current_orders(page_num=1, page_size=100)
        historical_orders = self.client.historical_orders(symbol=symbol, page_num=1, page_size=history_limit)
        global_position_rows = _rows(global_positions)
        position_rows = _rows(positions)
        open_order_rows = _rows(open_orders)
        target_open_order_rows = [
            row for row in open_order_rows if str(row.get("symbol") or "").upper() == symbol.upper()
        ]
        recent_order_rows = _rows(historical_orders)

        return {
            "timestamp": int(time.time() * 1000),
            "symbol": symbol.upper(),
            "currency": currency.upper(),
            "summary": {
                "assetCount": len(_rows(assets)),
                "openPositionCount": len(position_rows),
                "openOrderCount": len(open_order_rows),
                "targetOpenPositionCount": len(position_rows),
                "targetOpenOrderCount": len(target_open_order_rows),
                "globalOpenPositionCount": len(global_position_rows),
                "globalOpenOrderCount": len(open_order_rows),
                "recentOrderCount": len(recent_order_rows),
                "singleAssetSuccess": bool(single_asset.get("success")),
            },
            "assets": assets,
            "singleAsset": single_asset,
            "globalPositions": global_positions,
            "positions": positions,
            "openOrders": open_orders,
            "recentOrders": historical_orders,
        }


def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("resultList"), list):
        return [row for row in data["resultList"] if isinstance(row, dict)]
    return []
