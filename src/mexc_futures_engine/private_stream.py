from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Any

from .nautilus_mapping import MEXC_VENUE


@dataclass(frozen=True)
class PrivateStreamEventSpec:
    event_type: str
    channel: str
    venue: str
    ts_event_ns: int
    ts_init_ns: int
    payload: dict[str, Any]
    raw: dict[str, Any]

    def to_dict(self, *, include_raw: bool = True) -> dict[str, Any]:
        data = asdict(self)
        raw = data.pop("raw")
        payload = {
            "eventType": data.pop("event_type"),
            "channel": data.pop("channel"),
            "venue": data.pop("venue"),
            "tsEventNs": data.pop("ts_event_ns"),
            "tsInitNs": data.pop("ts_init_ns"),
            "payload": data.pop("payload"),
        }
        if include_raw:
            payload["raw"] = raw
        return payload


def parse_private_ws_message(
    message: dict[str, Any],
    *,
    ts_init_ms: int | None = None,
) -> PrivateStreamEventSpec:
    channel = str(message.get("channel") or "")
    data = message.get("data")
    ts_event_ms = _as_int(message.get("ts")) or _now_ms()
    event_type = classify_private_channel(channel)

    payload: dict[str, Any] = {
        "source": "MEXC private WebSocket",
        "data": data,
    }
    if event_type == "ControlAck":
        payload["ok"] = data == "success"
        payload["method"] = channel.removeprefix("rs.")

    return PrivateStreamEventSpec(
        event_type=event_type,
        channel=channel,
        venue=MEXC_VENUE,
        ts_event_ns=ts_event_ms * 1_000_000,
        ts_init_ns=(ts_init_ms if ts_init_ms is not None else _now_ms()) * 1_000_000,
        payload=payload,
        raw=message,
    )


def classify_private_channel(channel: str) -> str:
    normalized = channel.lower()
    if normalized.startswith("rs."):
        return "ControlAck"
    if "account" in normalized or "asset" in normalized or "balance" in normalized:
        return "AccountUpdate"
    if "position" in normalized:
        return "PositionUpdate"
    if "order" in normalized:
        return "OrderUpdate"
    if "deal" in normalized or "fill" in normalized or "trade" in normalized:
        return "FillUpdate"
    return "PrivateUpdate"


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)
