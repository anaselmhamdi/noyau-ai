/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        // Core palette (dark-first)
        ink: '#0B0F14',
        slate: '#111827',
        'slate-hover': '#1a2332',
        border: '#223047',
        'border-hover': '#2d3f5a',
        text: '#E5E7EB',
        muted: '#94A3B8',

        // Accent colors
        signal: '#22D3EE',
        'signal-muted': 'rgba(34, 211, 238, 0.15)',
        macro: '#F59E0B',
        good: '#22C55E',
        bad: '#EF4444',

        // Legacy aliases (for gradual migration)
        bg: '#0B0F14',
        surface: '#111827',
        'text-primary': '#E5E7EB',
        'text-secondary': '#94A3B8',
        accent: '#22D3EE',
        highlight: '#22C55E',
        locked: '#EF4444',
      },
      fontFamily: {
        // IBM Plex: technical, editorial, distinctive
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        display: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        // Type scale per visual identity
        'display': ['2.5rem', { lineHeight: '1.1', letterSpacing: '-0.02em', fontWeight: '700' }],
        'h1': ['1.875rem', { lineHeight: '1.2', letterSpacing: '-0.01em', fontWeight: '700' }],
        'h2': ['1.25rem', { lineHeight: '1.3', letterSpacing: '-0.01em', fontWeight: '600' }],
        'body': ['0.9375rem', { lineHeight: '1.6', fontWeight: '400' }],
        'meta': ['0.8125rem', { lineHeight: '1.4', fontWeight: '500' }],
        'micro': ['0.75rem', { lineHeight: '1.4', fontWeight: '500' }],
      },
      borderRadius: {
        'card': '16px',
        'pill': '9999px',
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      transitionDuration: {
        'hover': '150ms',
        'smooth': '300ms',
      },
      transitionTimingFunction: {
        'smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      boxShadow: {
        'card-hover': '0 8px 24px -8px rgba(0, 0, 0, 0.4)',
        'glow': '0 0 20px rgba(34, 211, 238, 0.15)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out forwards',
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
        'pulse-subtle': 'pulseSubtle 2s ease-in-out infinite',
        'shimmer': 'shimmer 1.5s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseSubtle: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      backgroundImage: {
        'grid-pattern': 'linear-gradient(rgba(34, 211, 238, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(34, 211, 238, 0.03) 1px, transparent 1px)',
        'gradient-fade': 'linear-gradient(to top, var(--tw-gradient-from), transparent)',
      },
      backgroundSize: {
        'grid': '48px 48px',
      },
    },
  },
  plugins: [],
};
