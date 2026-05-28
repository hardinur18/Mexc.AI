import { useMemo, useState } from "react";
import * as Checkbox from "@radix-ui/react-checkbox";
import { Check, ChevronDown, Users, Search, Settings as Cog } from "lucide-react";
import { useAccounts } from "@/hooks/useSnapshot";
import { useUiStore } from "@/store/ui";
import { Button } from "@/components/ui/Button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/Popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { fmt, fmtSign } from "@/lib/format";
import type { AccountMeta, AccountSummary } from "@/types/position";
import { cn } from "@/lib/cn";

const COLOR_TO_OKLCH: Record<string, string> = {
  violet: "oklch(72% 0.18 280)",
  emerald: "oklch(78% 0.17 165)",
  sky: "oklch(75% 0.13 220)",
  amber: "oklch(80% 0.17 75)",
  rose: "oklch(70% 0.22 25)",
  cyan: "oklch(80% 0.13 210)",
  fuchsia: "oklch(72% 0.22 320)",
  lime: "oklch(85% 0.18 130)",
};

interface AccountPickerProps {
  summaries?: AccountSummary[];
  onOpenSettings?: () => void;
  compact?: boolean;
}

export function AccountPicker({ summaries, onOpenSettings, compact }: AccountPickerProps) {
  const { data: accountsData, isLoading } = useAccounts();
  const accounts = accountsData?.accounts ?? [];
  const selected = useUiStore((s) => s.selectedAccounts);
  const touched = useUiStore((s) => s.accountSelectionTouched);
  const toggleAccount = useUiStore((s) => s.toggleAccount);
  const selectAllAccounts = useUiStore((s) => s.selectAllAccounts);
  const setSelectedAccounts = useUiStore((s) => s.setSelectedAccounts);
  const clearAccountSelection = useUiStore((s) => s.clearAccountSelection);

  const [search, setSearch] = useState("");
  const filtered = useMemo(
    () =>
      accounts.filter(
        (a) =>
          a.name.toLowerCase().includes(search.toLowerCase()) ||
          a.id.toLowerCase().includes(search.toLowerCase()),
      ),
    [accounts, search],
  );

  const isSelected = (a: AccountMeta) => (touched ? selected.has(a.id) : true);

  const effectiveCount = touched ? selected.size : accounts.length;
  const triggerLabel =
    !touched || selected.size === accounts.length
      ? `Semua akun`
      : selected.size === 0
        ? "Tidak ada akun"
        : selected.size === 1
          ? accounts.find((a) => a.id === Array.from(selected)[0])?.name || "1 dipilih"
          : `${selected.size} dipilih`;

  const invertSelection = () => {
    const next = accounts
      .filter((a) => !isSelected(a))
      .map((a) => a.id);
    setSelectedAccounts(next);
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          size="sm"
          tone={compact ? "ghost" : "default"}
          className={cn(
            "min-w-0 gap-1.5",
            compact
              ? "h-7 rounded-[var(--radius-sm)] px-2 text-[12px] shadow-none ring-0"
              : "gap-2 pr-2",
          )}
        >
          <Users size={13} />
          <span className={cn("truncate", compact ? "max-w-[98px]" : "max-w-[150px]")}>
            {triggerLabel}
          </span>
          <span className="inline-flex h-5 min-w-6 items-center justify-center rounded-[var(--radius-xs)] bg-[var(--color-accent-soft)] px-1.5 text-[11px] font-bold leading-none text-[var(--color-accent)] ring-1 ring-[var(--color-accent)]/30">
            {effectiveCount}/{accounts.length}
          </span>
          <ChevronDown size={12} className="opacity-60" />
        </Button>
      </PopoverTrigger>

      <PopoverContent align="end" className="min-w-[320px] p-0">
        <div className="px-3 pt-2.5 pb-2 border-b border-[var(--color-border)]">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
              Akun MEXC
            </div>
            <button
              type="button"
              onClick={onOpenSettings}
              className="text-[10px] uppercase tracking-wider text-[var(--color-accent)] hover:underline flex items-center gap-1"
            >
              <Cog size={10} />
              Kelola
            </button>
          </div>

          {/* Search */}
          {accounts.length > 5 && (
            <div className="relative mb-2">
              <Search
                size={12}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-fg-faint)]"
              />
              <input
                type="text"
                placeholder="Cari akun..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-7 pr-2 py-1 text-[11px] rounded-[var(--radius-sm)] bg-[var(--color-bg-elev-2)] ring-1 ring-[var(--color-border)] focus:ring-[var(--color-accent)] focus:outline-none"
              />
            </div>
          )}

          {/* Quick toggles */}
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              tone="ghost"
              onClick={() => selectAllAccounts(accounts.map((a) => a.id))}
              className="h-6 px-2 text-[10px]"
            >
              Semua
            </Button>
            <Button
              size="sm"
              tone="ghost"
              onClick={clearAccountSelection}
              className="h-6 px-2 text-[10px]"
            >
              Default
            </Button>
            <Button
              size="sm"
              tone="ghost"
              onClick={() => setSelectedAccounts([])}
              className="h-6 px-2 text-[10px]"
            >
              Kosong
            </Button>
            <Button
              size="sm"
              tone="ghost"
              onClick={invertSelection}
              className="h-6 px-2 text-[10px]"
            >
              Balik
            </Button>
          </div>
        </div>

        <div className="max-h-[420px] overflow-y-auto py-1">
          {isLoading ? (
            <div className="text-[11px] text-[var(--color-fg-subtle)] px-3 py-3">
              Memuat...
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-[11px] text-[var(--color-fg-subtle)] px-3 py-3 text-center">
              {accounts.length === 0
                ? "Belum ada akun. Klik Kelola untuk menambah."
                : "Tidak ada hasil."}
            </div>
          ) : (() => {
            // Group filtered by category
            const groups: Record<string, AccountMeta[]> = {};
            for (const a of filtered) {
              const k = a.category || "utama";
              groups[k] = groups[k] || [];
              groups[k].push(a);
            }
            const sortedKeys = Object.keys(groups).sort((a, b) => {
              const order = ["utama", "radar", "booster", "hedge", "test"];
              return (
                (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) -
                (order.indexOf(b) === -1 ? 99 : order.indexOf(b))
              );
            });
            return sortedKeys.flatMap((cat) => [
              <div
                key={`cat-${cat}`}
                className="px-3 pt-2 pb-1 text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] font-bold flex items-center justify-between"
              >
                <span>{cat}</span>
                <span className="text-[var(--color-fg-faint)]">{groups[cat].length}</span>
              </div>,
              ...groups[cat].map((a) => {
              const checked = isSelected(a);
              const sum = summaries?.find((s) => s.id === a.id);
              const dot = a.color?.startsWith("#")
                ? a.color
                : COLOR_TO_OKLCH[a.color] ?? COLOR_TO_OKLCH.violet;
              return (
                <button
                  key={a.id}
                  type="button"
                  className={cn(
                    "w-full text-left flex items-center gap-2.5 px-3 py-2 hover:bg-[var(--color-accent-soft)] transition",
                    checked && "bg-[var(--color-accent-soft)]/50",
                  )}
                  onClick={() => toggleAccount(a.id)}
                >
                  <Checkbox.Root
                    checked={checked}
                    className={cn(
                      "w-4 h-4 rounded-sm ring-1 flex items-center justify-center shrink-0 transition",
                      checked
                        ? "bg-[var(--color-accent)] ring-[var(--color-accent)]"
                        : "ring-[var(--color-border-strong)] bg-transparent",
                    )}
                  >
                    <Checkbox.Indicator>
                      <Check size={11} strokeWidth={3} className="text-[var(--color-fg)]" />
                    </Checkbox.Indicator>
                  </Checkbox.Root>

                  <div
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: dot }}
                  />

                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate">{a.name}</div>
                    <div className="text-[10px] text-[var(--color-fg-faint)] font-mono truncate">
                      {a.id}
                    </div>
                  </div>

                  {sum && !sum.error && (
                    <div className="text-right leading-tight">
                      <div className="text-[11px] num font-medium">
                        {fmt(sum.equity, 2)}
                      </div>
                      <div
                        className={cn(
                          "text-[10px] num",
                          sum.unrealized > 0
                            ? "text-[var(--color-success)]"
                            : sum.unrealized < 0
                              ? "text-[var(--color-danger)]"
                              : "text-[var(--color-fg-subtle)]",
                        )}
                      >
                        {fmtSign(sum.unrealized, 2)}
                      </div>
                      <div className="text-[9px] text-[var(--color-fg-faint)]">
                        {sum.position_count} pos
                      </div>
                    </div>
                  )}
                  {sum?.error && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-1 ring-[var(--color-danger)]/40 cursor-help"
                          onClick={(e) => e.stopPropagation()}
                        >
                          ERR
                        </span>
                      </TooltipTrigger>
                      <TooltipContent
                        side="left"
                        className="text-[11px] max-w-xs whitespace-normal"
                      >
                        {sum.error}
                      </TooltipContent>
                    </Tooltip>
                  )}
                </button>
              );
            })
            ]);
          })()}
        </div>

        <div className="border-t border-[var(--color-border)] px-3 py-1.5 text-[10px] text-[var(--color-fg-subtle)] flex items-center justify-between">
          <span>
            {effectiveCount} dipilih · {accounts.length} total
          </span>
          <button
            type="button"
            onClick={onOpenSettings}
            className="text-[var(--color-accent)] hover:underline flex items-center gap-1"
          >
            <Cog size={10} />
            Tambah akun
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
