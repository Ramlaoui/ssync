/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{svelte,js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "var(--border, #e5e5e5)",
        input: "var(--input, #fafafa)",
        ring: "var(--ring, #000000)",
        background: "var(--background, #ffffff)",
        foreground: "var(--foreground, #000000)",
        primary: {
          DEFAULT: "var(--primary, #000000)",
          foreground: "var(--primary-foreground, #ffffff)",
        },
        secondary: {
          DEFAULT: "var(--secondary, #f5f5f5)",
          foreground: "var(--secondary-foreground, #000000)",
        },
        destructive: {
          DEFAULT: "var(--destructive, #ff3333)",
          foreground: "var(--destructive-foreground, #ffffff)",
        },
        muted: {
          DEFAULT: "var(--muted, #666666)",
          foreground: "var(--muted-foreground, #999999)",
        },
        accent: {
          DEFAULT: "var(--accent, #0066ff)",
          foreground: "var(--accent-foreground, #ffffff)",
        },
        popover: {
          DEFAULT: "var(--popover, #ffffff)",
          foreground: "var(--popover-foreground, #000000)",
        },
        card: {
          DEFAULT: "var(--card, #ffffff)",
          foreground: "var(--card-foreground, #000000)",
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'gradient-mesh': 'radial-gradient(at 40% 20%, hsla(220, 90%, 85%, 0.3) 0px, transparent 50%), radial-gradient(at 80% 0%, hsla(189, 90%, 85%, 0.3) 0px, transparent 50%), radial-gradient(at 10% 50%, hsla(250, 90%, 85%, 0.3) 0px, transparent 50%)',
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-down": {
          from: { opacity: "0", transform: "translateY(-10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in": {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(0)" },
        },
        "slide-out": {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(100%)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.95)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-1000px 0" },
          "100%": { backgroundPosition: "1000px 0" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.3s ease-out",
        "fade-up": "fade-up 0.3s ease-out",
        "fade-down": "fade-down 0.3s ease-out",
        "slide-in": "slide-in 0.3s ease-out",
        "slide-out": "slide-out 0.3s ease-out",
        "scale-in": "scale-in 0.2s ease-out",
        shimmer: "shimmer 2s infinite linear",
        pulse: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["SF Mono", "Monaco", "Inconsolata", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
  ],
}