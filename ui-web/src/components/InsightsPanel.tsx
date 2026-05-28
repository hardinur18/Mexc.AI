import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Radar, Shield, Wallet, History, Zap, Award } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import { SignalsPanelInner } from "@/components/SignalsPanel";
import { ClosedPositionsPanelInner } from "@/components/ClosedPositionsPanel";
import { RiskDashboardInner } from "@/components/RiskDashboard";
import { AccountBreakdownInner } from "@/components/AccountBreakdown";
import { PortfolioHeatCard } from "@/components/analytics/PortfolioHeatCard";
import { CascadePanel } from "@/components/analytics/CascadePanel";
import { PerformanceDashboard } from "@/components/analytics/PerformanceDashboard";
import { PatternWinrateCard } from "@/components/analytics/PatternWinrateCard";
import { NarrativeHud } from "@/components/analytics/NarrativeHud";
import { useSignals, useClosedPositions, useCascadeActive } from "@/hooks/useSnapshot";
import type { Snapshot } from "@/types/position";
import { cn } from "@/lib/cn";

interface InsightsPanelProps {
  snapshot: Snapshot;
}

export function InsightsPanel({ snapshot }: InsightsPanelProps) {
  const { data: signals } = useSignals(45);
  const { data: closed } = useClosedPositions(50);
  const { data: cascadeData } = useCascadeActive();
  const [activeTab, setActiveTab] = useState<string>("signals");

  const signalCount = signals?.signal_count ?? 0;
  const closedCount = closed?.count ?? 0;
  const accountCount = snapshot.accounts.length;
  const cascadeActive = cascadeData?.items.filter(
    (c) => !["closed_win", "closed_loss", "closed_be", "cancelled", "error"].includes(c.state),
  ).length ?? 0;

  // Compute risk violation count (lightweight)
  const violationCount = (() => {
    if (!snapshot.positions.length) return 0;
    const equity = snapshot.account.equity || 1;
    const totalNotional = snapshot.totals.notional;
    let count = 0;
    // Effective lev > 10
    if (totalNotional / equity > 10) count++;
    // Any position > 5% equity
    for (const p of snapshot.positions) {
      if ((p.margin / equity) * 100 > 5) count++;
    }
    // Buffer < 10%
    for (const p of snapshot.positions) {
      if (p.buffer_pct != null && p.buffer_pct < 10) count++;
    }
    return count;
  })();

  // Auto-switch to risk tab if violation appears (priority safety)
  useEffect(() => {
    if (violationCount > 0 && activeTab !== "risk") {
      // Don't override user choice if they explicitly clicked something
      // Only auto-switch on initial mount or significant changes
    }
  }, [violationCount, activeTab]);

  return (
    <div className="glass rounded-[var(--radius-lg)] mb-5 overflow-hidden">
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="border-b border-[var(--color-border)]/40 px-4 py-2.5 flex items-center justify-between gap-3 flex-wrap">
          <TabsList>
            <TabsTrigger value="signals">
              <Radar size={11} className="mr-1.5" /> Sinyal
              {signalCount > 0 && <Badge tone="accent" count={signalCount} />}
            </TabsTrigger>
            <TabsTrigger value="cascade">
              <Zap size={11} className="mr-1.5" /> Cascade
              {cascadeActive > 0 && <Badge tone="accent" count={cascadeActive} />}
            </TabsTrigger>
            <TabsTrigger value="performance">
              <Award size={11} className="mr-1.5" /> Performance
            </TabsTrigger>
            <TabsTrigger value="risk">
              <Shield size={11} className="mr-1.5" /> Risiko
              {violationCount > 0 && <Badge tone="danger" count={violationCount} />}
            </TabsTrigger>
            <TabsTrigger value="accounts">
              <Wallet size={11} className="mr-1.5" /> Akun
              {accountCount > 0 && <Badge tone="neutral" count={accountCount} />}
            </TabsTrigger>
            <TabsTrigger value="history">
              <History size={11} className="mr-1.5" /> Riwayat
              {closedCount > 0 && <Badge tone="neutral" count={closedCount} />}
            </TabsTrigger>
          </TabsList>
          <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)]">
            insights · live monitoring
          </div>
        </div>

        <TabsContent value="signals" className="mt-0">
          <SignalsPanelInner />
        </TabsContent>
        <TabsContent value="cascade" className="mt-0">
          <div className="p-3 space-y-3">
            <CascadePanel />
            <NarrativeHud />
          </div>
        </TabsContent>
        <TabsContent value="performance" className="mt-0">
          <div className="p-3 space-y-3">
            <PerformanceDashboard />
            <PatternWinrateCard />
          </div>
        </TabsContent>
        <TabsContent value="risk" className="mt-0">
          <div className="p-3 space-y-3">
            <PortfolioHeatCard />
            {snapshot.positions.length > 0 ? (
              <RiskDashboardInner snapshot={snapshot} />
            ) : (
              <EmptyTab text="Belum ada posisi aktif — risiko 0" />
            )}
          </div>
        </TabsContent>
        <TabsContent value="accounts" className="mt-0">
          {snapshot.accounts.length > 0 ? (
            <AccountBreakdownInner accounts={snapshot.accounts} />
          ) : (
            <EmptyTab text="Belum ada akun terkonfigurasi" />
          )}
        </TabsContent>
        <TabsContent value="history" className="mt-0">
          <ClosedPositionsPanelInner />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Badge({
  tone,
  count,
}: {
  tone: "accent" | "danger" | "neutral";
  count: number;
}) {
  const style =
    tone === "accent"
      ? "bg-[var(--color-success-soft)] text-[var(--color-success)] ring-[var(--color-success)]/30"
      : tone === "danger"
        ? "bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-[var(--color-danger)]/40 [animation:pulse-glow_2s_ease-in-out_infinite]"
        : "bg-white/5 text-[var(--color-fg-muted)] ring-[var(--color-border)]";
  return (
    <motion.span
      key={count}
      initial={{ scale: 0.7, opacity: 0.5 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "ml-1.5 inline-flex items-center justify-center min-w-[14px] h-[14px] px-1 rounded-full text-[9px] font-bold ring-1",
        style,
      )}
    >
      {count}
    </motion.span>
  );
}

function EmptyTab({ text }: { text: string }) {
  return (
    <div className="px-4 py-8 text-center text-[11px] text-[var(--color-fg-faint)]">
      {text}
    </div>
  );
}
