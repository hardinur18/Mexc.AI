from mexc_futures_engine.models import OpenType, OrderRequest, OrderType, Side
from mexc_futures_engine.risk import RiskEngine
from mexc_futures_engine.settings import RiskSettings


def test_risk_rejects_unsafe_open_order():
    engine = RiskEngine(
        RiskSettings(
            allowed_symbols={"BTC_USDT"},
            max_leverage=3,
            max_order_vol=1,
            max_notional_usdt=50,
            require_stop_loss=True,
        )
    )
    order = OrderRequest(
        symbol="BTC_USDT",
        side=Side.OPEN_LONG,
        order_type=OrderType.LIMIT,
        open_type=OpenType.ISOLATED,
        price=100,
        vol=2,
        contract_size=1,
        leverage=10,
    )

    decision = engine.validate_order(order)

    assert not decision.allowed
    assert "order volume 2 exceeds max 1" in decision.reasons
    assert "estimated notional 200.00000000 exceeds max 50.00000000" in decision.reasons
    assert "leverage 10 exceeds max 3" in decision.reasons
    assert "stop loss is required when opening a position" in decision.reasons


def test_risk_allows_conservative_order():
    engine = RiskEngine(
        RiskSettings(
            allowed_symbols={"BTC_USDT"},
            max_leverage=3,
            max_order_vol=1,
            max_notional_usdt=100_000,
            require_stop_loss=True,
        )
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

    assert engine.validate_order(order).allowed


def test_risk_requires_contract_size_for_open_order_notional_check():
    engine = RiskEngine(
        RiskSettings(
            allowed_symbols={"BTC_USDT"},
            max_leverage=3,
            max_order_vol=10,
            max_notional_usdt=50,
            require_stop_loss=False,
        )
    )
    order = OrderRequest(
        symbol="BTC_USDT",
        side=Side.OPEN_LONG,
        order_type=OrderType.LIMIT,
        open_type=OpenType.ISOLATED,
        price=60_000,
        vol=1,
        leverage=2,
    )

    decision = engine.validate_order(order)

    assert not decision.allowed
    assert "contract size is required for notional risk check" in decision.reasons
