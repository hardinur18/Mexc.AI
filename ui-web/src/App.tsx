import { lazy, Suspense, useState, type CSSProperties } from "react";
import { motion } from "motion/react";
import { Toaster } from "sonner";
import { MobileNav, Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { StatCards } from "@/components/StatCards";
import { PositionTable } from "@/components/positions/PositionTable";
import { DashboardSkeleton } from "@/components/Skeleton";
import { TopProgressBar } from "@/components/ui/TopProgressBar";
import { MacroHud } from "@/components/analytics/MacroHud";
import { SignalsPanelInner } from "@/components/SignalsPanel";
import { ClosedPositionsPanelInner } from "@/components/ClosedPositionsPanel";
import { RiskDashboardInner } from "@/components/RiskDashboard";
import { AccountBreakdownInner } from "@/components/AccountBreakdown";
import { PortfolioHeatCard } from "@/components/analytics/PortfolioHeatCard";
import { CascadePanel } from "@/components/analytics/CascadePanel";
import { PerformanceDashboard } from "@/components/analytics/PerformanceDashboard";
import { PatternWinrateCard } from "@/components/analytics/PatternWinrateCard";
import { NarrativeHud } from "@/components/analytics/NarrativeHud";
import { useSnapshot, useSignals } from "@/hooks/useSnapshot";
import { useHotkeys } from "@/hooks/useHotkeys";
import { usePositionClosureDetector } from "@/hooks/usePositionClosureDetector";
import { useSignalAlert } from "@/hooks/useSignalAlert";
import { useUiStore } from "@/store/ui";

const CommandPalette = lazy(() =>
  import("@/components/CommandPalette").then((m) => ({ default: m.CommandPalette })),
);
const SettingsDialog = lazy(() =>
  import("@/components/settings/SettingsDialog").then((m) => ({
    default: m.SettingsDialog,
  })),
);

export default function App() {
  const { data, isError, isFetching, isLoading } = useSnapshot();
  const { data: signals } = useSignals(45);
  useHotkeys({ positions: data?.positions ?? [] });
  usePositionClosureDetector(data?.positions);
  useSignalAlert(signals?.signals, true);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const theme = useUiStore((s) => s.theme);
  const activePage = useUiStore((s) => s.activePage);
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);

  const sidebarWidth = sidebarCollapsed ? 72 : 236;

  return (
    <>
      <TopProgressBar active={isFetching} />
      <Toaster
        position="bottom-right"
        theme={theme}
        toastOptions={{
          style: {
            background: "var(--color-bg-elev)",
            border: "1px solid var(--color-border)",
            color: "var(--color-fg)",
            fontSize: "12px",
          },
        }}
      />

      {/* Sidebar */}
      <Sidebar onOpenSettings={() => setSettingsOpen(true)} />
      <MobileNav onOpenSettings={() => setSettingsOpen(true)} />

      {/* Main area */}
      <div
        className="min-h-screen transition-[padding] duration-200 ease-[cubic-bezier(0.25,1,0.5,1)] md:pl-[var(--sidebar-w)]"
        style={{ "--sidebar-w": `${sidebarWidth}px` } as CSSProperties}
      >
        {/* Topbar */}
        <div className="sticky top-0 z-30">
          <Topbar
            snapshot={data}
            isError={isError}
            isFetching={isFetching}
            onOpenCommandPalette={() => setCmdOpen(true)}
            onOpenSettings={() => setSettingsOpen(true)}
          />
        </div>

        {/* Page content */}
        <main className="app-page">
          {isLoading && !data ? (
            <DashboardSkeleton />
          ) : data ? (
            <motion.div
              key={activePage}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
            >
              <PageContent
                page={activePage}
                snapshot={data}
              />
            </motion.div>
          ) : (
            <div className="glass rounded-xl p-10 text-center">
              <p className="text-[var(--color-fg-subtle)]">
                {isError ? "Gagal connect ke /api/snapshot" : "Loading..."}
              </p>
            </div>
          )}
        </main>
      </div>

      <Suspense fallback={null}>
        {cmdOpen && (
          <CommandPalette
            open={cmdOpen}
            onOpenChange={setCmdOpen}
            positions={data?.positions ?? []}
            onOpenSettings={() => {
              setCmdOpen(false);
              setSettingsOpen(true);
            }}
          />
        )}
        {settingsOpen && (
          <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
        )}
      </Suspense>
    </>
  );
}

/* ─── Page router ─── */
import type { Snapshot } from "@/types/position";

function PageContent({
  page,
  snapshot,
}: {
  page: string;
  snapshot: Snapshot;
}) {
  switch (page) {
    case "dashboard":
      return <DashboardPage snapshot={snapshot} />;
    case "signals":
      return (
        <div className="space-y-4">
          <div className="page-panel page-titlebar">
            <PageHeader title="Sinyal" subtitle="Live signal monitoring & confluence scoring" />
          </div>
          <div className="page-panel overflow-hidden">
            <SignalsPanelInner />
          </div>
        </div>
      );
    case "cascade":
      return (
        <div className="space-y-4">
          <div className="page-panel page-titlebar">
            <PageHeader title="Cascade" subtitle="Multi-tier DCA pyramid orchestration" />
          </div>
          <CascadePanel />
          <NarrativeHud />
        </div>
      );
    case "performance":
      return (
        <div className="space-y-4">
          <div className="page-panel page-titlebar">
            <PageHeader title="Performance" subtitle="Win rate, profit factor & equity curve" />
          </div>
          <PerformanceDashboard />
          <PatternWinrateCard />
        </div>
      );
    case "risk":
      return (
        <div className="space-y-4">
          <div className="page-panel page-titlebar">
            <PageHeader title="Risiko" subtitle="Portfolio heat, exposure & circuit breaker" />
          </div>
          <PortfolioHeatCard />
          {snapshot.positions.length > 0 ? (
            <RiskDashboardInner snapshot={snapshot} />
          ) : (
            <EmptyState text="Belum ada posisi aktif — risiko 0" />
          )}
        </div>
      );
    case "accounts":
      return (
        <div className="space-y-4">
          <div className="page-panel page-titlebar">
            <PageHeader title="Akun" subtitle="Per-account allocation & equity breakdown" />
          </div>
          {snapshot.accounts.length > 0 ? (
            <AccountBreakdownInner accounts={snapshot.accounts} />
          ) : (
            <EmptyState text="Belum ada akun terkonfigurasi" />
          )}
        </div>
      );
    case "history":
      return (
        <div className="space-y-4">
          <div className="page-panel page-titlebar">
            <PageHeader title="Riwayat" subtitle="Closed positions & historical P&L" />
          </div>
          <div className="page-panel overflow-hidden">
            <ClosedPositionsPanelInner />
          </div>
        </div>
      );
    default:
      return <DashboardPage snapshot={snapshot} />;
  }
}

function DashboardPage({ snapshot }: { snapshot: Snapshot }) {
  return (
    <div className="space-y-4">
      <div className="page-panel page-titlebar flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <PageHeader title="Dashboard" subtitle="Real-time positions & market overview" />
        <MacroHud />
      </div>
      <StatCards
        account={snapshot.account}
        totals={snapshot.totals}
        positions={snapshot.positions}
        ts={snapshot.ts}
      />
      <PositionTable positions={snapshot.positions} />
    </div>
  );
}

function PageHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="min-w-0">
      <h2 className="page-title">{title}</h2>
      <p className="page-description">{subtitle}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="glass rounded-xl p-10 text-center">
      <p className="text-[13px] text-[var(--color-fg-faint)]">{text}</p>
    </div>
  );
}
