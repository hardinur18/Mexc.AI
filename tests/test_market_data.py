from mexc_futures_engine.market_data import MarketDataParser
from mexc_futures_engine.market_data import parse_public_ws_message


def test_ticker_message_to_quote_tick_spec():
    events = parse_public_ws_message(
        {
            "channel": "push.ticker",
            "symbol": "BTC_USDT",
            "ts": 1778733372863,
            "data": {
                "symbol": "BTC_USDT",
                "timestamp": 1778733372863,
                "bid1": 79295.4,
                "ask1": 79295.5,
                "lastPrice": 79295.4,
                "fairPrice": 79298.6,
                "indexPrice": 79335.9,
                "fundingRate": 0.000064,
            },
        },
        ts_init_ms=1778733373000,
    )

    event = events[0].to_dict()
    assert event["eventType"] == "QuoteTick"
    assert event["instrumentId"] == "BTC_USDT-PERP.MEXC"
    assert event["payload"]["bidPrice"] == "79295.4"
    assert event["payload"]["askPrice"] == "79295.5"
    assert event["payload"]["bidSize"] is None
    assert event["tsEventNs"] == 1778733372863000000


def test_deal_message_to_trade_tick_spec_preserves_raw_side_codes():
    events = parse_public_ws_message(
        {
            "channel": "push.deal",
            "symbol": "BTC_USDT",
            "ts": 1778733372707,
            "data": {
                "M": 2,
                "O": 3,
                "T": 2,
                "i": "14537542858",
                "p": 79295.4,
                "t": 1778733372706,
                "v": 38,
            },
        },
        ts_init_ms=1778733373000,
    )

    event = events[0].to_dict()
    assert event["eventType"] == "TradeTick"
    assert event["payload"]["tradeId"] == "14537542858"
    assert event["payload"]["price"] == "79295.4"
    assert event["payload"]["size"] == "38"
    assert event["payload"]["aggressorSide"] == "NO_AGGRESSOR"
    assert event["payload"]["rawTradeTypeCode"] == 2
    assert event["payload"]["rawOrderSideCode"] == 3


def test_depth_message_to_quote_tick_and_order_book_deltas_spec():
    events = parse_public_ws_message(
        {
            "channel": "push.depth",
            "symbol": "BTC_USDT",
            "ts": 1778733372748,
            "data": {
                "begin": 36746211629,
                "end": 36746211736,
                "version": 36746211736,
                "bids": [[79295.4, 15223, 1], [79290.4, 0, 0]],
                "asks": [[79295.5, 35697, 12]],
            },
        },
        ts_init_ms=1778733373000,
    )

    quote = events[0].to_dict()
    assert quote["eventType"] == "QuoteTick"
    assert quote["sequence"] == 36746211736
    assert quote["payload"]["bidPrice"] == "79295.4"
    assert quote["payload"]["bidSize"] == "15223"
    assert quote["payload"]["askPrice"] == "79295.5"
    assert quote["payload"]["askSize"] == "35697"
    assert quote["payload"]["source"] == "MEXC push.depth"

    event = events[1].to_dict()
    assert event["eventType"] == "OrderBookDeltas"
    assert event["sequence"] == 36746211736
    assert event["payload"]["bookType"] == "L2_MBP"
    assert event["payload"]["deltas"] == [
        {"side": "BID", "action": "UPDATE", "price": "79295.4", "size": "15223", "orderCount": 1},
        {"side": "BID", "action": "DELETE", "price": "79290.4", "size": "0", "orderCount": 0},
        {"side": "ASK", "action": "UPDATE", "price": "79295.5", "size": "35697", "orderCount": 12},
    ]


def test_depth_message_without_both_book_sides_only_emits_book_deltas():
    events = parse_public_ws_message(
        {
            "channel": "push.depth",
            "symbol": "BTC_USDT",
            "ts": 1778733372748,
            "data": {
                "version": 36746211736,
                "bids": [[79295.4, 15223, 1]],
                "asks": [],
            },
        },
        ts_init_ms=1778733373000,
    )

    assert [event.to_dict()["eventType"] for event in events] == ["OrderBookDeltas"]


def test_stateful_depth_book_dedupes_and_moves_quote_after_delete():
    parser = MarketDataParser()
    first = parser.parse_public_ws_message(
        {
            "channel": "push.depth",
            "symbol": "BTC_USDT",
            "ts": 1778733372748,
            "data": {
                "version": 1,
                "bids": [[101, 5, 1], [100, 9, 2]],
                "asks": [[102, 4, 1]],
            },
        },
        ts_init_ms=1778733373000,
    )
    repeat = parser.parse_public_ws_message(
        {
            "channel": "push.depth",
            "symbol": "BTC_USDT",
            "ts": 1778733372749,
            "data": {
                "version": 2,
                "bids": [[101, 5, 1]],
                "asks": [[102, 4, 1]],
            },
        },
        ts_init_ms=1778733373000,
    )
    after_delete = parser.parse_public_ws_message(
        {
            "channel": "push.depth",
            "symbol": "BTC_USDT",
            "ts": 1778733372750,
            "data": {
                "version": 3,
                "bids": [[101, 0, 0]],
                "asks": [],
            },
        },
        ts_init_ms=1778733373000,
    )

    assert [event.to_dict()["eventType"] for event in first] == ["QuoteTick", "OrderBookDeltas"]
    assert [event.to_dict()["eventType"] for event in repeat] == ["OrderBookDeltas"]
    assert [event.to_dict()["eventType"] for event in after_delete] == ["QuoteTick", "OrderBookDeltas"]
    quote = after_delete[0].to_dict()
    assert quote["payload"]["bidPrice"] == "100"
    assert quote["payload"]["bidSize"] == "9"
    assert quote["payload"]["askPrice"] == "102"
    assert quote["payload"]["askSize"] == "4"


def test_depth_quote_uses_matching_price_precision_for_nautilus_quote_tick():
    events = parse_public_ws_message(
        {
            "channel": "push.depth",
            "symbol": "BTC_USDT",
            "ts": 1778733372748,
            "data": {
                "version": 4,
                "bids": [[79706.5, 14118, 1]],
                "asks": [[79707, 5, 1]],
            },
        },
        ts_init_ms=1778733373000,
    )

    quote = events[0].to_dict()
    assert quote["eventType"] == "QuoteTick"
    assert quote["payload"]["bidPrice"] == "79706.5"
    assert quote["payload"]["askPrice"] == "79707.0"


def test_subscription_ack_has_no_market_data_events():
    assert parse_public_ws_message({"channel": "rs.sub.ticker", "data": "success"}) == []
