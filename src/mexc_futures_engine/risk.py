from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import OrderRequest
from .settings import RiskSettings


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()

    def raise_if_blocked(self) -> None:
        if not self.allowed:
            raise RiskRejected("; ".join(self.reasons))


class RiskRejected(RuntimeError):
    pass


class RiskEngine:
    def __init__(self, settings: RiskSettings):
        self.settings = settings

    def validate_order(self, order: OrderRequest) -> RiskDecision:
        reasons: list[str] = []
        symbol = order.symbol.upper()

        if Path(self.settings.kill_switch_file).exists():
            reasons.append(f"kill switch is active: {self.settings.kill_switch_file}")

        if self.settings.allowed_symbols and symbol not in self.settings.allowed_symbols:
            reasons.append(f"symbol {symbol} is not allowed")

        if order.vol <= 0:
            reasons.append("order volume must be positive")

        if order.vol > self.settings.max_order_vol:
            reasons.append(f"order volume {order.vol} exceeds max {self.settings.max_order_vol}")

        if order.price <= 0:
            reasons.append("order price must be positive")

        if order.opens_position and order.contract_size is None:
            reasons.append("contract size is required for notional risk check")
        elif order.contract_size is not None:
            estimated_notional = order.price * order.vol * order.contract_size
            if estimated_notional > self.settings.max_notional_usdt:
                reasons.append(
                    f"estimated notional {estimated_notional:.8f} exceeds max {self.settings.max_notional_usdt:.8f}"
                )

        if order.opens_position:
            if order.leverage is None:
                reasons.append("leverage is required when opening a position")
            elif order.leverage > self.settings.max_leverage:
                reasons.append(f"leverage {order.leverage} exceeds max {self.settings.max_leverage}")

            if self.settings.require_stop_loss and not order.stop_loss_price:
                reasons.append("stop loss is required when opening a position")

        return RiskDecision(allowed=not reasons, reasons=tuple(reasons))

    def validate_action(self, action: str) -> RiskDecision:
        reasons: list[str] = []
        if Path(self.settings.kill_switch_file).exists():
            reasons.append(f"kill switch is active: {self.settings.kill_switch_file}")
        return RiskDecision(allowed=not reasons, reasons=tuple(reasons))
