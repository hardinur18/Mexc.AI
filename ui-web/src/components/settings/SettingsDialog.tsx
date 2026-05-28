import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, AlertTriangle, Loader2, Users, Sliders, Tags } from "lucide-react";
import { toast } from "sonner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import { StrategyEditor } from "./StrategyEditor";
import { CategoriesManager } from "./CategoriesManager";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { AccountForm } from "./AccountForm";
import { useAccounts } from "@/hooks/useSnapshot";
import { deleteAccount } from "@/lib/api";
import type { AccountMeta } from "@/types/position";

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

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const { data, isLoading } = useAccounts();
  const accounts = data?.accounts ?? [];
  const [mode, setMode] = useState<"list" | "add" | "edit">("list");
  const [editing, setEditing] = useState<AccountMeta | null>(null);

  const reset = () => {
    setMode("list");
    setEditing(null);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent>
        <div className="px-5 pt-5 pb-3 border-b border-[var(--color-border)]">
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Manage akun MEXC kamu + strategi auto-entry. Config disimpan lokal di{" "}
            <code className="font-mono text-[11px] text-[var(--color-fg-muted)]">accounts.json</code>.
          </DialogDescription>
        </div>

        <Tabs defaultValue="accounts" className="px-5 py-4">
          <TabsList>
            <TabsTrigger value="accounts">
              <Users size={11} className="mr-1" /> Accounts
            </TabsTrigger>
            <TabsTrigger value="categories">
              <Tags size={11} className="mr-1" /> Categories
            </TabsTrigger>
            <TabsTrigger value="strategy">
              <Sliders size={11} className="mr-1" /> Strategy
            </TabsTrigger>
          </TabsList>

          <TabsContent value="accounts">
            {mode === "list" && (
              <ListView
                accounts={accounts}
                isLoading={isLoading}
                onAdd={() => setMode("add")}
                onEdit={(a) => {
                  setEditing(a);
                  setMode("edit");
                }}
              />
            )}

            {mode === "add" && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-3">
                  Add New Account
                </div>
                <AccountForm onSuccess={reset} onCancel={reset} />
              </div>
            )}

            {mode === "edit" && editing && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-3">
                  Edit · <span className="font-mono">{editing.id}</span>
                </div>
                <AccountForm existing={editing} onSuccess={reset} onCancel={reset} />
              </div>
            )}
          </TabsContent>

          <TabsContent value="categories">
            <CategoriesManager />
          </TabsContent>

          <TabsContent value="strategy">
            <StrategyEditor onClose={() => onOpenChange(false)} />
          </TabsContent>
        </Tabs>

        <div className="px-5 py-2.5 border-t border-[var(--color-border)] text-[10px] text-[var(--color-fg-faint)] flex items-center gap-1.5">
          <AlertTriangle size={11} />
          Keys disimpan plaintext di accounts.json (sudah .gitignored). Buat MEXC API
          dashboard pasang IP whitelist + disable withdraw permission.
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ─────────────── List View ─────────────── */
function ListView({
  accounts,
  isLoading,
  onAdd,
  onEdit,
}: {
  accounts: AccountMeta[];
  isLoading: boolean;
  onAdd: () => void;
  onEdit: (a: AccountMeta) => void;
}) {
  const qc = useQueryClient();
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteAccount(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["snapshot"] });
      setConfirmId(null);
      toast.success(`Account "${id}" removed`);
    },
    onError: (err: Error) => {
      toast.error("Failed to delete", { description: err.message });
    },
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-subtle)]">
          {accounts.length} {accounts.length === 1 ? "account" : "accounts"}
        </div>
        <Button onClick={onAdd} tone="accent" size="sm">
          <Plus size={12} /> Add Account
        </Button>
      </div>

      {isLoading ? (
        <div className="py-6 text-center text-[11px] text-[var(--color-fg-subtle)]">
          Loading…
        </div>
      ) : accounts.length === 0 ? (
        <div className="py-6 text-center text-[11px] text-[var(--color-fg-subtle)]">
          Belum ada akun. Klik <strong>Add Account</strong> untuk mulai.
        </div>
      ) : (
        <div className="space-y-2">
          {accounts.map((a) => (
            <div
              key={a.id}
              className="flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] hover:ring-[var(--color-border-strong)] transition"
            >
              <div
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ background: COLOR_TO_OKLCH[a.color] ?? COLOR_TO_OKLCH.violet }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate flex items-center gap-1.5">
                  {a.name}
                  <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/5 text-[var(--color-fg-muted)] ring-1 ring-[var(--color-border)] font-semibold">
                    {a.category}
                  </span>
                </div>
                <div className="text-[10px] text-[var(--color-fg-subtle)] font-mono truncate">
                  {a.id}
                </div>
              </div>

              {confirmId === a.id ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-[var(--color-danger)]">Sure?</span>
                  <Button
                    tone="default"
                    size="sm"
                    onClick={() => setConfirmId(null)}
                    disabled={deleteMut.isPending}
                  >
                    No
                  </Button>
                  <Button
                    tone="default"
                    size="sm"
                    onClick={() => deleteMut.mutate(a.id)}
                    disabled={deleteMut.isPending}
                    className="text-[var(--color-danger)] ring-[var(--color-danger)]/40"
                  >
                    {deleteMut.isPending ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      "Delete"
                    )}
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <Button tone="ghost" size="icon" onClick={() => onEdit(a)} title="Edit">
                    <Pencil size={13} />
                  </Button>
                  <Button
                    tone="ghost"
                    size="icon"
                    onClick={() => setConfirmId(a.id)}
                    title="Delete"
                    className="hover:text-[var(--color-danger)]"
                    disabled={accounts.length === 1}
                  >
                    <Trash2 size={13} />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {deleteMut.error && (
        <div className="text-[11px] text-[var(--color-danger)] mt-2">
          {(deleteMut.error as Error).message}
        </div>
      )}
    </div>
  );
}
