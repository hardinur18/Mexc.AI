from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MexcFuturesAdapterConfig:
    venue: str = "MEXC"
    account_type: str = "FUTURES"
    api_tradable_only: bool = True
    use_doh_dns: bool = True
    read_only: bool = True
    live_mutation_enabled: bool = False
    default_currency: str = "USDT"
    default_history_limit: int = 20
    default_deals_limit: int = 20
    default_market_messages: int = 2
    default_private_ws_messages: int = 5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def assert_read_only_safe(self) -> None:
        if not self.read_only:
            raise ValueError("MEXC adapter boundary must stay read-only for this phase")
        if self.live_mutation_enabled:
            raise ValueError("MEXC live mutation is not adapter-ready")
        if self.default_history_limit <= 0:
            raise ValueError("default_history_limit must be positive")
        if self.default_deals_limit <= 0:
            raise ValueError("default_deals_limit must be positive")
        if self.default_market_messages <= 0:
            raise ValueError("default_market_messages must be positive")
        if self.default_private_ws_messages <= 0:
            raise ValueError("default_private_ws_messages must be positive")
