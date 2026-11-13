/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Brand system — Hoosty-inspired purple/pink luxury
        "bg-base": "#100C18",
        plum: "#211329",
        "dark-purple": "#28152D",
        burgundy: "#38152E",
        pink: {
          DEFAULT: "#F078AD",
          hot: "#E84D9B",
        },
        lavender: "#BBA6FF",
        violet: "#8755D9",
        pearl: "#FFF7FC",
        ivory: "#FFF7FC",
        coral: "#FF806F",
        /* Legacy token names — remapped to the pink identity so all existing
           dashboard/login/voice classes pick up the new theme automatically. */
        teal: {
          deep: "#100C18",
        },
        midnight: "#28152D",
        mint: {
          DEFAULT: "#F078AD",
          soft: "rgba(240,120,173,0.15)",
        },
      },
      fontFamily: {
        sans: ["Figtree", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glass: "0 8px 32px rgba(16,12,24,0.55)",
        card: "0 4px 24px rgba(16,12,24,0.1)",
        soft: "0 2px 12px rgba(16,12,24,0.07)",
        pinkGlow: "0 0 24px rgba(240,120,173,0.35)",
      },
      keyframes: {
        floaty: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-10px)" },
        },
        pulseRing: {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
      },
      animation: {
        floaty: "floaty 5s ease-in-out infinite",
        pulseRing: "pulseRing 2.2s ease-out infinite",
      },
    },
  },
  plugins: [],
};
