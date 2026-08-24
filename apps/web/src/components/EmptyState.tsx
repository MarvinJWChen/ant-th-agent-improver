import type { ReactNode } from "react";
import { cn } from "../lib/utils";

export interface EmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  /** small glyph/icon shown above the title (text/emoji or inline svg — no icon library) */
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-hairline-strong px-6 py-10 text-center",
        className,
      )}
    >
      {icon && <div className="mb-1 text-muted">{icon}</div>}
      <div className="text-sm font-medium text-primary">{title}</div>
      {description && <p className="max-w-sm text-xs text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
