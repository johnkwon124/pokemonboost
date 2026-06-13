import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#08090c",
          900: "#0d0f14",
          800: "#13161d",
          700: "#1c2029",
          600: "#272c38",
          500: "#3a4150",
          400: "#5b6478",
          300: "#8a93a6",
          200: "#c0c6d4",
          100: "#e7eaf2"
        },
        accent: {
          DEFAULT: "#ffcc00",
          soft: "#ffe97a"
        }
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Text", "Inter", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
};
export default config;
