from mexc_futures_engine.nautilus_provider import build_instrument_provider_report
from mexc_futures_engine.nautilus_provider import normalize_symbols


def test_provider_filters_to_api_tradable_specs():
    report = build_instrument_provider_report(
        [
            _row("BTC_USDT"),
            _row("ETH_USDT", api_allowed=False),
            _row("SOL_USDT", hidden=True),
            _row("XRP_USDT", state=2),
        ],
        api_tradable_only=True,
    )

    assert report.total_contracts == 4
    assert report.selected_contracts == 4
    assert report.loaded == 1
    assert report.skipped == 3
    assert report.skipped_reasons == {
        "apiAllowed=false": 1,
        "hidden": 1,
        "state=2": 1,
    }
    assert report.to_dict(include_specs=False)["symbols"] == ["BTC_USDT"]


def test_provider_symbol_filter_keeps_requested_order_normalized():
    report = build_instrument_provider_report(
        [_row("BTC_USDT"), _row("ETH_USDT"), _row("SOL_USDT")],
        symbols=[" eth_usdt,btc_usdt ", "ETH_USDT"],
    )

    assert report.requested_symbols == ["ETH_USDT", "BTC_USDT"]
    assert report.selected_contracts == 2
    assert [spec.raw_symbol for spec in report.specs] == ["BTC_USDT", "ETH_USDT"]


def test_normalize_symbols_splits_commas_and_deduplicates():
    assert normalize_symbols(["btc_usdt, eth_usdt", "BTC_USDT", ""]) == ["BTC_USDT", "ETH_USDT"]


def _row(symbol, *, api_allowed=True, hidden=False, state=0):
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
        "apiAllowed": api_allowed,
        "state": state,
        "isHidden": hidden,
    }
