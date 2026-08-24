/** Join class name fragments, dropping falsy values. Zero-dependency `clsx` substitute. */
export function cn(
  ...classes: Array<string | false | null | undefined | 0>
): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * Middle-truncate a long identifier/hash, keeping `keep` characters at each end.
 * `truncateMiddle("sha256:9f2c...e114", 6)` -> "sha256:9f2c…e114"
 * (short strings are returned unchanged).
 */
export function truncateMiddle(value: string, keep = 8): string {
  if (value.length <= keep * 2 + 1) return value;
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

/** Locale-formatted integer/decimal, e.g. formatNumber(1042) -> "1,042". */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}
