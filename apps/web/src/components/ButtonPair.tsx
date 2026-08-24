import type { ReactNode } from "react";
import { cn } from "../lib/utils";
import { Spinner } from "./Spinner";

export interface ButtonPairAction {
  label: ReactNode;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  /** shown as a native tooltip when this action is disabled */
  disabledReason?: string;
}

export interface ButtonPairProps {
  /** typically the "captured" / offline action */
  left: ButtonPairAction;
  /** typically the "live" / rerun action */
  right: ButtonPairAction;
  /** optional caption line rendered beneath the pair */
  caption?: ReactNode;
  size?: "sm" | "md" | "lg";
  /** stretch to fill the parent's width, each half getting equal width */
  fullWidth?: boolean;
  className?: string;
}

const SIZE: Record<NonNullable<ButtonPairProps["size"]>, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-base",
  lg: "h-12 px-6 text-md font-semibold",
};

type HalfTone = "primary" | "secondary";

const TONE_CLASS: Record<HalfTone, string> = {
  // the safe, default action — reads as the primary Button variant
  primary:
    "bg-accent text-surface-0 font-semibold hover:bg-accent-hover active:bg-accent-muted " +
    "disabled:hover:bg-accent",
  // the slower / more expensive action — deliberately restrained, outline-only
  secondary:
    "bg-transparent text-secondary hover:bg-surface-2 hover:text-primary active:bg-surface-1 " +
    "disabled:hover:bg-transparent",
};

function Half({
  action,
  size,
  fullWidth,
  tone,
}: {
  action: ButtonPairAction;
  size: NonNullable<ButtonPairProps["size"]>;
  fullWidth: boolean;
  tone: HalfTone;
}) {
  const isDisabled = !!(action.disabled || action.loading);
  return (
    <button
      type="button"
      onClick={action.onClick}
      disabled={isDisabled}
      title={isDisabled ? action.disabledReason : undefined}
      aria-busy={action.loading || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 font-medium",
        "transition-colors duration-120",
        "disabled:cursor-not-allowed disabled:opacity-45",
        TONE_CLASS[tone],
        SIZE[size],
        fullWidth && "flex-1",
      )}
    >
      {action.loading && <Spinner size="xs" />}
      {action.label}
    </button>
  );
}

/**
 * Two actions sharing a single outer border with one hairline divider between
 * them — used everywhere we offer a "captured fixture" vs "live rerun" choice.
 * Reads as one deliberate segmented control: the left action (captured/safe
 * default) is styled as primary; the right action (live/expensive) is styled
 * as a restrained outline so it never competes for attention.
 */
export function ButtonPair({ left, right, caption, size = "md", fullWidth = false, className }: ButtonPairProps) {
  return (
    <div className={cn("inline-flex flex-col gap-2", fullWidth && "flex w-full", className)}>
      <div
        className={cn(
          "inline-flex overflow-hidden rounded-md border border-hairline-strong",
          fullWidth && "flex w-full",
        )}
      >
        <Half action={left} size={size} fullWidth={fullWidth} tone="primary" />
        <div className="w-px shrink-0 bg-hairline-strong" />
        <Half action={right} size={size} fullWidth={fullWidth} tone="secondary" />
      </div>
      {caption && <p className="text-sm text-muted">{caption}</p>}
    </div>
  );
}
