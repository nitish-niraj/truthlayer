import { formatDuration, formatAnalyzedAt } from '../utils/performanceMetrics'

const styles = {
  wrap: {
    background: '#FFFFFF',
    border: '1px solid #E4E6EB',
    borderRadius: 8,
    padding: 20,
    marginBottom: 28,
  },
  title: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 10,
    letterSpacing: '0.22em',
    textTransform: 'uppercase',
    color: '#6B7280',
    margin: '0 0 14px 0',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    columnGap: 24,
    rowGap: 10,
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    borderBottom: '1px dotted #E4E6EB',
    paddingBottom: 6,
  },
  key: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 11,
    color: '#6B7280',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  val: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 12,
    color: '#111318',
    fontWeight: 500,
  },
  valVerified: { color: '#16A34A' },
  valInaccurate: { color: '#D97706' },
  valFalse: { color: '#DC2626' },
}

function Row({ label, value, valueStyle }) {
  return (
    <div style={styles.row}>
      <span style={styles.key}>{label}</span>
      <span style={{ ...styles.val, ...(valueStyle || {}) }}>{value}</span>
    </div>
  )
}

export default function QASummary({ metrics }) {
  if (!metrics) return null
  const {
    filename,
    analyzedAt,
    totalClaims,
    verified,
    inaccurate,
    falseClaims,
    processingDurationMs,
    sourceCoverage,
    correctFactCoverage,
    searchCalls,
  } = metrics

  return (
    <section style={styles.wrap}>
      <h3 style={styles.title}>QA Summary</h3>
      <div style={styles.grid}>
        <Row label="File" value={filename} />
        <Row label="Analyzed" value={formatAnalyzedAt(analyzedAt)} />
        <Row label="Total claims" value={totalClaims} />
        <Row
          label="Verified"
          value={verified}
          valueStyle={styles.valVerified}
        />
        <Row
          label="Inaccurate"
          value={inaccurate}
          valueStyle={styles.valInaccurate}
        />
        <Row
          label="False"
          value={falseClaims}
          valueStyle={styles.valFalse}
        />
        <Row label="Processing" value={formatDuration(processingDurationMs)} />
        <Row label="Search calls" value={searchCalls} />
        <Row label="Sources covered" value={sourceCoverage} />
        <Row label="Correct facts" value={correctFactCoverage} />
      </div>
    </section>
  )
}
