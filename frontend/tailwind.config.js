/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,js,svelte,ts}', './src/**/*.svelte'],
  theme: {
    extend: {
      // Bernhardt Riley Brand Colors
      colors: {
        // Primary dark navy - headers, primary text
        contrast: {
          DEFAULT: '#181A31',
          light: '#39428E', // contrast-2 for secondary text
        },
        // Teal accent - CTAs, links, highlights
        accent: {
          DEFAULT: '#5AB7A3',
          text: '#316660', // WCAG AA compliant text color (5.2:1 contrast)
          hover: '#49998A',
          light: '#E8F5F2', // 10% opacity background
        },
        // Semantic colors aligned with brand
        primary: {
          50: '#E8F5F2',
          100: '#D1EBE5',
          200: '#A3D7CB',
          300: '#75C3B1',
          400: '#5AB7A3',
          500: '#49998A',
          600: '#3D8075',
          700: '#316660',
          800: '#254D48',
          900: '#193330',
        },
      },
      // Typography
      fontFamily: {
        heading: ['Raleway', 'system-ui', 'sans-serif'],
        body: ['Montserrat', 'system-ui', 'sans-serif'],
      },
      // Standardized border radius
      borderRadius: {
        'btn': '6px',    // Buttons, inputs
        'card': '8px',   // Cards, modals
        'pill': '9999px', // Badges, pills
      },
      // Consistent shadow system
      boxShadow: {
        'sm': '0 1px 2px 0 rgba(24, 26, 49, 0.05)',
        'DEFAULT': '0 1px 3px 0 rgba(24, 26, 49, 0.1), 0 1px 2px -1px rgba(24, 26, 49, 0.1)',
        'md': '0 4px 6px -1px rgba(24, 26, 49, 0.1), 0 2px 4px -2px rgba(24, 26, 49, 0.1)',
        'lg': '0 10px 15px -3px rgba(24, 26, 49, 0.1), 0 4px 6px -4px rgba(24, 26, 49, 0.1)',
        'card': '0 2px 8px 0 rgba(24, 26, 49, 0.08)',
        'dropdown': '0 4px 12px 0 rgba(24, 26, 49, 0.12)',
      },
      // 4px/8px spacing rhythm (Tailwind default, but explicitly documented)
      spacing: {
        '4.5': '1.125rem', // 18px
        '13': '3.25rem',   // 52px
        '15': '3.75rem',   // 60px
        '18': '4.5rem',    // 72px
      },
    },
  },
  plugins: [],
}
