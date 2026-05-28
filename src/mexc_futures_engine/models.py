from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class Side(IntEnum):
    OPEN_LONG = 1
    CLOSE_SHORT = 2
    OPEN_SHORT = 3
    CLOSE_LONG = 4


class OrderType(IntEnum):
    LIMIT = 1
    POST_ONLY = 2
    IOC = 3
    FOK = 4
    MARKET = 5


class OpenType(IntEnum):
    ISOLATED = 1
    CROSS = 2


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    order_type: OrderType
    open_type: OpenType
    vol: float
    price: float
    contract_size: float | None = None
    leverage: int | None = None
    external_oid: str | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    position_mode: int | None = None
    reduce_only: bool | None = None

    @property
    def opens_position(self) -> bool:
        return self.side in {Side.OPEN_LONG, Side.OPEN_SHORT}

    def to_mexc_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": self.symbol.upper(),
            "price": self.price,
            "vol": self.vol,
            "side": int(self.side),
            "type": int(self.order_type),
            "openType": int(self.open_type),
        }

        optional = {
            "leverage": self.leverage,
            "externalOid": self.external_oid,
            "stopLossPrice": self.stop_loss_price,
            "takeProfitPrice": self.take_profit_price,
            "positionMode": self.position_mode,
            "reduceOnly": self.reduce_only,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        return payload
