import { useEffect, useRef } from "react";
import { toast } from "sonner";
import type { Signal } from "@/types/position";

/**
 * Plays a Web Audio API beep + toast notification when a new high-confluence
 * signal appears. Tracks last-seen score per symbol to avoid spam.
 */
const HIGH_SCORE_THRESHOLD = 70;

function playBeep(freq = 880, durMs = 180): void {
  try {
    const Ctx = (window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext) as
      typeof AudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durMs / 1000);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + durMs / 1000);
    setTimeout(() => ctx.close(), durMs + 100);
  } catch {
    // user hasn't interacted with page yet — silent fail
  }
}

export function useSignalAlert(signals: Signal[] | undefined, enabled = true) {
  const seenRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    if (!enabled || !signals) return;
    for (const s of signals) {
      if (s.direction === "NONE" || s.confluence_score < HIGH_SCORE_THRESHOLD) continue;
      const seenScore = seenRef.current.get(s.symbol);
      if (seenScore != null && s.confluence_score <= seenScore + 5) {
        // Already seen at same/higher level
        continue;
      }
      seenRef.current.set(s.symbol, s.confluence_score);
      // Skip first-load alerts (large batch). Only alert subsequent ones.
      // Detect first load by checking if map was empty before
      if (seenRef.current.size <= 1) continue;
      const dirIcon = s.direction === "LONG" ? "📈" : "📉";
      const isPremium = s.confluence_score >= 80;
      toast(
        `${dirIcon} ${s.symbol} ${s.direction} score ${s.confluence_score}` +
          (isPremium ? " 🔥 PREMIUM" : ""),
        {
          description: s.verdict,
          duration: 6000,
        },
      );
      playBeep(isPremium ? 1108 : 880, isPremium ? 280 : 180);
    }
  }, [signals, enabled]);
}
