from __future__ import annotations

import time
from typing import Any

from .config import MexcFuturesAdapterConfig


def build_adapter_manifest(
    *,
    config: MexcFuturesAdapterConfig | None = None,
    upstream_reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or MexcFuturesAdapterConfig()
    config.assert_read_only_safe()

    return {
        "timestamp": int(time.time() * 1000),
        "adapter": "mexc_futures",
        "targetEngine": "NautilusTrader",
        "integrationMode": "packaged-read-only-boundary",
        "config": config.to_dict(),
        "modules": {
            "config": "mexc_futures_engine.nautilus_adapter.config",
            "provider": "mexc_futures_engine.nautilus_adapter.provider",
            "data": "mexc_futures_engine.nautilus_adapter.data",
            "execution": "mexc_futures_engine.nautilus_adapter.execution",
            "manifest": "mexc_futures_engine.nautilus_adapter.manifest",
        },
        "classes": {
            "instrumentProvider": "MexcFuturesInstrumentProviderBoundary",
            "dataClient": "MexcFuturesDataClientBoundary",
            "executionClient": "MexcFuturesExecutionClientBoundary",
            "liveMutationError": "LiveMutationUnavailable",
        },
        "capabilities": {
            "instrumentProvider": {
                "status": "implemented",
                "source": "MEXC REST /api/v1/contract/detail/country",
            },
            "marketData": {
                "status": "implemented",
                "channels": {
                    "ticker": "QuoteTick",
                    "deal": "TradeTick",
                    "depth": "OrderBookDeltas",
                },
                "source": "MEXC public WebSocket",
            },
            "executionReports": {
                "status": "implemented",
                "reportTypes": [
                    "AccountState",
                    "PositionStatusReport",
                    "OrderStatusReport",
                    "FillReport",
                ],
                "source": "MEXC private REST read-only",
            },
            "privateStream": {
                "status": "implemented",
                "eventTypes": [
                    "ControlAck",
                    "AccountUpdate",
                    "PositionUpdate",
                    "OrderUpdate",
                    "FillUpdate",
                    "PrivateUpdate",
                ],
                "source": "MEXC private WebSocket",
            },
            "reconciliation": {
                "status": "implemented",
                "mode": "REST_PRIVATE_WS_READ_ONLY",
            },
            "liveMutation": {
                "status": "locked",
                "submitOrder": False,
                "cancelOrder": False,
                "cancelAllOrders": False,
            },
        },
        "runtimePolicy": {
            "installsNautilusRuntime": False,
            "requiresNautilusRuntimeForImport": False,
            "networkForManifest": False,
            "liveTradingDefault": False,
            "liveOrderCliExposed": False,
        },
        "commands": {
            "manifest": "mexc-engine nautilus-adapter-manifest",
            "readiness": "mexc-engine nautilus-adapter-check --symbol BTC_USDT --currency USDT --summary-only",
            "instrumentProvider": "mexc-engine nautilus-instruments --summary-only",
            "marketData": "mexc-engine ws-bridge ticker BTC_USDT --messages 3",
            "executionReports": "mexc-engine execution-reports --symbol BTC_USDT --currency USDT --summary-only",
            "reconciliation": "mexc-engine reconcile-engine --symbol BTC_USDT --currency USDT --summary-only",
        },
        "upstreamReference": upstream_reference or {},
        "nextPhase": "prepare-sandboxed-nautilus-runtime-install-read-only",
    }
