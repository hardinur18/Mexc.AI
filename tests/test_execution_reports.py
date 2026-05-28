from mexc_futures_engine.execution_reports import build_execution_report_bundle
from mexc_futures_engine.execution_reports import summarize_execution_report_bundle


def test_execution_report_bundle_maps_account_order_and_fill():
    bundle = build_execution_report_bundle(
        asset_response={
            "data": {
                "currency": "USDT",
                "equity": 6,
                "availableBalance": 5.5,
                "frozenBalance": 0.5,
                "cashBalance": 6,
                "unrealized": 0,
                "positionMargin": 0,
            }
        },
        positions_response={"data": []},
        open_orders_response={"data": []},
        history_orders_response={
            "data": [
                {
                    "symbol": "BTC_USDT",
                    "orderId": "order-1",
                    "externalOid": "client-1",
                    "side": 1,
                    "state": 3,
                    "price": 76000,
                    "vol": 12,
                    "dealVol": 12,
                    "dealAvgPrice": 76005.3,
                    "createTime": 1776418097000,
                    "updateTime": 1776418097000,
                    "leverage": 2,
                    "feeCurrency": "USDT",
                    "totalFee": 0.01,
                }
            ]
        },
        order_deals_response={
            "data": [
                {
                    "symbol": "BTC_USDT",
                    "orderId": "order-1",
                    "id": "fill-1",
                    "side": 1,
                    "price": 76005.3,
                    "vol": 12,
                    "timestamp": 1776418097000,
                    "taker": True,
                    "fee": 0.01,
                    "feeCurrency": "USDT",
                }
            ]
        },
        symbol="BTC_USDT",
        currency="USDT",
        include_raw=False,
    )

    assert bundle["reportCount"] == 3
    assert bundle["reportCounts"] == {
        "AccountState": 1,
        "FillReport": 1,
        "OrderStatusReport": 1,
    }
    reports = {report["reportType"]: report for report in bundle["reports"]}
    assert reports["AccountState"]["payload"]["balances"][0]["free"] == "5.5"
    assert reports["OrderStatusReport"]["payload"]["instrumentId"] == "BTC_USDT-PERP.MEXC"
    assert reports["OrderStatusReport"]["payload"]["side"] == "OPEN_LONG"
    assert reports["OrderStatusReport"]["payload"]["rawStateCode"] == 3
    assert reports["FillReport"]["payload"]["liquiditySide"] == "TAKER"
    assert "raw" not in reports["FillReport"]


def test_execution_report_summary_omits_reports():
    bundle = build_execution_report_bundle(
        asset_response={"data": {"currency": "USDT"}},
        positions_response={"data": []},
        open_orders_response={"data": []},
        history_orders_response={"data": []},
        order_deals_response={"data": []},
        symbol="BTC_USDT",
        currency="USDT",
        include_raw=False,
    )

    summary = summarize_execution_report_bundle(bundle)

    assert summary["reportCount"] == 1
    assert "reports" not in summary
