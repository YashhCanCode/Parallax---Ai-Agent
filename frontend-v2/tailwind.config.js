/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "var(--surface-0)",
        card: "var(--surface-1)",
        sunken: "var(--surface-2)",
        line: "var(--border)",
        ink: "var(--text-primary)",
        ink2: "var(--text-secondary)",
        muted: "var(--text-muted)",
        accent: "var(--accent)",
        critical: "var(--status-critical)",
        panel: "var(--panel)",
        panelx: "var(--panel-strong)",
      },
      borderColor: { soft: "var(--panel-line)" },
      fontFamily: { sans: ["Inter Variable", "Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"] },
    },
  },
  plugins: [],
};
