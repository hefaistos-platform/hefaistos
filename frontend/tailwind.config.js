/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{ts,tsx,html}",
  ],
  theme: {
    extend: {
      colors: {
        hefaistos: {
          primary: '#1677ff', // Ant Design Blue
          secondary: '#f0f2f5',
          border: '#d9d9d9',
        }
      }
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
};