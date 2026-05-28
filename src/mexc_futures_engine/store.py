from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
from typing import Any


class StateStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        self._init_db()

    def save_event(self, event_type: str, payload: dict[str, Any]) -> int:
        now = int(time.time() * 1000)
        symbol = payload.get("symbol")
        currency = payload.get("currency")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (ts, event_type, symbol, currency, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, event_type, symbol, currency, json.dumps(payload, separators=(",", ":"), ensure_ascii=False)),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def latest_events(
        self,
        event_type: str | None = None,
        limit: int = 20,
        *,
        symbol: str | None = None,
        currency: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT id, ts, event_type, symbol, currency, payload_json FROM events"
        params: list[Any] = []
        where: list[str] = []
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        if symbol:
            where.append("symbol = ?")
            params.append(symbol.upper())
        if currency:
            where.append("currency = ?")
            params.append(currency.upper())
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            {
                "id": row["id"],
                "ts": row["ts"],
                "eventType": row["event_type"],
                "symbol": row["symbol"],
                "currency": row["currency"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def count_events(
        self,
        event_type: str | None = None,
        *,
        symbol: str | None = None,
        currency: str | None = None,
    ) -> int:
        sql = "SELECT COUNT(*) AS count FROM events"
        params: list[Any] = []
        where: list[str] = []
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        if symbol:
            where.append("symbol = ?")
            params.append(symbol.upper())
        if currency:
            where.append("currency = ?")
            params.append(currency.upper())
        if where:
            sql += " WHERE " + " AND ".join(where)

        with self._connect() as conn:
            return int(conn.execute(sql, params).fetchone()["count"])

    def stats(
        self,
        *,
        event_type: str | None = None,
        symbol: str | None = None,
        currency: str | None = None,
    ) -> dict[str, Any]:
        where, params = _event_filters(event_type=event_type, symbol=symbol, currency=currency)
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS count FROM events{where_sql}", params).fetchone()["count"]
            by_type = conn.execute(
                f"SELECT event_type, COUNT(*) AS count FROM events{where_sql} GROUP BY event_type ORDER BY event_type",
                params,
            ).fetchall()
        return {
            "path": str(self.path),
            "filters": {
                "eventType": event_type,
                "symbol": symbol.upper() if symbol else None,
                "currency": currency.upper() if currency else None,
            },
            "totalEvents": total,
            "byType": {row["event_type"]: row["count"] for row in by_type},
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    symbol TEXT,
                    currency TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type_id ON events(event_type, id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_symbol_id ON events(symbol, id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_type_symbol_currency_id "
                "ON events(event_type, symbol, currency, id)"
            )
            conn.commit()
        self.path.chmod(0o600)


def _event_filters(
    *,
    event_type: str | None = None,
    symbol: str | None = None,
    currency: str | None = None,
) -> tuple[list[str], list[Any]]:
    params: list[Any] = []
    where: list[str] = []
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    if symbol:
        where.append("symbol = ?")
        params.append(symbol.upper())
    if currency:
        where.append("currency = ?")
        params.append(currency.upper())
    return where, params
