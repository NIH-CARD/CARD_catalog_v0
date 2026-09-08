/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // GDC-ish accent
        accent: {
          DEFAULT: "#1f5fa6",
          light: "#3b82f6",
          dark: "#143d6b",
        },
      },
    },
  },
  plugins: [],
};
