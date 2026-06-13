import { useEffect, useReducer } from "react";

/**
 * Best-effort LIVE price stream straight from MEXC public contract WebSocket.
 * Same protocol the backend ws_client uses:
 *   url:  wss://contract.mexc.com/edge
 *   sub:  {"method":"sub.tickers","param":{}}
 *   push: {"channel":"push.tickers","data":[{symbol,lastPrice,fairPrice,...}]}
 *
 * Runs as a module singleton (one socket for the whole app). If the connection
 * fails (e.g. ISP DNS hijack — browsers can't DoH), `connected` stays false and
 * callers gracefully fall back to polled REST data.
 */
type Tick = { last: number; fair: number; ts: number };

const prices: Record<string, Tick> = {};
let ws: WebSocket | null = null;
let started = false;
let connected = false;
let pingTimer: number | null = null;
let reconnectTimer: number | null = null;
let backoff = 2000;

function handle(raw: string) {
  let msg: { channel?: string; c?: string; data?: unknown; d?: unknown };
  try {
    msg = JSON.parse(raw);
  } catch {
    return;
  }
  const channel = msg.channel || msg.c;
  if (channel === "pong" || channel === "rs.error") return;
  const data = msg.data ?? msg.d;
  if (!data) return;
  const items = Array.isArray(data) ? data : [data];
  const now = Date.now();
  for (const t of items as Record<string, unknown>[]) {
    if (!t || typeof t !== "object") continue;
    const sym = (t.symbol as string) || (t.s as string);
    if (!sym) continue;
    const last = Number(t.lastPrice ?? t.lp ?? 0) || 0;
    const fair = Number(t.fairPrice ?? t.fp ?? 0) || 0;
    if (!last && !fair) continue;
    prices[sym] = { last: last || fair, fair: fair || last, ts: now };
  }
}

function startPing() {
  stopPing();
  pingTimer = window.setInterval(() => {
    try {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ method: "ping" }));
    } catch {
      /* ignore */
    }
  }, 15000);
}
function stopPing() {
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, backoff);
  backoff = Math.min(backoff * 2, 30000);
}

function connect() {
  try {
    ws = new WebSocket("wss://contract.mexc.com/edge");
    ws.onopen = () => {
      connected = true;
      backoff = 2000;
      try {
        ws?.send(JSON.stringify({ method: "sub.tickers", param: {} }));
      } catch {
        /* ignore */
      }
      startPing();
    };
    ws.onmessage = (e) => handle(typeof e.data === "string" ? e.data : "");
    ws.onclose = () => {
      connected = false;
      stopPing();
      scheduleReconnect();
    };
    ws.onerror = () => {
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  } catch {
    scheduleReconnect();
  }
}

function ensureStarted() {
  if (started) return;
  started = true;
  connect();
}

export interface LivePrices {
  get: (symbol: string) => number | null;
  connected: boolean;
  count: number;
}

/** Subscribe to the live price stream; re-renders the caller every `refreshMs`. */
export function useLivePrices(refreshMs = 700): LivePrices {
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => {
    ensureStarted();
    const id = window.setInterval(() => force(), refreshMs);
    return () => clearInterval(id);
  }, [refreshMs]);

  return {
    get: (symbol: string) => {
      const t = prices[symbol];
      if (!t) return null;
      if (Date.now() - t.ts > 60000) return null; // stale guard
      return t.last || t.fair;
    },
    connected,
    count: Object.keys(prices).length,
  };
}
