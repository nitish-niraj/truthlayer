import { createElement } from 'react'
import { renderToString } from 'react-dom/server'

import VerificationReport from '../components/VerificationReport'
import { computeMetrics } from './performanceMetrics'

const REPORT_FONTS =
  "https://fonts.googleapis.com/css2?family=Syne:wght@500;600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap"

const REPORT_CSS = `
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: #FAFAFA;
  color: #111318;
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}
@media print {
  body { background: #FFFFFF; }
  a { color: inherit; text-decoration: underline; }
}
`

function buildHtmlDoc({ body, autoPrint }) {
  const printScript = autoPrint
    ? '<script>window.addEventListener("load", function(){ setTimeout(function(){ window.print(); }, 250); });</script>'
    : ''
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>TruthLayer — Verification Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="stylesheet" href="${REPORT_FONTS}" />
<style>${REPORT_CSS}</style>
</head>
<body>
${body}
${printScript}
</body>
</html>`
}

export function renderReportHtml(results, options = {}) {
  const { processingDurationMs = null } = options
  const metrics = computeMetrics(results, processingDurationMs)
  const claims = Array.isArray(results?.claims) ? results.claims : []
  return renderToString(
    createElement(VerificationReport, { metrics, claims })
  )
}

export function openReport(results, options = {}) {
  const { print = false, processingDurationMs = null } = options
  const body = renderReportHtml(results, { processingDurationMs })
  const html = buildHtmlDoc({ body, autoPrint: print })
  const win = window.open('', '_blank')
  if (!win) return false
  win.document.open()
  win.document.write(html)
  win.document.close()
  return true
}
