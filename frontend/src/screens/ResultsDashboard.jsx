import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Eye,
  FileImage,
  FileSearch,
  FileText,
  Image as ImageIcon,
  Printer,
  Search,
} from 'lucide-react'

import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ClaimCard from '../components/ClaimCard'
import SummaryBar from '../components/SummaryBar'
import FilePreviewCard from '../components/FilePreviewCard'
import ResultMetadataCard from '../components/ResultMetadataCard'
import { fadeIn, slideUp } from '../lib/motion'
import { openReport } from '../utils/reportGenerator'

const SUMMARY_CARDS = [
  { id: 'verified', label: 'Verified', color: 'text-verified', numClass: 'text-verified' },
  { id: 'inaccurate', label: 'Inaccurate', color: 'text-inaccurate', numClass: 'text-inaccurate' },
  { id: 'false', label: 'False', color: 'text-false', numClass: 'text-false' },
]

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg']

function detectInputType(filename, explicitType) {
  if (explicitType === 'image' || explicitType === 'document') return explicitType
  if (!filename) return 'document'
  const ext = filename.toLowerCase().split('.').pop()
  return IMAGE_EXTENSIONS.includes(ext) ? 'image' : 'document'
}

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

const EMPTY_IMAGE_HINTS = [
  'Statistics screenshots',
  'News snippets',
  'Charts',
  'Infographics',
  'Social media posts',
]

function ImageEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-bg-border bg-bg-elevated text-text-secondary">
        <ImageIcon className="h-6 w-6" aria-hidden />
      </div>
      <h2 className="font-display text-lg font-semibold text-text-primary">
        No verifiable claims detected
      </h2>
      <p className="mt-2 max-w-sm text-sm text-text-secondary">
        TruthLayer could not identify any factual claims in this image.
      </p>
      <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.18em] text-text-muted">
        Try uploading
      </p>
      <ul className="mt-3 flex flex-wrap justify-center gap-2">
        {EMPTY_IMAGE_HINTS.map((hint) => (
          <li
            key={hint}
            className="inline-flex items-center rounded-full border border-bg-border bg-bg-surface px-3 py-1 font-mono text-[11px] uppercase tracking-wider text-text-secondary"
          >
            {hint}
          </li>
        ))}
      </ul>
    </div>
  )
}

function DocumentEmptyState() {
  return (
    <EmptyState
      icon={<FileSearch className="h-6 w-6" aria-hidden />}
      title="No verifiable claims found"
      description="TruthLayer could not identify any factual claims in this document."
    />
  )
}

export default function ResultsDashboard({
  results,
  onReset,
  processingDurationMs = null,
  processingTimeSeconds = null,
  previewUrl = null,
  fileType = null,
  fileSize = null,
  pages = null,
}) {
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
  const inputType = detectInputType(results.filename, fileType)
  const resetLabel =
    inputType === 'image' ? 'Verify Another Image' : 'Analyze Another Document'

  const metadataProcessingSeconds =
    processingTimeSeconds ??
    (typeof processingDurationMs === 'number' ? processingDurationMs / 1000 : null)

  return (
    <motion.div className="mx-auto w-full max-w-[860px] space-y-8" {...slideUp}>
      {inputType === 'image' ? (
        <FilePreviewCard
          filename={results.filename}
          fileType={inputType}
          previewUrl={previewUrl}
          fileSize={fileSize}
        />
      ) : null}

      <motion.div {...fadeIn}>
        <ResultMetadataCard
          filename={results.filename}
          fileType={inputType}
          summary={summary}
          processingDurationMs={processingDurationMs}
          processingTimeSeconds={metadataProcessingSeconds}
          totalClaims={total}
        />
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

      <AnimatePresence mode="wait">
        {claims.length > 0 ? (
          <motion.ul
            key="claims"
            className="space-y-4"
            variants={listVariants}
            initial="initial"
            animate="animate"
            exit={{ opacity: 0 }}
          >
            {claims.map((claim) => (
              <motion.li key={claim.id} variants={cardVariants}>
                <ClaimCard claim={claim} />
              </motion.li>
            ))}
          </motion.ul>
        ) : (
          <motion.div
            key="empty"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <Card>
              {inputType === 'image' ? <ImageEmptyState /> : <DocumentEmptyState />}
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

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
            {resetLabel}
          </Button>
        </div>
        {reportNotice ? (
          <p className="font-mono text-xs text-inaccurate">{reportNotice}</p>
        ) : null}
      </motion.div>
    </motion.div>
  )
}
