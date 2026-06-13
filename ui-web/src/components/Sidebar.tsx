import {
  LayoutDashboard,
  Activity,
  Radar,
  TrendingUp,
  TrendingDown,
  Bot,
  Zap,
  Award,
  Shield,
  Wallet,
  History,
  Settings,
  ChevronsLeft,
  ChevronsRight,
  Sun,
  Moon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useUiStore } from "@/store/ui";
import { cn } from "@/lib/cn";
import { motion } from "motion/react";

type Page = "dashboard" | "terminal" | "signals" | "gainers" | "losers" | "bot" | "cascade" | "performance" | "risk" | "accounts" | "history";

interface NavItem {
  id: Page;
  label: string;
  eyebrow: string;
  icon: ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dasbor", eyebrow: "Ikhtisar", icon: <LayoutDashboard size={17} /> },
  { id: "terminal", label: "Live Terminal", eyebrow: "Neon · realtime", icon: <Activity size={17} /> },
  { id: "signals", label: "Sinyal", eyebrow: "Confluence", icon: <Radar size={17} /> },
  { id: "gainers", label: "Top Gainer 7H", eyebrow: "Naik 7 hari", icon: <TrendingUp size={17} /> },
  { id: "losers", label: "Top Loser 7H", eyebrow: "Turun 7 hari", icon: <TrendingDown size={17} /> },
  { id: "bot", label: "Bot Paper", eyebrow: "Simulasi $100", icon: <Bot size={17} /> },
  { id: "cascade", label: "Rantai DCA", eyebrow: "Eksekusi", icon: <Zap size={17} /> },
  { id: "performance", label: "Kinerja", eyebrow: "Win rate", icon: <Award size={17} /> },
  { id: "risk", label: "Risiko", eyebrow: "Exposure", icon: <Shield size={17} /> },
  { id: "accounts", label: "Akun", eyebrow: "Allocation", icon: <Wallet size={17} /> },
  { id: "history", label: "Riwayat", eyebrow: "Closed PnL", icon: <History size={17} /> },
];

export function Sidebar({ onOpenSettings }: { onOpenSettings: () => void }) {
  const activePage = useUiStore((s) => s.activePage);
  const setActivePage = useUiStore((s) => s.setActivePage);
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const theme = useUiStore((s) => s.theme);
  const toggleTheme = useUiStore((s) => s.toggleTheme);

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 72 : 236 }}
      transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
      className="fixed inset-y-0 left-0 z-40 hidden p-3 md:flex"
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-elev)]/92 shadow-[var(--shadow-card)] backdrop-blur-2xl">
        <div className={cn("flex h-16 shrink-0 items-center border-b border-[var(--color-border)]/60 px-3", collapsed ? "justify-center" : "gap-3")}>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent)] shadow-[var(--shadow-soft)]">
            <span className="text-[12px] font-black text-white">MX</span>
          </div>
          {!collapsed && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="min-w-0">
              <div className="truncate text-[14px] font-bold leading-tight text-[var(--color-fg)]">
                MEXC Futures
              </div>
              <div className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-fg-faint)]">
                Konsol Trading
              </div>
            </motion.div>
          )}
        </div>

        <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto overflow-x-hidden px-2 py-3">
          {!collapsed && (
            <div className="px-3 pb-1 text-[10px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
              Ruang Kerja
            </div>
          )}
          {NAV_ITEMS.map((item) => {
            const active = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActivePage(item.id)}
                className={cn(
                  "group relative flex h-11 w-full items-center rounded-[var(--radius-md)] text-left transition-all duration-150",
                  collapsed ? "justify-center px-0" : "gap-3 px-3",
                  active
                    ? "border border-[var(--color-border-strong)] bg-[var(--color-bg-elev-2)] text-[var(--color-fg)] shadow-[var(--shadow-soft)]"
                    : "text-[var(--color-fg-muted)] hover:bg-[var(--color-bg-elev-2)]/70 hover:text-[var(--color-fg)]",
                )}
                title={collapsed ? item.label : undefined}
              >
                <span
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] transition",
                    active
                      ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                      : "text-[var(--color-fg-subtle)] group-hover:text-[var(--color-fg)]",
                  )}
                >
                  {item.icon}
                </span>
                {!collapsed && (
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-semibold">{item.label}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-[var(--color-fg-faint)]">
                      {item.eyebrow}
                    </span>
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="shrink-0 space-y-1 border-t border-[var(--color-border)]/60 p-2">
          <SidebarAction
            collapsed={collapsed}
            icon={theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            label={theme === "dark" ? "Mode Siang" : "Mode Malam"}
            onClick={toggleTheme}
          />
          <SidebarAction
            collapsed={collapsed}
            icon={<Settings size={17} />}
            label="Pengaturan"
            onClick={onOpenSettings}
          />
          <SidebarAction
            collapsed={collapsed}
            icon={collapsed ? <ChevronsRight size={17} /> : <ChevronsLeft size={17} />}
            label="Ciutkan"
            muted
            onClick={toggleSidebar}
          />
        </div>
      </div>
    </motion.aside>
  );
}

export function MobileNav({ onOpenSettings }: { onOpenSettings: () => void }) {
  const activePage = useUiStore((s) => s.activePage);
  const setActivePage = useUiStore((s) => s.setActivePage);

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-[var(--color-border)] bg-[var(--color-bg-elev)]/94 px-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2 shadow-[var(--shadow-pop)] backdrop-blur-2xl md:hidden">
      <div className="mx-auto flex max-w-md gap-1 overflow-x-auto">
        {NAV_ITEMS.map((item) => {
          const active = activePage === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setActivePage(item.id)}
              className={cn(
                "flex h-12 min-w-[62px] flex-col items-center justify-center gap-1 rounded-[var(--radius-md)] px-1 transition",
                active
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                  : "text-[var(--color-fg-subtle)] hover:bg-[var(--color-bg-elev-2)] hover:text-[var(--color-fg)]",
              )}
            >
              {item.icon}
              <span className="max-w-full truncate text-[9px] font-semibold leading-none">
                {item.label}
              </span>
            </button>
          );
        })}
        <button
          type="button"
          onClick={onOpenSettings}
          className="flex h-12 min-w-[62px] flex-col items-center justify-center gap-1 rounded-[var(--radius-md)] px-1 text-[var(--color-fg-subtle)] transition hover:bg-[var(--color-bg-elev-2)] hover:text-[var(--color-fg)]"
        >
          <Settings size={17} />
          <span className="max-w-full truncate text-[9px] font-semibold leading-none">
            Setup
          </span>
        </button>
      </div>
    </div>
  );
}

function SidebarAction({
  collapsed,
  icon,
  label,
  muted,
  onClick,
}: {
  collapsed: boolean;
  icon: ReactNode;
  label: string;
  muted?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={collapsed ? label : undefined}
      className={cn(
        "flex h-10 w-full items-center rounded-[var(--radius-md)] transition-all duration-150 hover:bg-[var(--color-bg-elev-2)]",
        collapsed ? "justify-center px-0" : "gap-3 px-3",
        muted ? "text-[var(--color-fg-faint)] hover:text-[var(--color-fg-muted)]" : "text-[var(--color-fg-muted)] hover:text-[var(--color-fg)]",
      )}
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center">{icon}</span>
      {!collapsed && <span className="truncate text-[12px] font-medium">{label}</span>}
    </button>
  );
}
