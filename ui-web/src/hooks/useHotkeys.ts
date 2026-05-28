import { useEffect } from "react";
import { useUiStore } from "@/store/ui";
import type { Position } from "@/types/position";

interface UseHotkeysParams {
  positions: Position[];
}

/**
 * Keyboard shortcuts:
 *   J / ↓        next position (cursor)
 *   K / ↑        prev position (cursor)
 *   Enter / Space toggle expand cursor row
 *   E            expand all
 *   C / Esc      collapse all
 *   1-9          jump to position N
 *   Space        pause/resume polling
 */
export function useHotkeys({ positions }: UseHotkeysParams) {
  const cursor = useUiStore((s) => s.cursor);
  const setCursor = useUiStore((s) => s.setCursor);
  const toggleExpand = useUiStore((s) => s.toggleExpand);
  const expandAll = useUiStore((s) => s.expandAll);
  const collapseAll = useUiStore((s) => s.collapseAll);
  const togglePaused = useUiStore((s) => s.togglePaused);

  useEffect(() => {
    const handler = (ev: KeyboardEvent) => {
      // Ignore when typing in inputs
      const tag = (ev.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (ev.target as HTMLElement)?.isContentEditable) return;
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;

      const key = ev.key;
      const n = positions.length;
      if (n === 0) return;

      if (key === "j" || key === "ArrowDown") {
        ev.preventDefault();
        setCursor(Math.min(cursor + 1, n - 1));
      } else if (key === "k" || key === "ArrowUp") {
        ev.preventDefault();
        setCursor(Math.max(cursor - 1, 0));
      } else if (key === "Enter" || key === " ") {
        // Space pauses unless on a row -> expand instead
        if (cursor >= 0 && cursor < n && key === "Enter") {
          ev.preventDefault();
          toggleExpand(positions[cursor].position_id);
        } else if (key === " ") {
          ev.preventDefault();
          togglePaused();
        }
      } else if (key === "e") {
        ev.preventDefault();
        expandAll(positions.map((p) => p.position_id));
      } else if (key === "c" || key === "Escape") {
        ev.preventDefault();
        collapseAll();
      } else if (/^[1-9]$/.test(key)) {
        const idx = parseInt(key, 10) - 1;
        if (idx < n) {
          ev.preventDefault();
          setCursor(idx);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [cursor, positions, setCursor, toggleExpand, expandAll, collapseAll, togglePaused]);
}
