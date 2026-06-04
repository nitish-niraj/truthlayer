import { motion } from 'framer-motion'

export default function SummaryBar({ summary }) {
  const total =
    (summary?.verified ?? 0) +
    (summary?.inaccurate ?? 0) +
    (summary?.false ?? 0)
  const safeTotal = total > 0 ? total : 1
  const v = (summary?.verified ?? 0) / safeTotal
  const i = (summary?.inaccurate ?? 0) / safeTotal
  const f = (summary?.false ?? 0) / safeTotal

  const segments = [
    { id: 'verified', pct: v * 100, color: 'bg-verified', delay: 0 },
    { id: 'inaccurate', pct: i * 100, color: 'bg-inaccurate', delay: 0.1 },
    { id: 'false', pct: f * 100, color: 'bg-false', delay: 0.2 },
  ]

  return (
    <div>
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-bg-elevated"
        role="img"
        aria-label="Verdict distribution"
      >
        {segments.map((seg) => (
          <motion.div
            key={seg.id}
            className={`h-full ${seg.color}`}
            initial={{ width: 0 }}
            animate={{ width: `${seg.pct}%` }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: seg.delay }}
          />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] uppercase tracking-wider text-text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-verified" aria-hidden />
          {summary?.verified ?? 0} verified
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-inaccurate" aria-hidden />
          {summary?.inaccurate ?? 0} inaccurate
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-false" aria-hidden />
          {summary?.false ?? 0} false
        </span>
      </div>
    </div>
  )
}
