import { useState } from 'react'
import { motion } from 'framer-motion'
import { Eye, FileSearch, FileText, Printer, Search } from 'lucide-react'

import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ClaimCard from '../components/ClaimCard'
import SummaryBar from '../components/SummaryBar'
import { fadeIn, slideUp } from '../lib/motion'
import { openReport } from '../utils/reportGenerator'

const SUMMARY_CARDS = [
  { id: 'verified', label: 'Verified', color: 'text-verified', numClass: 'text-verified' },
  { id: 'inaccurate', label: 'Inaccurate', color: 'text-inaccurate', numClass: 'text-inaccurate' },
  { id: 'false', label: 'False', color: 'text-false', numClass: 'text-false' },
]

const cardVariants = {
  initial: { opacity: 0, y: 16 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: [0.22, 1, 0.36, 1] },
  },
}

const listVariants = {
  initial: {},
  animate: {
    transition: { staggerChildren: 0.08, delayChildren: 0.2 },
  },
}

function FileInfoRow({ filename, total }) {
  return (
    <div className="flex items-center gap-3 font-mono text-sm text-text-secondary">
      <span className="flex h-9 w-9 items-center justify-center rounded-md border border-bg-border bg-bg-surface text-text-secondary">
        <FileText className="h-4 w-4" aria-hidden />
      </span>
      <span className="truncate text-text-primary">{filename ?? 'document.pdf'}</span>
      {typeof total === 'number' ? (
        <span className="text-text-muted">
          &middot; {total} claim{total === 1 ? '' : 's'} analyzed
        </span>
      ) : null}
    </div>
  )
}

function SummaryNumbers({ summary }) {
  const safe = {
    verified: summary?.verified ?? 0,
    inaccurate: summary?.inaccurate ?? 0,
    false: summary?.false ?? 0,
  }
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {SUMMARY_CARDS.map((c, i) => (
        <motion.div
          key={c.id}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: 'easeOut', delay: i * 0.08 }}
        >
          <Card className="!p-5">
            <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
              {c.label}
            </span>
            <p
              className={`mt-3 font-display text-4xl font-semibold tracking-tight sm:text-5xl ${c.numClass}`}
            >
              {safe[c.id]}
            </p>
            <p className="mt-1 text-xs text-text-secondary">claims</p>
          </Card>
        </motion.div>
      ))}
    </div>
  )
}

function Divider({ label }) {
  return (
    <div className="flex items-center gap-4">
      <span className="h-px flex-1 bg-bg-border" aria-hidden />
      <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-text-muted">
        {label}
      </span>
      <span className="h-px flex-1 bg-bg-border" aria-hidden />
    </div>
  )
}

export default function ResultsDashboard({ results, onReset, processingDurationMs = null }) {
  const [reportNotice, setReportNotice] = useState(null)

  const handleViewReport = () => {
    const ok = openReport(results, { print: false, processingDurationMs })
    if (!ok) setReportNotice('Popup blocked — allow popups for this site to view the report.')
    else setReportNotice(null)
  }

  const handleExportReport = () => {
    const ok = openReport(results, { print: true, processingDurationMs })
    if (!ok) setReportNotice('Popup blocked — allow popups for this site to export the report.')
    else setReportNotice(null)
  }

  if (!results) {
    return (
      <motion.div className="mx-auto w-full max-w-[700px]" {...slideUp}>
        <Card>
          <EmptyState
            icon={<FileSearch className="h-6 w-6" aria-hidden />}
            title="No analysis yet"
            description="Upload a document to see the verification report."
            action={
              <Button variant="outline" onClick={onReset} className="uppercase tracking-wider">
                Start over
              </Button>
            }
          />
        </Card>
      </motion.div>
    )
  }

  const summary = results.summary ?? {}
  const claims = Array.isArray(results.claims) ? results.claims : []
  const total = summary?.total ?? claims.length

  return (
    <motion.div className="mx-auto w-full max-w-[860px] space-y-10" {...slideUp}>
      <motion.div {...fadeIn}>
        <FileInfoRow filename={results.filename} total={total} />
      </motion.div>

      <SummaryNumbers summary={summary} />

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.25 }}
      >
        <SummaryBar summary={summary} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        <Divider label="Claim Analysis" />
      </motion.div>

      {claims.length > 0 ? (
        <motion.ul
          className="space-y-4"
          variants={listVariants}
          initial="initial"
          animate="animate"
        >
          {claims.map((claim) => (
            <motion.li key={claim.id} variants={cardVariants}>
              <ClaimCard claim={claim} />
            </motion.li>
          ))}
        </motion.ul>
      ) : (
        <Card>
          <EmptyState
            icon={<Search className="h-6 w-6" aria-hidden />}
            title="No verifiable claims found"
            description="TruthLayer could not identify any factual claims in this document."
          />
        </Card>
      )}

      <motion.div
        className="flex flex-col items-center gap-3 pt-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.6 }}
      >
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Button
            variant="outline"
            onClick={handleViewReport}
            className="uppercase tracking-wider"
          >
            <Eye className="h-4 w-4" aria-hidden />
            View Report
          </Button>
          <Button
            variant="outline"
            onClick={handleExportReport}
            className="uppercase tracking-wider"
          >
            <Printer className="h-4 w-4" aria-hidden />
            Export Report
          </Button>
          <Button
            variant="outline"
            onClick={onReset}
            className="uppercase tracking-wider"
          >
            Analyze Another Document
          </Button>
        </div>
        {reportNotice ? (
          <p className="font-mono text-xs text-inaccurate">{reportNotice}</p>
        ) : null}
      </motion.div>
    </motion.div>
  )
}
