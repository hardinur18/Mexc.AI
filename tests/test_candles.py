from decimal import Decimal

from mexc_futures_engine.candles import (
    CandleParseError,
    canonical_candle_interval,
    mexc_candle_interval,
    parse_rest_klines,
    parse_ws_kline,
)
from mexc_futures_engine.client import MexcApiError, MexcFuturesClient
from mexc_futures_engine.settings import MexcSettings
from mexc_futures_engine.ws import kline_subscription


def test_interval_mapping_accepts_canonical_and_exchange_names():
    assert mexc_candle_interval("1m") == "Min1"
    assert mexc_candle_interval("4h") == "Hour4"
    assert mexc_candle_interval("Min60") == "Min60"
    assert canonical_candle_interval("Min60") == "1h"

    try:
        mexc_candle_interval("2m")
    except CandleParseError:
        pass
    else:
        raise AssertionError("unsupported interval should raise CandleParseError")


def test_parse_rest_klines_from_mexc_perpetual_shape():
    candles = parse_rest_klines(
        {
            "success": True,
            "data": {
                "time": [1718751000, 1718751060000],
                "open": [65213.5, "65210.5"],
                "high": [65233.5, "65220.0"],
                "low": [65208.5, "65200.0"],
                "close": [65210.5, "65215.0"],
                "vol": [512797, "9.5"],
                "amount": [3344326.96161, "99.25"],
            },
        },
        symbol="btc_usdt",
        interval="1h",
    )

    assert len(candles) == 2
    assert candles[0].symbol == "BTC_USDT"
    assert candles[0].interval == "1h"
    assert candles[0].exchange_interval == "Min60"
    assert candles[0].open_time_ms == 1718751000000
    assert candles[0].open == Decimal("65213.5")
    assert candles[0].quote_volume == Decimal("3344326.96161")
    assert candles[1].open_time_ms == 1718751060000
    assert candles[1].to_dict()["close"] == "65215"


def test_parse_ws_kline_from_mexc_perpetual_push_message():
    candle = parse_ws_kline(
        {
            "symbol": "BTC_USDT",
            "data": {
                "symbol": "BTC_USDT",
                "interval": "Min60",
                "t": 1718751060,
                "o": 65213.5,
                "c": 65210.5,
                "h": 65233.5,
                "l": 65208.5,
                "a": 3344326.96161,
                "q": 512797,
                "ro": 65213.4,
                "rc": 65210.5,
                "rh": 65233.5,
                "rl": 65208.5,
            },
            "channel": "push.kline",
            "ts": 1718751106472,
        }
    )

    assert candle is not None
    assert candle.open_time_ms == 1718751060000
    assert candle.close_time_ms == 1718751106472
    assert candle.high == Decimal("65233.5")
    assert candle.low == Decimal("65208.5")
    assert candle.volume == Decimal("512797")
    assert candle.quote_volume == Decimal("3344326.96161")
    assert parse_ws_kline({"channel": "push.ticker"}) is None


def test_kline_subscription_message_matches_local_upstream_shape():
    assert kline_subscription("btc_usdt", "1h").to_message() == {
        "method": "sub.kline",
        "param": {"symbol": "BTC_USDT", "interval": "Min60"},
        "gzip": False,
    }


def test_client_klines_builds_read_only_public_rest_request():
    calls = []

    class FakeClient(MexcFuturesClient):
        def _request(self, method, path, *, params=None, body=None, private):
            calls.append((method, path, params, body, private))
            return {"success": True, "data": {}}

    client = FakeClient(MexcSettings(access_key="", secret_key=""))
    assert client.klines("btc_usdt", "5m", start_time_ms=1000, end_time_ms=2000) == {"success": True, "data": {}}
    assert calls == [
        (
            "GET",
            "/api/v1/contract/kline/BTC_USDT",
            {"interval": "Min5", "startTime": 1000, "endTime": 2000},
            None,
            False,
        )
    ]


def test_client_klines_requires_start_and_end_time_together():
    client = MexcFuturesClient(MexcSettings(access_key="", secret_key=""))
    try:
        client.klines("BTC_USDT", "1m", start_time_ms=1000)
    except MexcApiError:
        pass
    else:
        raise AssertionError("klines should require start and end time together")
