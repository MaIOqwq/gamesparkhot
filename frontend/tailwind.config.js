/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#165DFF',
        secondary: '#0FC6C2',
        success: '#00B42A',
        warning: '#FF7D00',
        danger: '#F53F3F',
        dark: '#0b0f19',
        'dark-light': 'rgba(255,255,255,0.03)',
        'border-light': 'rgba(255,255,255,0.06)',
      },
      boxShadow: {
        'card': '0 4px 20px rgba(0,0,0,0.1)',
        'card-hover': '0 8px 30px rgba(0,0,0,0.2)',
      },
    },
  },
  plugins: [],
}