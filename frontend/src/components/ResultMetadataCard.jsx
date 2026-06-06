import { motion } from 'framer-motion'
import { Clock, FileImage, FileText, Hash } from 'lucide-react'

import { formatDuration } from '../utils/performanceMetrics'
import Card from './ui/Card'

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg']

function detectFileType(filename) {
  if (!filename) return 'document'
  const ext = filename.toLowerCase().split('.').pop()
  return IMAGE_EXTENSIONS.includes(ext) ? 'image' : 'document'
}

const cardVariants = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1], delay: 0.1 },
  },
}

function Field({ label, value, tone = 'default', testId }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
        {label}
      </span>
      <span
        data-testid={testId}
        className={[
          'font-mono text-sm',
          tone === 'verified' && 'text-verified',
          tone === 'inaccurate' && 'text-inaccurate',
          tone === 'false' && 'text-false',
          tone === 'default' && 'text-text-primary',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {value}
      </span>
    </div>
  )
}

export default function ResultMetadataCard({
  filename,
  fileType,
  summary,
  processingDurationMs = null,
  processingTimeSeconds = null,
  totalClaims = null,
}) {
  const resolvedType = fileType ?? detectFileType(filename)
  const verified = summary?.verified ?? 0
  const inaccurate = summary?.inaccurate ?? 0
  const falseClaims = summary?.false ?? 0
  const total =
    totalClaims ?? summary?.total ?? verified + inaccurate + falseClaims

  const durationMs =
    typeof processingDurationMs === 'number'
      ? processingDurationMs
      : typeof processingTimeSeconds === 'number'
        ? processingTimeSeconds * 1000
        : null

  const FileTypeIcon = resolvedType === 'image' ? FileImage : FileText

  return (
    <motion.div
      variants={cardVariants}
      initial="initial"
      animate="animate"
      data-testid="result-metadata-card"
    >
      <Card>
        <div className="flex items-center gap-2">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-text-muted">
            Result Metadata
          </p>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <Field
            label="Input Type"
            value={
              <span className="inline-flex items-center gap-1.5">
                <FileTypeIcon className="h-3.5 w-3.5" aria-hidden />
                {resolvedType === 'image' ? 'Image' : 'Document'}
              </span>
            }
            testId="meta-input-type"
          />
          <Field
            label="Filename"
            value={filename ?? '—'}
            testId="meta-filename"
          />
          <Field
            label="Claims Found"
            value={total}
            tone="default"
            testId="meta-claims-total"
          />
          <Field
            label="Verified"
            value={verified}
            tone="verified"
            testId="meta-verified"
          />
          <Field
            label="Inaccurate"
            value={inaccurate}
            tone="inaccurate"
            testId="meta-inaccurate"
          />
          <Field
            label="False"
            value={falseClaims}
            tone="false"
            testId="meta-false"
          />
        </div>

        {durationMs !== null ? (
          <div className="mt-4 flex items-center gap-2 border-t border-bg-border pt-3 font-mono text-[11px] uppercase tracking-wider text-text-muted">
            <Clock className="h-3.5 w-3.5" aria-hidden />
            <span>Processing Time:</span>
            <span data-testid="meta-processing-time" className="text-text-primary">
              {formatDuration(durationMs)}
            </span>
          </div>
        ) : (
          <div
            data-testid="meta-processing-time-empty"
            className="mt-4 flex items-center gap-2 border-t border-bg-border pt-3 font-mono text-[11px] uppercase tracking-wider text-text-muted"
          >
            <Clock className="h-3.5 w-3.5" aria-hidden />
            <span>Processing Time:</span>
            <span className="inline-flex items-center gap-1">
              <Hash className="h-3 w-3" aria-hidden />
              not measured
            </span>
          </div>
        )}
      </Card>
    </motion.div>
  )
}
