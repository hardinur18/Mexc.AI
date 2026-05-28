from __future__ import annotations

import json
import ssl
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .candles import mexc_candle_interval
from .dns import DnsError, override_getaddrinfo, resolve_a_records_doh
from .models import OpenType, OrderRequest, OrderType, Side
from .pairs import extract_contract_rows
from .risk import RiskEngine
from .settings import MexcSettings
from .signing import canonical_query, compact_json, sign
from .strategy import build_micro_signal


class MexcApiError(RuntimeError):
    pass


class LiveTradingLocked(MexcApiError):
    pass


class MexcFuturesClient:
    def __init__(self, settings: MexcSettings, risk_engine: RiskEngine | None = None):
        self.settings = settings
        self.risk_engine = risk_engine
        self._dns_cache: dict[str, str] = {}

    def ping(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/contract/ping", private=False)

    def contract_detail(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol.upper()} if symbol else None
        return self._request("GET", "/api/v1/contract/detail/country", params=params, private=False)

    def ticker(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol.upper()} if symbol else None
        return self._request("GET", "/api/v1/contract/ticker", params=params, private=False)

    def depth(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        params = {"limit": limit} if limit is not None else None
        return self._request("GET", f"/api/v1/contract/depth/{symbol.upper()}", params=params, private=False)

    def index_price(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/contract/index_price/{symbol.upper()}", private=False)

    def fair_price(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/contract/fair_price/{symbol.upper()}", private=False)

    def funding_rate(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/contract/funding_rate/{symbol.upper()}", private=False)

    def funding_rate_history(self, symbol: str, *, page_num: int = 1, page_size: int = 100) -> dict[str, Any]:
        """Historical funding rates (last N settlements). page_size max ~1000."""
        params = {"symbol": symbol.upper(), "page_num": page_num, "page_size": page_size}
        return self._request(
            "GET",
            "/api/v1/contract/funding_rate/history",
            params=params,
            private=False,
        )

    def open_interest_history(self, symbol: str, *, interval: str = "Min15", count: int = 100) -> dict[str, Any]:
        """Open Interest history over time (snapshots per interval)."""
        params = {"symbol": symbol.upper(), "interval": interval, "count": count}
        return self._request(
            "GET",
            "/api/v1/contract/oi_history",
            params=params,
            private=False,
        )

    def long_short_ratio(self, symbol: str, *, interval: str = "Min15", count: int = 100) -> dict[str, Any]:
        """Long/short account ratio history."""
        params = {"symbol": symbol.upper(), "interval": interval, "count": count}
        return self._request(
            "GET",
            "/api/v1/contract/long_short_ratio",
            params=params,
            private=False,
        )

    def deals(self, symbol: str, *, limit: int = 100) -> dict[str, Any]:
        """Recent trades (used for cumulative delta proxy)."""
        params = {"symbol": symbol.upper(), "limit": limit}
        return self._request(
            "GET",
            f"/api/v1/contract/deals/{symbol.upper()}",
            params=params,
            private=False,
        )

    def klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> dict[str, Any]:
        if (start_time_ms is None) != (end_time_ms is None):
            raise MexcApiError("start_time_ms and end_time_ms must be provided together for MEXC klines")
        params: dict[str, Any] = {"interval": mexc_candle_interval(interval)}
        if start_time_ms is not None and end_time_ms is not None:
            params["startTime"] = start_time_ms
            params["endTime"] = end_time_ms
        return self._request("GET", f"/api/v1/contract/kline/{symbol.upper()}", params=params, private=False)

    def asset(self, currency: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/private/account/asset/{currency.upper()}", private=True)

    def all_assets(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/private/account/assets", private=True)

    def open_positions(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol.upper()} if symbol else None
        return self._request("GET", "/api/v1/private/position/open_positions", params=params, private=True)

    def current_orders(self, *, page_num: int = 1, page_size: int = 100) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/private/order/list/open_orders",
            params={"page_num": page_num, "page_size": page_size},
            private=True,
        )

    def historical_orders(
        self,
        *,
        symbol: str | None = None,
        page_num: int = 1,
        page_size: int = 20,
        states: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page_num": page_num, "page_size": page_size}
        if symbol:
            params["symbol"] = symbol.upper()
        if states:
            params["states"] = states
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        return self._request("GET", "/api/v1/private/order/list/history_orders", params=params, private=True)

    def order_deals(
        self,
        symbol: str,
        *,
        page_num: int = 1,
        page_size: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"symbol": symbol.upper(), "page_num": page_num, "page_size": page_size}
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        return self._request("GET", "/api/v1/private/order/list/order_deals/v3", params=params, private=True)

    def reconcile_snapshot(self, *, symbol: str | None = None, currency: str = "USDT") -> dict[str, Any]:
        assets = self.all_assets()
        single_asset = self.asset(currency)
        positions = self.open_positions(symbol)
        open_orders = self.current_orders(page_num=1, page_size=100)
        historical_orders = self.historical_orders(symbol=symbol, page_num=1, page_size=20)

        asset_rows = assets.get("data") if isinstance(assets.get("data"), list) else []
        position_rows = positions.get("data") if isinstance(positions.get("data"), list) else []
        open_order_rows = open_orders.get("data") if isinstance(open_orders.get("data"), list) else []
        history_data = historical_orders.get("data")
        recent_rows = []
        if isinstance(history_data, dict) and isinstance(history_data.get("resultList"), list):
            recent_rows = history_data["resultList"]
        elif isinstance(history_data, list):
            recent_rows = history_data

        return {
            "timestamp": int(time.time() * 1000),
            "symbol": symbol.upper() if symbol else None,
            "currency": currency.upper(),
            "summary": {
                "assetCount": len(asset_rows),
                "openPositionCount": len(position_rows),
                "openOrderCount": len(open_order_rows),
                "recentOrderCount": len(recent_rows),
                "singleAssetSuccess": bool(single_asset.get("success")),
            },
            "assets": assets,
            "singleAsset": single_asset,
            "positions": positions,
            "openOrders": open_orders,
            "recentOrders": historical_orders,
        }

    def reconcile_summary(self, *, symbol: str | None = None, currency: str = "USDT") -> dict[str, Any]:
        snapshot = self.reconcile_snapshot(symbol=symbol, currency=currency)
        asset_rows = snapshot["assets"].get("data") if isinstance(snapshot["assets"].get("data"), list) else []
        nonzero_assets = [
            {
                "currency": row.get("currency"),
                "equity": row.get("equity"),
                "availableBalance": row.get("availableBalance"),
                "unrealized": row.get("unrealized"),
                "positionMargin": row.get("positionMargin"),
            }
            for row in asset_rows
            if any(float(row.get(key) or 0) != 0 for key in ("equity", "availableBalance", "unrealized", "positionMargin"))
        ]

        return {
            "timestamp": snapshot["timestamp"],
            "symbol": snapshot["symbol"],
            "currency": snapshot["currency"],
            "summary": snapshot["summary"],
            "nonzeroAssets": nonzero_assets,
            "positions": snapshot["positions"].get("data"),
            "openOrders": snapshot["openOrders"].get("data"),
            "recentOrderPreview": _preview_recent_orders(snapshot["recentOrders"], limit=5),
        }

    def order_preflight(self, order: OrderRequest, *, currency: str = "USDT") -> dict[str, Any]:
        symbol = order.symbol.upper()
        contract_response = self.contract_detail(symbol)
        contract_rows = extract_contract_rows(contract_response)
        contract = contract_rows[0] if contract_rows else {}
        contract_size = order.contract_size or _as_float(contract.get("contractSize"))
        effective_order = order if order.contract_size else _replace_order_contract_size(order, contract_size)

        risk_decision = self.risk_engine.validate_order(effective_order) if self.risk_engine else None
        asset = self.asset(currency)
        positions = self.open_positions(symbol)
        open_orders = self.current_orders(page_num=1, page_size=100)

        asset_data = asset.get("data") if isinstance(asset.get("data"), dict) else {}
        available_balance = _as_float(asset_data.get("availableBalance")) or 0.0
        notional = effective_order.price * effective_order.vol * (effective_order.contract_size or 0.0)
        required_margin = notional / effective_order.leverage if effective_order.leverage else None

        position_rows = positions.get("data") if isinstance(positions.get("data"), list) else []
        open_order_rows = open_orders.get("data") if isinstance(open_orders.get("data"), list) else []
        symbol_open_orders = [row for row in open_order_rows if row.get("symbol") == symbol]

        reasons: list[str] = []
        warnings: list[str] = []
        if not contract:
            reasons.append(f"contract not found for {symbol}")
        if contract and not bool(contract.get("apiAllowed")):
            reasons.append(f"contract {symbol} is not API tradable")
        if contract and bool(contract.get("isHidden")):
            reasons.append(f"contract {symbol} is hidden")
        if contract and contract.get("state") not in (None, 0):
            reasons.append(f"contract {symbol} state is not tradable: {contract.get('state')}")
        if contract_size is None or contract_size <= 0:
            reasons.append("contract size is missing or invalid")
        min_vol = _as_float(contract.get("minVol"))
        max_vol = _as_float(contract.get("maxVol"))
        max_leverage = _as_float(contract.get("maxLeverage"))
        if min_vol is not None and effective_order.vol < min_vol:
            reasons.append(f"volume {effective_order.vol} is below exchange minVol {min_vol}")
        if max_vol is not None and effective_order.vol > max_vol:
            reasons.append(f"volume {effective_order.vol} is above exchange maxVol {max_vol}")
        if max_leverage is not None and effective_order.leverage is not None and effective_order.leverage > max_leverage:
            reasons.append(f"leverage {effective_order.leverage} is above exchange maxLeverage {max_leverage}")
        if risk_decision and not risk_decision.allowed:
            reasons.extend(risk_decision.reasons)
        if required_margin is not None and available_balance < required_margin:
            reasons.append(
                f"available balance {available_balance:.8f} is below estimated margin {required_margin:.8f}"
            )
        if position_rows and effective_order.opens_position:
            warnings.append(f"existing open position count for {symbol}: {len(position_rows)}")
        if symbol_open_orders:
            warnings.append(f"existing open order count for {symbol}: {len(symbol_open_orders)}")

        return {
            "timestamp": int(time.time() * 1000),
            "preflightAllowed": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "symbol": symbol,
            "currency": currency.upper(),
            "contract": {
                "symbol": contract.get("symbol"),
                "apiAllowed": contract.get("apiAllowed"),
                "state": contract.get("state"),
                "isHidden": contract.get("isHidden"),
                "contractSize": contract_size,
                "minVol": contract.get("minVol"),
                "maxVol": contract.get("maxVol"),
                "maxLeverage": contract.get("maxLeverage"),
            },
            "account": {
                "availableBalance": available_balance,
                "equity": asset_data.get("equity"),
                "positionMargin": asset_data.get("positionMargin"),
                "unrealized": asset_data.get("unrealized"),
            },
            "order": effective_order.to_mexc_payload(),
            "estimated": {
                "notional": notional,
                "requiredMargin": required_margin,
            },
            "state": {
                "openPositionCount": len(position_rows),
                "openOrderCount": len(symbol_open_orders),
            },
        }

    def strategy_signal(
        self,
        *,
        symbol: str,
        leverage: int,
        max_notional_usdt: float,
        currency: str = "USDT",
        allowed_sides: set[str] | None = None,
    ) -> dict[str, Any]:
        contract_response = self.contract_detail(symbol)
        contract_rows = extract_contract_rows(contract_response)
        contract = contract_rows[0] if contract_rows else {}
        contract_size = _as_float(contract.get("contractSize"))
        taker_fee_rate = _as_float(contract.get("takerFeeRate") or contract.get("takerFee"))
        ticker = self.ticker(symbol)
        depth = self.depth(symbol, limit=20)
        funding = self.funding_rate(symbol)
        signal = build_micro_signal(
            symbol=symbol,
            ticker=ticker,
            depth=depth,
            funding_rate=funding,
            contract_size=contract_size,
            leverage=leverage,
            max_notional_usdt=max_notional_usdt,
            taker_fee_rate=taker_fee_rate,
            allowed_sides=allowed_sides if allowed_sides is not None else self.settings.strategy_allowed_sides,
        )

        candidate = signal["candidateOrder"]
        preflight = None
        if signal["signal"]["side"] in {"open-long", "open-short"}:
            side = Side.OPEN_LONG if signal["signal"]["side"] == "open-long" else Side.OPEN_SHORT
            order = OrderRequest(
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                open_type=OpenType.ISOLATED,
                price=candidate["price"],
                vol=candidate["vol"],
                contract_size=candidate["contractSize"],
                leverage=leverage,
                stop_loss_price=candidate["stopLossPrice"],
                take_profit_price=candidate["takeProfitPrice"],
            )
            preflight = self.order_preflight(order, currency=currency)

        return {
            "timestamp": int(time.time() * 1000),
            "symbol": symbol.upper(),
            "currency": currency.upper(),
            "contract": {
                "symbol": contract.get("symbol"),
                "apiAllowed": contract.get("apiAllowed"),
                "state": contract.get("state"),
                "isHidden": contract.get("isHidden"),
                "contractSize": contract_size,
                "takerFeeRate": taker_fee_rate,
                "minVol": contract.get("minVol"),
                "maxVol": contract.get("maxVol"),
                "maxLeverage": contract.get("maxLeverage"),
                "strategyAllowedSides": sorted(
                    allowed_sides if allowed_sides is not None else self.settings.strategy_allowed_sides or []
                ),
            },
            "signal": signal,
            "preflight": preflight,
        }

    def network_check(self) -> dict[str, Any]:
        checks = [
            ("base", self.settings.base_url),
            ("ping", f"{self.settings.base_url}/api/v1/contract/ping"),
            ("legacyPing", "https://contract.mexc.com/api/v1/contract/ping"),
        ]
        return {
            "useDohDns": self.settings.use_doh_dns,
            "dohUrl": self.settings.doh_url,
            "checks": [self._probe_url(name, url) for name, url in checks],
        }

    def dns_check(self) -> dict[str, Any]:
        hosts = ["api.mexc.com", "contract.mexc.com"]
        results = []
        for host in hosts:
            system_ips: list[str] = []
            system_error = None
            try:
                system_ips = sorted({item[4][0] for item in __import__("socket").getaddrinfo(host, 443)})
            except Exception as exc:
                system_error = str(exc)

            doh_ips: list[str] = []
            doh_error = None
            try:
                doh_ips = resolve_a_records_doh(host, self.settings.doh_url)
            except DnsError as exc:
                doh_error = str(exc)

            results.append(
                {
                    "host": host,
                    "systemIps": system_ips,
                    "systemError": system_error,
                    "dohIps": doh_ips,
                    "dohError": doh_error,
                    "systemLooksPoisoned": any(ip.startswith("114.7.173.") for ip in system_ips),
                }
            )

        return {"useDohDns": self.settings.use_doh_dns, "dohUrl": self.settings.doh_url, "hosts": results}

    def change_leverage(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.live_trading_enabled:
            return {"success": True, "dryRun": True, "endpoint": "/api/v1/private/position/change_leverage", "payload": payload}
        self._assert_live_allowed("change_leverage")
        return self._request("POST", "/api/v1/private/position/change_leverage", body=payload, private=True)

    def place_order(self, order: OrderRequest) -> dict[str, Any]:
        if self.risk_engine:
            self.risk_engine.validate_order(order).raise_if_blocked()

        payload = order.to_mexc_payload()
        if not self.settings.live_trading_enabled:
            return {"success": True, "dryRun": True, "endpoint": "/api/v1/private/order/create", "payload": payload}

        self._assert_live_allowed("place_order")
        return self._request("POST", "/api/v1/private/order/create", body=payload, private=True)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        private: bool,
    ) -> dict[str, Any]:
        method = method.upper()
        if _is_private_mutation_request(method, path, body=body):
            self._assert_live_allowed(f"{method} {path}")
        query = canonical_query(params)
        url = f"{self.settings.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        body_bytes: bytes | None = None
        parameter_string = query
        if body is not None:
            parameter_string = compact_json(body)
            body_bytes = parameter_string.encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if private:
            self._require_credentials()
            request_time = str(int(time.time() * 1000))
            headers.update(
                {
                    "ApiKey": self.settings.access_key,
                    "Request-Time": request_time,
                    "Signature": sign(
                        self.settings.access_key,
                        self.settings.secret_key,
                        request_time,
                        parameter_string,
                    ),
                    "Recv-Window": str(self.settings.recv_window),
                }
            )

        request = Request(url, data=body_bytes, headers=headers, method=method)
        try:
            with self._dns_context(url):
                with urlopen(request, timeout=15) as response:
                    raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MexcApiError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            hint = ""
            if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc):
                hint = (
                    " This often means the endpoint is blocked/intercepted by the local network "
                    "or the CA store is broken. Do not bypass TLS for private trading requests; "
                    "use a clean VPS/VPN/network."
                )
            raise MexcApiError(f"Network error: {exc}.{hint}") from exc

        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            snippet = raw[:500]
            hint = ""
            if "<html" in raw.lower() or "<!doctype html" in raw.lower():
                hint = " Received HTML instead of JSON, likely a captive portal, ISP block page, or reverse proxy."
            raise MexcApiError(f"Invalid JSON response: {snippet}{hint}") from exc

        return decoded

    def _require_credentials(self) -> None:
        if not self.settings.access_key or not self.settings.secret_key:
            raise MexcApiError("MEXC_ACCESS_KEY and MEXC_SECRET_KEY are required for private endpoints")

    def _assert_live_allowed(self, action: str) -> None:
        if self.settings.live_confirm != "I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK":
            raise LiveTradingLocked(
                "live trading is locked; set MEXC_LIVE_CONFIRM=I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK "
                f"before {action}"
            )
        if not self.settings.live_mutation_phase_enabled:
            raise LiveTradingLocked(
                "live mutation phase is locked; set MEXC_LIVE_MUTATION_PHASE_ENABLED=true only after "
                f"paper readiness and performance gates pass before {action}"
            )
        raise LiveTradingLocked(
            "live mutation client is disabled in this local-paper build; implement the explicit live "
            f"execution phase before {action}"
        )

    def _probe_url(self, name: str, url: str) -> dict[str, Any]:
        request = Request(url, headers={"Accept": "application/json, text/plain;q=0.9, */*;q=0.1"}, method="GET")
        try:
            with self._dns_context(url):
                with urlopen(request, timeout=10) as response:
                    raw = response.read(500).decode("utf-8", errors="replace")
                    content_type = response.headers.get("content-type", "")
                    status = response.status
        except HTTPError as exc:
            raw = exc.read(500).decode("utf-8", errors="replace")
            return {
                "name": name,
                "url": url,
                "ok": False,
                "status": exc.code,
                "error": raw[:300],
                "looksBlocked": self._looks_blocked(raw),
            }
        except URLError as exc:
            return {
                "name": name,
                "url": url,
                "ok": False,
                "error": str(exc),
                "looksBlocked": "CERTIFICATE_VERIFY_FAILED" in str(exc),
            }

        looks_json = raw.lstrip().startswith("{") or raw.lstrip().startswith("[")
        looks_blocked = self._looks_blocked(raw)
        return {
            "name": name,
            "url": url,
            "ok": bool(status < 400 and looks_json and not looks_blocked),
            "status": status,
            "contentType": content_type,
            "looksJson": looks_json,
            "looksBlocked": looks_blocked,
            "sample": raw[:300],
            }

    @staticmethod
    def _looks_blocked(raw: str) -> bool:
        lower = raw.lower()
        return any(
            marker in lower
            for marker in (
                "internet positif",
                "indosatooredoo",
                "<!doctype html",
                "<html",
                "negativepage",
            )
        )

    def _dns_context(self, url: str):
        host = urlparse(url).hostname
        if not self.settings.use_doh_dns or not host or not host.endswith("mexc.com"):
            return override_getaddrinfo({})
        ip = self._resolve_host(host)
        return override_getaddrinfo({host: ip})

    def _resolve_host(self, host: str) -> str:
        cached = self._dns_cache.get(host)
        if cached:
            return cached
        ip = resolve_a_records_doh(host, self.settings.doh_url)[0]
        self._dns_cache[host] = ip
        return ip


def _preview_recent_orders(response: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    data = response.get("data")
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict) and isinstance(data.get("resultList"), list):
        rows = data["resultList"]
    elif isinstance(data, list):
        rows = data
    return [
        {
            "symbol": row.get("symbol"),
            "side": row.get("side"),
            "state": row.get("state"),
            "orderType": row.get("orderType"),
            "price": row.get("price"),
            "vol": row.get("vol"),
            "leverage": row.get("leverage"),
            "profit": row.get("profit"),
            "createTime": row.get("createTime"),
            "orderId": row.get("orderId"),
        }
        for row in rows[:limit]
    ]


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_private_mutation_request(method: str, path: str, *, body: dict[str, Any] | None) -> bool:
    if not path.startswith("/api/v1/private/"):
        return False
    # Paths that are mutation regardless of method (defense in depth).
    write_only_markers = (
        "/order/create",
        "/order/submit",
        "/order/cancel",
        "/order/batch",
        "/position/change",
        "/position/close",
        "/position/leverage",
    )
    # planorder/stoporder expose both list (GET) and place/cancel (POST) endpoints.
    # GET is read-only and safe; non-GET is mutation.
    dual_markers = ("/planorder", "/stoporder")
    return (
        method != "GET"
        or body is not None
        or any(marker in path for marker in write_only_markers)
        or (method != "GET" and any(marker in path for marker in dual_markers))
    )


def _replace_order_contract_size(order: OrderRequest, contract_size: float | None) -> OrderRequest:
    return OrderRequest(
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        open_type=order.open_type,
        vol=order.vol,
        price=order.price,
        contract_size=contract_size,
        leverage=order.leverage,
        external_oid=order.external_oid,
        stop_loss_price=order.stop_loss_price,
        take_profit_price=order.take_profit_price,
        position_mode=order.position_mode,
        reduce_only=order.reduce_only,
    )
