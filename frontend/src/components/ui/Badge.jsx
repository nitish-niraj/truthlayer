const VARIANTS = {
  verified: 'bg-verified-bg text-verified border-verified/20',
  inaccurate: 'bg-inaccurate-bg text-inaccurate border-inaccurate/20',
  false: 'bg-false-bg text-false border-false/20',
  neutral: 'bg-bg-elevated text-text-secondary border-bg-border',
}

export default function Badge({ children, variant = 'neutral', className = '' }) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-wider',
        VARIANTS[variant] || VARIANTS.neutral,
        className,
      ].join(' ')}
    >
      {children}
    </span>
  )
}
