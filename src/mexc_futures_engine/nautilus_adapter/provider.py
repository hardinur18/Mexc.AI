from __future__ import annotations

from typing import Any, Iterable

from ..nautilus_provider import InstrumentProviderReport
from ..nautilus_provider import MexcNautilusInstrumentProvider
from .config import MexcFuturesAdapterConfig


class MexcFuturesInstrumentProviderBoundary:
    """Read-only instrument provider boundary shaped for a future Nautilus adapter."""

    def __init__(
        self,
        client: Any,
        config: MexcFuturesAdapterConfig | None = None,
    ):
        self.config = config or MexcFuturesAdapterConfig()
        self.config.assert_read_only_safe()
        self._provider = MexcNautilusInstrumentProvider(client)

    def load_all(self) -> InstrumentProviderReport:
        return self._provider.load_all(api_tradable_only=self.config.api_tradable_only)

    def load_symbols(self, symbols: Iterable[str]) -> InstrumentProviderReport:
        return self._provider.load_symbols(symbols, api_tradable_only=self.config.api_tradable_only)
