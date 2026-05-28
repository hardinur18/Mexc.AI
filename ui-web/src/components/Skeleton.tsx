import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative overflow-hidden bg-white/[0.04] rounded-[var(--radius-sm)]",
        className,
      )}
    >
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.06) 50%, transparent 100%)",
          backgroundSize: "200% 100%",
          animation: "shimmer 1.4s linear infinite",
        }}
      />
    </div>
  );
}

/** Skeleton placeholder layout matching stat cards + table */
export function DashboardSkeleton() {
  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="glass rounded-[var(--radius-xl)] p-3 space-y-2"
          >
            <Skeleton className="h-2.5 w-14" />
            <Skeleton className="h-6 w-20" />
            <Skeleton className="h-2 w-10" />
          </div>
        ))}
      </div>

      <div className="glass rounded-[var(--radius-xl)] overflow-hidden">
        <div className="px-3 py-3 border-b border-[var(--color-border)]">
          <Skeleton className="h-3 w-32" />
        </div>
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-3 px-3 py-3 border-b border-[var(--color-border)] last:border-b-0"
          >
            <Skeleton className="w-7 h-7 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-2 w-32" />
            </div>
            <Skeleton className="h-3 w-12" />
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-3 w-14" />
          </div>
        ))}
      </div>
    </div>
  );
}
