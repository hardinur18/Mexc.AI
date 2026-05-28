import type {
  AccountsResponse,
  CategoriesResponse,
  CircuitBreaker,
  ClosedPositionsResponse,
  MacroContext,
  PortfolioHeat,
  SignalsResponse,
  Snapshot,
  SymbolAnalytics,
} from "@/types/position";

export async function fetchSnapshot(
  accountIds: string[] | null,
  signal?: AbortSignal,
): Promise<Snapshot> {
  const qs = accountIds && accountIds.length > 0 ? `?accounts=${accountIds.join(",")}` : "";
  const res = await fetch(`/api/snapshot${qs}`, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`snapshot HTTP ${res.status}`);
  return (await res.json()) as Snapshot;
}

export async function fetchAccounts(signal?: AbortSignal): Promise<AccountsResponse> {
  const res = await fetch("/api/accounts", { signal });
  if (!res.ok) throw new Error(`accounts HTTP ${res.status}`);
  return (await res.json()) as AccountsResponse;
}

export async function fetchCategories(signal?: AbortSignal): Promise<CategoriesResponse> {
  const res = await fetch("/api/categories", { signal });
  if (!res.ok) throw new Error(`categories HTTP ${res.status}`);
  return (await res.json()) as CategoriesResponse;
}

export async function fetchSignals(minScore = 65, signal?: AbortSignal): Promise<SignalsResponse> {
  const res = await fetch(`/api/signals?min_score=${minScore}`, { signal });
  if (!res.ok) throw new Error(`signals HTTP ${res.status}`);
  return (await res.json()) as SignalsResponse;
}

export async function fetchAnalytics(symbol: string, signal?: AbortSignal): Promise<SymbolAnalytics> {
  const res = await fetch(`/api/analytics/${symbol}`, { signal });
  if (!res.ok) throw new Error(`analytics HTTP ${res.status}`);
  return (await res.json()) as SymbolAnalytics;
}

export async function fetchClosedPositions(limit = 20, signal?: AbortSignal): Promise<ClosedPositionsResponse> {
  const res = await fetch(`/api/closed-positions?limit=${limit}`, { signal });
  if (!res.ok) throw new Error(`closed HTTP ${res.status}`);
  return (await res.json()) as ClosedPositionsResponse;
}

// ─── Phase 5 endpoints ───
export async function fetchMacro(signal?: AbortSignal): Promise<MacroContext> {
  const res = await fetch("/api/macro", { signal });
  if (!res.ok) throw new Error(`macro HTTP ${res.status}`);
  return (await res.json()) as MacroContext;
}

export async function fetchPortfolioRisk(signal?: AbortSignal): Promise<PortfolioHeat> {
  const res = await fetch("/api/risk/portfolio", { signal });
  if (!res.ok) throw new Error(`risk HTTP ${res.status}`);
  return (await res.json()) as PortfolioHeat;
}

export async function fetchCircuitBreaker(signal?: AbortSignal): Promise<CircuitBreaker> {
  const res = await fetch("/api/risk/circuit-breaker", { signal });
  if (!res.ok) throw new Error(`circuit HTTP ${res.status}`);
  return (await res.json()) as CircuitBreaker;
}

export async function fetchSignalJournal(
  limit = 100,
  signal?: AbortSignal,
): Promise<{ ts: number; count: number; entries: Array<Record<string, unknown>> }> {
  const res = await fetch(`/api/risk/journal?limit=${limit}`, { signal });
  if (!res.ok) throw new Error(`journal HTTP ${res.status}`);
  return await res.json();
}

export async function fetchPatternWinrate(
  signal?: AbortSignal,
): Promise<import("@/types/position").PatternWinrate> {
  const res = await fetch("/api/risk/pattern-winrate", { signal });
  if (!res.ok) throw new Error(`pattern-winrate HTTP ${res.status}`);
  return await res.json();
}

export interface DeFiLlamaData {
  dex_total_24h_volume_usd?: number;
  dex_total_7d_volume_usd?: number;
  dex_change_24h_pct?: number;
  dex_change_7d_pct?: number;
  defi_total_tvl_usd?: number;
  defi_tvl_change_24h_pct?: number;
  defi_tvl_change_7d_pct?: number;
}

export async function fetchDeFiLlama(signal?: AbortSignal): Promise<DeFiLlamaData> {
  const res = await fetch("/api/external/defillama", { signal });
  if (!res.ok) throw new Error(`defillama HTTP ${res.status}`);
  return await res.json();
}

export interface WsStatus {
  connected: boolean;
  cache_size: number;
  last_message_age_sec: number | null;
  stats: { messages: number; connects: number; errors: number };
}

export async function fetchWsStatus(signal?: AbortSignal): Promise<WsStatus> {
  const res = await fetch("/api/ws/status", { signal });
  if (!res.ok) throw new Error(`ws-status HTTP ${res.status}`);
  return await res.json();
}

// ─── Phase 6: Cascade orchestrator ───
import type {
  CascadeActiveResponse,
  PerformanceMetrics,
  FearGreed,
  CoinGeckoGlobal,
  DeribitOptions,
  BinanceFunding,
  CryptoPanicNews,
  BacktestResult,
  Cascade,
} from "@/types/position";

export async function fetchCascadeActive(signal?: AbortSignal): Promise<CascadeActiveResponse> {
  const res = await fetch("/api/cascade/active", { signal });
  if (!res.ok) throw new Error(`cascade-active HTTP ${res.status}`);
  return await res.json();
}

export async function fetchCascadeAll(signal?: AbortSignal): Promise<CascadeActiveResponse> {
  const res = await fetch("/api/cascade/all", { signal });
  if (!res.ok) throw new Error(`cascade-all HTTP ${res.status}`);
  return await res.json();
}

export async function fetchPerformance(signal?: AbortSignal): Promise<PerformanceMetrics> {
  const res = await fetch("/api/cascade/performance", { signal });
  if (!res.ok) throw new Error(`performance HTTP ${res.status}`);
  return await res.json();
}

export async function startCascade(
  symbol: string,
  account_id: string,
  mode: "paper" | "live" = "paper",
  size_multiplier: number = 1.0,
): Promise<{ ok: boolean; cascade: Cascade }> {
  const res = await fetch("/api/cascade/start", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ symbol, account_id, mode, size_multiplier }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "unknown" }));
    throw new Error(err.detail || `cascade-start HTTP ${res.status}`);
  }
  return await res.json();
}

export async function cancelCascade(id: string): Promise<{ ok: boolean; cascade: Cascade }> {
  const res = await fetch(`/api/cascade/${id}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(`cascade-cancel HTTP ${res.status}`);
  return await res.json();
}

export async function setCascadeMode(id: string, mode: "paper" | "live"): Promise<{ ok: boolean; cascade: Cascade }> {
  const res = await fetch(`/api/cascade/${id}/mode`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "unknown" }));
    throw new Error(err.detail || `cascade-mode HTTP ${res.status}`);
  }
  return await res.json();
}

export async function killSwitch(): Promise<{ ok: boolean; cancelled_count: number }> {
  const res = await fetch("/api/cascade/kill-switch", { method: "POST" });
  if (!res.ok) throw new Error(`kill-switch HTTP ${res.status}`);
  return await res.json();
}

// ─── External data ───
export async function fetchFearGreed(signal?: AbortSignal): Promise<FearGreed> {
  const res = await fetch("/api/external/fear-greed", { signal });
  if (!res.ok) throw new Error(`fng HTTP ${res.status}`);
  return await res.json();
}

export async function fetchCoinGeckoGlobal(signal?: AbortSignal): Promise<CoinGeckoGlobal> {
  const res = await fetch("/api/external/coingecko-global", { signal });
  if (!res.ok) throw new Error(`coingecko HTTP ${res.status}`);
  return await res.json();
}

export async function fetchDeribitOptions(currency: "BTC" | "ETH", signal?: AbortSignal): Promise<DeribitOptions> {
  const res = await fetch(`/api/external/deribit-options?currency=${currency}`, { signal });
  if (!res.ok) throw new Error(`deribit HTTP ${res.status}`);
  return await res.json();
}

export async function fetchBinanceFunding(symbol = "BTCUSDT", signal?: AbortSignal): Promise<BinanceFunding> {
  const res = await fetch(`/api/external/binance-funding?symbol=${symbol}`, { signal });
  if (!res.ok) throw new Error(`binance HTTP ${res.status}`);
  return await res.json();
}

export async function fetchCryptoPanic(currencies = "", signal?: AbortSignal): Promise<CryptoPanicNews> {
  const params = currencies ? `?currencies=${currencies}` : "";
  const res = await fetch(`/api/external/cryptopanic${params}`, { signal });
  if (!res.ok) throw new Error(`cryptopanic HTTP ${res.status}`);
  return await res.json();
}

export async function fetchBacktest(
  symbol: string,
  bars = 200,
  interval = "Hour4",
  signal?: AbortSignal,
): Promise<BacktestResult> {
  const res = await fetch(`/api/backtest/${symbol}?bars=${bars}&interval=${interval}`, { signal });
  if (!res.ok) throw new Error(`backtest HTTP ${res.status}`);
  return await res.json();
}

export interface AccountInput {
  id: string;
  name: string;
  color: string;
  category: string;
  access_key: string;
  secret_key: string;
}

export interface AccountPatchInput {
  name?: string;
  color?: string;
  category?: string;
  access_key?: string;
  secret_key?: string;
  strategy?: Record<string, unknown>;
}

async function jsonOrThrow(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail ?? `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export async function testAccountConnection(access_key: string, secret_key: string) {
  const res = await fetch("/api/accounts/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_key, secret_key }),
  });
  return jsonOrThrow(res) as Promise<{ success: boolean; equity: number; available: number }>;
}

export async function createAccount(payload: AccountInput) {
  const res = await fetch("/api/accounts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return jsonOrThrow(res);
}

export async function updateAccount(id: string, patch: AccountPatchInput) {
  const res = await fetch(`/api/accounts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return jsonOrThrow(res);
}

export async function deleteAccount(id: string) {
  const res = await fetch(`/api/accounts/${id}`, { method: "DELETE" });
  return jsonOrThrow(res);
}

export async function renameAccountId(currentId: string, newId: string) {
  const res = await fetch(`/api/accounts/${currentId}/rename-id`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_id: newId }),
  });
  return jsonOrThrow(res);
}

export async function renameCategory(oldName: string, newName: string) {
  const res = await fetch("/api/categories/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_name: oldName, new_name: newName }),
  });
  return jsonOrThrow(res);
}
