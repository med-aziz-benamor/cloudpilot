import type { Config } from "tailwindcss";

// CloudPilot design system — exact tokens from the knowledge base.
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#0D6EFD",
          accent: "#0DCAF0",
          navy: "#0A1628",
        },
        neutral: {
          0: "#FFFFFF",
          50: "#F8FAFC",
          100: "#F1F5F9",
          200: "#E2E8F0",
          300: "#CBD5E1",
          400: "#94A3B8",
          500: "#64748B",
          600: "#475569",
          700: "#334155",
          800: "#1E293B",
          900: "#0F172A",
        },
        status: {
          success: "#10B981",
          warning: "#F59E0B",
          danger: "#EF4444",
          info: "#0DCAF0",
        },
        agent: {
          cost: "#0D6EFD",
          rightsizing: "#0DCAF0",
          forecast: "#7C3AED",
          architect: "#10B981",
        },
        provider: {
          azure: "#0078D4",
          aws: "#FF9900",
          gcp: "#4285F4",
        },
      },
      fontFamily: {
        sans: ["Inter var", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      fontSize: {
        display: ["48px", { lineHeight: "1.1", letterSpacing: "-0.04em", fontWeight: "800" }],
        h1: ["32px", { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "700" }],
        h2: ["24px", { lineHeight: "1.3", letterSpacing: "-0.01em", fontWeight: "600" }],
        h3: ["20px", { lineHeight: "1.4", fontWeight: "600" }],
        h4: ["16px", { lineHeight: "1.4", fontWeight: "600" }],
        "body-lg": ["16px", { lineHeight: "1.6" }],
        body: ["14px", { lineHeight: "1.5" }],
        "body-sm": ["13px", { lineHeight: "1.5" }],
        caption: ["12px", { lineHeight: "1.4", letterSpacing: "0.01em", fontWeight: "500" }],
        label: ["11px", { lineHeight: "1", letterSpacing: "0.06em", fontWeight: "600" }],
      },
      boxShadow: {
        sm: "0 1px 2px rgba(10,22,40,.05)",
        card: "0 1px 3px rgba(10,22,40,.08), 0 8px 24px rgba(10,22,40,.06)",
        "card-hover": "0 4px 12px rgba(10,22,40,.12), 0 16px 40px rgba(10,22,40,.1)",
        elevated: "0 8px 32px rgba(10,22,40,.16)",
        modal: "0 24px 64px rgba(10,22,40,.24)",
        "glow-brand": "0 0 0 3px rgba(13,110,253,.2)",
        "glow-accent": "0 0 0 3px rgba(13,202,240,.2)",
      },
      borderRadius: {
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "12px",
        card: "12px",
        xl: "16px",
        modal: "16px",
        "2xl": "24px",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.16, 1, 0.3, 1)",
        bounce: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-468px 0" },
          "100%": { backgroundPosition: "468px 0" },
        },
        pulseDot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
        shimmer: "shimmer 1.5s infinite linear",
        "pulse-dot": "pulseDot 2s infinite ease-in-out",
        "scale-in": "scaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
