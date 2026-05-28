from mexc_futures_engine.nautilus_mapping import contract_row_to_nautilus_spec


def test_contract_row_to_nautilus_crypto_perpetual_spec():
    spec = contract_row_to_nautilus_spec(
        {
            "symbol": "BTC_USDT",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "settleCoin": "USDT",
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
            "minLeverage": 1,
            "maxLeverage": 500,
        }
    ).to_dict()

    assert spec["instrumentType"] == "CryptoPerpetual"
    assert spec["instrumentId"] == "BTC_USDT-PERP.MEXC"
    assert spec["rawSymbol"] == "BTC_USDT"
    assert spec["baseCurrency"] == "BTC"
    assert spec["quoteCurrency"] == "USDT"
    assert spec["settlementCurrency"] == "USDT"
    assert not spec["isInverse"]
    assert spec["pricePrecision"] == 1
    assert spec["sizePrecision"] == 0
    assert spec["priceIncrement"] == "0.1"
    assert spec["sizeIncrement"] == "1"
    assert spec["multiplier"] == "0.0001"
    assert spec["minQuantity"] == "1"
    assert spec["maxQuantity"] == "400000"
    assert spec["marginInit"] == "0.002"
    assert spec["marginMaint"] == "0.001"
    assert spec["makerFee"] == "0"
    assert spec["takerFee"] == "0.0001"
    assert spec["tsEventNs"] == 1591242684000000000
    assert spec["info"]["apiAllowed"] is True
