from mexc_futures_engine.nautilus_adapter.state_handoff import build_nautilus_state_handoff_report
from mexc_futures_engine.nautilus_adapter.state_handoff import summarize_nautilus_state_handoff_report


def test_state_handoff_ready_from_three_wires_and_strategy_preview():
    report = build_nautilus_state_handoff_report(
        instrument_wire=_instrument_wire(),
        market_wire=_market_wire(),
        execution_wire=_execution_wire(),
        strategy_signal=_strategy_signal("open-long", preflight_allowed=True),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is True
    assert report["readyForStrategyReadOnly"] is True
    assert report["stateCache"]["instrument"]["instrumentId"] == "BTC_USDT-PERP.MEXC"
    assert report["stateCache"]["account"]["balance"]["free"] == "6.00000001"
    assert report["stateCache"]["execution"]["activeOrderCount"] == 0
    assert report["strategyHandoff"]["safeToEvaluateSignals"] is True
    assert report["strategyHandoff"]["safeToOpenNewPositionPreflight"] is True
    assert report["strategyHandoff"]["strategyPreview"]["side"] == "open-long"


def test_state_handoff_filters_orders_to_target_symbol_but_preserves_global_counts():
    execution_wire = _execution_wire()
    execution_wire["sandboxWire"]["objectCounts"] = {"AccountState": 1, "OrderStatusReport": 2, "FillReport": 1}
    execution_wire["sandboxWire"]["objects"].insert(
        1,
        {
            "class": "OrderStatusReport",
            "instrumentId": "ETH_USDT-PERP.MEXC",
            "orderStatus": "ACCEPTED",
            "venueOrderId": "eth-active",
        },
    )

    report = build_nautilus_state_handoff_report(
        instrument_wire=_instrument_wire(),
        market_wire=_market_wire(),
        execution_wire=execution_wire,
        strategy_signal=_strategy_signal("open-long", preflight_allowed=True),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is True
    assert report["stateCache"]["execution"]["recentOrderCount"] == 1
    assert report["stateCache"]["execution"]["globalRecentOrderCount"] == 2
    assert report["stateCache"]["execution"]["activeOrderCount"] == 0
    assert report["stateCache"]["execution"]["globalActiveOrderCount"] == 1
    assert report["stateCache"]["execution"]["latestOrder"]["venueOrderId"] == "order-1"
    assert report["stateCache"]["account"]["globalActiveOrderCount"] == 1
    assert report["strategyHandoff"]["safeToOpenNewPositionPreflight"] is False


def test_state_handoff_blocks_missing_market_book():
    market_wire = _market_wire()
    market_wire["sandboxWire"]["objects"] = [
        {"class": "TradeTick", "instrumentId": "BTC_USDT-PERP.MEXC", "price": "76000", "size": "1"},
    ]
    market_wire["sandboxWire"]["objectCounts"] = {"TradeTick": 1}

    report = build_nautilus_state_handoff_report(
        instrument_wire=_instrument_wire(),
        market_wire=market_wire,
        execution_wire=_execution_wire(),
        strategy_signal=_strategy_signal("hold"),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is False
    assert "state cache has no OrderBookDeltas market object" in report["blockers"]


def test_state_handoff_blocks_missing_market_quote():
    market_wire = _market_wire()
    market_wire["sandboxWire"]["objects"] = [
        item for item in market_wire["sandboxWire"]["objects"] if item["class"] != "QuoteTick"
    ]
    market_wire["sandboxWire"]["objectCounts"] = {"TradeTick": 1, "OrderBookDeltas": 1}

    report = build_nautilus_state_handoff_report(
        instrument_wire=_instrument_wire(),
        market_wire=market_wire,
        execution_wire=_execution_wire(),
        strategy_signal=_strategy_signal("hold"),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is False
    assert "state cache has no QuoteTick market object" in report["blockers"]


def test_state_handoff_blocks_live_flag():
    report = build_nautilus_state_handoff_report(
        instrument_wire=_instrument_wire(),
        market_wire=_market_wire(),
        execution_wire=_execution_wire(),
        strategy_signal=_strategy_signal("hold"),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=True,
    )

    assert report["ok"] is False
    assert "live trading flag is enabled; state handoff requires read-only mode" in report["blockers"]


def test_state_handoff_summary_omits_inputs():
    report = build_nautilus_state_handoff_report(
        instrument_wire=_instrument_wire(),
        market_wire=_market_wire(),
        execution_wire=_execution_wire(),
        strategy_signal=_strategy_signal("hold"),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
        include_raw=True,
    )

    summary = summarize_nautilus_state_handoff_report(report)

    assert "inputs" in report
    assert "inputs" not in summary
    assert summary["ok"] is True


def _instrument_wire():
    return {
        "ok": True,
        "readyForSandboxedNautilusRuntimeReadOnly": True,
        "wireMode": "sandboxed-runtime-read-only",
        "sandboxWire": {
            "objectCount": 1,
            "objects": [
                {
                    "class": "CryptoPerpetual",
                    "instrumentId": "BTC_USDT-PERP.MEXC",
                    "rawSymbol": "BTC_USDT",
                    "baseCurrency": "BTC",
                    "quoteCurrency": "USDT",
                    "settlementCurrency": "USDT",
                    "priceIncrement": "0.1",
                    "sizeIncrement": "1",
                    "multiplier": "0.0001",
                }
            ],
            "errors": [],
        },
        "blockers": [],
    }


def _market_wire():
    return {
        "ok": True,
        "readyForSandboxedNautilusMarketDataReadOnly": True,
        "wireMode": "sandboxed-market-data-read-only",
        "sandboxWire": {
            "objectCount": 3,
            "objectCounts": {"QuoteTick": 1, "TradeTick": 1, "OrderBookDeltas": 1},
            "objects": [
                {
                    "class": "QuoteTick",
                    "instrumentId": "BTC_USDT-PERP.MEXC",
                    "bidPrice": "75999.9",
                    "askPrice": "76000.1",
                    "bidSize": "2",
                    "askSize": "3",
                },
                {"class": "TradeTick", "instrumentId": "BTC_USDT-PERP.MEXC", "price": "76000", "size": "1"},
                {
                    "class": "OrderBookDeltas",
                    "instrumentId": "BTC_USDT-PERP.MEXC",
                    "deltaCount": 20,
                    "sequence": 7,
                },
            ],
            "errors": [],
        },
        "blockers": [],
        "warnings": [],
    }


def _execution_wire():
    return {
        "ok": True,
        "readyForSandboxedNautilusExecutionReadOnly": True,
        "wireMode": "sandboxed-execution-read-only",
        "sandboxWire": {
            "objectCount": 3,
            "objectCounts": {"AccountState": 1, "OrderStatusReport": 1, "FillReport": 1},
            "balanceAdjustments": [],
            "objects": [
                {
                    "class": "AccountState",
                    "accountId": "MEXC-FUTURES",
                    "accountType": "MARGIN",
                    "baseCurrency": "USDT",
                    "balances": [
                        {
                            "currency": "USDT",
                            "total": "6.00000001 USDT",
                            "locked": "0.00000000 USDT",
                            "free": "6.00000001 USDT",
                        }
                    ],
                },
                {
                    "class": "OrderStatusReport",
                    "instrumentId": "BTC_USDT-PERP.MEXC",
                    "orderStatus": "FILLED",
                    "venueOrderId": "order-1",
                },
                {
                    "class": "FillReport",
                    "instrumentId": "BTC_USDT-PERP.MEXC",
                    "tradeId": "fill-1",
                    "lastPx": "76000",
                },
            ],
            "errors": [],
        },
        "blockers": [],
        "warnings": [],
    }


def _strategy_signal(side, *, preflight_allowed=None):
    preflight = None if preflight_allowed is None else {"preflightAllowed": preflight_allowed, "reasons": []}
    return {
        "signal": {
            "signal": {
                "side": side,
                "confidence": 0.72 if side != "hold" else 0,
                "reasons": ["test"],
            },
            "candidateOrder": {"symbol": "BTC_USDT", "side": side},
        },
        "preflight": preflight,
    }
