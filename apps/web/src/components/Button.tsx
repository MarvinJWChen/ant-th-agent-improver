import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../lib/utils";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "size"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /** Native tooltip. Especially useful paired with `disabled` to explain why. */
  title?: string;
}

const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap select-none " +
  "transition-colors duration-120 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-accent text-surface-0 font-semibold hover:bg-accent-hover",
  secondary:
    "bg-surface-2 text-primary border border-hairline-strong hover:border-accent/40 hover:bg-surface-2/70",
  ghost: "bg-transparent text-secondary hover:bg-surface-2 hover:text-primary",
  danger: "bg-danger text-surface-0 font-semibold hover:brightness-110",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-8 px-3.5 text-sm",
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
