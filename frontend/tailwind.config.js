/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        /* ------------------------------------------------------------------
         * ASHA Swar Nirantar — premium burgundy, rose, ivory & white identity.
         *
         *   Deep Burgundy #321321   Burgundy      #7A1638   Wine Rose  #881144
         *   Rose Pink     #C64F78   Dusty Rose    #B96F85   Blush Pink #E8A8B8
         *   Pale Blush    #F4DCE4   Warm Ivory    #FFF7F0   Ivory Beige#F5E9E2
         *   Pure White    #FFFFFF   Primary Text  #2B1F26   Secondary  #685B62
         *   Border        #EADCE1   Success #367A59 Warning #A86B20 Error #B4233F
         *
         * Legacy token names are remapped for consistent adoption.
         * ---------------------------------------------------------------- */
        night: "#321321",
        "bg-base": "#FFF7F0",
        plum: "#F4DCE4",
        "dark-purple": "#321321",
        burgundy: {
          DEFAULT: "#7A1638",
          deep: "#321321",
          wine: "#881144",
        },
        wine: "#881144",

        pink: {
          DEFAULT: "#C64F78", // Rose Pink (primary actions/highlights)
          hot: "#C64F78",
          blush: "#E8A8B8", // Blush Pink
          soft: "#F4DCE4", // Pale Blush
        },

        rose: {
          DEFAULT: "#C64F78",
          dusty: "#B96F85",
          wine: "#881144",
          blush: "#E8A8B8",
          pale: "#F4DCE4",
        },

        lavender: "#B96F85",
        violet: "#7A1638",
        pearl: "#FFFFFF",
        ivory: "#FFF7F0",
        beige: "#F5E9E2",

        /* Semantic colours */
        coral: "#B4233F", // error
        success: "#367A59",
        warning: "#A86B20",
        info: "#7A1638",

        /* Legacy tokens */
        teal: {
          deep: "#321321", // deep burgundy for backgrounds/nav/buttons
        },
        midnight: "#321321",
        mint: {
          DEFAULT: "#C64F78", // primary accent
          soft: "rgba(244,220,228,0.85)",
          surface: "#F4DCE4",
        },
      },
      fontFamily: {
        sans: ["Figtree", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glass: "0 8px 32px rgba(50,19,33,0.18)",
        card: "0 6px 24px rgba(43,31,38,0.08)",
        soft: "0 2px 12px rgba(43,31,38,0.06)",
        pinkGlow: "0 0 24px rgba(198,79,120,0.28)",
        blush: "0 10px 30px rgba(122,22,56,0.16)",
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
