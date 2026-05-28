import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Trash2, Radar, Layers, Rocket, Save, Loader2 } from "lucide-react";
import { useAccounts } from "@/hooks/useSnapshot";
import { updateAccount } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

type Role = "radar" | "main" | "booster" | "passive";

interface TpLevel {
  pct_margin: number;
  close_pct_position: number;
  reason?: string;
}

interface SlPlus {
  enabled: boolean;
  activation_pct_margin: number;
  trail_distance_pct_margin: number;
  ratchet_step_pct_margin: number;
  min_lock_pct_margin: number;
}

interface StrategyConfig {
  role: Role;
  tier?: number;
  follow_radar?: string;
  trigger_threshold_pct_margin?: number;
  entry_size_pct_equity?: number;
  leverage?: number;
  take_profit_ladder: TpLevel[];
  sl_plus: SlPlus;
  allowed_symbols?: string[];
  min_confluence_score?: number;
}

const DEFAULT_STRATEGY: StrategyConfig = {
  role: "passive",
  take_profit_ladder: [
    { pct_margin: 500, close_pct_position: 33, reason: "Secure cost + small gain" },
    { pct_margin: 1500, close_pct_position: 33, reason: "RR 1:5 main target" },
    { pct_margin: 3000, close_pct_position: 34, reason: "Moonshot — RR 1:10+" },
  ],
  sl_plus: {
    enabled: false,
    activation_pct_margin: 100,
    trail_distance_pct_margin: 50,
    ratchet_step_pct_margin: 25,
    min_lock_pct_margin: 25,
  },
};

interface StrategyEditorProps {
  onClose?: () => void;
}

export function StrategyEditor({ onClose: _onClose }: StrategyEditorProps) {
  const qc = useQueryClient();
  const { data: accountsData } = useAccounts();
  const accounts = accountsData?.accounts ?? [];
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(
    accounts[0]?.id ?? null,
  );
  const [strategy, setStrategy] = useState<StrategyConfig>(DEFAULT_STRATEGY);

  const radarAccounts = accounts.filter((a) => a.category === "radar");

  const saveMut = useMutation({
    mutationFn: () =>
      updateAccount(selectedAccountId!, { strategy: strategy as unknown as Record<string, unknown> }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      toast.success("Strategy saved", {
        description: `Updated config for ${accounts.find((a) => a.id === selectedAccountId)?.name}`,
      });
    },
    onError: (err: Error) => toast.error("Save failed", { description: err.message }),
  });

  if (accounts.length === 0) {
    return (
      <div className="text-[11px] text-[var(--color-fg-subtle)] py-6 text-center">
        Tidak ada akun. Add account dulu di tab Accounts.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-[10px] text-[var(--color-fg-faint)] bg-[var(--color-warning-soft)] ring-1 ring-[var(--color-warning)]/30 rounded-[var(--radius-sm)] px-3 py-2 leading-snug">
        ⚠️ <strong>Paper mode.</strong> Strategy disimpan tapi <strong>tidak eksekusi otomatis</strong>.
        Live execution butuh validasi backtest + paper monitoring dulu.
      </div>

      {/* Account picker */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-1.5 font-semibold">
          Pilih akun
        </div>
        <div className="flex flex-wrap gap-1.5">
          {accounts.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setSelectedAccountId(a.id)}
              className={cn(
                "text-[11px] px-2.5 py-1 rounded-[var(--radius-sm)] font-medium transition ring-1",
                selectedAccountId === a.id
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)] ring-[var(--color-accent)]/40"
                  : "bg-[var(--color-surface)] text-[var(--color-fg-muted)] ring-[var(--color-border)] hover:text-[var(--color-fg)]",
              )}
            >
              {a.name}
              <span className="text-[9px] text-[var(--color-fg-faint)] ml-1.5 uppercase">
                {a.category}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Role */}
      <Field label="Role / Tier" hint="Apa peran akun ini di pyramid?">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
          {(["radar", "main", "booster", "passive"] as Role[]).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setStrategy({ ...strategy, role: r })}
              className={cn(
                "text-[11px] px-2 py-1.5 rounded-[var(--radius-sm)] font-medium transition ring-1 flex items-center justify-center gap-1.5",
                strategy.role === r
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)] ring-[var(--color-accent)]/40"
                  : "bg-[var(--color-surface)] text-[var(--color-fg-muted)] ring-[var(--color-border)]",
              )}
            >
              {r === "radar" && <Radar size={11} />}
              {r === "main" && <Layers size={11} />}
              {r === "booster" && <Rocket size={11} />}
              {r}
            </button>
          ))}
        </div>
      </Field>

      {strategy.role === "main" || strategy.role === "booster" ? (
        <>
          <Field label="Follow Radar" hint="Akun radar yang di-monitor untuk trigger">
            <select
              value={strategy.follow_radar ?? ""}
              onChange={(e) => setStrategy({ ...strategy, follow_radar: e.target.value })}
              className="w-full text-[11px] px-2 py-1.5 rounded-[var(--radius-sm)] bg-[var(--color-bg-elev-2)] ring-1 ring-[var(--color-border)] focus:ring-[var(--color-accent)] focus:outline-none text-[var(--color-fg)]"
            >
              <option value="">— pilih radar —</option>
              {radarAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.id})
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Trigger threshold"
            hint="Entry saat radar PnL ≤ X% margin (negatif = drawdown)"
          >
            <NumberInput
              value={strategy.trigger_threshold_pct_margin ?? -500}
              onChange={(v) => setStrategy({ ...strategy, trigger_threshold_pct_margin: v })}
              suffix="% margin"
              step={100}
            />
          </Field>

          <Field label="Entry size" hint="Persen equity per entry tier ini">
            <NumberInput
              value={strategy.entry_size_pct_equity ?? 5}
              onChange={(v) => setStrategy({ ...strategy, entry_size_pct_equity: v })}
              suffix="% equity"
              step={1}
              min={0.5}
              max={20}
            />
          </Field>

          <Field label="Leverage">
            <NumberInput
              value={strategy.leverage ?? 50}
              onChange={(v) => setStrategy({ ...strategy, leverage: v })}
              suffix="x"
              step={5}
              min={1}
              max={125}
            />
          </Field>
        </>
      ) : null}

      {strategy.role === "radar" && (
        <Field label="Min confluence score" hint="Entry hanya kalau score ≥ ini (rec. 75+)">
          <NumberInput
            value={strategy.min_confluence_score ?? 75}
            onChange={(v) => setStrategy({ ...strategy, min_confluence_score: v })}
            min={0}
            max={100}
            step={5}
          />
        </Field>
      )}

      {/* TP Ladder */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
            Take Profit Ladder
          </span>
          <Button
            type="button"
            tone="ghost"
            size="sm"
            onClick={() =>
              setStrategy({
                ...strategy,
                take_profit_ladder: [
                  ...strategy.take_profit_ladder,
                  { pct_margin: 1000, close_pct_position: 25, reason: "" },
                ],
              })
            }
          >
            <Plus size={11} /> Add level
          </Button>
        </div>
        <div className="space-y-2">
          {strategy.take_profit_ladder.map((tp, i) => (
            <div
              key={i}
              className="grid grid-cols-[28px_1fr_1fr_2fr_28px] gap-2 items-center text-[11px]"
            >
              <span className="text-[10px] font-bold text-[var(--color-accent)] text-center">
                TP{i + 1}
              </span>
              <NumberInput
                value={tp.pct_margin}
                onChange={(v) => {
                  const next = [...strategy.take_profit_ladder];
                  next[i] = { ...next[i], pct_margin: v };
                  setStrategy({ ...strategy, take_profit_ladder: next });
                }}
                suffix="% margin"
                step={100}
              />
              <NumberInput
                value={tp.close_pct_position}
                onChange={(v) => {
                  const next = [...strategy.take_profit_ladder];
                  next[i] = { ...next[i], close_pct_position: v };
                  setStrategy({ ...strategy, take_profit_ladder: next });
                }}
                suffix="% close"
                step={5}
                min={0}
                max={100}
              />
              <input
                type="text"
                value={tp.reason ?? ""}
                onChange={(e) => {
                  const next = [...strategy.take_profit_ladder];
                  next[i] = { ...next[i], reason: e.target.value };
                  setStrategy({ ...strategy, take_profit_ladder: next });
                }}
                placeholder="reason..."
                className="px-2 py-1 rounded-[var(--radius-sm)] bg-[var(--color-bg-elev-2)] ring-1 ring-[var(--color-border)] focus:ring-[var(--color-accent)] focus:outline-none text-[10px]"
              />
              <button
                type="button"
                onClick={() => {
                  const next = strategy.take_profit_ladder.filter((_, j) => j !== i);
                  setStrategy({ ...strategy, take_profit_ladder: next });
                }}
                className="text-[var(--color-fg-subtle)] hover:text-[var(--color-danger)]"
                aria-label="Remove TP level"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* SL+ */}
      <div className="rounded-[var(--radius-md)] bg-[var(--color-bg-elev)] ring-1 ring-[var(--color-border)] px-3 py-2.5">
        <label className="flex items-center justify-between mb-2 cursor-pointer">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
            SL+ (Trailing Profit Lock)
          </span>
          <input
            type="checkbox"
            checked={strategy.sl_plus.enabled}
            onChange={(e) =>
              setStrategy({
                ...strategy,
                sl_plus: { ...strategy.sl_plus, enabled: e.target.checked },
              })
            }
            className="accent-[var(--color-accent)]"
          />
        </label>
        {strategy.sl_plus.enabled && (
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <Field label="Activate at" hint="PnL ≥ ini → SL+ aktif" tight>
              <NumberInput
                value={strategy.sl_plus.activation_pct_margin}
                onChange={(v) =>
                  setStrategy({
                    ...strategy,
                    sl_plus: { ...strategy.sl_plus, activation_pct_margin: v },
                  })
                }
                suffix="% margin"
                step={25}
              />
            </Field>
            <Field label="Trail distance" hint="jaga X% margin di belakang peak" tight>
              <NumberInput
                value={strategy.sl_plus.trail_distance_pct_margin}
                onChange={(v) =>
                  setStrategy({
                    ...strategy,
                    sl_plus: { ...strategy.sl_plus, trail_distance_pct_margin: v },
                  })
                }
                suffix="% margin"
                step={25}
              />
            </Field>
            <Field label="Ratchet step" hint="Move SL+ tiap +X% margin" tight>
              <NumberInput
                value={strategy.sl_plus.ratchet_step_pct_margin}
                onChange={(v) =>
                  setStrategy({
                    ...strategy,
                    sl_plus: { ...strategy.sl_plus, ratchet_step_pct_margin: v },
                  })
                }
                suffix="% margin"
                step={5}
              />
            </Field>
            <Field label="Min lock" hint="Initial guaranteed profit" tight>
              <NumberInput
                value={strategy.sl_plus.min_lock_pct_margin}
                onChange={(v) =>
                  setStrategy({
                    ...strategy,
                    sl_plus: { ...strategy.sl_plus, min_lock_pct_margin: v },
                  })
                }
                suffix="% margin"
                step={5}
              />
            </Field>
          </div>
        )}
      </div>

      <div className="flex items-center justify-end gap-2 pt-2">
        <Button
          type="button"
          tone="accent"
          size="md"
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending || !selectedAccountId}
        >
          {saveMut.isPending ? (
            <>
              <Loader2 size={12} className="animate-spin" /> Saving
            </>
          ) : (
            <>
              <Save size={12} /> Save Strategy
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
  tight,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  tight?: boolean;
}) {
  return (
    <div className={tight ? "space-y-0.5" : "space-y-1"}>
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

function NumberInput({
  value,
  onChange,
  suffix,
  step = 1,
  min,
  max,
}: {
  value: number;
  onChange: (v: number) => void;
  suffix?: string;
  step?: number;
  min?: number;
  max?: number;
}) {
  return (
    <div className="flex items-center gap-1 px-2 py-1 rounded-[var(--radius-sm)] bg-[var(--color-bg-elev-2)] ring-1 ring-[var(--color-border)] focus-within:ring-[var(--color-accent)]">
      <input
        type="number"
        value={value}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
        step={step}
        min={min}
        max={max}
        className="flex-1 min-w-0 bg-transparent text-[11px] focus:outline-none text-[var(--color-fg)] num"
      />
      {suffix && (
        <span className="text-[9px] text-[var(--color-fg-faint)] uppercase tracking-wider shrink-0">
          {suffix}
        </span>
      )}
    </div>
  );
}
