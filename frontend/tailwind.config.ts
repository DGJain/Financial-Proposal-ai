import type { Config } from "tailwindcss";

/**
 * Design tokens for the platform UI. Semantic colors carry meaning the dashboard
 * relies on: quality/grounding greens, rising-loss warn/danger, and an `accent`
 * used for repository-contribution bars (it is *share*, not quality).
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // "Counting House at Night" — warm dark theme (dark-mode values).
        canvas: "#1a1712", // Page
        surface: "#221b18", // Panel
        "surface-2": "#2a251e", // Field
        border: "#3a342b", // Rule
        muted: "#9c9482", // Muted
        ink: "#ece6da", // Ink
        accent: { DEFAULT: "#c45a50", soft: "#7e2d2a" }, // Claret
        citation: { DEFAULT: "#7fb0c9", soft: "#2c4a6b" }, // Citation
        success: "#22c55e",
        warn: "#f59e0b",
        danger: "#ef4444",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: { xl: "0.9rem" },
    },
  },
  plugins: [],
};

export default config;
