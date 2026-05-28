from mexc_futures_engine.client import LiveTradingLocked, MexcFuturesClient
from mexc_futures_engine.models import OpenType, OrderRequest, OrderType, Side
from mexc_futures_engine.risk import RiskEngine
from mexc_futures_engine.settings import MexcSettings, RiskSettings


def test_live_order_requires_explicit_confirmation_phrase():
    client = MexcFuturesClient(
        MexcSettings(
            access_key="access",
            secret_key="secret",
            live_trading_enabled=True,
            live_confirm="",
        ),
        risk_engine=RiskEngine(
            RiskSettings(
                allowed_symbols={"BTC_USDT"},
                max_leverage=3,
                max_order_vol=1,
                max_notional_usdt=100_000,
                require_stop_loss=True,
            )
        ),
    )
    order = OrderRequest(
        symbol="BTC_USDT",
        side=Side.OPEN_LONG,
        order_type=OrderType.LIMIT,
        open_type=OpenType.ISOLATED,
        price=60_000,
        vol=1,
        contract_size=0.0001,
        leverage=2,
        stop_loss_price=59_000,
    )

    try:
        client.place_order(order)
    except LiveTradingLocked as exc:
        assert "MEXC_LIVE_CONFIRM" in str(exc)
    else:
        raise AssertionError("live order should be locked without confirmation phrase")


def test_live_order_requires_mutation_phase_lock_after_confirmation_phrase():
    client = MexcFuturesClient(
        MexcSettings(
            access_key="access",
            secret_key="secret",
            live_trading_enabled=True,
            live_confirm="I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK",
            live_mutation_phase_enabled=False,
        ),
        risk_engine=RiskEngine(
            RiskSettings(
                allowed_symbols={"BTC_USDT"},
                max_leverage=3,
                max_order_vol=1,
                max_notional_usdt=100_000,
                require_stop_loss=True,
            )
        ),
    )
    order = OrderRequest(
        symbol="BTC_USDT",
        side=Side.OPEN_LONG,
        order_type=OrderType.LIMIT,
        open_type=OpenType.ISOLATED,
        price=60_000,
        vol=1,
        contract_size=0.0001,
        leverage=2,
        stop_loss_price=59_000,
    )

    try:
        client.place_order(order)
    except LiveTradingLocked as exc:
        assert "MEXC_LIVE_MUTATION_PHASE_ENABLED" in str(exc)
    else:
        raise AssertionError("live order should be locked until live mutation phase is enabled")


def test_live_order_still_disabled_after_triple_lock_until_live_phase_exists():
    client = MexcFuturesClient(
        MexcSettings(
            access_key="access",
            secret_key="secret",
            live_trading_enabled=True,
            live_confirm="I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK",
            live_mutation_phase_enabled=True,
        ),
        risk_engine=RiskEngine(
            RiskSettings(
                allowed_symbols={"BTC_USDT"},
                max_leverage=3,
                max_order_vol=1,
                max_notional_usdt=100_000,
                require_stop_loss=True,
            )
        ),
    )
    order = OrderRequest(
        symbol="BTC_USDT",
        side=Side.OPEN_LONG,
        order_type=OrderType.LIMIT,
        open_type=OpenType.ISOLATED,
        price=60_000,
        vol=1,
        contract_size=0.0001,
        leverage=2,
        stop_loss_price=59_000,
    )

    try:
        client.place_order(order)
    except LiveTradingLocked as exc:
        assert "live mutation client is disabled" in str(exc)
    else:
        raise AssertionError("live order should stay disabled until explicit live execution is implemented")


def test_live_leverage_change_still_disabled_after_triple_lock_until_live_phase_exists():
    client = MexcFuturesClient(
        MexcSettings(
            access_key="access",
            secret_key="secret",
            live_trading_enabled=True,
            live_confirm="I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK",
            live_mutation_phase_enabled=True,
        ),
        risk_engine=RiskEngine(
            RiskSettings(
                allowed_symbols={"BTC_USDT"},
                max_leverage=3,
                max_order_vol=1,
                max_notional_usdt=100_000,
                require_stop_loss=True,
            )
        ),
    )

    try:
        client.change_leverage({"symbol": "BTC_USDT", "leverage": 2})
    except LiveTradingLocked as exc:
        assert "live mutation client is disabled" in str(exc)
    else:
        raise AssertionError("live leverage mutation should stay disabled until explicit live execution is implemented")


def test_direct_private_mutation_request_is_locked_before_network_call():
    client = MexcFuturesClient(
        MexcSettings(
            access_key="access",
            secret_key="secret",
            live_trading_enabled=True,
            live_confirm="I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK",
            live_mutation_phase_enabled=True,
        )
    )

    try:
        client._request(  # noqa: SLF001 - intentional guard coverage for low-level bypass.
            "POST",
            "/api/v1/private/order/create",
            body={"symbol": "BTC_USDT"},
            private=True,
        )
    except LiveTradingLocked as exc:
        assert "live mutation client is disabled" in str(exc)
    else:
        raise AssertionError("direct private mutation request should stay disabled before network I/O")


def test_direct_private_mutation_path_is_locked_even_if_private_flag_is_false():
    client = MexcFuturesClient(
        MexcSettings(
            access_key="access",
            secret_key="secret",
            live_trading_enabled=False,
        )
    )

    try:
        client._request(  # noqa: SLF001 - intentional guard coverage for low-level bypass.
            "POST",
            "/api/v1/private/order/create",
            body={"symbol": "BTC_USDT"},
            private=False,
        )
    except LiveTradingLocked as exc:
        assert "MEXC_LIVE_CONFIRM" in str(exc)
    else:
        raise AssertionError("private mutation endpoint path should be blocked before network I/O")
