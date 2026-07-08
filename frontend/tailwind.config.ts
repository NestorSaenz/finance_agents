import type { Config } from "tailwindcss";

// Design tokens live here so components reference `bg-brand-600`, `text-ink`,
// etc. instead of raw hex values (consistency + one place to retheme).
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand = teal (trust + money). Standard Tailwind teal scale.
        brand: {
          50: "#f0fdfa",
          100: "#ccfbf1",
          200: "#99f6e4",
          300: "#5eead4",
          400: "#2dd4bf",
          500: "#14b8a6",
          600: "#0d9488",
          700: "#0f766e",
          800: "#115e59",
          900: "#134e4a",
        },
        ink: "#0f172a", // slate-900 for primary text
        muted: "#64748b", // slate-500 for secondary text
        surface: "#ffffff",
        canvas: "#f8fafc", // slate-50 app background
        line: "#e2e8f0", // slate-200 borders
        positive: "#059669", // emerald-600 (income / on-track)
        negative: "#dc2626", // red-600 (over budget)
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      boxShadow: {
        card: "0 1px 3px 0 rgb(15 23 42 / 0.06), 0 1px 2px -1px rgb(15 23 42 / 0.10)",
        pop: "0 10px 30px -12px rgb(15 23 42 / 0.25)",
      },
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: {
          "0%, 80%, 100%": { opacity: "0.2" },
          "40%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.25s ease-out",
        blink: "blink 1.4s infinite both",
      },
    },
  },
  plugins: [],
};

export default config;
