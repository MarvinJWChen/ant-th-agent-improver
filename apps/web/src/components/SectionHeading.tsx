import type { ReactNode } from "react";
import { cn } from "../lib/utils";

export interface SectionHeadingProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** action slot, e.g. a Button or ButtonPair, right-aligned */
  right?: ReactNode;
  /**
   * "sm" -> in-page section heading (~22px), "md" (default) -> page title
   * (~30px), "lg" -> hero page title (~36px) for the rare page that wants
   * more presence.
   */
  size?: "sm" | "md" | "lg";
  className?: string;
  as?: "h1" | "h2" | "h3";
}

const SIZE_CLASS: Record<NonNullable<SectionHeadingProps["size"]>, string> = {
  sm: "text-xl",
  md: "text-3xl",
  lg: "text-4xl",
};

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
        <Tag className={cn("truncate font-semibold tracking-tight text-primary", SIZE_CLASS[size])}>{title}</Tag>
        {subtitle && <p className="mt-1.5 text-base text-secondary">{subtitle}</p>}
      </div>
      {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
    </div>
  );
}
