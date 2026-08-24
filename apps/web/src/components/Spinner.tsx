import { cn } from "../lib/utils";

export type SpinnerSize = "xs" | "sm" | "md";

export interface SpinnerProps {
  size?: SpinnerSize;
  className?: string;
  /** screen-reader-only label */
  label?: string;
}

const SIZE: Record<SpinnerSize, string> = {
  xs: "h-3 w-3 border-[1.5px]",
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
};

/** Indeterminate loading indicator. Pure CSS (Tailwind's built-in spin keyframe) — no JS animation library. */
export function Spinner({ size = "sm", className, label = "Loading" }: SpinnerProps) {
  return (
    <span role="status" className={cn("inline-flex items-center justify-center", className)}>
      <span
        className={cn(
          "animate-spin rounded-full border-current border-t-transparent text-muted",
          SIZE[size],
        )}
      />
      <span className="sr-only">{label}</span>
    </span>
  );
}
