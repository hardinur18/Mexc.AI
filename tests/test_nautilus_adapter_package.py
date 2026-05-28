from mexc_futures_engine.nautilus_adapter import LiveMutationUnavailable
from mexc_futures_engine.nautilus_adapter import MexcFuturesAdapterConfig
from mexc_futures_engine.nautilus_adapter import MexcFuturesExecutionClientBoundary
from mexc_futures_engine.nautilus_adapter import MexcFuturesInstrumentProviderBoundary
from mexc_futures_engine.nautilus_adapter import build_adapter_manifest


def test_adapter_manifest_declares_readonly_boundary_modules():
    manifest = build_adapter_manifest(upstream_reference={"nautilusTrader": {"exists": True}})

    assert manifest["adapter"] == "mexc_futures"
    assert manifest["targetEngine"] == "NautilusTrader"
    assert manifest["runtimePolicy"]["requiresNautilusRuntimeForImport"] is False
    assert manifest["capabilities"]["liveMutation"]["status"] == "locked"
    assert manifest["modules"]["execution"] == "mexc_futures_engine.nautilus_adapter.execution"
    assert manifest["nextPhase"] == "prepare-sandboxed-nautilus-runtime-install-read-only"


def test_adapter_config_rejects_live_mutation():
    config = MexcFuturesAdapterConfig(live_mutation_enabled=True)

    try:
        config.assert_read_only_safe()
    except ValueError as exc:
        assert "live mutation" in str(exc)
    else:
        raise AssertionError("live mutation config should be rejected")


def test_provider_boundary_loads_symbols_with_existing_mapping():
    provider = MexcFuturesInstrumentProviderBoundary(FakeClient())

    report = provider.load_symbols(["btc_usdt"])

    assert report.loaded == 1
    assert report.specs[0].raw_symbol == "BTC_USDT"
    assert report.specs[0].instrument_id == "BTC_USDT-PERP.MEXC"


def test_execution_boundary_live_mutations_are_unavailable():
    boundary = MexcFuturesExecutionClientBoundary(FakeClient(), object())

    try:
        boundary.submit_order({})
    except LiveMutationUnavailable as exc:
        assert "submit_order" in str(exc)
    else:
        raise AssertionError("submit_order should be unavailable")

    try:
        boundary.cancel_order({})
    except LiveMutationUnavailable as exc:
        assert "cancel_order" in str(exc)
    else:
        raise AssertionError("cancel_order should be unavailable")


def test_execution_boundary_rest_snapshot_preserves_global_positions():
    boundary = MexcFuturesExecutionClientBoundary(FakeExecutionClient(), object())

    snapshot = boundary._rest_snapshot(symbol="BTC_USDT", currency="USDT", history_limit=20)

    assert snapshot["summary"]["targetOpenPositionCount"] == 0
    assert snapshot["summary"]["globalOpenPositionCount"] == 1
    assert snapshot["globalPositions"]["data"][0]["symbol"] == "ETH_USDT"


class FakeClient:
    def contract_detail(self, symbol=None):
        return {"success": True, "data": _row((symbol or "BTC_USDT").upper())}


class FakeExecutionClient:
    def all_assets(self):
        return {"success": True, "data": [{"currency": "USDT"}]}

    def asset(self, currency):
        return {"success": True, "data": {"currency": currency}}

    def open_positions(self, symbol=None):
        if symbol:
            return {"success": True, "data": []}
        return {"success": True, "data": [{"symbol": "ETH_USDT", "holdVol": 1}]}

    def current_orders(self, *, page_num=1, page_size=100):
        return {"success": True, "data": []}

    def historical_orders(self, *, symbol=None, page_num=1, page_size=20):
        return {"success": True, "data": {"resultList": []}}


def _row(symbol):
    base, quote = symbol.split("_", 1)
    return {
        "symbol": symbol,
        "baseCoin": base,
        "quoteCoin": quote,
        "settleCoin": quote,
        "priceScale": 1,
        "priceUnit": 0.1,
        "volScale": 0,
        "volUnit": 1,
        "contractSize": 0.0001,
        "minVol": 1,
        "maxVol": 400000,
        "initialMarginRate": 0.002,
        "maintenanceMarginRate": 0.001,
        "makerFeeRate": 0,
        "takerFeeRate": 0.0001,
        "createTime": 1591242684000,
        "apiAllowed": True,
        "state": 0,
        "isHidden": False,
    }
