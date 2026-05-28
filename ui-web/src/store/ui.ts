import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { Position } from "@/types/position";

type SortKey = keyof Pick<
  Position,
  | "no"
  | "coin"
  | "symbol"
  | "side"
  | "lev"
  | "margin"
  | "notional"
  | "entry"
  | "price"
  | "price_delta_pct"
  | "pnl_usdt"
  | "pnl_pct_lev"
  | "tp_price"
  | "tp_dist_pct"
  | "sl_price"
  | "margin_ratio"
  | "liq_price"
  | "buffer_pct"
>;
type SortDir = "asc" | "desc";

interface UiState {
  intervalSec: 2 | 5 | 10;
  paused: boolean;
  expanded: Set<number>;
  sortKey: SortKey;
  sortDir: SortDir;
  /** Selected account IDs. Empty Set = backend default (all). */
  selectedAccounts: Set<string>;
  /** True once user has manually changed account selection. */
  accountSelectionTouched: boolean;
  /** Keyboard cursor row index (J/K nav). */
  cursor: number;
  /** Group positions by account in table. */
  groupByAccount: boolean;
  /** Fullscreen mode flag — tells layout to use full viewport. */
  fullscreen: boolean;
  /** Theme mode — dark or light. */
  theme: "dark" | "light";
  /** Active page in sidebar navigation. */
  activePage: "dashboard" | "signals" | "cascade" | "performance" | "risk" | "accounts" | "history";
  /** Sidebar collapsed state. */
  sidebarCollapsed: boolean;

  setIntervalSec: (v: 2 | 5 | 10) => void;
  togglePaused: () => void;
  toggleExpand: (id: number) => void;
  expandAll: (ids: number[]) => void;
  collapseAll: () => void;
  setSort: (k: SortKey) => void;
  toggleAccount: (id: string) => void;
  setSelectedAccounts: (ids: string[]) => void;
  selectAllAccounts: (ids: string[]) => void;
  clearAccountSelection: () => void;
  setCursor: (i: number) => void;
  toggleGroupByAccount: () => void;
  toggleFullscreen: () => void;
  toggleTheme: () => void;
  setActivePage: (page: UiState["activePage"]) => void;
  toggleSidebar: () => void;
}

export const useUiStore = create<UiState>()(persist((set) => ({
  intervalSec: 2,
  paused: false,
  expanded: new Set<number>(),
  sortKey: "pnl_pct_lev",
  sortDir: "desc",
  selectedAccounts: new Set<string>(),
  accountSelectionTouched: false,
  cursor: 0,
  groupByAccount: false,
  fullscreen: false,
  theme: "dark" as "dark" | "light",
  activePage: "dashboard" as UiState["activePage"],
  sidebarCollapsed: false,

  setIntervalSec: (v) => set({ intervalSec: v }),
  togglePaused: () => set((s) => ({ paused: !s.paused })),
  toggleExpand: (id) =>
    set((s) => {
      const next = new Set(s.expanded);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { expanded: next };
    }),
  expandAll: (ids) => set({ expanded: new Set(ids) }),
  collapseAll: () => set({ expanded: new Set() }),
  setSort: (k) =>
    set((s) => ({
      sortKey: k,
      sortDir: s.sortKey === k ? (s.sortDir === "asc" ? "desc" : "asc") : "desc",
    })),
  toggleAccount: (id) =>
    set((s) => {
      const next = new Set(s.selectedAccounts);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { selectedAccounts: next, accountSelectionTouched: true };
    }),
  setSelectedAccounts: (ids) =>
    set({ selectedAccounts: new Set(ids), accountSelectionTouched: true }),
  selectAllAccounts: (ids) =>
    set({ selectedAccounts: new Set(ids), accountSelectionTouched: true }),
  clearAccountSelection: () =>
    set({ selectedAccounts: new Set(), accountSelectionTouched: false }),
  setCursor: (i) => set({ cursor: i }),
  toggleGroupByAccount: () => set((s) => ({ groupByAccount: !s.groupByAccount })),
  toggleFullscreen: () => set((s) => ({ fullscreen: !s.fullscreen })),
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      return { theme: next };
    }),
  setActivePage: (page) => set({ activePage: page }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}), {
  name: "mexc-dashboard-ui",
  storage: createJSONStorage(() => localStorage),
  partialize: (s) => ({
    intervalSec: s.intervalSec,
    sortKey: s.sortKey,
    sortDir: s.sortDir,
    selectedAccounts: Array.from(s.selectedAccounts),
    accountSelectionTouched: s.accountSelectionTouched,
    groupByAccount: s.groupByAccount,
    fullscreen: s.fullscreen,
    theme: s.theme,
    activePage: s.activePage,
    sidebarCollapsed: s.sidebarCollapsed,
  }),
  // Reviver: convert array back to Set
  merge: (persisted: any, current) => {
    const theme = persisted?.theme ?? "dark";
    document.documentElement.setAttribute("data-theme", theme);
    return {
      ...current,
      ...(persisted ?? {}),
      theme,
      selectedAccounts: new Set<string>(persisted?.selectedAccounts ?? []),
      expanded: new Set<number>(),
    };
  },
}));

export type { SortKey, SortDir };
