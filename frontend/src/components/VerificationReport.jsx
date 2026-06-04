import QASummary from './QASummary'

const VERDICT_LABELS = {
  verified: 'VERIFIED',
  inaccurate: 'INACCURATE',
  false: 'FALSE',
}

const VERDICT_COLORS = {
  verified: { fg: '#16A34A', bg: '#DCFCE7', border: '#86EFAC' },
  inaccurate: { fg: '#D97706', bg: '#FEF3C7', border: '#FCD34D' },
  false: { fg: '#DC2626', bg: '#FEE2E2', border: '#FCA5A5' },
}

const styles = {
  page: {
    background: '#FAFAFA',
    color: '#111318',
    fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
    padding: '40px 48px',
    minHeight: '100vh',
    boxSizing: 'border-box',
    WebkitFontSmoothing: 'antialiased',
  },
  header: {
    borderBottom: '2px solid #111318',
    paddingBottom: 16,
    marginBottom: 24,
  },
  brand: {
    fontFamily: "'Syne', 'IBM Plex Sans', sans-serif",
    fontSize: 11,
    letterSpacing: '0.32em',
    textTransform: 'uppercase',
    color: '#6B7280',
    margin: 0,
  },
  title: {
    fontFamily: "'Syne', 'IBM Plex Sans', sans-serif",
    fontSize: 28,
    fontWeight: 700,
    margin: '6px 0 4px 0',
    color: '#111318',
    letterSpacing: '-0.01em',
  },
  subtitle: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 12,
    color: '#6B7280',
    margin: 0,
  },
  sectionTitle: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 10,
    letterSpacing: '0.22em',
    textTransform: 'uppercase',
    color: '#6B7280',
    margin: '0 0 14px 0',
  },
  claimCard: {
    background: '#FFFFFF',
    border: '1px solid #E4E6EB',
    borderRadius: 8,
    padding: 20,
    marginBottom: 16,
    pageBreakInside: 'avoid',
  },
  claimHead: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  claimNumber: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 10,
    color: '#6B7280',
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
  },
  claimType: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 10,
    color: '#6B7280',
    marginLeft: 10,
    padding: '2px 8px',
    background: '#F3F4F6',
    borderRadius: 4,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  badge: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.16em',
    padding: '4px 10px',
    borderRadius: 4,
    textTransform: 'uppercase',
  },
  claimText: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 13,
    lineHeight: 1.6,
    color: '#111318',
    background: '#F9FAFB',
    borderLeft: '3px solid #E4E6EB',
    padding: '12px 14px',
    borderRadius: 4,
    margin: '0 0 14px 0',
  },
  fieldLabel: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 9,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    color: '#6B7280',
    margin: '0 0 4px 0',
  },
  fieldBody: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 12,
    lineHeight: 1.6,
    color: '#374151',
    margin: '0 0 12px 0',
  },
  correctFact: {
    background: '#FFFBEB',
    border: '1px solid #FCD34D',
    borderLeft: '4px solid #D97706',
    borderRadius: 4,
    padding: '12px 14px',
    margin: '0 0 12px 0',
  },
  correctFactLabel: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 9,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    color: '#92400E',
    margin: '0 0 4px 0',
    fontWeight: 600,
  },
  correctFactBody: {
    fontFamily: "'IBM Plex Sans', sans-serif",
    fontSize: 12,
    lineHeight: 1.6,
    color: '#78350F',
    margin: 0,
  },
  sourceLink: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 11,
    color: '#2563EB',
    textDecoration: 'none',
    wordBreak: 'break-all',
  },
  footer: {
    marginTop: 32,
    paddingTop: 16,
    borderTop: '1px solid #E4E6EB',
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 10,
    color: '#6B7280',
    textAlign: 'center',
    letterSpacing: '0.1em',
  },
}

function VerdictBadge({ verdict }) {
  const colors = VERDICT_COLORS[verdict] || VERDICT_COLORS.false
  return (
    <span
      style={{
        ...styles.badge,
        color: colors.fg,
        background: colors.bg,
        border: `1px solid ${colors.border}`,
      }}
    >
      {VERDICT_LABELS[verdict] || 'UNKNOWN'}
    </span>
  )
}

function ClaimBlock({ claim, index, total }) {
  const verdict = claim.verdict
  const hasCorrectFact =
    typeof claim.correct_fact === 'string' && claim.correct_fact.trim().length > 0
  const hasSourceUrl =
    typeof claim.source_url === 'string' && claim.source_url.trim().length > 0

  return (
    <article style={styles.claimCard}>
      <div style={styles.claimHead}>
        <div>
          <span style={styles.claimNumber}>
            Claim {String(index + 1).padStart(2, '0')} of {String(total).padStart(2, '0')}
          </span>
          {claim.type ? <span style={styles.claimType}>{claim.type}</span> : null}
        </div>
        <VerdictBadge verdict={verdict} />
      </div>

      <p style={styles.claimText}>{claim.claim}</p>

      <p style={styles.fieldLabel}>Source sentence</p>
      <p style={styles.fieldBody}>{claim.source_sentence || '—'}</p>

      <p style={styles.fieldLabel}>Explanation</p>
      <p style={styles.fieldBody}>{claim.explanation || '—'}</p>

      {hasCorrectFact ? (
        <div style={styles.correctFact}>
          <p style={styles.correctFactLabel}>Correct fact</p>
          <p style={styles.correctFactBody}>{claim.correct_fact}</p>
        </div>
      ) : null}

      {hasSourceUrl ? (
        <>
          <p style={styles.fieldLabel}>Reference</p>
          <a style={styles.sourceLink} href={claim.source_url} target="_blank" rel="noreferrer">
            {claim.source_url}
          </a>
        </>
      ) : null}
    </article>
  )
}

export default function VerificationReport({ metrics, claims = [] }) {
  const safeClaims = Array.isArray(claims) ? claims : []
  const total = safeClaims.length
  const filename = metrics?.filename ?? 'document.pdf'
  const analyzedAt = metrics?.analyzedAt ?? new Date().toISOString()

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <p style={styles.brand}>TruthLayer</p>
        <h1 style={styles.title}>Verification Report</h1>
        <p style={styles.subtitle}>{filename}</p>
      </header>

      <QASummary metrics={metrics} />

      <h3 style={styles.sectionTitle}>Claim Analysis</h3>
      {total > 0 ? (
        safeClaims.map((claim, i) => (
          <ClaimBlock key={claim.id ?? i} claim={claim} index={i} total={total} />
        ))
      ) : (
        <p style={styles.fieldBody}>No verifiable claims were found in this document.</p>
      )}

      <footer style={styles.footer}>
        Generated by TruthLayer · {new Date(analyzedAt).toUTCString()}
      </footer>
    </div>
  )
}
