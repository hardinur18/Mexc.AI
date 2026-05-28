import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { CheckCircle, XCircle } from "lucide-react";
import type { Position } from "@/types/position";
import { createElement } from "react";

interface PositionSnapshot {
  symbol: string;
  side: string;
  account_name: string;
  account_id: string;
  pnl_usdt: number;
  seenCount: number;  // how many polls we've seen this id
  lastSeenTs: number;
}

const MIN_OBSERVATIONS = 2;          // must see position 2+ times before tracking
const MIN_AGE_MS = 8000;             // position must be tracked for 8s+ to be considered "closed"
const MAX_TOAST_BURST = 3;           // if more than 3 closures in same poll, suppress (account swap)

/**
 * Detects position closures = position present in prior poll but missing now.
 * Guards:
 *  - Skip if accounts in scope changed (filter shift, not real closure)
 *  - Require min observations (avoid one-off snapshot blip)
 *  - Suppress mass-closure burst (= account filter, not real closures)
 */
export function usePositionClosureDetector(positions: Position[] | undefined) {
  const previousRef = useRef<Map<number, PositionSnapshot>>(new Map());
  const prevAccountsRef = useRef<Set<string>>(new Set());
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!positions) return;

    const now = Date.now();
    const currentIds = new Set(positions.map((p) => p.position_id));
    const currentAccounts = new Set(positions.map((p) => p.account_id));
    const prev = previousRef.current;
    const prevAccounts = prevAccountsRef.current;

    // Detect account-scope change: if any account in our previous set isn't in current set,
    // that means filter changed (we de-selected an account). Skip closure detection.
    const accountScopeChanged = (() => {
      // If a previously-seen account is no longer present, scope shrunk
      for (const a of prevAccounts) {
        if (!currentAccounts.has(a)) return true;
      }
      // If a new account appeared, scope grew (no closure inference issue but still skip first tick)
      for (const a of currentAccounts) {
        if (!prevAccounts.has(a)) return true;
      }
      return false;
    })();

    if (initializedRef.current && !accountScopeChanged) {
      // Detect closures
      const closures: PositionSnapshot[] = [];
      for (const [id, info] of prev.entries()) {
        if (currentIds.has(id)) continue;
        // Filter: only fire if we observed this position multiple times + long enough age
        if (info.seenCount < MIN_OBSERVATIONS) continue;
        if (now - info.lastSeenTs > 15000) continue; // stale (probably api gap, not real closure)
        const age = now - (info.lastSeenTs - 5000); // rough lifetime
        if (age < MIN_AGE_MS) continue;
        closures.push(info);
      }

      // Suppress mass-closure burst (probably account filter change we missed)
      if (closures.length <= MAX_TOAST_BURST) {
        for (const info of closures) {
          const wasProfit = info.pnl_usdt >= 0;
          toast(
            createElement(
              "div",
              { style: { display: "flex", flexDirection: "column", gap: 2 } },
              createElement("div", { style: { fontWeight: 600 } }, `Position closed: ${info.symbol}`),
              createElement(
                "div",
                {
                  style: {
                    fontSize: 11,
                    color: wasProfit ? "var(--color-success)" : "var(--color-danger)",
                  },
                },
                `${wasProfit ? "+" : ""}${info.pnl_usdt.toFixed(4)} USDT · ${info.side} · ${info.account_name}`,
              ),
            ),
            {
              icon: createElement(wasProfit ? CheckCircle : XCircle, {
                size: 16,
                style: { color: wasProfit ? "var(--color-success)" : "var(--color-danger)" },
              }),
              duration: 8000,
            },
          );
        }
      }
    }
    initializedRef.current = true;
    prevAccountsRef.current = currentAccounts;

    // Update snapshot — increment seenCount for existing, init for new
    const newMap = new Map<number, PositionSnapshot>();
    for (const p of positions) {
      const existing = prev.get(p.position_id);
      newMap.set(p.position_id, {
        symbol: p.symbol,
        side: p.side,
        account_name: p.account_name,
        account_id: p.account_id,
        pnl_usdt: p.pnl_usdt,
        seenCount: (existing?.seenCount ?? 0) + 1,
        lastSeenTs: now,
      });
    }
    previousRef.current = newMap;
  }, [positions]);
}
