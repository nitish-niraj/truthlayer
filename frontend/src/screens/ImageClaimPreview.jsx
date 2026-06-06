import { useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  FileImage,
  ScanSearch,
  Sparkles,
} from 'lucide-react'

import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { fadeIn, slideUp } from '../lib/motion'

const TYPE_LABELS = {
  statistic: 'Statistic',
  financial: 'Financial',
  date: 'Date',
  technical: 'Technical',
  attribution: 'Attribution',
}

export default function ImageClaimPreview({
  filename,
  imageUrl,
  claims = [],
  onReset,
  onExtractAnother,
}) {
  // Revoke the object URL when the component unmounts so the browser
  // releases the blob memory.
  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl)
    }
  }, [imageUrl])

  const sortedClaims = useMemo(
    () => [...claims].sort((a, b) => (a.id ?? 0) - (b.id ?? 0)),
    [claims],
  )

  const claimCount = sortedClaims.length
  const noClaims = claimCount === 0

  return (
    <motion.div className="mx-auto w-full max-w-[800px]" {...slideUp}>
      {/* Header */}
      <motion.header className="mb-8 text-center" {...fadeIn}>
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-text-primary sm:text-[36px]">
          Extracted Claims
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm text-text-secondary sm:text-base">
          Kimi Vision found <span className="text-accent">{claimCount}</span>{' '}
          verifiable claim{claimCount === 1 ? '' : 's'} in your image.
        </p>
      </motion.header>

      {/* Filename + preview */}
      <Card className="!p-5">
        <div className="flex items-center gap-4">
          {imageUrl ? (
            <div className="h-16 w-16 shrink-0 overflow-hidden rounded-md border border-bg-border bg-bg-elevated">
              <img
                src={imageUrl}
                alt={filename}
                className="h-full w-full object-cover"
              />
            </div>
          ) : (
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-bg-border bg-bg-elevated text-text-secondary">
              <FileImage className="h-5 w-5" aria-hidden />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
              Source
            </p>
            <p className="mt-0.5 truncate font-mono text-sm text-text-primary">
              {filename}
            </p>
          </div>
          <Badge variant="neutral">Claims Found: {claimCount}</Badge>
        </div>
      </Card>

      {/* Claims list */}
      <div className="mt-6 space-y-3">
        {noClaims ? (
          <Card className="!p-6 text-center">
            <ScanSearch className="mx-auto h-8 w-8 text-text-muted" aria-hidden />
            <p className="mt-3 text-sm text-text-secondary">
              No verifiable factual claims were detected in this image.
            </p>
            <p className="mt-1 font-mono text-xs text-text-muted">
              The image may contain only opinions, marketing copy, or imagery
              without measurable facts.
            </p>
          </Card>
        ) : (
          sortedClaims.map((claim, idx) => (
            <motion.div key={`${claim.id ?? idx}-${idx}`} {...fadeIn}>
              <Card className="!p-5">
                <div className="flex items-start justify-between gap-3">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                    Claim #{idx + 1}
                  </p>
                  <Badge variant="neutral">
                    {TYPE_LABELS[claim.type] ?? claim.type}
                  </Badge>
                </div>
                <p className="mt-3 break-words font-mono text-sm leading-relaxed text-text-primary">
                  {claim.claim}
                </p>
                {claim.source_sentence ? (
                  <p className="mt-2 break-words font-sans text-xs italic text-text-muted">
                    &ldquo;{claim.source_sentence}&rdquo;
                  </p>
                ) : null}
              </Card>
            </motion.div>
          ))
        )}
      </div>

      {/* Footer note about Phase 2 scope */}
      {!noClaims ? (
        <motion.div {...fadeIn} className="mt-6">
          <Card className="!p-4 border-l-4 border-l-accent">
            <div className="flex items-start gap-3">
              <Sparkles className="h-4 w-4 shrink-0 text-accent" aria-hidden />
              <div>
                <p className="font-mono text-[11px] uppercase tracking-wider text-accent">
                  Phase 2 — Extraction only
                </p>
                <p className="mt-1 text-xs text-text-secondary">
                  Claims are extracted but not yet verified. Web search and
                  verdict generation are coming in a later phase.
                </p>
              </div>
            </div>
          </Card>
        </motion.div>
      ) : null}

      {/* Actions */}
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Button onClick={onExtractAnother ?? onReset} variant="primary">
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Upload Another Image
        </Button>
      </div>
    </motion.div>
  )
}
