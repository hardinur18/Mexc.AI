from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


OPEN_SIGNAL_SIDES = {"open-long", "open-short"}


@dataclass(frozen=True)
class SignalCandidate:
    symbol: str
    side: str
    price: float
    stop_loss_price: float
    take_profit_price: float
    confidence: float
    reasons: list[str]
    metrics: dict[str, Any]


def build_micro_signal(
    *,
    symbol: str,
    ticker: dict[str, Any],
    depth: dict[str, Any],
    funding_rate: dict[str, Any],
    contract_size: float | None,
    leverage: int,
    max_notional_usdt: float,
    taker_fee_rate: float | None = None,
    stop_loss_bps: float = 35.0,
    take_profit_bps: float = 55.0,
    min_depth_imbalance: float = 0.12,
    max_spread_bps: float = 2.5,
    max_abs_funding_rate: float = 0.0005,
    fair_alignment_bps: float = 0.0,
    min_expected_net_bps: float = 8.0,
    allowed_sides: set[str] | None = None,
) -> dict[str, Any]:
    ticker_data = ticker.get("data") if isinstance(ticker.get("data"), dict) else {}
    depth_data = depth.get("data") if isinstance(depth.get("data"), dict) else {}
    funding_data = funding_rate.get("data") if isinstance(funding_rate.get("data"), dict) else {}

    bid = _as_float(ticker_data.get("bid1"))
    ask = _as_float(ticker_data.get("ask1"))
    last = _as_float(ticker_data.get("lastPrice"))
    fair = _as_float(ticker_data.get("fairPrice"))
    index = _as_float(ticker_data.get("indexPrice"))
    rate = _as_float(funding_data.get("fundingRate"))

    asks = depth_data.get("asks") if isinstance(depth_data.get("asks"), list) else []
    bids = depth_data.get("bids") if isinstance(depth_data.get("bids"), list) else []
    bid_size = _sum_book_size(bids[:10])
    ask_size = _sum_book_size(asks[:10])
    total_size = bid_size + ask_size
    imbalance = (bid_size - ask_size) / total_size if total_size else 0.0

    mid = (bid + ask) / 2 if bid is not None and ask is not None else last
    spread = ask - bid if bid is not None and ask is not None else None
    fair_premium_bps = ((fair - index) / index * 10_000) if fair and index else None
    spread_bps = (spread / mid * 10_000) if spread is not None and mid and mid > 0 else None
    round_trip_taker_fee_bps = 2 * (taker_fee_rate if taker_fee_rate is not None else 0.0001) * 10_000
    expected_net_take_profit_bps = (
        take_profit_bps - round_trip_taker_fee_bps - (spread_bps or 0.0)
    )

    reasons: list[str] = []
    side = "hold"
    confidence = 0.0
    allowed_signal_sides = set(OPEN_SIGNAL_SIDES if allowed_sides is None else allowed_sides)

    if mid is None or mid <= 0:
        reasons.append("missing usable market price")
    elif spread_bps is None:
        reasons.append("missing usable spread")
    elif spread_bps > max_spread_bps:
        reasons.append(f"spread {spread_bps:.6f} bps above gate {max_spread_bps}")
    elif abs(rate or 0.0) > max_abs_funding_rate:
        reasons.append(f"absolute funding rate {abs(rate or 0.0):.8f} above gate {max_abs_funding_rate}")
    elif fair_premium_bps is None:
        reasons.append("missing fair/index premium")
    elif expected_net_take_profit_bps < min_expected_net_bps:
        reasons.append(
            f"expected net take-profit {expected_net_take_profit_bps:.6f} bps below gate {min_expected_net_bps}"
        )
    else:
        if imbalance >= min_depth_imbalance and fair_premium_bps >= fair_alignment_bps:
            side = "open-long"
            confidence = min(0.9, 0.5 + abs(imbalance))
            reasons.append("bid-side depth imbalance and fair premium support long")
        elif imbalance <= -min_depth_imbalance and fair_premium_bps <= -fair_alignment_bps:
            side = "open-short"
            confidence = min(0.9, 0.5 + abs(imbalance))
            reasons.append("ask-side depth imbalance and fair premium support short")
        else:
            reasons.append(
                "no strong depth/fair alignment: "
                f"imbalance={imbalance:.8f}, fairPremiumBps={fair_premium_bps:.8f}"
            )

    if side in OPEN_SIGNAL_SIDES and side not in allowed_signal_sides:
        reasons.append(f"strategy side {side} disabled by allowed side policy")
        side = "hold"
        confidence = 0.0

    if side == "open-long":
        price = ask or mid or 0.0
        stop_loss = price * (1 - stop_loss_bps / 10_000)
        take_profit = price * (1 + take_profit_bps / 10_000)
    elif side == "open-short":
        price = bid or mid or 0.0
        stop_loss = price * (1 + stop_loss_bps / 10_000)
        take_profit = price * (1 - take_profit_bps / 10_000)
    else:
        price = mid or 0.0
        stop_loss = 0.0
        take_profit = 0.0

    effective_contract_size = contract_size or _as_float(ticker_data.get("contractSize"))
    vol = max(1, int(max_notional_usdt / max(price * (effective_contract_size or 1), 1e-12))) if price else 1
    vol = min(vol, 1)

    return {
        "timestamp": int(time.time() * 1000),
        "symbol": symbol.upper(),
        "signal": {
            "side": side,
            "confidence": round(confidence, 6),
            "reasons": reasons,
        },
        "candidateOrder": {
            "symbol": symbol.upper(),
            "side": side,
            "price": round(price, 8),
            "vol": vol,
            "contractSize": effective_contract_size,
            "leverage": leverage,
            "stopLossPrice": round(stop_loss, 8),
            "takeProfitPrice": round(take_profit, 8),
        },
        "metrics": {
            "bid": bid,
            "ask": ask,
            "last": last,
            "fair": fair,
            "index": index,
            "spread": spread,
            "spreadBps": round(spread_bps, 8) if spread_bps is not None else None,
            "fundingRate": rate,
            "bidSizeTop10": bid_size,
            "askSizeTop10": ask_size,
            "depthImbalanceTop10": round(imbalance, 8),
            "fairPremiumBps": round(fair_premium_bps, 8) if fair_premium_bps is not None else None,
            "roundTripTakerFeeBps": round(round_trip_taker_fee_bps, 8),
            "expectedNetTakeProfitBps": round(expected_net_take_profit_bps, 8),
            "minDepthImbalance": min_depth_imbalance,
            "maxSpreadBps": max_spread_bps,
            "maxAbsFundingRate": max_abs_funding_rate,
            "fairAlignmentBps": fair_alignment_bps,
            "minExpectedNetBps": min_expected_net_bps,
            "allowedSides": sorted(allowed_signal_sides),
            "contractSize": effective_contract_size,
        },
    }


def evaluate_strategy_events(
    events: list[dict[str, Any]],
    *,
    symbol: str,
    currency: str = "USDT",
    min_consensus: int = 3,
    min_confidence: float = 0.65,
) -> dict[str, Any]:
    if min_consensus <= 0:
        raise ValueError("min_consensus must be positive")
    if min_confidence < 0:
        raise ValueError("min_confidence must be non-negative")

    target_symbol = symbol.upper()
    target_currency = currency.upper()
    samples = [
        sample
        for event in events
        if (sample := _event_to_sample(event, default_currency=target_currency)) is not None
        and sample["symbol"] == target_symbol
        and sample["currency"] == target_currency
    ]

    reasons: list[str] = []
    blocking_reasons: list[str] = []
    latest_side = None
    consecutive_valid = 0

    if not samples:
        reasons.append(f"no stored strategy_signal events match {target_symbol}/{target_currency}")
    else:
        latest = samples[0]
        latest_side = latest["side"]
        if latest_side not in OPEN_SIGNAL_SIDES:
            reasons.append(f"latest signal is not actionable: {latest_side}")
        else:
            for sample in samples:
                if sample["side"] != latest_side:
                    blocking_reasons.append(
                        f"signal changed at event {sample['eventId']}: {sample['side']} after {consecutive_valid} valid sample(s)"
                    )
                    break
                if sample["confidence"] is None or sample["confidence"] < min_confidence:
                    blocking_reasons.append(
                        f"event {sample['eventId']} confidence {sample['confidence']} is below {min_confidence}"
                    )
                    break
                if sample["preflightAllowed"] is not True:
                    blocking_reasons.append(f"event {sample['eventId']} preflight is not allowed")
                    if sample["preflightReasons"]:
                        blocking_reasons.extend([f"preflight: {reason}" for reason in sample["preflightReasons"]])
                    break
                consecutive_valid += 1

            if consecutive_valid < min_consensus and not any(reason.startswith("latest signal") for reason in reasons):
                reasons.extend(blocking_reasons)
                reasons.append(
                    f"only {consecutive_valid} consecutive valid {latest_side} signal(s); need {min_consensus}"
                )

    actionable = bool(latest_side in OPEN_SIGNAL_SIDES and consecutive_valid >= min_consensus)
    if actionable:
        reasons.append(
            f"{consecutive_valid} consecutive {latest_side} signal(s) passed confidence and preflight gates"
        )

    return {
        "timestamp": int(time.time() * 1000),
        "symbol": target_symbol,
        "currency": target_currency,
        "actionable": actionable,
        "side": latest_side,
        "consecutiveValid": consecutive_valid,
        "minConsensus": min_consensus,
        "minConfidence": min_confidence,
        "sampleCount": len(samples),
        "reasons": reasons,
        "samples": samples,
    }


def _event_to_sample(event: dict[str, Any], *, default_currency: str) -> dict[str, Any] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None

    outer_signal = payload.get("signal")
    signal = outer_signal.get("signal") if isinstance(outer_signal, dict) else None
    if not isinstance(signal, dict):
        return None

    preflight = payload.get("preflight")
    preflight_allowed = None
    preflight_reasons: list[str] = []
    if isinstance(preflight, dict):
        preflight_allowed = preflight.get("preflightAllowed")
        raw_reasons = preflight.get("reasons")
        if isinstance(raw_reasons, list):
            preflight_reasons = [str(reason) for reason in raw_reasons]

    return {
        "eventId": event.get("id"),
        "timestamp": payload.get("timestamp") or event.get("ts"),
        "symbol": str(payload.get("symbol") or event.get("symbol") or "").upper(),
        "currency": str(payload.get("currency") or event.get("currency") or default_currency).upper(),
        "side": str(signal.get("side") or "hold"),
        "confidence": _as_float(signal.get("confidence")),
        "preflightAllowed": preflight_allowed,
        "preflightReasons": preflight_reasons,
    }


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_book_size(rows: list[Any]) -> float:
    total = 0.0
    for row in rows:
        if isinstance(row, list) and len(row) >= 2:
            total += _as_float(row[1]) or 0.0
    return total
