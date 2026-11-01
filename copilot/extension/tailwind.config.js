/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{ts,tsx,html}"],
  theme: {
    extend: {
      colors: {
        // Matches TradingView's dark theme palette.
        tv: {
          bg: "#131722",
          panel: "#1e222d",
          border: "#2a2e39",
          hover: "#2a2e39",
          text: "#d1d4dc",
          muted: "#787b86",
          up: "#26a69a",
          down: "#ef5350",
          blue: "#2962ff",
          amber: "#f7a600",
        },
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Trebuchet MS", "Roboto", "Ubuntu", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
