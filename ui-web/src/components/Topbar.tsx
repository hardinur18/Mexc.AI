import { Activity, Command, Pause, Play, RefreshCw, Settings } from "lucide-react";
import { useUiStore } from "@/store/ui";
import { Button } from "@/components/ui/Button";
import { AccountPicker } from "@/components/AccountPicker";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { cn } from "@/lib/cn";
import type { Snapshot } from "@/types/position";

interface TopbarProps {
  snapshot: Snapshot | undefined;
  isError: boolean;
  isFetching: boolean;
  onOpenCommandPalette?: () => void;
  onOpenSettings: () => void;
}

export function Topbar({
  snapshot,
  isError,
  isFetching,
  onOpenCommandPalette,
  onOpenSettings,
}: TopbarProps) {
  const intervalSec = useUiStore((s) => s.intervalSec);
  const paused = useUiStore((s) => s.paused);
  const setIntervalSec = useUiStore((s) => s.setIntervalSec);
  const togglePaused = useUiStore((s) => s.togglePaused);
  const connected = !!snapshot && !isError;
  const intervals: Array<2 | 5 | 10> = [2, 5, 10];

  return (
    <div className="px-3 pt-3 md:px-4">
      <div className="flex min-h-14 items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-elev)]/90 px-3 py-2 shadow-[var(--shadow-soft)] backdrop-blur-2xl md:px-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <ConnectionDot connected={connected} isError={isError} snapshot={snapshot} />

          {snapshot && (
            <div className="flex min-w-0 items-center gap-3">
              <div className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-accent-soft)] text-[var(--color-accent)] sm:flex">
                <Activity size={15} />
              </div>
              <div className="min-w-0">
                <div className="ui-kicker">
                  Ekuitas
                </div>
                <div className="flex min-w-0 items-baseline gap-1.5">
                  <AnimatedNumber
                    value={snapshot.account.equity}
                    decimals={2}
                    className="num truncate text-[18px] font-bold leading-tight text-[var(--color-fg)]"
                  />
                  <span className="text-[10px] text-[var(--color-fg-faint)]">USDT</span>
                </div>
              </div>
              <div
                className={cn(
                  "hidden items-center gap-1 rounded-[var(--radius-sm)] px-2 py-1 text-[11px] font-semibold ring-1 sm:flex",
                  snapshot.account.unrealized > 0 &&
                    "bg-[var(--color-success-soft)] text-[var(--color-success)] ring-[var(--color-success)]/30",
                  snapshot.account.unrealized < 0 &&
                    "bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-[var(--color-danger)]/30",
                  snapshot.account.unrealized === 0 &&
                    "bg-[var(--color-bg-elev-2)] text-[var(--color-fg-subtle)] ring-[var(--color-border)]",
                )}
              >
                <AnimatedNumber
                  value={snapshot.account.unrealized}
                  decimals={2}
                  signed
                  className="num"
                />
              </div>
            </div>
          )}
        </div>

        <div className="ml-auto flex h-9 shrink-0 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-[var(--shadow-soft)]">
          {onOpenCommandPalette && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  tone="ghost"
                  onClick={onOpenCommandPalette}
                  aria-label="Command palette"
                  className="h-7 w-7 rounded-[var(--radius-sm)] shadow-none ring-0"
                >
                  <Command size={14} />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-[11px]">
                Palet perintah
              </TooltipContent>
            </Tooltip>
          )}

          <div className="hidden md:block">
            <AccountPicker
              summaries={snapshot?.accounts}
              onOpenSettings={onOpenSettings}
              compact
            />
          </div>

          <div className="hidden h-7 items-center gap-0.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev)] p-0.5 sm:flex">
            {intervals.map((iv) => (
              <button
                key={iv}
                type="button"
                onClick={() => setIntervalSec(iv)}
                className={cn(
                  "h-6 min-w-7 rounded-[var(--radius-xs)] px-1.5 text-[11px] font-semibold leading-none transition",
                  intervalSec === iv
                    ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                    : "text-[var(--color-fg-subtle)] hover:bg-[var(--color-bg-elev-2)] hover:text-[var(--color-fg)]",
                )}
              >
                {iv}s
              </button>
            ))}
          </div>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                tone="ghost"
                aria-label="Status refresh"
                disabled
                className="h-7 w-7 rounded-[var(--radius-sm)] shadow-none ring-0"
              >
                <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-[11px]">
              {isFetching ? "Memuat ulang" : "Siaga"}
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                tone="ghost"
                onClick={togglePaused}
                aria-label="Jeda / Lanjut"
                className="h-7 w-7 rounded-[var(--radius-sm)] shadow-none ring-0"
              >
                {paused ? <Play size={12} /> : <Pause size={12} />}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-[11px]">
              {paused ? "Lanjut" : "Jeda"} / Space
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                tone="ghost"
                onClick={onOpenSettings}
                aria-label="Pengaturan"
                className="h-7 w-7 rounded-[var(--radius-sm)] shadow-none ring-0"
              >
                <Settings size={13} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-[11px]">
              Pengaturan
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  );
}

function ConnectionDot({
  connected,
  isError,
  snapshot,
}: {
  connected: boolean;
  isError: boolean;
  snapshot: Snapshot | undefined;
}) {
  const intervalSec = useUiStore((s) => s.intervalSec);
  const paused = useUiStore((s) => s.paused);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-surface)] ring-1 ring-[var(--color-border)]"
          aria-label={connected ? "Connected" : "Disconnected"}
        >
          <span
            className={cn(
              "absolute h-2.5 w-2.5 rounded-full",
              connected && "bg-[var(--color-success)]",
              !connected && isError && "bg-[var(--color-danger)]",
              !connected && !isError && "bg-[var(--color-fg-faint)]",
            )}
          />
          {connected && (
            <span className="absolute h-2.5 w-2.5 rounded-full bg-[var(--color-success)] opacity-60 [animation:ghost-ring_2s_ease-out_infinite]" />
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="text-[11px]">
        <div className="space-y-0.5">
          <div className="font-semibold">
            {connected ? "Live" : isError ? "Terputus" : "Memuat"}
          </div>
          {snapshot && (
            <>
              <div className="text-[var(--color-fg-subtle)]">
                Polling {intervalSec}s / {paused ? "jeda" : "aktif"}
              </div>
              <div className="text-[var(--color-fg-faint)]">
                Latensi {snapshot.latency_ms}ms
              </div>
            </>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
