from mexc_futures_engine.settings import MexcSettings
from mexc_futures_engine.ws import (
    build_ping_message,
    build_private_filter_message,
    build_private_login_message,
    deal_subscription,
    decode_ws_payload,
    depth_subscription,
    ticker_subscription,
)


def test_public_subscription_messages():
    assert ticker_subscription("btc_usdt").to_message() == {
        "method": "sub.ticker",
        "param": {"symbol": "BTC_USDT"},
        "gzip": False,
    }
    assert deal_subscription("BTC_USDT").to_message()["method"] == "sub.deal"
    assert depth_subscription("BTC_USDT").to_message()["method"] == "sub.depth"


def test_ping_and_filter_messages():
    assert build_ping_message() == {"method": "ping"}
    assert build_private_filter_message() == {"method": "personal.filter", "param": {"filters": []}}


def test_private_login_message_shape():
    settings = MexcSettings(access_key="access", secret_key="secret")
    message = build_private_login_message(settings)

    assert message["method"] == "login"
    assert message["param"]["apiKey"] == "access"
    assert message["param"]["reqTime"].isdigit()
    assert len(message["param"]["signature"]) == 64


def test_decode_plain_json_payload():
    assert decode_ws_payload('{"channel":"pong","data":1}') == {"channel": "pong", "data": 1}
