from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _bool_from_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _csv_from_env(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().upper() for item in value.split(",") if item.strip()}


def _strategy_sides_from_env(value: str | None) -> set[str]:
    allowed = {"open-long", "open-short"}
    if value is None:
        return set(allowed)
    configured = {item.strip().lower() for item in value.split(",") if item.strip()}
    if not configured:
        return set()
    return configured & allowed


def _load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class MexcSettings:
    access_key: str
    secret_key: str
    base_url: str = "https://api.mexc.com"
    recv_window: int = 5000
    use_doh_dns: bool = False
    doh_url: str = "https://cloudflare-dns.com/dns-query"
    live_trading_enabled: bool = False
    live_confirm: str = ""
    live_mutation_phase_enabled: bool = False
    state_db: str = "data/mexc_engine.sqlite3"
    strategy_allowed_sides: set[str] | None = None

    @classmethod
    def from_env(cls) -> "MexcSettings":
        _load_dotenv()
        return cls(
            access_key=os.getenv("MEXC_ACCESS_KEY", ""),
            secret_key=os.getenv("MEXC_SECRET_KEY", ""),
            base_url=os.getenv("MEXC_BASE_URL", "https://api.mexc.com").rstrip("/"),
            recv_window=int(os.getenv("MEXC_RECV_WINDOW", "5000")),
            use_doh_dns=_bool_from_env(os.getenv("MEXC_USE_DOH_DNS")),
            doh_url=os.getenv("MEXC_DOH_URL", "https://cloudflare-dns.com/dns-query"),
            live_trading_enabled=_bool_from_env(os.getenv("MEXC_LIVE_TRADING_ENABLED")),
            live_confirm=os.getenv("MEXC_LIVE_CONFIRM", ""),
            live_mutation_phase_enabled=_bool_from_env(os.getenv("MEXC_LIVE_MUTATION_PHASE_ENABLED")),
            state_db=os.getenv("MEXC_STATE_DB", "data/mexc_engine.sqlite3"),
            strategy_allowed_sides=_strategy_sides_from_env(os.getenv("MEXC_STRATEGY_ALLOWED_SIDES")),
        )


@dataclass(frozen=True)
class RiskSettings:
    allowed_symbols: set[str]
    max_leverage: int = 3
    max_order_vol: float = 1.0
    max_notional_usdt: float = 50.0
    require_stop_loss: bool = True
    kill_switch_file: str = ".kill-switch"

    @classmethod
    def from_env(cls) -> "RiskSettings":
        _load_dotenv()
        return cls(
            allowed_symbols=_csv_from_env(os.getenv("MEXC_ALLOWED_SYMBOLS")),
            max_leverage=int(os.getenv("MEXC_MAX_LEVERAGE", "3")),
            max_order_vol=float(os.getenv("MEXC_MAX_ORDER_VOL", "1")),
            max_notional_usdt=float(os.getenv("MEXC_MAX_NOTIONAL_USDT", "50")),
            require_stop_loss=_bool_from_env(os.getenv("MEXC_REQUIRE_STOP_LOSS"), True),
            kill_switch_file=os.getenv("MEXC_KILL_SWITCH_FILE", ".kill-switch"),
        )
