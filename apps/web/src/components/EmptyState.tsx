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
        "flex flex-col items-center justify-center gap-2.5 rounded-lg border border-dashed border-hairline-strong px-6 py-14 text-center",
        className,
      )}
    >
      {icon && <div className="mb-1 text-muted">{icon}</div>}
      <div className="text-lg font-medium text-primary">{title}</div>
      {description && <p className="max-w-sm text-sm text-secondary">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
