import type { ReactNode } from "react";
import { cn } from "../lib/utils";

export interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  /** slot rendered to the right of the title, e.g. a Badge or Button */
  right?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** drop the default body padding, e.g. when the child manages its own (a Table) */
  noPadding?: boolean;
}

export function Card({
  title,
  subtitle,
  right,
  footer,
  children,
  className,
  bodyClassName,
  noPadding = false,
}: CardProps) {
  const hasHeader = !!(title || subtitle || right);
  return (
    <div className={cn("rounded-md border border-hairline bg-surface-2", className)}>
      {hasHeader && (
        <div className="flex items-start justify-between gap-3 border-b border-hairline px-4 py-3">
          <div className="min-w-0">
            {title && <h3 className="truncate text-sm font-semibold text-primary">{title}</h3>}
            {subtitle && <p className="mt-0.5 truncate text-xs text-muted">{subtitle}</p>}
          </div>
          {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
        </div>
      )}
      {children != null && (
        <div className={cn(!noPadding && "p-4", bodyClassName)}>{children}</div>
      )}
      {footer && <div className="border-t border-hairline px-4 py-2.5">{footer}</div>}
    </div>
  );
}
