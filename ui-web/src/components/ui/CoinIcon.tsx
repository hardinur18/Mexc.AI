import { useState } from "react";
import { cn } from "@/lib/cn";

interface CoinIconProps {
  coin: string;
  iconUrl?: string | null;
  size?: number;
  className?: string;
}

/**
 * Coin logo with graceful fallback to gradient initials.
 * Tries MEXC's baseCoinIconUrl first; on error falls back to text avatar.
 */
export function CoinIcon({ coin, iconUrl, size = 32, className }: CoinIconProps) {
  const [failed, setFailed] = useState(false);
  const showImage = !!iconUrl && !failed;

  return (
    <div
      className={cn(
        "relative shrink-0 rounded-full overflow-hidden ring-1 ring-white/10 bg-gradient-to-br from-[var(--color-accent-soft)] to-[var(--color-info)]/30 flex items-center justify-center",
        className,
      )}
      style={{ width: size, height: size }}
    >
      {showImage ? (
        <img
          src={iconUrl ?? undefined}
          alt={coin}
          width={size}
          height={size}
          loading="lazy"
          referrerPolicy="no-referrer"
          decoding="async"
          onError={() => setFailed(true)}
          className="w-full h-full object-cover"
        />
      ) : (
        <span
          className="font-bold text-white/90 select-none"
          style={{ fontSize: Math.max(9, size * 0.3) }}
        >
          {coin.slice(0, 3)}
        </span>
      )}
    </div>
  );
}
