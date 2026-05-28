from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import time
from typing import Any, Iterable

from .nautilus_mapping import NautilusInstrumentSpec, contract_row_to_nautilus_spec
from .pairs import extract_contract_rows


@dataclass(frozen=True)
class InstrumentMappingError:
    symbol: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "reason": self.reason}


@dataclass(frozen=True)
class InstrumentProviderReport:
    timestamp: int
    total_contracts: int
    selected_contracts: int
    api_tradable_only: bool
    requested_symbols: list[str] | None
    specs: list[NautilusInstrumentSpec]
    skipped_reasons: dict[str, int]
    mapping_errors: list[InstrumentMappingError]

    @property
    def loaded(self) -> int:
        return len(self.specs)

    @property
    def skipped(self) -> int:
        return sum(self.skipped_reasons.values()) + len(self.mapping_errors)

    def to_dict(self, *, include_specs: bool = True, include_symbols: bool = True) -> dict[str, Any]:
        symbols = [spec.raw_symbol for spec in self.specs]
        payload: dict[str, Any] = {
            "timestamp": self.timestamp,
            "source": "MEXC live contract detail",
            "totalContracts": self.total_contracts,
            "selectedContracts": self.selected_contracts,
            "loaded": self.loaded,
            "skipped": self.skipped,
            "apiTradableOnly": self.api_tradable_only,
            "requestedSymbols": self.requested_symbols,
            "skippedReasons": self.skipped_reasons,
            "mappingErrors": [error.to_dict() for error in self.mapping_errors],
            "summary": self._summary(),
            "symbolsPreview": symbols[:20],
            "symbolsPreviewCount": min(len(symbols), 20),
        }
        if include_symbols:
            payload["symbols"] = symbols
        if include_specs:
            payload["specs"] = [spec.to_dict() for spec in self.specs]
        return payload

    def _summary(self) -> dict[str, Any]:
        quote_counts = Counter(spec.quote_currency for spec in self.specs)
        settlement_counts = Counter(spec.settlement_currency for spec in self.specs)
        return {
            "instrumentTypes": dict(Counter(spec.instrument_type for spec in self.specs)),
            "quoteCurrencies": dict(sorted(quote_counts.items())),
            "settlementCurrencies": dict(sorted(settlement_counts.items())),
            "inverseCount": sum(1 for spec in self.specs if spec.is_inverse),
        }


class MexcNautilusInstrumentProvider:
    def __init__(self, client: Any):
        self._client = client

    def load_all(
        self,
        *,
        api_tradable_only: bool = True,
        symbols: Iterable[str] | None = None,
    ) -> InstrumentProviderReport:
        response = self._client.contract_detail()
        return build_instrument_provider_report(
            extract_contract_rows(response),
            api_tradable_only=api_tradable_only,
            symbols=symbols,
        )

    def load_symbols(
        self,
        symbols: Iterable[str],
        *,
        api_tradable_only: bool = True,
    ) -> InstrumentProviderReport:
        requested_symbols = normalize_symbols(symbols)
        rows: list[dict[str, Any]] = []
        for symbol in requested_symbols:
            rows.extend(extract_contract_rows(self._client.contract_detail(symbol)))
        return build_instrument_provider_report(
            rows,
            api_tradable_only=api_tradable_only,
            symbols=requested_symbols,
        )


def build_instrument_provider_report(
    rows: list[dict[str, Any]],
    *,
    api_tradable_only: bool = True,
    symbols: Iterable[str] | None = None,
) -> InstrumentProviderReport:
    requested_symbols = normalize_symbols(symbols) if symbols else None
    requested_set = set(requested_symbols or [])
    specs: list[NautilusInstrumentSpec] = []
    skipped_reasons: Counter[str] = Counter()
    mapping_errors: list[InstrumentMappingError] = []
    selected_contracts = 0

    for row in rows:
        symbol = _row_symbol(row)
        if requested_set and symbol not in requested_set:
            continue
        selected_contracts += 1

        skip_reason = _skip_reason(row, api_tradable_only=api_tradable_only)
        if skip_reason:
            skipped_reasons[skip_reason] += 1
            continue

        try:
            specs.append(contract_row_to_nautilus_spec(row))
        except ValueError as exc:
            mapping_errors.append(InstrumentMappingError(symbol=symbol, reason=str(exc)))

    return InstrumentProviderReport(
        timestamp=int(time.time() * 1000),
        total_contracts=len(rows),
        selected_contracts=selected_contracts,
        api_tradable_only=api_tradable_only,
        requested_symbols=requested_symbols,
        specs=sorted(specs, key=lambda spec: spec.raw_symbol),
        skipped_reasons=dict(sorted(skipped_reasons.items())),
        mapping_errors=mapping_errors,
    )


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for raw_symbol in symbols:
        for piece in str(raw_symbol).split(","):
            symbol = piece.strip().upper()
            if symbol and symbol not in normalized:
                normalized.append(symbol)
    return normalized


def _skip_reason(row: dict[str, Any], *, api_tradable_only: bool) -> str | None:
    if not api_tradable_only:
        return None
    if not bool(row.get("apiAllowed")):
        return "apiAllowed=false"
    if bool(row.get("isHidden")):
        return "hidden"
    state = row.get("state")
    if state not in (None, 0):
        return f"state={state}"
    return None


def _row_symbol(row: dict[str, Any]) -> str | None:
    raw_symbol = row.get("symbol")
    return str(raw_symbol).upper() if raw_symbol else None
