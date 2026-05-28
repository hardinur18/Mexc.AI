from tempfile import TemporaryDirectory
from pathlib import Path

from mexc_futures_engine.store import StateStore


def test_latest_events_can_filter_symbol_and_currency_before_limit():
    with TemporaryDirectory() as tmp:
        store = StateStore(str(Path(tmp) / "state.sqlite3"))
        for index in range(5):
            store.save_event(
                "nautilus_paper_decision",
                {"symbol": "ETH_USDT", "currency": "USDT", "index": index},
            )
        target_id = store.save_event(
            "nautilus_paper_decision",
            {"symbol": "BTC_USDT", "currency": "USDT", "index": "target"},
        )
        for index in range(5, 10):
            store.save_event(
                "nautilus_paper_decision",
                {"symbol": "ETH_USDT", "currency": "USDT", "index": index},
            )

        events = store.latest_events(
            event_type="nautilus_paper_decision",
            limit=1,
            symbol="BTC_USDT",
            currency="USDT",
        )

    assert len(events) == 1
    assert events[0]["id"] == target_id
    assert events[0]["symbol"] == "BTC_USDT"


def test_count_events_can_filter_symbol_and_currency():
    with TemporaryDirectory() as tmp:
        store = StateStore(str(Path(tmp) / "state.sqlite3"))
        store.save_event("nautilus_paper_decision", {"symbol": "BTC_USDT", "currency": "USDT"})
        store.save_event("nautilus_paper_decision", {"symbol": "BTC_USDT", "currency": "USDT"})
        store.save_event("nautilus_paper_decision", {"symbol": "ETH_USDT", "currency": "USDT"})
        store.save_event("nautilus_paper_ledger", {"symbol": "BTC_USDT", "currency": "USDT"})

        count = store.count_events(
            event_type="nautilus_paper_decision",
            symbol="BTC_USDT",
            currency="USDT",
        )

    assert count == 2


def test_stats_can_filter_symbol_currency_and_event_type():
    with TemporaryDirectory() as tmp:
        store = StateStore(str(Path(tmp) / "state.sqlite3"))
        store.save_event("nautilus_paper_decision", {"symbol": "BTC_USDT", "currency": "USDT"})
        store.save_event("nautilus_paper_decision", {"symbol": "ETH_USDT", "currency": "USDT"})
        store.save_event("nautilus_paper_ledger", {"symbol": "BTC_USDT", "currency": "USDT"})

        stats = store.stats(
            event_type="nautilus_paper_decision",
            symbol="BTC_USDT",
            currency="USDT",
        )

    assert stats["totalEvents"] == 1
    assert stats["byType"] == {"nautilus_paper_decision": 1}
    assert stats["filters"]["symbol"] == "BTC_USDT"
