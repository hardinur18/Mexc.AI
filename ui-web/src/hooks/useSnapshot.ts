import { useQuery } from "@tanstack/react-query";
import {
  fetchAccounts,
  fetchAnalytics,
  fetchBacktest,
  fetchBinanceFunding,
  fetchCascadeActive,
  fetchCascadeAll,
  fetchCategories,
  fetchCircuitBreaker,
  fetchClosedPositions,
  fetchCoinGeckoGlobal,
  fetchCryptoPanic,
  fetchDeribitOptions,
  fetchFearGreed,
  fetchMacro,
  fetchPerformance,
  fetchPortfolioRisk,
  fetchDeFiLlama,
  fetchPatternWinrate,
  fetchSignalJournal,
  fetchWsStatus,
  fetchSignals,
  fetchSnapshot,
} from "@/lib/api";
import { useUiStore } from "@/store/ui";

export function useSnapshot() {
  const intervalSec = useUiStore((s) => s.intervalSec);
  const paused = useUiStore((s) => s.paused);
  const selectedAccounts = useUiStore((s) => s.selectedAccounts);
  const accountSelectionTouched = useUiStore((s) => s.accountSelectionTouched);

  const idsForQuery = accountSelectionTouched ? Array.from(selectedAccounts) : null;

  return useQuery({
    queryKey: ["snapshot", idsForQuery?.join(",") ?? "all"],
    queryFn: ({ signal }) => fetchSnapshot(idsForQuery, signal),
    refetchInterval: paused ? false : intervalSec * 1000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: !paused,
    staleTime: 0,
  });
}

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: ({ signal }) => fetchAccounts(signal),
    staleTime: 5 * 60 * 1000,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: ({ signal }) => fetchCategories(signal),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSignals(minScore = 65) {
  const intervalSec = useUiStore((s) => s.intervalSec);
  const paused = useUiStore((s) => s.paused);
  return useQuery({
    queryKey: ["signals", minScore],
    queryFn: ({ signal }) => fetchSignals(minScore, signal),
    refetchInterval: paused ? false : Math.max(intervalSec, 10) * 1000,
    refetchIntervalInBackground: false,
    staleTime: 0,
  });
}

export function useAnalytics(symbol: string | null) {
  return useQuery({
    queryKey: ["analytics", symbol],
    queryFn: ({ signal }) => fetchAnalytics(symbol!, signal),
    enabled: !!symbol,
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}

export function useClosedPositions(limit = 20) {
  return useQuery({
    queryKey: ["closed-positions", limit],
    queryFn: ({ signal }) => fetchClosedPositions(limit, signal),
    refetchInterval: 30 * 1000,
    staleTime: 0,
  });
}

// ─── Phase 5 hooks ───
export function useMacro() {
  return useQuery({
    queryKey: ["macro"],
    queryFn: ({ signal }) => fetchMacro(signal),
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  });
}

export function usePortfolioRisk() {
  return useQuery({
    queryKey: ["risk-portfolio"],
    queryFn: ({ signal }) => fetchPortfolioRisk(signal),
    refetchInterval: 15 * 1000,
    staleTime: 0,
  });
}

export function useCircuitBreaker() {
  return useQuery({
    queryKey: ["risk-circuit"],
    queryFn: ({ signal }) => fetchCircuitBreaker(signal),
    refetchInterval: 30 * 1000,
    staleTime: 0,
  });
}

export function useSignalJournal(limit = 100) {
  return useQuery({
    queryKey: ["risk-journal", limit],
    queryFn: ({ signal }) => fetchSignalJournal(limit, signal),
    refetchInterval: 30 * 1000,
    staleTime: 0,
  });
}

// ─── Phase 6 hooks ───
export function useCascadeActive() {
  return useQuery({
    queryKey: ["cascade-active"],
    queryFn: ({ signal }) => fetchCascadeActive(signal),
    refetchInterval: 5 * 1000,
    staleTime: 0,
  });
}

export function useCascadeAll() {
  return useQuery({
    queryKey: ["cascade-all"],
    queryFn: ({ signal }) => fetchCascadeAll(signal),
    refetchInterval: 10 * 1000,
    staleTime: 0,
  });
}

export function usePerformance() {
  return useQuery({
    queryKey: ["performance"],
    queryFn: ({ signal }) => fetchPerformance(signal),
    refetchInterval: 30 * 1000,
    staleTime: 0,
  });
}

export function useFearGreed() {
  return useQuery({
    queryKey: ["fng"],
    queryFn: ({ signal }) => fetchFearGreed(signal),
    refetchInterval: 30 * 60 * 1000,
    staleTime: 15 * 60 * 1000,
  });
}

export function useCoinGeckoGlobal() {
  return useQuery({
    queryKey: ["coingecko-global"],
    queryFn: ({ signal }) => fetchCoinGeckoGlobal(signal),
    refetchInterval: 5 * 60 * 1000,
    staleTime: 60 * 1000,
  });
}

export function useDeribitOptions(currency: "BTC" | "ETH") {
  return useQuery({
    queryKey: ["deribit", currency],
    queryFn: ({ signal }) => fetchDeribitOptions(currency, signal),
    refetchInterval: 10 * 60 * 1000,
    staleTime: 5 * 60 * 1000,
  });
}

export function useBinanceFunding(symbol = "BTCUSDT") {
  return useQuery({
    queryKey: ["binance-funding", symbol],
    queryFn: ({ signal }) => fetchBinanceFunding(symbol, signal),
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  });
}

export function useCryptoPanic(currencies = "") {
  return useQuery({
    queryKey: ["cryptopanic", currencies],
    queryFn: ({ signal }) => fetchCryptoPanic(currencies, signal),
    refetchInterval: 5 * 60 * 1000,
    staleTime: 60 * 1000,
  });
}

export function useBacktest(symbol: string | null, bars = 200, interval = "Hour4") {
  return useQuery({
    queryKey: ["backtest", symbol, bars, interval],
    queryFn: ({ signal }) => fetchBacktest(symbol!, bars, interval, signal),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePatternWinrate() {
  return useQuery({
    queryKey: ["pattern-winrate"],
    queryFn: ({ signal }) => fetchPatternWinrate(signal),
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  });
}

export function useDeFiLlama() {
  return useQuery({
    queryKey: ["defillama"],
    queryFn: ({ signal }) => fetchDeFiLlama(signal),
    refetchInterval: 10 * 60 * 1000,
    staleTime: 5 * 60 * 1000,
  });
}

export function useWsStatus() {
  return useQuery({
    queryKey: ["ws-status"],
    queryFn: ({ signal }) => fetchWsStatus(signal),
    refetchInterval: 5 * 1000,
    staleTime: 0,
  });
}
