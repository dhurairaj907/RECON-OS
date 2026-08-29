import type { Config } from "tailwindcss";

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
        background: "#0B0E14",
        surface: {
          DEFAULT: "#121722",
          subtle: "#161D2B",
          hover: "#1B2334",
          elevated: "#212A3E",
        },
        border: {
          DEFAULT: "#1E2638",
          subtle: "#182030",
          highlight: "#2C3852",
        },
        accent: {
          DEFAULT: "#2563EB",
          hover: "#1D4ED8",
          subtle: "#1E3A8A",
          glow: "rgba(37, 99, 235, 0.15)",
        },
        status: {
          success: {
            DEFAULT: "#10B981",
            bg: "rgba(16, 185, 129, 0.1)",
            border: "rgba(16, 185, 129, 0.25)",
          },
          warning: {
            DEFAULT: "#F59E0B",
            bg: "rgba(245, 158, 11, 0.1)",
            border: "rgba(245, 158, 11, 0.25)",
          },
          danger: {
            DEFAULT: "#EF4444",
            bg: "rgba(239, 68, 68, 0.1)",
            border: "rgba(239, 68, 68, 0.25)",
          },
          info: {
            DEFAULT: "#3B82F6",
            bg: "rgba(59, 130, 246, 0.1)",
            border: "rgba(59, 130, 246, 0.25)",
          },
          neutral: {
            DEFAULT: "#94A3B8",
            bg: "rgba(148, 163, 184, 0.1)",
            border: "rgba(148, 163, 184, 0.2)",
          },
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
