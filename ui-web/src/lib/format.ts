/**
 * Centralized formatters. Pakai di mana saja yang butuh nampilin angka/persen.
 * Default locale: en-US (international standard untuk angka trading).
 */

export function fmt(n: number | null | undefined, dp = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString("en-US", {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
}

export function fmtSign(n: number | null | undefined, dp = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return sign + fmt(n, dp);
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return sign + Number(n).toFixed(2) + "%";
}

export function fmtPctPlain(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(2) + "%";
}

/** Auto-precision price formatter (lebih banyak desimal untuk harga kecil). */
export function fmtPrice(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const v = Math.abs(n);
  const dp = v >= 1000 ? 2 : v >= 1 ? 4 : 6;
  return fmt(n, dp);
}

export function fmtTime(ms: number): string {
  return new Date(ms).toLocaleTimeString("id-ID");
}

/** PnL semantic class — green / red / neutral. */
export function pnlTone(n: number | null | undefined): "up" | "down" | "zero" {
  if (n == null || Number.isNaN(n)) return "zero";
  if (n > 0) return "up";
  if (n < 0) return "down";
  return "zero";
}

/** Buffer warning level. */
export function bufferTone(n: number | null | undefined): "ok" | "warn" | "danger" {
  if (n == null) return "ok";
  if (n < 10) return "danger";
  if (n < 25) return "warn";
  return "ok";
}

/** Margin ratio severity. */
export function marginRatioTone(n: number | null | undefined): "ok" | "warn" | "danger" {
  if (n == null) return "ok";
  if (n > 50) return "danger";
  if (n > 20) return "warn";
  return "ok";
}
