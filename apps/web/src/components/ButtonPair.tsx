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
  size?: "sm" | "md";
  /** stretch to fill the parent's width, each half getting equal width */
  fullWidth?: boolean;
  className?: string;
}

const SIZE: Record<NonNullable<ButtonPairProps["size"]>, string> = {
  sm: "h-7 px-3 text-xs",
  md: "h-8 px-4 text-sm",
};

function Half({
  action,
  size,
  fullWidth,
}: {
  action: ButtonPairAction;
  size: NonNullable<ButtonPairProps["size"]>;
  fullWidth: boolean;
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
        "inline-flex items-center justify-center gap-1.5 bg-surface-2 font-medium text-primary",
        "transition-colors duration-120 hover:bg-surface-2/60",
        "disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-surface-2",
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
 */
export function ButtonPair({ left, right, caption, size = "md", fullWidth = false, className }: ButtonPairProps) {
  return (
    <div className={cn("inline-flex flex-col gap-1.5", fullWidth && "flex w-full", className)}>
      <div
        className={cn(
          "inline-flex overflow-hidden rounded-md border border-hairline-strong",
          fullWidth && "flex w-full",
        )}
      >
        <Half action={left} size={size} fullWidth={fullWidth} />
        <div className="w-px shrink-0 bg-hairline-strong" />
        <Half action={right} size={size} fullWidth={fullWidth} />
      </div>
      {caption && <p className="text-xs text-muted">{caption}</p>}
    </div>
  );
}
