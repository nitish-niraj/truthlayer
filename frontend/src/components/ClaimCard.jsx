import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  XCircle,
} from 'lucide-react'
import Card from './ui/Card'
import Badge from './ui/Badge'

const VERDICT_META = {
  verified: {
    label: 'Verified',
    Icon: CheckCircle2,
    badgeVariant: 'verified',
    leftBorder: 'border-l-verified',
  },
  inaccurate: {
    label: 'Inaccurate',
    Icon: AlertTriangle,
    badgeVariant: 'inaccurate',
    leftBorder: 'border-l-inaccurate',
  },
  false: {
    label: 'False',
    Icon: XCircle,
    badgeVariant: 'false',
    leftBorder: 'border-l-false',
  },
}

export default function ClaimCard({ claim }) {
  if (!claim) return null

  const meta = VERDICT_META[claim.verdict] || VERDICT_META.false
  const VerdictIcon = meta.Icon
  const showCorrectFact =
    claim.verdict !== 'verified' && claim.correct_fact && claim.correct_fact.trim().length > 0
  const showSource = claim.source_url && claim.source_url.trim().length > 0

  return (
    <Card className={`!p-6 border-l-4 ${meta.leftBorder}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge variant={meta.badgeVariant}>
          <VerdictIcon className="h-3 w-3" aria-hidden />
          {meta.label}
        </Badge>
        {claim.type ? (
          <span className="inline-flex items-center rounded-full border border-bg-border bg-bg-elevated px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-wider text-text-secondary">
            {claim.type}
          </span>
        ) : null}
      </div>

      <p className="mt-4 break-words font-mono text-sm leading-relaxed text-text-primary">
        {claim.claim}
      </p>

      {claim.source_sentence ? (
        <p className="mt-2 break-words font-sans text-xs italic text-text-muted">
          &ldquo;{claim.source_sentence}&rdquo;
        </p>
      ) : null}

      {claim.explanation ? (
        <p className="mt-3 break-words text-sm leading-relaxed text-text-secondary">
          {claim.explanation}
        </p>
      ) : null}

      {showCorrectFact ? (
        <div className="mt-4 rounded-md border-l-2 border-accent bg-accent-dim/30 py-2.5 pl-4 pr-3">
          <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
            Correct fact
          </p>
          <p className="mt-1 break-words text-sm text-text-primary">
            {claim.correct_fact}
          </p>
        </div>
      ) : null}

      {showSource ? (
        <a
          href={claim.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 inline-flex items-center gap-1.5 text-sm text-accent transition-colors hover:text-accent-hover"
        >
          <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          Source
        </a>
      ) : null}
    </Card>
  )
}
