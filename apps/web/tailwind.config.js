/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          0: "rgb(var(--color-surface-0) / <alpha-value>)",
          1: "rgb(var(--color-surface-1) / <alpha-value>)",
          2: "rgb(var(--color-surface-2) / <alpha-value>)",
        },
        hairline: "rgb(var(--color-hairline) / <alpha-value>)",
        "hairline-strong": "rgb(var(--color-hairline-strong) / <alpha-value>)",
        primary: "rgb(var(--color-text-primary) / <alpha-value>)",
        secondary: "rgb(var(--color-text-secondary) / <alpha-value>)",
        muted: "rgb(var(--color-text-muted) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--color-accent) / <alpha-value>)",
          hover: "rgb(var(--color-accent-hover) / <alpha-value>)",
          muted: "rgb(var(--color-accent-muted) / <alpha-value>)",
        },
        ok: "rgb(var(--color-ok) / <alpha-value>)",
        warn: "rgb(var(--color-warn) / <alpha-value>)",
        danger: "rgb(var(--color-danger) / <alpha-value>)",
        info: "rgb(var(--color-info) / <alpha-value>)",
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          '"SF Mono"',
          '"JetBrains Mono"',
          "Menlo",
          "monospace",
        ],
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          '"Segoe UI"',
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
      fontSize: {
        // tiny uppercase labels (badges, table headers, KeyValue keys)
        xs: ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.02em" }],
        // table cells, monospace identifiers/hashes — smallest "readable" tier
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        // body/prose default
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        // larger body / lg button label
        md: ["1rem", { lineHeight: "1.5rem" }],
        lg: ["1.125rem", { lineHeight: "1.75rem" }],
        // section headings (~20-24px)
        xl: ["1.375rem", { lineHeight: "1.85rem" }],
        "2xl": ["1.625rem", { lineHeight: "2rem" }],
        // page titles (~28-32px) and hero numbers (StatTile, gate verdict)
        "3xl": ["1.875rem", { lineHeight: "2.25rem" }],
        "4xl": ["2.25rem", { lineHeight: "2.5rem" }],
      },
      spacing: {
        4.5: "1.125rem",
        13: "3.25rem",
        14: "3.5rem",
        15: "3.75rem",
        18: "4.5rem",
      },
      borderRadius: {
        sm: "3px",
        DEFAULT: "5px",
        md: "6px",
        lg: "8px",
      },
      transitionDuration: {
        DEFAULT: "120ms",
      },
      boxShadow: {
        overlay: "0 8px 24px -8px rgb(0 0 0 / 0.5)",
      },
    },
  },
  plugins: [],
};
