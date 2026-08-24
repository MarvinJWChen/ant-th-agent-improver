import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../lib/utils";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "size"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /** Native tooltip. Especially useful paired with `disabled` to explain why. */
  title?: string;
}

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap select-none " +
  "transition-all duration-120 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none";

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-surface-0 font-semibold shadow-sm shadow-accent/20 " +
    "hover:bg-accent-hover hover:shadow-md hover:shadow-accent/30 active:bg-accent-muted",
  secondary:
    "bg-surface-2 text-primary border border-hairline-strong hover:border-accent/40 hover:bg-surface-2/70 active:bg-surface-1",
  ghost: "bg-transparent text-secondary hover:bg-surface-2 hover:text-primary active:bg-surface-1",
  danger:
    "bg-danger text-surface-0 font-semibold shadow-sm shadow-danger/20 hover:brightness-110 active:brightness-95",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-base",
  lg: "h-12 px-6 text-md font-semibold",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading = false, disabled, className, children, type, ...rest },
  ref,
) {
  const isDisabled = disabled || loading;
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={cn(BASE, VARIANT[variant], SIZE[size], className)}
      {...rest}
    >
      {loading && <Spinner size="xs" />}
      {children}
    </button>
  );
});
