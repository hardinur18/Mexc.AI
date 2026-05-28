from __future__ import annotations

from decimal import Decimal, InvalidOperation
import time
from typing import Any


OPEN_STATUSES = {"OPEN"}
RECENT_EQUITY_WINDOW = 5


def build_paper_performance_report(
    ledger_report: dict[str, Any],
    *,
    initial_equity: Any | None = None,
) -> dict[str, Any]:
    """Build read-only paper performance metrics from a paper ledger report."""
    orders = _orders(ledger_report)
    priced_closed_orders = _priced_closed_orders(orders)
    unpriced_closed_orders = _unpriced_closed_orders(orders)
    open_count = len(_open_orders(orders))
    closed_pnls = [_priced_pnl(order) for order in priced_closed_orders]

    starting_equity = _initial_equity(ledger_report, initial_equity)
    curve = _raw_equity_curve_from_closed_orders(ledger_report, initial_equity=starting_equity)
    equity_trend = _recent_equity_trend(curve, window=RECENT_EQUITY_WINDOW)
    ending_equity = curve[-1]["equity"] if curve else starting_equity
    peak_equity = max([starting_equity, *[point["equity"] for point in curve]])
    max_drawdown = max([point["drawdown"] for point in curve], default=Decimal("0"))
    max_drawdown_pct = max(
        (point["drawdownPct"] for point in curve if point["drawdownPct"] is not None),
        default=_ratio(max_drawdown, starting_equity),
    )

    wins = [pnl for pnl in closed_pnls if pnl > 0]
    losses = [pnl for pnl in closed_pnls if pnl < 0]
    gross_win = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))
    closed_count = len(priced_closed_orders)
    warnings = [
        "paper performance is derived from priced closed paper ledger orders only",
        "paper performance is read-only and never submits exchange orders",
    ]
    if unpriced_closed_orders:
        warnings.append(
            f"skipped {len(unpriced_closed_orders)} unpriced closed paper ledger orders"
        )

    return {
        "timestamp": int(time.time() * 1000),
        "mode": "paper-performance-read-only",
        "symbol": ledger_report.get("symbol"),
        "currency": ledger_report.get("currency"),
        "initialEquity": _decimal_text(starting_equity),
        "endingEquity": _decimal_text(ending_equity),
        "netPnlUsdt": _decimal_text(ending_equity - starting_equity),
        "returnPct": _ratio(ending_equity - starting_equity, starting_equity),
        "peakEquity": _decimal_text(peak_equity),
        "maxDrawdown": _decimal_text(max_drawdown),
        "maxDrawdownPct": max_drawdown_pct,
        "winRate": _ratio(Decimal(len(wins)), Decimal(closed_count)),
        "averageWin": _average_text(wins),
        "averageLoss": _average_text(losses),
        "profitFactor": _profit_factor(gross_win, gross_loss),
        "tradeCount": len(orders),
        "closedCount": closed_count,
        "evaluableClosedCount": closed_count,
        "unpricedClosedCount": len(unpriced_closed_orders),
        "skippedClosedCount": len(unpriced_closed_orders),
        "openCount": open_count,
        "expectancy": _average_text(closed_pnls),
        "consecutiveLosses": _max_consecutive_losses(closed_pnls),
        "equityCurve": [_serialize_curve_point(point) for point in curve],
        "equityTrend": equity_trend,
        "liveOrderSubmitted": False,
        "warnings": warnings,
        "nextPhase": "review-paper-equity-and-risk-adjust-strategy-policy",
    }


def equity_curve_from_closed_orders(
    ledger_report: dict[str, Any],
    *,
    initial_equity: Any | None = None,
) -> list[dict[str, Any]]:
    return [
        _serialize_curve_point(point)
        for point in _raw_equity_curve_from_closed_orders(ledger_report, initial_equity=initial_equity)
    ]


def _raw_equity_curve_from_closed_orders(
    ledger_report: dict[str, Any],
    *,
    initial_equity: Any | None = None,
) -> list[dict[str, Any]]:
    starting_equity = _initial_equity(ledger_report, initial_equity)
    equity = starting_equity
    peak = starting_equity
    curve: list[dict[str, Any]] = []

    for index, order in enumerate(_priced_closed_orders(_orders(ledger_report)), start=1):
        pnl = _priced_pnl(order)
        equity += pnl
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        curve.append(
            {
                "index": index,
                "timestamp": _exit_timestamp(order),
                "orderId": order.get("orderId"),
                "sourceEventId": order.get("sourceEventId"),
                "status": order.get("status"),
                "side": order.get("side"),
                "pnl": pnl,
                "equity": equity,
                "peakEquity": peak,
                "drawdown": drawdown,
                "drawdownPct": _ratio(drawdown, peak),
            }
        )

    return curve


def _orders(ledger_report: dict[str, Any]) -> list[dict[str, Any]]:
    orders = ledger_report.get("orders")
    if not isinstance(orders, list):
        return []
    return [order for order in orders if isinstance(order, dict)]


def _open_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [order for order in orders if str(order.get("status") or "").upper() in OPEN_STATUSES]


def _closed_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [order for order in orders if str(order.get("status") or "").upper() not in OPEN_STATUSES],
        key=_order_close_key,
    )


def _priced_closed_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [order for order in _closed_orders(orders) if _priced_pnl(order) is not None]


def _unpriced_closed_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [order for order in _closed_orders(orders) if _priced_pnl(order) is None]


def _order_close_key(order: dict[str, Any]) -> tuple[int, int, str]:
    return (
        _as_int(_exit_timestamp(order)) or _as_int(order.get("createdTimestamp")) or 0,
        _as_int(order.get("sourceEventId")) or 0,
        str(order.get("orderId") or ""),
    )


def _exit_timestamp(order: dict[str, Any]) -> Any:
    exit_detail = order.get("exit") if isinstance(order.get("exit"), dict) else {}
    return exit_detail.get("exitTimestamp") or order.get("createdTimestamp")


def _priced_pnl(order: dict[str, Any]) -> Decimal | None:
    value = _decimal_or_none(order.get("roughNetPnlUsdt"))
    if value is not None:
        return value
    exit_detail = order.get("exit") if isinstance(order.get("exit"), dict) else {}
    return _decimal_or_none(exit_detail.get("roughNetPnlUsdt"))


def _initial_equity(ledger_report: dict[str, Any], explicit: Any | None) -> Decimal:
    if explicit is not None:
        return _decimal_or_none(explicit) or Decimal("0")
    for key in ("initialEquity", "startingEquity", "equity"):
        value = _decimal_or_none(ledger_report.get(key))
        if value is not None:
            return value
    return Decimal("0")


def _average_text(values: list[Decimal]) -> str | None:
    if not values:
        return None
    return _decimal_text(sum(values, Decimal("0")) / Decimal(len(values)))


def _profit_factor(gross_win: Decimal, gross_loss: Decimal) -> float | None:
    if gross_loss == 0:
        return None
    return float(gross_win / abs(gross_loss))


def _ratio(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def _max_consecutive_losses(pnls: list[Decimal]) -> int:
    longest = 0
    current = 0
    for pnl in pnls:
        if pnl < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _recent_equity_trend(curve: list[dict[str, Any]], *, window: int) -> dict[str, Any]:
    recent = curve[-window:]
    count = len(recent)
    pnls = [point["pnl"] for point in recent]
    positive_steps = sum(1 for pnl in pnls if pnl > 0)
    net_change = sum(pnls, Decimal("0"))
    slope = _equity_slope(recent)
    improving = count >= window and net_change > 0 and slope is not None and slope > 0
    return {
        "window": window,
        "count": count,
        "enoughSamples": count >= window,
        "recentEquityChange": _decimal_text(net_change) if count else None,
        "recentEquitySlope": _decimal_text(slope),
        "positiveStepRate": _ratio(Decimal(positive_steps), Decimal(count)),
        "recentEquityImproving": improving,
    }


def _equity_slope(points: list[dict[str, Any]]) -> Decimal | None:
    if not points:
        return None
    first_equity = points[0]["equity"] - points[0]["pnl"]
    values = [first_equity, *[point["equity"] for point in points]]
    n = Decimal(len(values))
    mean_x = Decimal(len(values) - 1) / Decimal("2")
    mean_y = sum(values, Decimal("0")) / n
    numerator = sum((Decimal(index) - mean_x) * (value - mean_y) for index, value in enumerate(values))
    denominator = sum((Decimal(index) - mean_x) ** 2 for index in range(len(values)))
    if denominator == 0:
        return None
    return numerator / denominator


def _serialize_curve_point(point: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(point)
    for key in ("pnl", "equity", "peakEquity", "drawdown"):
        serialized[key] = _decimal_text(serialized[key])
    return serialized


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "build_paper_performance_report",
    "equity_curve_from_closed_orders",
]
