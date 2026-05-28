from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContractPair:
    symbol: str
    api_allowed: bool
    state: int | None
    hidden: bool
    max_leverage: int | None
    contract_size: float | None
    min_vol: float | None
    max_vol: float | None
    maker_fee_rate: float | None
    taker_fee_rate: float | None

    @property
    def enabled(self) -> bool:
        return self.state in (None, 0) and not self.hidden

    @property
    def api_tradable(self) -> bool:
        return self.enabled and self.api_allowed


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_contract_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def parse_contract_pairs(response: dict[str, Any]) -> list[ContractPair]:
    pairs: list[ContractPair] = []
    for row in extract_contract_rows(response):
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue

        pairs.append(
            ContractPair(
                symbol=symbol,
                api_allowed=bool(row.get("apiAllowed")),
                state=_as_int(row.get("state")),
                hidden=bool(row.get("isHidden")),
                max_leverage=_as_int(row.get("maxLeverage")),
                contract_size=_as_float(row.get("contractSize")),
                min_vol=_as_float(row.get("minVol")),
                max_vol=_as_float(row.get("maxVol")),
                maker_fee_rate=_as_float(row.get("makerFeeRate")),
                taker_fee_rate=_as_float(row.get("takerFeeRate")),
            )
        )
    return sorted(pairs, key=lambda item: item.symbol)


def pair_summary(pairs: list[ContractPair]) -> dict[str, Any]:
    enabled = [pair for pair in pairs if pair.enabled]
    api_tradable = [pair for pair in pairs if pair.api_tradable]
    return {
        "total": len(pairs),
        "enabled": len(enabled),
        "apiTradable": len(api_tradable),
        "symbols": [pair.symbol for pair in pairs],
        "apiTradableSymbols": [pair.symbol for pair in api_tradable],
    }

