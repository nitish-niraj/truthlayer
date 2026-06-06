import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, ExternalLink, Globe } from 'lucide-react'

function getHostname(url) {
  if (!url || typeof url !== 'string') return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

function normalizeSources(claim) {
  if (Array.isArray(claim?.evidence) && claim.evidence.length > 0) {
    return claim.evidence
      .map((e) => ({
        url: typeof e?.url === 'string' ? e.url : '',
        title: typeof e?.title === 'string' ? e.title : '',
        domain: e?.domain || getHostname(e?.url),
      }))
      .filter((s) => s.url)
  }
  if (claim?.source_url) {
    return [
      {
        url: claim.source_url,
        title: claim.source_title || '',
        domain: getHostname(claim.source_url),
      },
    ]
  }
  return []
}

function EvidenceRow({ source, index }) {
  return (
    <motion.li
      data-testid="evidence-source"
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2, delay: index * 0.04, ease: 'easeOut' }}
      className="rounded-md border border-bg-border bg-bg-base p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          {source.domain ? (
            <p className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-accent">
              <Globe className="h-3 w-3" aria-hidden />
              <span className="truncate">{source.domain}</span>
            </p>
          ) : null}
          {source.title ? (
            <p className="mt-1 break-words text-sm text-text-primary">
              {source.title}
            </p>
          ) : null}
        </div>
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-bg-border bg-bg-surface px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-text-secondary transition-colors hover:border-accent hover:text-accent"
        >
          <ExternalLink className="h-3 w-3" aria-hidden />
          Open Source
        </a>
      </div>
    </motion.li>
  )
}

export default function EvidencePanel({ claim }) {
  const [expanded, setExpanded] = useState(false)
  const sources = normalizeSources(claim)
  const hasEvidence = sources.length > 0
  const hasCorrectFact =
    claim?.correct_fact && claim.correct_fact.trim().length > 0

  if (!hasEvidence && !hasCorrectFact) {
    return null
  }

  const toggle = () => setExpanded((v) => !v)
  const panelId = `evidence-panel-${claim?.id ?? 'claim'}`

  return (
    <div className="mt-4 border-t border-bg-border pt-4">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={expanded}
        aria-controls={panelId}
        data-testid="evidence-toggle"
        className="group inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-text-secondary transition-colors hover:text-accent"
      >
        <ChevronDown
          className={[
            'h-3.5 w-3.5 transition-transform duration-200',
            expanded ? 'rotate-0' : '-rotate-90',
          ].join(' ')}
          aria-hidden
        />
        {expanded ? 'Hide Evidence' : 'Show Evidence'}
      </button>

      <AnimatePresence initial={false}>
        {expanded ? (
          <motion.div
            key="panel"
            id={panelId}
            data-testid="evidence-panel"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-4 space-y-4">
              {hasCorrectFact ? (
                <div className="rounded-md border-l-2 border-accent bg-accent-dim/30 py-2.5 pl-4 pr-3">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                    Correct Fact
                  </p>
                  <p
                    data-testid="evidence-correct-fact"
                    className="mt-1 break-words text-sm text-text-primary"
                  >
                    {claim.correct_fact}
                  </p>
                </div>
              ) : null}

              {hasEvidence ? (
                <div>
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-wider text-text-muted">
                    Evidence Sources
                  </p>
                  <ul className="space-y-2">
                    {sources.map((source, i) => (
                      <EvidenceRow
                        key={`${source.url}-${i}`}
                        source={source}
                        index={i}
                      />
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
