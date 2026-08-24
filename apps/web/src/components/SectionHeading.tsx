import type { ReactNode } from "react";
import { cn } from "../lib/utils";

export interface SectionHeadingProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** action slot, e.g. a Button or ButtonPair, right-aligned */
  right?: ReactNode;
  size?: "sm" | "md";
  className?: string;
  as?: "h1" | "h2" | "h3";
}

export function SectionHeading({
  title,
  subtitle,
  right,
  size = "md",
  className,
  as: Tag = "h2",
}: SectionHeadingProps) {
  return (
    <div className={cn("flex items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        <Tag
          className={cn(
            "truncate font-semibold text-primary",
            size === "md" ? "text-lg" : "text-sm",
          )}
        >
          {title}
        </Tag>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
    </div>
  );
}
