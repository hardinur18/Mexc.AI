import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Pencil, Loader2, Tags, Check, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useAccounts, useCategories } from "@/hooks/useSnapshot";
import { renameCategory } from "@/lib/api";

export function CategoriesManager() {
  const { data: cats, isLoading: catsLoading } = useCategories();
  const { data: accountsResp } = useAccounts();
  const qc = useQueryClient();
  const [editingCat, setEditingCat] = useState<string | null>(null);
  const [renameTo, setRenameTo] = useState("");

  const renameMu = useMutation({
    mutationFn: ({ old_name, new_name }: { old_name: string; new_name: string }) =>
      renameCategory(old_name, new_name),
    onSuccess: (res) => {
      toast.success("Category renamed", {
        description: `${res.updated ?? 0} account(s) updated`,
      });
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["categories"] });
      qc.invalidateQueries({ queryKey: ["snapshot"] });
      setEditingCat(null);
      setRenameTo("");
    },
    onError: (e: Error) => toast.error("Rename failed", { description: e.message }),
  });

  const used = cats?.used ?? [];
  const suggestions = cats?.categories ?? [];
  const accountCounts: Record<string, number> = {};
  for (const a of accountsResp?.accounts ?? []) {
    const c = a.category ?? "uncategorized";
    accountCounts[c] = (accountCounts[c] ?? 0) + 1;
  }

  if (catsLoading) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-[var(--color-fg-subtle)] py-6 justify-center">
        <Loader2 size={12} className="animate-spin" /> Loading categories...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="text-[11px] text-[var(--color-fg-subtle)] leading-relaxed">
        Kategori akun grouping di dropdown picker & breakdown. Rename di sini akan
        propagate ke semua akun yang pakai kategori tersebut.
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2 flex items-center gap-1.5">
          <Tags size={11} /> Active Categories ({used.length})
        </div>

        {used.length === 0 ? (
          <div className="text-[11px] text-[var(--color-fg-faint)] italic py-3">
            Belum ada kategori aktif. Set kategori di Add/Edit account form.
          </div>
        ) : (
          <div className="space-y-1.5">
            {used.map((cat) => {
              const count = accountCounts[cat] ?? 0;
              const isEditing = editingCat === cat;
              return (
                <div
                  key={cat}
                  className="flex items-center gap-2 px-3 py-2 rounded-[var(--radius-md)] bg-black/20 ring-1 ring-[var(--color-border)] hover:ring-[var(--color-border-strong)] transition"
                >
                  <div className="flex-1">
                    {isEditing ? (
                      <input
                        type="text"
                        value={renameTo}
                        onChange={(e) => setRenameTo(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && renameTo.trim()) {
                            renameMu.mutate({
                              old_name: cat,
                              new_name: renameTo.trim(),
                            });
                          } else if (e.key === "Escape") {
                            setEditingCat(null);
                          }
                        }}
                        autoFocus
                        placeholder="new category name"
                        className="w-full bg-black/30 ring-1 ring-[var(--color-accent)]/40 rounded-[var(--radius-sm)] px-2 py-1 text-[12px] font-mono text-[var(--color-fg)] outline-none focus:ring-[var(--color-accent)]"
                      />
                    ) : (
                      <div className="flex items-center gap-2">
                        <span className="text-[12px] font-mono font-semibold text-[var(--color-fg)]">
                          {cat}
                        </span>
                        <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] bg-white/5 px-1.5 py-0.5 rounded ring-1 ring-[var(--color-border)]">
                          {count} account{count !== 1 ? "s" : ""}
                        </span>
                      </div>
                    )}
                  </div>

                  {isEditing ? (
                    <>
                      <Button
                        tone="accent"
                        size="sm"
                        onClick={() =>
                          renameMu.mutate({
                            old_name: cat,
                            new_name: renameTo.trim(),
                          })
                        }
                        disabled={
                          !renameTo.trim() ||
                          renameTo.trim() === cat ||
                          renameMu.isPending
                        }
                      >
                        {renameMu.isPending ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <>
                            <Check size={12} /> Save
                          </>
                        )}
                      </Button>
                      <Button
                        tone="ghost"
                        size="sm"
                        onClick={() => {
                          setEditingCat(null);
                          setRenameTo("");
                        }}
                      >
                        <X size={12} />
                      </Button>
                    </>
                  ) : (
                    <Button
                      tone="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingCat(cat);
                        setRenameTo(cat);
                      }}
                    >
                      <Pencil size={11} /> Rename
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">
          Suggested Categories
        </div>
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <span
              key={s}
              className="text-[11px] font-mono px-2 py-1 rounded-[var(--radius-sm)] bg-white/5 ring-1 ring-[var(--color-border)] text-[var(--color-fg-muted)]"
            >
              {s}
            </span>
          ))}
        </div>
        <div className="text-[10px] text-[var(--color-fg-faint)] mt-2 leading-relaxed">
          Suggestions ini auto-complete di Add/Edit form. Bikin kategori baru: ketik nama
          baru di form (e.g., "radar", "utama_1", "utama_2", "booster", "scalp", "hedge").
        </div>
      </div>
    </div>
  );
}
