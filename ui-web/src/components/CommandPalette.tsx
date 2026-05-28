import { useEffect } from "react";
import { Command } from "cmdk";
import {
  ChevronsDown,
  ChevronsUp,
  Pause,
  Play,
  Plus,
  Search,
  Settings,
  Target,
  Users,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/Dialog";
import { useUiStore } from "@/store/ui";
import { useAccounts } from "@/hooks/useSnapshot";
import type { Position } from "@/types/position";
import "./CommandPalette.css";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  positions: Position[];
  onOpenSettings: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
  positions,
  onOpenSettings,
}: CommandPaletteProps) {
  const { data: accountsData } = useAccounts();
  const accounts = accountsData?.accounts ?? [];
  const toggleExpand = useUiStore((s) => s.toggleExpand);
  const expandAll = useUiStore((s) => s.expandAll);
  const collapseAll = useUiStore((s) => s.collapseAll);
  const togglePaused = useUiStore((s) => s.togglePaused);
  const paused = useUiStore((s) => s.paused);
  const toggleAccount = useUiStore((s) => s.toggleAccount);
  const setSelectedAccounts = useUiStore((s) => s.setSelectedAccounts);
  const setCursor = useUiStore((s) => s.setCursor);

  // Cmd+K to open
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onOpenChange]);

  const runAndClose = (fn: () => void) => {
    fn();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent hideClose className="p-0 overflow-hidden w-[min(540px,calc(100vw-32px))]">
        <Command label="Command palette" className="cmdk-root">
          <div className="flex items-center gap-2 px-4 border-b border-[var(--color-border)]">
            <Search size={14} className="text-[var(--color-fg-subtle)]" />
            <Command.Input
              placeholder="Cari posisi, akun, atau aksi..."
              className="flex-1 h-12 bg-transparent text-sm outline-none text-[var(--color-fg)] placeholder:text-[var(--color-fg-faint)]"
              autoFocus
            />
            <kbd className="text-[10px] text-[var(--color-fg-faint)] font-mono px-1.5 py-0.5 rounded border border-[var(--color-border)]">
              ESC
            </kbd>
          </div>

          <Command.List className="max-h-[400px] overflow-y-auto p-1.5">
            <Command.Empty className="px-3 py-6 text-center text-[11px] text-[var(--color-fg-subtle)]">
              No results found.
            </Command.Empty>

            <Command.Group heading="Positions" className="cmdk-group">
              {positions.map((p, idx) => (
                <Command.Item
                  key={p.position_id}
                  value={`${p.coin} ${p.symbol} ${p.side} pos${idx + 1}`}
                  onSelect={() =>
                    runAndClose(() => {
                      setCursor(idx);
                      toggleExpand(p.position_id);
                    })
                  }
                  className="cmdk-item"
                >
                  <Target size={13} className="text-[var(--color-accent)]" />
                  <div className="flex-1">
                    <span className="font-medium">{p.coin}</span>
                    <span className="text-[var(--color-fg-faint)] ml-2 text-[11px] font-mono">
                      {p.symbol}
                    </span>
                  </div>
                  <span
                    className={
                      "text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded " +
                      (p.side === "LONG"
                        ? "text-[var(--color-success)] bg-[var(--color-success-soft)]"
                        : "text-[var(--color-danger)] bg-[var(--color-danger-soft)]")
                    }
                  >
                    {p.side}
                  </span>
                  <span
                    className="text-[10px] num"
                    style={{
                      color:
                        p.pnl_usdt > 0
                          ? "var(--color-success)"
                          : p.pnl_usdt < 0
                            ? "var(--color-danger)"
                            : "var(--color-fg-muted)",
                    }}
                  >
                    {p.pnl_usdt > 0 ? "+" : ""}
                    {p.pnl_usdt.toFixed(4)}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group heading="Accounts" className="cmdk-group">
              {accounts.map((a) => (
                <Command.Item
                  key={a.id}
                  value={`account ${a.name} ${a.id}`}
                  onSelect={() => runAndClose(() => toggleAccount(a.id))}
                  className="cmdk-item"
                >
                  <Users size={13} className="text-[var(--color-fg-muted)]" />
                  <span>Toggle {a.name}</span>
                  <span className="text-[10px] font-mono text-[var(--color-fg-faint)] ml-auto">
                    {a.id}
                  </span>
                </Command.Item>
              ))}
              <Command.Item
                value="all accounts select"
                onSelect={() =>
                  runAndClose(() => setSelectedAccounts(accounts.map((a) => a.id)))
                }
                className="cmdk-item"
              >
                <Users size={13} className="text-[var(--color-accent)]" />
                <span>Select all accounts</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Actions" className="cmdk-group">
              <Command.Item
                value="expand all positions"
                onSelect={() =>
                  runAndClose(() => expandAll(positions.map((p) => p.position_id)))
                }
                className="cmdk-item"
              >
                <ChevronsDown size={13} />
                <span>Expand all positions</span>
                <kbd className="cmdk-kbd">E</kbd>
              </Command.Item>
              <Command.Item
                value="collapse all positions"
                onSelect={() => runAndClose(collapseAll)}
                className="cmdk-item"
              >
                <ChevronsUp size={13} />
                <span>Collapse all positions</span>
                <kbd className="cmdk-kbd">C</kbd>
              </Command.Item>
              <Command.Item
                value="pause resume polling"
                onSelect={() => runAndClose(togglePaused)}
                className="cmdk-item"
              >
                {paused ? <Play size={13} /> : <Pause size={13} />}
                <span>{paused ? "Resume" : "Pause"} polling</span>
                <kbd className="cmdk-kbd">Space</kbd>
              </Command.Item>
              <Command.Item
                value="settings open accounts"
                onSelect={() => runAndClose(onOpenSettings)}
                className="cmdk-item"
              >
                <Settings size={13} />
                <span>Open account settings</span>
              </Command.Item>
              <Command.Item
                value="add new account"
                onSelect={() => runAndClose(onOpenSettings)}
                className="cmdk-item"
              >
                <Plus size={13} className="text-[var(--color-accent)]" />
                <span>Add new MEXC account</span>
              </Command.Item>
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
