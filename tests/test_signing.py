from mexc_futures_engine.signing import canonical_query, compact_json, sign


def test_canonical_query_sorts_and_encodes_values():
    assert canonical_query({"symbol": "BTC_USDT", "order_ids": "1,2", "empty": None}) == (
        "order_ids=1%2C2&symbol=BTC_USDT"
    )


def test_compact_json_uses_stable_no_space_format():
    assert compact_json({"symbol": "BTC_USDT", "vol": 1}) == '{"symbol":"BTC_USDT","vol":1}'


def test_sign_hmac_sha256_hex():
    assert sign("access", "secret", "123", "a=1") == (
        "99a2fe9f174846924428de5436463ad5b8468988aea4268e30ae6f08c6b72f1a"
    )
