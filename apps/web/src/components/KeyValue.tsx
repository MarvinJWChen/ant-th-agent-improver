import type { ReactNode } from "react";
import { cn, truncateMiddle } from "../lib/utils";

export interface KeyValueItem {
  key: string;
  label: ReactNode;
  value: ReactNode;
  /** middle-truncate long monospace values (hashes, ids) with the full value in a title tooltip */
  truncateMiddle?: boolean;
  /** render value in monospace (default true) */
  mono?: boolean;
}

export interface KeyValueProps {
  items: KeyValueItem[];
  className?: string;
  /** lay out as two columns of rows instead of one */
  columns?: 1 | 2;
}

export function KeyValue({ items, className, columns = 1 }: KeyValueProps) {
  return (
    <dl
      className={cn(
        columns === 2 ? "grid grid-cols-1 gap-x-8 gap-y-2.5 sm:grid-cols-2" : "flex flex-col divide-y divide-hairline",
        className,
      )}
    >
      {items.map((item) => {
        const displayValue =
          item.truncateMiddle && typeof item.value === "string"
            ? truncateMiddle(item.value, 8)
            : item.value;
        return (
          <div
            key={item.key}
            className={cn(
              "flex items-baseline justify-between gap-4 py-2.5",
              columns === 1 && "first:pt-0 last:pb-0",
            )}
          >
            <dt className="shrink-0 text-xs text-muted">{item.label}</dt>
            <dd
              className={cn(
                "min-w-0 truncate text-right text-sm text-primary",
                item.mono !== false && "font-mono",
              )}
              title={typeof item.value === "string" ? item.value : undefined}
            >
              {displayValue}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
