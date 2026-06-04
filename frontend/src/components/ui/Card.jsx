export default function Card({ children, className = '' }) {
  return (
    <div
      className={[
        'rounded-xl border border-bg-border bg-bg-surface p-6 transition-colors hover:bg-bg-elevated',
        className,
      ].join(' ')}
    >
      {children}
    </div>
  )
}
