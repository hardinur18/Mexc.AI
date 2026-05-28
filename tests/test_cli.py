import json
import os
from pathlib import Path
import tempfile

from mexc_futures_engine import cli
from mexc_futures_engine.settings import _strategy_sides_from_env
from mexc_futures_engine.settings import MexcSettings
from mexc_futures_engine.settings import RiskSettings
from mexc_futures_engine.store import StateStore


def test_dry_run_order_never_calls_place_order():
    outputs = []
    original_client = cli.MexcFuturesClient
    original_print_json = cli.print_json

    class FakeClient:
        def __init__(self, settings, *, risk_engine=None):
            self.settings = settings
            self.risk_engine = risk_engine

        def order_preflight(self, order, *, currency="USDT"):
            return {
                "preflightAllowed": False,
                "reasons": ["contract size is missing or invalid"],
                "warnings": [],
                "symbol": order.symbol.upper(),
                "currency": currency,
                "order": order.to_mexc_payload(),
            }

        def place_order(self, order):
            raise AssertionError("dry-run-order must not call place_order")

    try:
        cli.MexcFuturesClient = FakeClient
        cli.print_json = outputs.append
        status = cli.main(
            [
                "dry-run-order",
                "--symbol",
                "BTC_USDT",
                "--side",
                "open-long",
                "--order-type",
                "limit",
                "--price",
                "80000",
                "--vol",
                "1",
                "--leverage",
                "2",
                "--stop-loss-price",
                "79000",
            ]
        )
    finally:
        cli.MexcFuturesClient = original_client
        cli.print_json = original_print_json

    assert status == 0
    assert outputs[0]["dryRun"] is True
    assert outputs[0]["wouldSubmitLive"] is False
    assert outputs[0]["liveOrderSubmitted"] is False


def test_audit_safety_requires_successful_private_readonly_auth_probe():
    class FakeClient:
        def network_check(self):
            return {"checks": [{"name": "ping", "ok": True}]}

        def asset(self, currency):
            return {"success": False, "code": 401, "message": "invalid key"}

    payload = _run_audit_safety_in_temp_root(FakeClient())

    assert payload["readyForReadonly"] is False
    assert payload["privateReadonlyAuth"]["ok"] is False
    assert "private read-only auth probe failed" in payload["findings"]


def test_audit_safety_ready_for_readonly_when_ping_and_private_auth_pass():
    class FakeClient:
        def network_check(self):
            return {"checks": [{"name": "ping", "ok": True}]}

        def asset(self, currency):
            return {"success": True, "code": 0, "message": "success", "data": {"currency": currency}}

    payload = _run_audit_safety_in_temp_root(FakeClient())

    assert payload["ok"] is True
    assert payload["readyForReadonly"] is True
    assert payload["privateReadonlyAuth"]["ok"] is True


def test_audit_safety_never_marks_live_ready_from_flags_only():
    class FakeClient:
        def network_check(self):
            return {"checks": [{"name": "ping", "ok": True}]}

        def asset(self, currency):
            return {"success": True, "code": 0, "message": "success", "data": {"currency": currency}}

    cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env").write_text("MEXC_ACCESS_KEY=access-123\nMEXC_SECRET_KEY=secret-456\n", encoding="utf-8")
        (root / ".env").chmod(0o600)
        (root / ".gitignore").write_text(".env\n", encoding="utf-8")
        os.chdir(root)
        try:
            payload = cli.audit_safety(
                MexcSettings(
                    access_key="access-123",
                    secret_key="secret-456",
                    live_trading_enabled=True,
                    live_confirm="I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK",
                    live_mutation_phase_enabled=True,
                    state_db=str(root / "data" / "state.sqlite3"),
                    strategy_allowed_sides={"open-short"},
                ),
                RiskSettings(allowed_symbols={"BTC_USDT"}, kill_switch_file=str(root / ".kill-switch")),
                FakeClient(),
            )
        finally:
            os.chdir(cwd)

    assert payload["liveMutationFlagsArmed"] is True
    assert payload["readyForLive"] is False


def test_audit_safety_blocks_empty_strategy_side_policy():
    class FakeClient:
        def network_check(self):
            return {"checks": [{"name": "ping", "ok": True}]}

        def asset(self, currency):
            return {"success": True, "code": 0, "message": "success", "data": {"currency": currency}}

    cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env").write_text("MEXC_ACCESS_KEY=access-123\nMEXC_SECRET_KEY=secret-456\n", encoding="utf-8")
        (root / ".env").chmod(0o600)
        (root / ".gitignore").write_text(".env\n", encoding="utf-8")
        os.chdir(root)
        try:
            payload = cli.audit_safety(
                MexcSettings(
                    access_key="access-123",
                    secret_key="secret-456",
                    state_db=str(root / "data" / "state.sqlite3"),
                    strategy_allowed_sides=set(),
                ),
                RiskSettings(allowed_symbols={"BTC_USDT"}, kill_switch_file=str(root / ".kill-switch")),
                FakeClient(),
            )
        finally:
            os.chdir(cwd)

    assert payload["ok"] is False
    assert "strategy allowed sides policy is empty or invalid" in payload["findings"]


def test_invalid_strategy_allowed_sides_env_fails_closed():
    assert _strategy_sides_from_env(None) == {"open-long", "open-short"}
    assert _strategy_sides_from_env("") == set()
    assert _strategy_sides_from_env("   ") == set()
    assert _strategy_sides_from_env("bad-side,open-flat") == set()
    assert _strategy_sides_from_env("open-short,bad-side") == {"open-short"}


def test_nautilus_paper_performance_reads_ledger_file_without_live_order():
    outputs = []
    original_print_json = cli.print_json
    cwd = Path.cwd()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger_path = root / "ledger.json"
        ledger_path.write_text(
            json.dumps(
                {
                    "mode": "paper-execution-ledger-read-only",
                    "symbol": "BTC_USDT",
                    "currency": "USDT",
                    "orders": [
                        {
                            "orderId": "entry-1",
                            "status": "TAKE_PROFIT",
                            "roughNetPnlUsdt": "1.5",
                            "exit": {"exitTimestamp": 1000, "roughNetPnlUsdt": "1.5"},
                            "liveOrderSubmitted": False,
                        },
                        {
                            "orderId": "entry-2",
                            "status": "OPEN",
                            "roughNetPnlUsdt": None,
                            "exit": None,
                            "liveOrderSubmitted": False,
                        },
                    ],
                    "liveOrderSubmitted": False,
                }
            ),
            encoding="utf-8",
        )
        os.chdir(root)
        try:
            cli.print_json = outputs.append
            status = cli.main(
                [
                    "nautilus-paper-performance",
                    "--ledger",
                    str(ledger_path),
                    "--initial-equity",
                    "10",
                ]
            )
        finally:
            cli.print_json = original_print_json
            os.chdir(cwd)

    assert status == 0
    assert outputs[0]["mode"] == "paper-performance-read-only"
    assert outputs[0]["endingEquity"] == "11.5"
    assert outputs[0]["liveOrderSubmitted"] is False


def test_nautilus_paper_performance_can_save_snapshot_event():
    outputs = []
    original_print_json = cli.print_json
    cwd = Path.cwd()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger_path = root / "ledger.json"
        ledger_path.write_text(
            json.dumps(
                {
                    "mode": "paper-execution-ledger-read-only",
                    "symbol": "BTC_USDT",
                    "currency": "USDT",
                    "orders": [
                        {
                            "orderId": "entry-1",
                            "status": "EXPIRED",
                            "roughNetPnlUsdt": "-0.2",
                            "exit": {"exitTimestamp": 1000, "roughNetPnlUsdt": "-0.2"},
                            "liveOrderSubmitted": False,
                        }
                    ],
                    "liveOrderSubmitted": False,
                }
            ),
            encoding="utf-8",
        )
        os.chdir(root)
        try:
            cli.print_json = outputs.append
            status = cli.main(
                [
                    "nautilus-paper-performance",
                    "--ledger",
                    str(ledger_path),
                    "--initial-equity",
                    "10",
                    "--save",
                ]
            )
            events = StateStore("data/mexc_engine.sqlite3").latest_events(
                event_type="nautilus_paper_performance",
                limit=1,
                symbol="BTC_USDT",
                currency="USDT",
            )
        finally:
            cli.print_json = original_print_json
            os.chdir(cwd)

    assert status == 0
    assert outputs[0]["savedEventId"] == events[0]["id"]
    assert events[0]["payload"]["mode"] == "paper-performance-read-only"
    assert events[0]["payload"]["liveOrderSubmitted"] is False


def test_nautilus_paper_ledger_can_save_lifecycle_snapshot_event():
    outputs = []
    original_print_json = cli.print_json
    cwd = Path.cwd()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        os.chdir(root)
        try:
            store = StateStore("data/mexc_engine.sqlite3")
            store.save_event(
                "nautilus_paper_decision",
                {
                    "timestamp": 1000,
                    "mode": "paper-trading-read-only",
                    "symbol": "BTC_USDT",
                    "currency": "USDT",
                    "wouldOpen": True,
                    "action": "paper-open-long",
                    "side": "open-long",
                    "confidence": "0.72",
                    "virtualOrder": {
                        "entryPrice": "80000",
                        "vol": "1",
                        "contractSize": "0.0001",
                        "estimatedTakerFee": "0.0008",
                        "takeProfitPrice": "80100",
                    },
                    "market": {"lastTradePrice": "80000"},
                    "liveOrderSubmitted": False,
                },
            )
            store.save_event(
                "nautilus_paper_decision",
                {
                    "timestamp": 2000,
                    "mode": "paper-trading-read-only",
                    "symbol": "BTC_USDT",
                    "currency": "USDT",
                    "wouldOpen": False,
                    "action": "hold",
                    "side": "hold",
                    "confidence": "0",
                    "virtualOrder": None,
                    "market": {"lastTradePrice": "80200"},
                    "liveOrderSubmitted": False,
                },
            )
            cli.print_json = outputs.append
            status = cli.main(
                [
                    "nautilus-paper-ledger",
                    "--symbol",
                    "BTC_USDT",
                    "--currency",
                    "USDT",
                    "--lookback",
                    "10",
                    "--horizon-samples",
                    "1",
                    "--save",
                ]
            )
            events = StateStore("data/mexc_engine.sqlite3").latest_events(
                event_type="nautilus_paper_ledger",
                limit=1,
                symbol="BTC_USDT",
                currency="USDT",
            )
        finally:
            cli.print_json = original_print_json
            os.chdir(cwd)

    assert status == 0
    assert outputs[0]["savedEventId"] == events[0]["id"]
    assert events[0]["payload"]["mode"] == "paper-execution-ledger-read-only"
    assert events[0]["payload"]["orders"][0]["lifecycle"] == ["NEW", "FILLED", "TAKE_PROFIT"]
    assert events[0]["payload"]["liveOrderSubmitted"] is False


def test_nautilus_paper_loop_caps_iterations_at_target_samples():
    calls = []
    original_runner = cli.run_nautilus_paper_decision
    cwd = Path.cwd()

    def fake_runner(*args, **kwargs):
        calls.append(kwargs)
        return {
            "timestamp": 1000 + len(calls),
            "mode": "paper-trading-read-only",
            "symbol": kwargs["symbol"],
            "currency": kwargs["currency"],
            "ok": True,
            "wouldOpen": False,
            "action": "hold",
            "side": "hold",
            "confidence": "0",
            "liveOrderSubmitted": False,
            "blockers": ["test hold"],
            "warnings": [],
            "nextPhase": "collect-paper-loop-samples-and-review-edge",
        }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        os.chdir(root)
        try:
            cli.run_nautilus_paper_decision = fake_runner
            settings = MexcSettings(
                access_key="access",
                secret_key="secret",
                state_db=str(root / "data" / "state.sqlite3"),
                strategy_allowed_sides={"open-short"},
            )
            payload = cli.run_nautilus_paper_loop(
                object(),
                settings,
                symbol="BTC_USDT",
                currency="USDT",
                market_messages=1,
                history_limit=1,
                deals_limit=1,
                leverage=2,
                max_notional_usdt=10,
                min_confidence=0.65,
                max_margin_fraction=0.75,
                paper_equity_usdt=None,
                min_depth_imbalance=0.12,
                max_spread_bps=2.5,
                max_abs_funding_rate=0.0005,
                max_market_age_seconds=60,
                quality_gate_lookback=0,
                quality_min_samples=5,
                quality_edge_horizon_samples=3,
                quality_min_edge_evaluable=3,
                quality_min_edge_win_rate=0.55,
                quality_min_side_edge_evaluable=2,
                quality_min_side_edge_win_rate=0.55,
                quality_recovery_window_evaluable=3,
                quality_recovery_min_win_rate=0.55,
                quality_max_sample_age_seconds=3600,
                quality_rolling_windows=(5, 10, 25, 50),
                trend_filter_enabled=False,
                trend_interval="1m",
                trend_lookback=60,
                trend_short_period=5,
                trend_long_period=20,
                trend_max_candle_age_seconds=300,
                volatility_filter_enabled=False,
                volatility_interval="1m",
                volatility_lookback=60,
                min_avg_range_bps=None,
                max_avg_range_bps=None,
                min_latest_range_bps=None,
                max_latest_range_bps=None,
                volatility_max_candle_age_seconds=300,
                iterations=5,
                interval=0,
                target_samples=2,
                target_closed_trades=None,
                include_raw=False,
                save=True,
            )
        finally:
            cli.run_nautilus_paper_decision = original_runner
            os.chdir(cwd)

    assert len(calls) == 2
    assert payload["requestedIterations"] == 5
    assert payload["iterations"] == 2
    assert payload["sampleProgress"]["beforeCount"] == 0
    assert payload["sampleProgress"]["afterCount"] == 2
    assert payload["sampleProgress"]["targetReached"] is True
    assert payload["liveOrderSubmitted"] is False


def test_nautilus_paper_loop_requires_save_when_targeting_collection():
    with tempfile.TemporaryDirectory() as tmp:
        settings = MexcSettings(
            access_key="access",
            secret_key="secret",
            state_db=str(Path(tmp) / "data" / "state.sqlite3"),
            strategy_allowed_sides={"open-short"},
        )

        try:
            cli.run_nautilus_paper_loop(
                object(),
                settings,
                **_paper_loop_kwargs(target_samples=1, target_closed_trades=None, save=False),
            )
        except cli.MexcApiError as exc:
            assert "requires --save" in str(exc)
        else:
            raise AssertionError("targeted paper loop should require save")


def test_nautilus_paper_loop_continues_when_closed_target_unmet():
    calls = []
    original_runner = cli.run_nautilus_paper_decision
    original_candles = cli._price_simulation_candles

    def fake_runner(*args, **kwargs):
        calls.append(kwargs)
        return _paper_decision_payload(timestamp=2000 + len(calls))

    def fake_candles(*args, **kwargs):
        return [], {"candleSource": "test-empty"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = MexcSettings(
            access_key="access",
            secret_key="secret",
            state_db=str(root / "data" / "state.sqlite3"),
            strategy_allowed_sides={"open-short"},
        )
        store = StateStore(settings.state_db)
        store.save_event("nautilus_paper_decision", _paper_decision_payload(timestamp=1000))
        store.save_event("nautilus_paper_decision", _paper_decision_payload(timestamp=1001))
        try:
            cli.run_nautilus_paper_decision = fake_runner
            cli._price_simulation_candles = fake_candles
            payload = cli.run_nautilus_paper_loop(
                object(),
                settings,
                **_paper_loop_kwargs(
                    iterations=3,
                    target_samples=2,
                    target_closed_trades=1,
                    save=True,
                ),
            )
        finally:
            cli.run_nautilus_paper_decision = original_runner
            cli._price_simulation_candles = original_candles

    assert len(calls) == 3
    assert payload["iterations"] == 3
    assert payload["sampleProgress"]["beforeCount"] == 2
    assert payload["sampleProgress"]["afterCount"] == 5
    assert payload["sampleProgress"]["remainingBefore"] == 0
    assert payload["sampleProgress"]["remainingClosedTradesBefore"] == 1
    assert payload["sampleProgress"]["targetReached"] is False
    assert payload["liveOrderSubmitted"] is False


def test_nautilus_paper_loop_does_not_count_unpriced_closed_entries_as_target():
    calls = []
    original_runner = cli.run_nautilus_paper_decision
    original_candles = cli._price_simulation_candles

    def fake_runner(*args, **kwargs):
        calls.append(kwargs)
        return _paper_decision_payload(timestamp=5000 + len(calls))

    def fake_candles(*args, **kwargs):
        return [], {"candleSource": "test-empty"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = MexcSettings(
            access_key="access",
            secret_key="secret",
            state_db=str(root / "data" / "state.sqlite3"),
            strategy_allowed_sides={"open-short"},
        )
        store = StateStore(settings.state_db)
        store.save_event("nautilus_paper_decision", _paper_decision_payload(timestamp=1000, would_open=True))
        store.save_event("nautilus_paper_decision", _paper_decision_payload(timestamp=2000))
        store.save_event("nautilus_paper_decision", _paper_decision_payload(timestamp=3000))
        store.save_event("nautilus_paper_decision", _paper_decision_payload(timestamp=4000))
        try:
            cli.run_nautilus_paper_decision = fake_runner
            cli._price_simulation_candles = fake_candles
            payload = cli.run_nautilus_paper_loop(
                object(),
                settings,
                **_paper_loop_kwargs(
                    iterations=1,
                    target_samples=4,
                    target_closed_trades=1,
                    save=True,
                ),
            )
        finally:
            cli.run_nautilus_paper_decision = original_runner
            cli._price_simulation_candles = original_candles

    assert len(calls) == 1
    assert payload["sampleProgress"]["beforeCount"] == 4
    assert payload["sampleProgress"]["remainingBefore"] == 0
    assert payload["sampleProgress"]["closedVirtualEntryCountBefore"] == 0
    assert payload["sampleProgress"]["unpricedClosedCountBefore"] == 1
    assert payload["sampleProgress"]["targetReached"] is False


def test_store_latest_cli_filters_symbol_and_currency():
    outputs = []
    original_print_json = cli.print_json
    cwd = Path.cwd()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        os.chdir(root)
        try:
            store = StateStore("data/mexc_engine.sqlite3")
            store.save_event("nautilus_paper_decision", {"symbol": "ETH_USDT", "currency": "USDT"})
            target_id = store.save_event("nautilus_paper_decision", {"symbol": "BTC_USDT", "currency": "USDT"})
            cli.print_json = outputs.append
            status = cli.main(
                [
                    "store",
                    "latest",
                    "--event-type",
                    "nautilus_paper_decision",
                    "--symbol",
                    "BTC_USDT",
                    "--currency",
                    "USDT",
                    "--limit",
                    "5",
                ]
            )
        finally:
            cli.print_json = original_print_json
            os.chdir(cwd)

    assert status == 0
    assert len(outputs[0]) == 1
    assert outputs[0][0]["id"] == target_id


def test_store_stats_cli_filters_symbol_and_currency():
    outputs = []
    original_print_json = cli.print_json
    cwd = Path.cwd()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        os.chdir(root)
        try:
            store = StateStore("data/mexc_engine.sqlite3")
            store.save_event("nautilus_paper_decision", {"symbol": "ETH_USDT", "currency": "USDT"})
            store.save_event("nautilus_paper_decision", {"symbol": "BTC_USDT", "currency": "USDT"})
            cli.print_json = outputs.append
            status = cli.main(
                [
                    "store",
                    "stats",
                    "--event-type",
                    "nautilus_paper_decision",
                    "--symbol",
                    "BTC_USDT",
                    "--currency",
                    "USDT",
                ]
            )
        finally:
            cli.print_json = original_print_json
            os.chdir(cwd)

    assert status == 0
    assert outputs[0]["totalEvents"] == 1
    assert outputs[0]["filters"]["symbol"] == "BTC_USDT"


def _run_audit_safety_in_temp_root(fake_client):
    cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env").write_text("MEXC_ACCESS_KEY=access-123\nMEXC_SECRET_KEY=secret-456\n", encoding="utf-8")
        (root / ".env").chmod(0o600)
        (root / ".gitignore").write_text(".env\n", encoding="utf-8")
        os.chdir(root)
        try:
            return cli.audit_safety(
                MexcSettings(
                    access_key="access-123",
                    secret_key="secret-456",
                    state_db=str(root / "data" / "state.sqlite3"),
                    strategy_allowed_sides={"open-short"},
                ),
                RiskSettings(allowed_symbols={"BTC_USDT"}, kill_switch_file=str(root / ".kill-switch")),
                fake_client,
            )
        finally:
            os.chdir(cwd)


def _paper_loop_kwargs(**overrides):
    kwargs = {
        "symbol": "BTC_USDT",
        "currency": "USDT",
        "market_messages": 1,
        "history_limit": 1,
        "deals_limit": 1,
        "leverage": 2,
        "max_notional_usdt": 10,
        "min_confidence": 0.65,
        "max_margin_fraction": 0.75,
        "paper_equity_usdt": None,
        "min_depth_imbalance": 0.12,
        "max_spread_bps": 2.5,
        "max_abs_funding_rate": 0.0005,
        "max_market_age_seconds": 60,
        "quality_gate_lookback": 0,
        "quality_min_samples": 5,
        "quality_edge_horizon_samples": 3,
        "quality_min_edge_evaluable": 3,
        "quality_min_edge_win_rate": 0.55,
        "quality_min_side_edge_evaluable": 2,
        "quality_min_side_edge_win_rate": 0.55,
        "quality_recovery_window_evaluable": 3,
        "quality_recovery_min_win_rate": 0.55,
        "quality_max_sample_age_seconds": 3600,
        "quality_rolling_windows": (5, 10, 25, 50),
        "trend_filter_enabled": False,
        "trend_interval": "1m",
        "trend_lookback": 60,
        "trend_short_period": 5,
        "trend_long_period": 20,
        "trend_max_candle_age_seconds": 300,
        "volatility_filter_enabled": False,
        "volatility_interval": "1m",
        "volatility_lookback": 60,
        "min_avg_range_bps": None,
        "max_avg_range_bps": None,
        "min_latest_range_bps": None,
        "max_latest_range_bps": None,
        "volatility_max_candle_age_seconds": 300,
        "iterations": 1,
        "interval": 0,
        "target_samples": None,
        "target_closed_trades": None,
        "include_raw": False,
        "save": True,
    }
    kwargs.update(overrides)
    return kwargs


def _paper_decision_payload(*, timestamp, would_open=False):
    action = "paper-open-short" if would_open else "hold"
    side = "open-short" if would_open else "hold"
    return {
        "timestamp": timestamp,
        "mode": "paper-trading-read-only",
        "symbol": "BTC_USDT",
        "currency": "USDT",
        "ok": True,
        "wouldOpen": would_open,
        "action": action,
        "side": side,
        "confidence": "0.72" if would_open else "0",
        "virtualOrder": {
            "entryPrice": "80000",
            "vol": "1",
            "contractSize": "0.0001",
            "estimatedTakerFee": "0.0008",
            "stopLossPrice": "80100",
            "takeProfitPrice": "79800",
        }
        if would_open
        else None,
        "liveOrderSubmitted": False,
        "blockers": ["test hold"],
        "warnings": [],
        "nextPhase": "collect-paper-loop-samples-and-review-edge",
    }
