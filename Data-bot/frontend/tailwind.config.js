/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: "#ef4444",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
