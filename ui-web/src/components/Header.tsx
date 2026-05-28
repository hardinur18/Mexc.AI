import { useState } from "react";
import { useUiStore } from "@/store/ui";
import { Button } from "@/components/ui/Button";
import {
  Pause,
  Play,
  ChevronsDown,
  ChevronsUp,
  Settings,
  Command,
  Layers,
  Maximize2,
  Minimize2,
  MoreHorizontal,
  Check,
  Sun,
  Moon,
} from "lucide-react";
import type { Snapshot } from "@/types/position";
import { lazy, Suspense } from "react";
import { AccountPicker } from "@/components/AccountPicker";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/Popover";

const SettingsDialog = lazy(() =>
  import("@/components/settings/SettingsDialog").then((m) => ({ default: m.SettingsDialog })),
);
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/Tooltip";

interface HeaderProps {
  snapshot: Snapshot | undefined;
  isError: boolean;
  isFetching: boolean;
  onOpenCommandPalette?: () => void;
}

export function Header({ snapshot, isError, onOpenCommandPalette }: HeaderProps) {
  const intervalSec = useUiStore((s) => s.intervalSec);
  const paused = useUiStore((s) => s.paused);
  const setIntervalSec = useUiStore((s) => s.setIntervalSec);
  const togglePaused = useUiStore((s) => s.togglePaused);
  const expandAll = useUiStore((s) => s.expandAll);
  const collapseAll = useUiStore((s) => s.collapseAll);
  const expandedSize = useUiStore((s) => s.expanded.size);
  const groupByAccount = useUiStore((s) => s.groupByAccount);
  const toggleGroupByAccount = useUiStore((s) => s.toggleGroupByAccount);
  const fullscreen = useUiStore((s) => s.fullscreen);
  const toggleFullscreen = useUiStore((s) => s.toggleFullscreen);
  const theme = useUiStore((s) => s.theme);
  const toggleTheme = useUiStore((s) => s.toggleTheme);

  const triggerFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
    toggleFullscreen();
  };

  const connected = !!snapshot && !isError;
  const intervals: Array<2 | 5 | 10> = [2, 5, 10];
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const hasPositions = !!(snapshot && snapshot.positions.length > 0);

  return (
    <div className="flex items-center justify-between gap-4 flex-wrap">
      <div className="flex items-center gap-4">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="relative flex items-center justify-center w-2.5 h-2.5 rounded-full transition cursor-help"
              aria-label={connected ? "Connected" : "Disconnected"}
            >
              <span
                className={
                  "absolute inset-0 rounded-full " +
                  (connected
                    ? "bg-[var(--color-success)]"
                    : isError
                      ? "bg-[var(--color-danger)]"
                      : "bg-[var(--color-fg-faint)]")
                }
              />
              {connected && (
                <span className="absolute inset-0 rounded-full bg-[var(--color-success)] opacity-60 [animation:ghost-ring_2s_ease-out_infinite]" />
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-[11px]">
            <div className="space-y-0.5">
              <div className="font-semibold">
                {connected ? "Live" : isError ? "Disconnected" : "Loading"}
              </div>
              {snapshot && (
                <>
                  <div className="text-[var(--color-fg-subtle)]">
                    Polling {intervalSec}s · {paused ? "paused" : "active"}
                  </div>
                  <div className="text-[var(--color-fg-faint)]">
                    Latency {snapshot.latency_ms}ms
                  </div>
                </>
              )}
            </div>
          </TooltipContent>
        </Tooltip>

        <div className="flex items-baseline gap-3 min-w-0">
          <h1 className="text-base font-semibold text-[var(--color-fg-muted)] shrink-0">
            MEXC Futures
          </h1>
          {snapshot && (
            <>
              <div className="hidden md:flex items-baseline gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)]">
                  Equity
                </span>
                <AnimatedNumber
                  value={snapshot.account.equity}
                  decimals={2}
                  className="text-lg font-bold num text-[var(--color-fg)]"
                />
                <span className="text-[10px] text-[var(--color-fg-faint)]">USDT</span>
              </div>
              <div
                className={
                  "hidden md:flex items-center gap-1 px-2 py-0.5 rounded-[var(--radius-sm)] text-[11px] font-semibold ring-1 " +
                  (snapshot.account.unrealized > 0
                    ? "bg-[var(--color-success-soft)] text-[var(--color-success)] ring-[var(--color-success)]/30"
                    : snapshot.account.unrealized < 0
                      ? "bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-[var(--color-danger)]/30"
                      : "bg-[var(--color-bg-elev-2)] text-[var(--color-fg-subtle)] ring-[var(--color-border)]")
                }
              >
                <AnimatedNumber
                  value={snapshot.account.unrealized}
                  decimals={2}
                  signed
                  className="num"
                />
              </div>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap justify-end">
        {/* PRIMARY: Command palette (frequent search) */}
        {onOpenCommandPalette && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                tone="default"
                onClick={onOpenCommandPalette}
                aria-label="Buka command palette"
              >
                <Command size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-[11px]">
              Cmd · K
            </TooltipContent>
          </Tooltip>
        )}

        {/* PRIMARY: Account filter */}
        <AccountPicker
          summaries={snapshot?.accounts}
          onOpenSettings={() => setSettingsOpen(true)}
        />

        {/* PRIMARY: Polling interval */}
        <div className="flex items-center gap-0.5 px-1 py-0.5 rounded-[var(--radius-md)] bg-[var(--color-surface)] ring-1 ring-[var(--color-border)]">
          {intervals.map((iv) => (
            <button
              key={iv}
              type="button"
              onClick={() => setIntervalSec(iv)}
              className={
                "h-6 px-2 text-[10px] rounded-[var(--radius-sm)] font-medium transition " +
                (intervalSec === iv
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                  : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]")
              }
            >
              {iv}s
            </button>
          ))}
        </div>

        {/* PRIMARY: Pause / Resume */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button size="icon" tone="default" onClick={togglePaused} aria-label="Jeda / Lanjut">
              {paused ? <Play size={12} /> : <Pause size={12} />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-[11px]">
            {paused ? "Lanjut" : "Jeda"} · <span className="font-mono">Space</span>
          </TooltipContent>
        </Tooltip>

        {/* OVERFLOW: View toggles + settings */}
        <Popover open={overflowOpen} onOpenChange={setOverflowOpen}>
          <PopoverTrigger asChild>
            <Button size="icon" tone="default" aria-label="Aksi lainnya">
              <MoreHorizontal size={14} />
            </Button>
          </PopoverTrigger>
          <PopoverContent side="bottom" align="end" className="w-56 p-1">
            {/* Section label */}
            <div className="px-2 pt-1.5 pb-1 text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] font-semibold">
              Tampilan
            </div>
            {hasPositions && (
              <>
                <MenuItem
                  icon={<Layers size={13} />}
                  label="Kelompokkan per akun"
                  active={groupByAccount}
                  onClick={() => {
                    toggleGroupByAccount();
                    setOverflowOpen(false);
                  }}
                />
                <MenuItem
                  icon={<ChevronsDown size={13} />}
                  label="Expand semua"
                  shortcut="E"
                  onClick={() => {
                    if (snapshot) expandAll(snapshot.positions.map((p) => p.position_id));
                    setOverflowOpen(false);
                  }}
                />
                <MenuItem
                  icon={<ChevronsUp size={13} />}
                  label="Collapse semua"
                  shortcut="C"
                  disabled={expandedSize === 0}
                  onClick={() => {
                    collapseAll();
                    setOverflowOpen(false);
                  }}
                />
              </>
            )}
            <MenuItem
              icon={fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
              label={fullscreen ? "Keluar fullscreen" : "Mode fullscreen"}
              active={fullscreen}
              onClick={() => {
                triggerFullscreen();
                setOverflowOpen(false);
              }}
            />
            <MenuItem
              icon={theme === "dark" ? <Sun size={13} /> : <Moon size={13} />}
              label={theme === "dark" ? "Mode siang" : "Mode malam"}
              onClick={() => {
                toggleTheme();
                setOverflowOpen(false);
              }}
            />

            <div className="my-1 h-px bg-[var(--color-border)]/60" />

            <div className="px-2 pt-1 pb-1 text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] font-semibold">
              Pengaturan
            </div>
            <MenuItem
              icon={<Settings size={13} />}
              label="Pengaturan akun"
              onClick={() => {
                setSettingsOpen(true);
                setOverflowOpen(false);
              }}
            />
          </PopoverContent>
        </Popover>

        <Suspense fallback={null}>
          {settingsOpen && <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />}
        </Suspense>
      </div>
    </div>
  );
}

function MenuItem({
  icon,
  label,
  shortcut,
  active,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  shortcut?: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={
        "w-full flex items-center gap-2 px-2 py-1.5 rounded-[var(--radius-sm)] text-[11px] font-medium transition " +
        (disabled
          ? "opacity-40 cursor-not-allowed"
          : active
            ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)]"
            : "text-[var(--color-fg-muted)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-fg)]")
      }
    >
      <span className="text-[var(--color-fg-subtle)] shrink-0">{icon}</span>
      <span className="flex-1 text-left">{label}</span>
      {active && <Check size={11} className="text-[var(--color-accent)]" />}
      {shortcut && !active && (
        <span className="text-[9px] font-mono text-[var(--color-fg-faint)] px-1 py-0.5 rounded bg-[var(--color-surface)] ring-1 ring-[var(--color-border)]">
          {shortcut}
        </span>
      )}
    </button>
  );
}
