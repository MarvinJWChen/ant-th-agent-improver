/**
 * Shared semantic tone system used across the component kit (Badge, GateChecklist,
 * ProvenanceBadge, StatTile, JourneyStepper, Timeline chips, ...).
 *
 * All class fragments reference Tailwind theme colors (see tailwind.config.js /
 * src/styles.css) — never raw hex.
 */
export type Tone = "neutral" | "ok" | "warn" | "danger" | "info" | "accent";

export interface ToneClasses {
  /** foreground text color, for use on dark surfaces */
  text: string;
  /** translucent tint background, for chips/badges/panels */
  bg: string;
  /** translucent tint border, pairs with `bg` */
  border: string;
  /** solid indicator dot/fill */
  dot: string;
  /** solid background, for filled buttons/circles */
  solidBg: string;
  /** text color to place on top of `solidBg` (kept dark for contrast) */
  onSolid: string;
}

export const TONE: Record<Tone, ToneClasses> = {
  neutral: {
    text: "text-secondary",
    bg: "bg-surface-2",
    border: "border-hairline-strong",
    dot: "bg-muted",
    solidBg: "bg-surface-2",
    onSolid: "text-primary",
  },
  ok: {
    text: "text-ok",
    bg: "bg-ok/10",
    border: "border-ok/30",
    dot: "bg-ok",
    solidBg: "bg-ok",
    onSolid: "text-surface-0",
  },
  warn: {
    text: "text-warn",
    bg: "bg-warn/10",
    border: "border-warn/30",
    dot: "bg-warn",
    solidBg: "bg-warn",
    onSolid: "text-surface-0",
  },
  danger: {
    text: "text-danger",
    bg: "bg-danger/10",
    border: "border-danger/30",
    dot: "bg-danger",
    solidBg: "bg-danger",
    onSolid: "text-surface-0",
  },
  info: {
    text: "text-info",
    bg: "bg-info/10",
    border: "border-info/30",
    dot: "bg-info",
    solidBg: "bg-info",
    onSolid: "text-surface-0",
  },
  accent: {
    text: "text-accent",
    bg: "bg-accent/10",
    border: "border-accent/30",
    dot: "bg-accent",
    solidBg: "bg-accent",
    onSolid: "text-surface-0",
  },
};
