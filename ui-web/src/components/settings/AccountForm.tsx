import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Eye, EyeOff, Loader2, Plug, Plus, Tag } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/Button";
import {
  type AccountInput,
  createAccount,
  renameAccountId,
  testAccountConnection,
  updateAccount,
} from "@/lib/api";
import { useCategories } from "@/hooks/useSnapshot";
import type { AccountMeta } from "@/types/position";
import { cn } from "@/lib/cn";

const COLORS = [
  { id: "violet", swatch: "oklch(72% 0.18 280)" },
  { id: "emerald", swatch: "oklch(78% 0.17 165)" },
  { id: "sky", swatch: "oklch(75% 0.13 220)" },
  { id: "amber", swatch: "oklch(80% 0.17 75)" },
  { id: "rose", swatch: "oklch(70% 0.22 25)" },
  { id: "cyan", swatch: "oklch(80% 0.13 210)" },
  { id: "fuchsia", swatch: "oklch(72% 0.22 320)" },
  { id: "lime", swatch: "oklch(85% 0.18 130)" },
];

interface AccountFormProps {
  /** If set, render as edit form for this account. */
  existing?: AccountMeta;
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function AccountForm({ existing, onSuccess, onCancel }: AccountFormProps) {
  const qc = useQueryClient();
  const isEdit = !!existing;
  const { data: catData } = useCategories();

  const [id, setId] = useState(existing?.id ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const [color, setColor] = useState(existing?.color ?? "violet");
  const [category, setCategory] = useState(existing?.category ?? "utama");
  const [showNewCategory, setShowNewCategory] = useState(false);
  const [newCategory, setNewCategory] = useState("");
  const [accessKey, setAccessKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    msg: string;
    equity?: number;
  } | null>(null);

  const allCategories = catData?.categories ?? ["utama", "radar", "booster", "hedge", "test"];

  const testMut = useMutation({
    mutationFn: () => testAccountConnection(accessKey, secretKey),
    onSuccess: (data) =>
      setTestResult({ ok: true, msg: "Credentials valid", equity: data.equity }),
    onError: (err: Error) => setTestResult({ ok: false, msg: err.message }),
  });

  const createMut = useMutation({
    mutationFn: (payload: AccountInput) => createAccount(payload),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["snapshot"] });
      toast.success(`Account "${vars.name}" connected`, { description: `ID: ${vars.id}` });
      onSuccess?.();
    },
    onError: (err: Error) => {
      toast.error("Failed to add account", { description: err.message });
    },
  });

  const updateMut = useMutation({
    mutationFn: async () => {
      // 1. Rename ID first if changed (separate endpoint)
      if (id !== existing!.id) {
        await renameAccountId(existing!.id, id);
      }
      // 2. Then update other fields using NEW id
      const newId = id !== existing!.id ? id : existing!.id;
      return updateAccount(newId, {
        name: name !== existing!.name ? name : undefined,
        color: color !== existing!.color ? color : undefined,
        category: category !== existing!.category ? category : undefined,
        access_key: accessKey || undefined,
        secret_key: secretKey || undefined,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["snapshot"] });
      qc.invalidateQueries({ queryKey: ["categories"] });
      toast.success(`Account "${name}" updated`);
      onSuccess?.();
    },
    onError: (err: Error) => {
      toast.error("Failed to update account", { description: err.message });
    },
  });

  const submitErr = createMut.error || updateMut.error;
  const submitting = createMut.isPending || updateMut.isPending;
  const canSubmit = isEdit
    ? !!name &&
      !!id &&
      (name !== existing!.name ||
        color !== existing!.color ||
        category !== existing!.category ||
        id !== existing!.id ||
        !!accessKey)
    : !!id && !!name && !!accessKey && !!secretKey;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!canSubmit) return;
        if (isEdit) updateMut.mutate();
        else
          createMut.mutate({
            id,
            name,
            color,
            category,
            access_key: accessKey,
            secret_key: secretKey,
          });
      }}
      className="space-y-3"
    >
      {/* ID — editable di add & edit mode */}
      <Field
        label="Account ID"
        hint={
          isEdit
            ? `Rename hanya kalau memang perlu. Old: ${existing!.id}`
            : "Identifier internal (a-z, 0-9, _, -)"
        }
      >
        <input
          type="text"
          value={id}
          onChange={(e) => setId(e.target.value.replace(/[^a-zA-Z0-9_-]/g, ""))}
          placeholder="scalp_bot"
          className={inputCls}
          autoFocus={!isEdit}
        />
      </Field>

      {/* Name */}
      <Field label="Display Name" hint="Yang muncul di dropdown & badge">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Scalp Bot"
          className={inputCls}
        />
      </Field>

      {/* Color */}
      <Field label="Color Tag">
        <div className="flex items-center gap-2">
          {COLORS.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setColor(c.id)}
              className={cn(
                "w-6 h-6 rounded-full transition relative",
                color === c.id ? "ring-2 ring-white scale-110" : "ring-1 ring-white/10 hover:scale-105",
              )}
              style={{ background: c.swatch }}
              aria-label={c.id}
            >
              {color === c.id && (
                <Check size={12} className="absolute inset-0 m-auto text-white drop-shadow" />
              )}
            </button>
          ))}
        </div>
      </Field>

      {/* Category */}
      <Field label="Category" hint="Group akun untuk strategi (radar, utama, booster…)">
        <div className="flex items-center gap-1.5 flex-wrap">
          {allCategories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => {
                setCategory(c);
                setShowNewCategory(false);
              }}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[var(--radius-sm)] text-[11px] font-medium transition ring-1",
                category === c
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)] ring-[var(--color-accent)]/40"
                  : "bg-white/[0.03] text-[var(--color-fg-muted)] ring-[var(--color-border)] hover:ring-[var(--color-border-strong)] hover:text-[var(--color-fg)]",
              )}
            >
              <Tag size={10} />
              {c}
            </button>
          ))}
          {!showNewCategory ? (
            <button
              type="button"
              onClick={() => setShowNewCategory(true)}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-[var(--radius-sm)] text-[11px] text-[var(--color-fg-subtle)] hover:text-[var(--color-accent)] ring-1 ring-dashed ring-[var(--color-border)] hover:ring-[var(--color-accent)]/40 transition"
            >
              <Plus size={10} />
              new
            </button>
          ) : (
            <div className="inline-flex items-center gap-1">
              <input
                type="text"
                value={newCategory}
                onChange={(e) =>
                  setNewCategory(
                    e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""),
                  )
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    if (newCategory) {
                      setCategory(newCategory);
                      setShowNewCategory(false);
                      setNewCategory("");
                    }
                  }
                  if (e.key === "Escape") {
                    setShowNewCategory(false);
                    setNewCategory("");
                  }
                }}
                placeholder="e.g. hedge"
                autoFocus
                className="px-2 py-1 rounded-[var(--radius-sm)] bg-black/30 ring-1 ring-[var(--color-accent)]/40 focus:outline-none text-[11px] w-24"
              />
              <button
                type="button"
                onClick={() => {
                  if (newCategory) {
                    setCategory(newCategory);
                    setShowNewCategory(false);
                    setNewCategory("");
                  }
                }}
                className="text-[var(--color-accent)] text-[11px]"
              >
                <Check size={12} />
              </button>
            </div>
          )}
        </div>
        {category && !allCategories.includes(category) && (
          <div className="text-[10px] text-[var(--color-accent)] mt-1.5 flex items-center gap-1">
            <Plus size={9} /> Will create new category: <strong>{category}</strong>
          </div>
        )}
      </Field>

      {/* Access Key */}
      <Field
        label="Access Key"
        hint={isEdit ? "Kosongkan jika tidak ingin ganti" : undefined}
      >
        <input
          type="text"
          value={accessKey}
          onChange={(e) => setAccessKey(e.target.value)}
          placeholder="mx0v..."
          className={cn(inputCls, "font-mono text-[12px]")}
          spellCheck={false}
        />
      </Field>

      {/* Secret Key */}
      <Field label="Secret Key" hint={isEdit ? "Kosongkan jika tidak ingin ganti" : undefined}>
        <div className="relative">
          <input
            type={showSecret ? "text" : "password"}
            value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)}
            placeholder="••••••••"
            className={cn(inputCls, "font-mono text-[12px] pr-9")}
            spellCheck={false}
          />
          <button
            type="button"
            onClick={() => setShowSecret(!showSecret)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]"
          >
            {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </Field>

      {/* Test connection */}
      {(accessKey && secretKey) || isEdit ? (
        <div className="flex items-center gap-3">
          <Button
            type="button"
            tone="default"
            size="sm"
            onClick={() => {
              if (accessKey && secretKey) testMut.mutate();
            }}
            disabled={!accessKey || !secretKey || testMut.isPending}
          >
            {testMut.isPending ? (
              <>
                <Loader2 size={12} className="animate-spin" /> Testing
              </>
            ) : (
              <>
                <Plug size={12} /> Test Connection
              </>
            )}
          </Button>
          {testResult && (
            <div
              className={cn(
                "text-[11px] flex items-center gap-1.5",
                testResult.ok ? "text-[var(--color-success)]" : "text-[var(--color-danger)]",
              )}
            >
              {testResult.ok ? <Check size={12} /> : "✗"}
              {testResult.msg}
              {testResult.equity !== undefined && (
                <span className="text-[var(--color-fg-faint)]">
                  · equity {testResult.equity.toFixed(2)} USDT
                </span>
              )}
            </div>
          )}
        </div>
      ) : null}

      {submitErr && (
        <div className="text-[11px] text-[var(--color-danger)] bg-[var(--color-danger-soft)] ring-1 ring-[var(--color-danger)]/30 rounded-[var(--radius-sm)] px-2.5 py-1.5">
          {(submitErr as Error).message}
        </div>
      )}

      <div className="flex items-center justify-end gap-2 pt-1">
        {onCancel && (
          <Button type="button" tone="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" tone="accent" size="md" disabled={!canSubmit || submitting}>
          {submitting ? (
            <>
              <Loader2 size={12} className="animate-spin" />
              {isEdit ? "Saving..." : "Connecting..."}
            </>
          ) : isEdit ? (
            "Save Changes"
          ) : (
            "Connect & Save"
          )}
        </Button>
      </div>
    </form>
  );
}

const inputCls =
  "w-full px-2.5 py-1.5 rounded-[var(--radius-sm)] bg-black/30 ring-1 ring-[var(--color-border)] focus:ring-[var(--color-accent)] focus:outline-none text-sm text-[var(--color-fg)] placeholder:text-[var(--color-fg-faint)] transition";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <label className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          {label}
        </label>
        {hint && <span className="text-[10px] text-[var(--color-fg-faint)]">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
