from mexc_futures_engine.strategy import build_micro_signal
from mexc_futures_engine.strategy import evaluate_strategy_events


def test_strategy_evaluator_rejects_flip_in_latest_window():
    result = evaluate_strategy_events(
        [
            _event(7, "open-long", 0.70),
            _event(6, "open-short", 0.72),
            _event(5, "open-short", 0.75),
        ],
        symbol="BTC_USDT",
        min_consensus=3,
        min_confidence=0.65,
    )

    assert not result["actionable"]
    assert result["side"] == "open-long"
    assert result["consecutiveValid"] == 1
    assert any("signal changed" in reason for reason in result["reasons"])


def test_strategy_evaluator_accepts_consecutive_preflighted_signals():
    result = evaluate_strategy_events(
        [
            _event(7, "open-short", 0.70),
            _event(6, "open-short", 0.72),
            _event(5, "open-short", 0.75),
        ],
        symbol="BTC_USDT",
        min_consensus=3,
        min_confidence=0.65,
    )

    assert result["actionable"]
    assert result["side"] == "open-short"
    assert result["consecutiveValid"] == 3


def test_strategy_evaluator_requires_preflight_allowed():
    result = evaluate_strategy_events(
        [
            _event(7, "open-long", 0.70, allowed=False, preflight_reasons=["available balance too low"]),
            _event(6, "open-long", 0.72),
            _event(5, "open-long", 0.75),
        ],
        symbol="BTC_USDT",
        min_consensus=3,
        min_confidence=0.65,
    )

    assert not result["actionable"]
    assert result["consecutiveValid"] == 0
    assert "event 7 preflight is not allowed" in result["reasons"]
    assert "preflight: available balance too low" in result["reasons"]


def test_micro_signal_rejects_long_without_fair_premium_alignment():
    signal = build_micro_signal(
        symbol="BTC_USDT",
        ticker=_ticker(fair=99.95, index=100.0),
        depth=_depth(bid_size=80, ask_size=20),
        funding_rate=_funding(0.0001),
        contract_size=0.0001,
        leverage=2,
        max_notional_usdt=10,
        taker_fee_rate=0.0001,
    )

    assert signal["signal"]["side"] == "hold"
    assert any("no strong depth/fair alignment" in reason for reason in signal["signal"]["reasons"])
    assert signal["metrics"]["depthImbalanceTop10"] == 0.6
    assert signal["metrics"]["fairPremiumBps"] == -5.0


def test_micro_signal_accepts_short_with_friction_adjusted_alignment():
    signal = build_micro_signal(
        symbol="BTC_USDT",
        ticker=_ticker(fair=99.95, index=100.0),
        depth=_depth(bid_size=20, ask_size=80),
        funding_rate=_funding(0.0001),
        contract_size=0.0001,
        leverage=2,
        max_notional_usdt=10,
        taker_fee_rate=0.0001,
    )

    assert signal["signal"]["side"] == "open-short"
    assert signal["signal"]["confidence"] == 0.9
    assert signal["metrics"]["expectedNetTakeProfitBps"] > 50


def test_micro_signal_holds_when_allowed_side_policy_disables_long():
    signal = build_micro_signal(
        symbol="BTC_USDT",
        ticker=_ticker(fair=100.05, index=100.0),
        depth=_depth(bid_size=80, ask_size=20),
        funding_rate=_funding(0.0001),
        contract_size=0.0001,
        leverage=2,
        max_notional_usdt=10,
        taker_fee_rate=0.0001,
        allowed_sides={"open-short"},
    )

    assert signal["signal"]["side"] == "hold"
    assert "strategy side open-long disabled by allowed side policy" in signal["signal"]["reasons"]
    assert signal["metrics"]["allowedSides"] == ["open-short"]


def test_micro_signal_rejects_wide_spread():
    signal = build_micro_signal(
        symbol="BTC_USDT",
        ticker=_ticker(bid=99.0, ask=101.0, fair=99.95, index=100.0),
        depth=_depth(bid_size=20, ask_size=80),
        funding_rate=_funding(0.0001),
        contract_size=0.0001,
        leverage=2,
        max_notional_usdt=10,
        taker_fee_rate=0.0001,
        max_spread_bps=2.5,
    )

    assert signal["signal"]["side"] == "hold"
    assert any("spread" in reason and "above gate" in reason for reason in signal["signal"]["reasons"])


def _event(
    event_id,
    side,
    confidence,
    *,
    symbol="BTC_USDT",
    currency="USDT",
    allowed=True,
    preflight_reasons=None,
):
    return {
        "id": event_id,
        "ts": event_id * 1000,
        "eventType": "strategy_signal",
        "symbol": symbol,
        "currency": currency,
        "payload": {
            "timestamp": event_id * 1000,
            "symbol": symbol,
            "currency": currency,
            "signal": {
                "signal": {
                    "side": side,
                    "confidence": confidence,
                    "reasons": [],
                },
            },
            "preflight": {
                "preflightAllowed": allowed,
                "reasons": preflight_reasons or [],
            },
        },
    }


def _ticker(*, bid=99.99, ask=100.01, fair=100.0, index=100.0):
    return {
        "success": True,
        "data": {
            "bid1": bid,
            "ask1": ask,
            "lastPrice": 100.0,
            "fairPrice": fair,
            "indexPrice": index,
        },
    }


def _depth(*, bid_size, ask_size):
    return {
        "success": True,
        "data": {
            "bids": [["99.99", str(bid_size)]],
            "asks": [["100.01", str(ask_size)]],
        },
    }


def _funding(rate):
    return {"success": True, "data": {"fundingRate": rate}}
