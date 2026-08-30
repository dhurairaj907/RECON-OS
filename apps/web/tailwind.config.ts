import type { Config } from "tailwindcss";

/**
 * RECON OS — semantic design tokens.
 *
 * Every colour below resolves to a CSS variable defined in
 * `src/styles/globals.css`. The variables are RGB triplets ("11 14 20"),
 * so Tailwind's `<alpha-value>` slash syntax (`bg-surface/40`) keeps working.
 *
 * Two intentionally-designed themes:
 *   • dark  — the primary RECON identity (`.dark` on <html>, the SSR default)
 *   • light — a genuine professional light theme (default `:root`)
 */
const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "rgb(var(--c-bg) / <alpha-value>)",
        surface: {
          DEFAULT: "rgb(var(--c-surface) / <alpha-value>)",
          subtle: "rgb(var(--c-surface-subtle) / <alpha-value>)",
          hover: "rgb(var(--c-surface-hover) / <alpha-value>)",
          elevated: "rgb(var(--c-surface-elevated) / <alpha-value>)",
        },
        border: {
          DEFAULT: "rgb(var(--c-border) / <alpha-value>)",
          subtle: "rgb(var(--c-border-subtle) / <alpha-value>)",
          highlight: "rgb(var(--c-border-highlight) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--c-accent) / <alpha-value>)",
          hover: "rgb(var(--c-accent-hover) / <alpha-value>)",
          subtle: "rgb(var(--c-accent-subtle) / <alpha-value>)",
          glow: "rgb(var(--c-accent) / 0.15)",
        },
        /* Semantic foreground / text ramp */
        fg: {
          DEFAULT: "rgb(var(--c-fg) / <alpha-value>)",
          secondary: "rgb(var(--c-fg-secondary) / <alpha-value>)",
          muted: "rgb(var(--c-fg-muted) / <alpha-value>)",
          faint: "rgb(var(--c-fg-faint) / <alpha-value>)",
          inverse: "rgb(var(--c-fg-inverse) / <alpha-value>)",
        },
        status: {
          success: {
            DEFAULT: "rgb(var(--c-success) / <alpha-value>)",
            bg: "rgb(var(--c-success) / 0.12)",
            border: "rgb(var(--c-success) / 0.28)",
          },
          warning: {
            DEFAULT: "rgb(var(--c-warning) / <alpha-value>)",
            bg: "rgb(var(--c-warning) / 0.12)",
            border: "rgb(var(--c-warning) / 0.28)",
          },
          danger: {
            DEFAULT: "rgb(var(--c-danger) / <alpha-value>)",
            bg: "rgb(var(--c-danger) / 0.12)",
            border: "rgb(var(--c-danger) / 0.28)",
          },
          info: {
            DEFAULT: "rgb(var(--c-info) / <alpha-value>)",
            bg: "rgb(var(--c-info) / 0.12)",
            border: "rgb(var(--c-info) / 0.28)",
          },
          neutral: {
            DEFAULT: "rgb(var(--c-neutral) / <alpha-value>)",
            bg: "rgb(var(--c-neutral) / 0.10)",
            border: "rgb(var(--c-neutral) / 0.20)",
          },
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "var(--shadow-card)",
        elevated: "var(--shadow-elevated)",
        "depth-hover": "var(--shadow-depth-hover)",
      },
      fontSize: {
        /* Slightly opened-up base scale for readability — a polished
         * enterprise-dashboard feel rather than the tighter defaults.
         * xs 12->13px, sm 14->15px; base/lg untouched (already in range). */
        xs: ["0.8125rem", { lineHeight: "1.25rem" }],
        sm: ["0.9375rem", { lineHeight: "1.4rem" }],
        "display-sm": ["1.5rem", { lineHeight: "1", letterSpacing: "-0.02em" }],
        "display-md": ["2.25rem", { lineHeight: "1", letterSpacing: "-0.024em" }],
        "display-lg": ["clamp(1.75rem,3.6vw,2.75rem)", { lineHeight: "1", letterSpacing: "-0.022em" }],
        "display-xl": ["clamp(2.5rem,6vw,4.75rem)", { lineHeight: "0.95", letterSpacing: "-0.03em" }],
      },
      transitionTimingFunction: {
        spatial: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      keyframes: {
        reveal: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "node-in": {
          "0%": { opacity: "0", transform: "translateY(6px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "flow-dash": {
          "0%": { strokeDashoffset: "24" },
          "100%": { strokeDashoffset: "0" },
        },
        "pulse-node": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
        "ambient-drift": {
          "0%, 100%": { transform: "translate3d(0,0,0) scale(1)" },
          "50%": { transform: "translate3d(2%, -1.5%, 0) scale(1.06)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(2%)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "drawer-in": {
          "0%": { opacity: "0", transform: "translateX(3%) scale(0.99)" },
          "100%": { opacity: "1", transform: "translateX(0) scale(1)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        reveal: "reveal 220ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "node-in": "node-in 260ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "flow-dash": "flow-dash 900ms linear infinite",
        "pulse-node": "pulse-node 2s ease-in-out infinite",
        "ambient-drift": "ambient-drift 44s ease-in-out infinite",
        "fade-in": "fade-in 160ms ease-out both",
        "slide-in-right": "slide-in-right 240ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "drawer-in": "drawer-in 280ms cubic-bezier(0.22, 1, 0.36, 1) both",
        shimmer: "shimmer 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
