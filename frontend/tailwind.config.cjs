module.exports = {
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['Syne', 'system-ui', 'sans-serif'],
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        'bg-base': 'var(--bg-base)',
        'bg-surface': 'var(--bg-surface)',
        'bg-elevated': 'var(--bg-elevated)',
        'bg-border': 'var(--bg-border)',
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted': 'var(--text-muted)',
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          dim: 'var(--accent-dim)',
        },
        verified: {
          DEFAULT: 'var(--verified)',
          bg: 'var(--verified-bg)',
        },
        inaccurate: {
          DEFAULT: 'var(--inaccurate)',
          bg: 'var(--inaccurate-bg)',
        },
        false: {
          DEFAULT: 'var(--false)',
          bg: 'var(--false-bg)',
        },
      },
    },
  },
  plugins: [],
}
