import { lazy, Suspense, useState } from "react";
import { motion } from "motion/react";
import { Toaster } from "sonner";
import { Header } from "@/components/Header";
import { StatCards } from "@/components/StatCards";
import { InsightsPanel } from "@/components/InsightsPanel";
import { PositionTable } from "@/components/positions/PositionTable";
import { DashboardSkeleton } from "@/components/Skeleton";
import { TopProgressBar } from "@/components/ui/TopProgressBar";
import { MacroHud } from "@/components/analytics/MacroHud";
import { useSnapshot, useSignals } from "@/hooks/useSnapshot";
import { useHotkeys } from "@/hooks/useHotkeys";
import { usePositionClosureDetector } from "@/hooks/usePositionClosureDetector";
import { useSignalAlert } from "@/hooks/useSignalAlert";
import { useUiStore } from "@/store/ui";

// Lazy-load rarely-used heavy components
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
  const fullscreen = useUiStore((s) => s.fullscreen);

  return (
    <>
      <TopProgressBar active={isFetching} />
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: "var(--color-bg-elev)",
            border: "1px solid var(--color-border)",
            color: "var(--color-fg)",
            fontSize: "12px",
          },
        }}
      />

      <div className={fullscreen ? "px-6" : "px-6 max-w-[1500px] mx-auto"}>
        <div className="sticky top-0 z-30 -mx-6 px-6 py-3.5 bg-[var(--color-bg)]/85 backdrop-blur-md backdrop-saturate-150 border-b border-[var(--color-border)]/40">
          <Header
            snapshot={data}
            isError={isError}
            isFetching={isFetching}
            onOpenCommandPalette={() => setCmdOpen(true)}
          />
        </div>

        <div className="py-5">
        {isLoading && !data ? (
          <DashboardSkeleton />
        ) : data ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
          >
            <div className="mb-3 flex justify-end">
              <MacroHud />
            </div>
            <StatCards
              account={data.account}
              totals={data.totals}
              positions={data.positions}
              ts={data.ts}
            />
            <InsightsPanel snapshot={data} />
            <PositionTable positions={data.positions} />
          </motion.div>
        ) : (
          <div className="glass rounded-[var(--radius-xl)] p-10 text-center">
            <p className="text-[var(--color-fg-subtle)]">
              {isError ? "Gagal connect ke /api/snapshot" : "Loading..."}
            </p>
          </div>
        )}
        </div>
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
