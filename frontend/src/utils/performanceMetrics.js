function safeCount(summary, key) {
  const v = summary?.[key]
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

export function formatDuration(ms) {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const totalSeconds = ms / 1000
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = Math.floor(totalSeconds % 60)
  return `${minutes}m ${seconds.toString().padStart(2, '0')}s`
}

export function formatAnalyzedAt(input) {
  const date = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n) => n.toString().padStart(2, '0')
  const yyyy = date.getFullYear()
  const mm = pad(date.getMonth() + 1)
  const dd = pad(date.getDate())
  const hh = pad(date.getHours())
  const mi = pad(date.getMinutes())
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`
}

export function computeMetrics(results, processingDurationMs = null) {
  const summary = results?.summary ?? {}
  const claims = Array.isArray(results?.claims) ? results.claims : []
  const total = safeCount(summary, 'total') || claims.length
  const verified = safeCount(summary, 'verified')
  const inaccurate = safeCount(summary, 'inaccurate')
  const falseClaims = safeCount(summary, 'false')

  const withCorrectFact = claims.filter(
    (c) => typeof c.correct_fact === 'string' && c.correct_fact.trim().length > 0
  ).length
  const withSourceUrl = claims.filter(
    (c) => typeof c.source_url === 'string' && c.source_url.trim().length > 0
  ).length

  return {
    filename: results?.filename ?? 'document.pdf',
    totalClaims: total,
    verified,
    inaccurate,
    falseClaims,
    processingDurationMs:
      typeof processingDurationMs === 'number' && Number.isFinite(processingDurationMs)
        ? processingDurationMs
        : null,
    sourceCoverage: total > 0 ? `${withSourceUrl}/${total}` : '—',
    correctFactCoverage: total > 0 ? `${withCorrectFact}/${total}` : '—',
    searchCalls: '—',
    analyzedAt: new Date().toISOString(),
  }
}
