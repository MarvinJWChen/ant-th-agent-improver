import { useMemo, useState, type ReactNode } from "react";
import { cn } from "../lib/utils";

export interface TableColumn<T> {
  key: string;
  header: ReactNode;
  /** custom cell renderer; defaults to String((row as any)[key]) */
  render?: (row: T) => ReactNode;
  /** right-align + monospace, for metric/numeric columns */
  numeric?: boolean;
  sortable?: boolean;
  /** accessor used when sorting; defaults to (row as any)[key] */
  sortValue?: (row: T) => string | number;
  width?: string;
  className?: string;
}

export interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  className?: string;
  /** dense (default) or comfortable row padding */
  dense?: boolean;
  stickyHeader?: boolean;
  initialSortKey?: string;
  initialSortDir?: "asc" | "desc";
  /** cap the table's height and scroll vertically inside it, e.g. "max-h-96" */
  maxHeightClassName?: string;
}

function defaultAccessor<T>(row: T, key: string): string | number {
  const value = (row as Record<string, unknown>)[key];
  if (typeof value === "number") return value;
  return value == null ? "" : String(value);
}

export function Table<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  emptyMessage = "No data",
  className,
  dense = true,
  stickyHeader = true,
  initialSortKey,
  initialSortDir = "asc",
  maxHeightClassName,
}: TableProps<T>) {
  const [sortKey, setSortKey] = useState<string | undefined>(initialSortKey);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(initialSortDir);

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return rows;
    const accessor = col.sortValue ?? ((row: T) => defaultAccessor(row, col.key));
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = accessor(a);
      const bv = accessor(b);
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [rows, columns, sortKey, sortDir]);

  function toggleSort(col: TableColumn<T>) {
    if (!col.sortable) return;
    if (sortKey !== col.key) {
      setSortKey(col.key);
      setSortDir("asc");
    } else {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    }
  }

  const rowPad = dense ? "py-1.5" : "py-2.5";

  return (
    <div
      className={cn(
        "scrollbar-thin overflow-auto rounded-md border border-hairline",
        maxHeightClassName,
        className,
      )}
    >
      <table className="w-full min-w-max border-collapse text-left text-sm">
        <thead>
          <tr>
            {columns.map((col) => {
              const isSorted = sortKey === col.key;
              return (
                <th
                  key={col.key}
                  style={col.width ? { width: col.width } : undefined}
                  aria-sort={isSorted ? (sortDir === "asc" ? "ascending" : "descending") : undefined}
                  className={cn(
                    "border-b border-hairline bg-surface-1 px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted",
                    stickyHeader && "sticky top-0 z-10",
                    col.numeric && "text-right",
                    col.sortable && "cursor-pointer select-none hover:text-secondary",
                  )}
                  onClick={() => toggleSort(col)}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {col.sortable && (
                      <span className={cn("text-[10px]", !isSorted && "opacity-30")} aria-hidden>
                        {isSorted ? (sortDir === "asc" ? "▲" : "▼") : "▲"}
                      </span>
                    )}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-xs text-muted">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sortedRows.map((row) => {
              const key = rowKey(row);
              const clickable = !!onRowClick;
              return (
                <tr
                  key={key}
                  tabIndex={clickable ? 0 : undefined}
                  role={clickable ? "button" : undefined}
                  onClick={clickable ? () => onRowClick!(row) : undefined}
                  onKeyDown={
                    clickable
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onRowClick!(row);
                          }
                        }
                      : undefined
                  }
                  className={cn(
                    "border-b border-hairline last:border-b-0",
                    clickable && "cursor-pointer hover:bg-surface-1 focus-visible:bg-surface-1",
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        "px-3 text-primary",
                        rowPad,
                        col.numeric && "text-right font-mono tabular-nums",
                        col.className,
                      )}
                    >
                      {col.render ? col.render(row) : defaultAccessor(row, col.key)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
