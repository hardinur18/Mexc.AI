import { motion, AnimatePresence } from "motion/react";

interface TopProgressBarProps {
  active: boolean;
}

/**
 * Thin progress bar at the very top of viewport, NProgress-style.
 * Shows when `active` (e.g., during query refetch).
 */
export function TopProgressBar({ active }: TopProgressBarProps) {
  return (
    <AnimatePresence>
      {active && (
        <motion.div
          key="progress"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed top-0 left-0 right-0 h-[2px] z-[100] pointer-events-none"
        >
          <motion.div
            initial={{ x: "-100%" }}
            animate={{ x: "100%" }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "linear" }}
            className="h-full w-1/3 bg-gradient-to-r from-transparent via-[var(--color-accent)] to-transparent"
            style={{ boxShadow: "0 0 12px var(--color-accent-ring)" }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
