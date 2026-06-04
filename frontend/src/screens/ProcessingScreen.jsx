import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileSearch,
  FileText,
  Globe,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'

import { pollVerifyUntilDone, startVerify } from '../services/api'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import { fadeIn, slideUp } from '../lib/motion'

const STEPS = [
  {
    id: 'extract',
    title: 'Extracting Text',
    description: 'Reading document structure',
    Icon: FileSearch,
  },
  {
    id: 'claims',
    title: 'Identifying Claims',
    description: 'Finding verifiable facts and statistics',
    Icon: Sparkles,
  },
  {
    id: 'search',
    title: 'Searching Live Sources',
    description: 'Gathering evidence from trusted sources',
    Icon: Globe,
  },
  {
    id: 'verdicts',
    title: 'Generating Verdicts',
    description: 'Comparing evidence and assigning verdicts',
    Icon: ShieldCheck,
  },
]

const STEP_ADVANCE_MS = [2000, 3000, 4000]
const PROGRESS_DURATION_MS = 45_000
const PROGRESS_TICK_MS = 100
const MESSAGE_ROTATE_MS = 3500
const LONG_HINT_MS = 30_000
const COMPLETION_PAUSE_MS = 600
// The polling loop in services/api.js bounds the total wait at 130s; the
// progress bar now reflects that wider window so the user sees smooth
// 0-100% movement instead of a stalled bar.
const POLL_TIMEOUT_MS = 130_000

const STATUS_MESSAGES = [
  'Parsing PDF structure...',
  'Extracting factual claims...',
  'Searching trusted sources...',
  'Comparing evidence...',
  'Generating verdicts...',
]

function getApiErrorMessage(err) {
  if (err?.code === 'ECONNABORTED') {
    return 'Analysis timed out. Please try again or use a smaller document.'
  }
  if (err?.code === 'ERR_NETWORK') return 'Server unavailable'
  if (err?.response?.status === 404) {
    return 'The analysis job was lost (server restarted). Please upload again.'
  }
  if (err?.response?.data?.detail) return err.response.data.detail
  if (err?.message) return err.message
  return 'Unable to complete analysis.'
}

function stepState(index, activeStep, allComplete) {
  if (allComplete) return 'complete'
  if (index < activeStep) return 'complete'
  if (index === activeStep) return 'active'
  return 'waiting'
}

export default function ProcessingScreen({
  uploadData,
  onResults,
  onError,
  onCancel,
}) {
  const [activeStep, setActiveStep] = useState(0)
  const [allComplete, setAllComplete] = useState(false)
  const [error, setError] = useState(null)
  const [progress, setProgress] = useState(0)
  const [messageIndex, setMessageIndex] = useState(0)
  const [showLongHint, setShowLongHint] = useState(false)

  const cancelledRef = useRef(false)
  const timersRef = useRef([])
  const requestStartedAtRef = useRef(0)
  const hasStartedRef = useRef(false)

  const clearTimers = () => {
    timersRef.current.forEach((t) => clearTimeout(t) || clearInterval(t))
    timersRef.current = []
  }

  const scheduleTimer = (fn, delay, isInterval = false) => {
    const id = isInterval
      ? setInterval(() => fn(), delay)
      : setTimeout(() => fn(), delay)
    timersRef.current.push(id)
    return id
  }

  const runAnalysis = useCallback(
    ({ skipRequest = false, isRemount = false } = {}) => {
      if (!uploadData?.text || !uploadData?.filename) {
        onError?.('No document to analyze. Please upload a PDF.')
        return
      }

      cancelledRef.current = false
      setActiveStep(0)
      setAllComplete(false)
      setError(null)
      setProgress(0)
      setMessageIndex(0)
      setShowLongHint(false)
      if (!isRemount) {
        requestStartedAtRef.current = Date.now()
      }

      // Timeline: advance activeStep at 0/2/5/9s
      STEP_ADVANCE_MS.reduce((acc, delay) => acc + delay, 0)
      let cumulative = 0
      STEP_ADVANCE_MS.forEach((delay, i) => {
        cumulative += delay
        scheduleTimer(() => {
          if (!cancelledRef.current) setActiveStep(i + 1)
        }, cumulative)
      })

      // Progress bar: 0 → 90% over 30s, linear
      scheduleTimer(
        () => {
          if (cancelledRef.current) return
          const elapsed = Date.now() - requestStartedAtRef.current
          const pct = Math.min(90, (elapsed / PROGRESS_DURATION_MS) * 90)
          setProgress(pct)
        },
        PROGRESS_TICK_MS,
        true
      )

      // Status message rotation
      scheduleTimer(
        () => {
          if (cancelledRef.current) return
          setMessageIndex((i) => (i + 1) % STATUS_MESSAGES.length)
        },
        MESSAGE_ROTATE_MS,
        true
      )

      // Long-hint at 30s
      scheduleTimer(() => {
        if (!cancelledRef.current) setShowLongHint(true)
      }, LONG_HINT_MS)

      if (skipRequest) return

      // The actual API call — start a background job and poll for the
      // result. The POST itself returns in <100ms with a job_id; the heavy
      // work runs server-side and we poll every 1.5s. The previous
      // synchronous /api/verify was killed by Render's 30s proxy timeout
      // whenever the LLM cold-start pushed the pipeline past that wall.
      let jobId = null
      startVerify(uploadData.text, uploadData.filename)
        .then(({ job_id }) => {
          if (cancelledRef.current) return null
          jobId = job_id
          return pollVerifyUntilDone(job_id, {
            intervalMs: 1500,
            timeoutMs: 130_000,
            onProgress: (payload) => {
              if (cancelledRef.current) return
              // Map server stage onto the stepper. Extraction done -> step 1.
              // Verification running -> step 2/3. Done -> step 3.
              const stage = payload?.progress?.stage
              if (stage === 'extraction') setActiveStep(1)
              else if (stage === 'verification') setActiveStep(2)
              else if (stage === 'claim_done') setActiveStep(2)
              else if (stage === 'done') setActiveStep(3)
            },
          })
        })
        .then((data) => {
          if (cancelledRef.current || !data) return
          setAllComplete(true)
          setActiveStep(STEPS.length - 1)
          setProgress(100)
          setShowLongHint(false)
          setMessageIndex(STATUS_MESSAGES.length - 1)
          scheduleTimer(() => {
            if (cancelledRef.current) return
            onResults?.(data)
          }, COMPLETION_PAUSE_MS)
        })
        .catch((err) => {
          if (cancelledRef.current) return
          const message = getApiErrorMessage(err)
          setError(message)
          onError?.(message)
        })
    },
    [uploadData, onResults, onError]
  )

  useEffect(() => {
    if (hasStartedRef.current) {
      // StrictMode re-mount: re-create the animation but do NOT fire a new
      // request — the in-flight request from the first mount will deliver
      // its result. Keep the original requestStartedAtRef so the progress
      // bar is continuous.
      runAnalysis({ skipRequest: true, isRemount: true })
      return
    }
    hasStartedRef.current = true
    runAnalysis()
    return () => {
      cancelledRef.current = true
      clearTimers()
    }
  }, [runAnalysis])

  const handleStartOver = () => {
    cancelledRef.current = true
    hasStartedRef.current = false
    clearTimers()
    onCancel?.()
  }

  const handleRetry = () => {
    hasStartedRef.current = false
    clearTimers()
    runAnalysis()
  }

  const filename = uploadData?.filename ?? 'document.pdf'
  const pages = uploadData?.pages

  return (
    <motion.div className="mx-auto w-full max-w-[650px]" {...slideUp}>
      {/* File header */}
      <div className="mb-8 flex items-center gap-3 font-mono text-sm text-text-secondary">
        <span className="flex h-9 w-9 items-center justify-center rounded-md border border-bg-border bg-bg-surface text-text-secondary">
          <FileText className="h-4 w-4" aria-hidden />
        </span>
        <span className="truncate text-text-primary">{filename}</span>
        {pages ? (
          <span className="text-text-muted">&middot; {pages} pages</span>
        ) : null}
      </div>

      <header className="mb-10 text-center">
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-text-primary sm:text-[32px]">
          Analyzing Document
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm text-text-secondary sm:text-base">
          TruthLayer is extracting claims, searching live sources, and
          generating fact-check verdicts.
        </p>
      </header>

      <Card>
        <ul className="space-y-6">
          {STEPS.map((step, i) => {
            const state = stepState(i, activeStep, allComplete)
            const StepIcon = step.Icon
            const prevState = i > 0 ? stepState(i - 1, activeStep, allComplete) : null
            return (
              <li key={step.id} className="relative pl-14">
                {i > 0 ? (
                  <span
                    aria-hidden
                    className={[
                      'absolute left-[19px] -top-6 block h-6 w-px transition-colors duration-300',
                      prevState === 'complete' ? 'bg-verified' : 'bg-bg-elevated',
                    ].join(' ')}
                  />
                ) : null}
                <span
                  className={[
                    'absolute left-0 top-0 flex h-10 w-10 items-center justify-center rounded-full transition-colors duration-300',
                    state === 'waiting' &&
                      'border border-bg-border bg-bg-surface text-text-muted',
                    state === 'active' &&
                      'border border-accent bg-accent-dim text-accent animate-pulse-glow',
                    state === 'complete' &&
                      'border border-verified bg-verified-bg text-verified',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  <AnimatePresence mode="wait" initial={false}>
                    {state === 'complete' ? (
                      <motion.span
                        key="check"
                        initial={{ opacity: 0, scale: 0.6 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.6 }}
                        transition={{ duration: 0.2, ease: 'easeOut' }}
                      >
                        <CheckCircle2 className="h-5 w-5" aria-hidden />
                      </motion.span>
                    ) : (
                      <motion.span
                        key="icon"
                        initial={{ opacity: 0, scale: 0.6 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.6 }}
                        transition={{ duration: 0.2, ease: 'easeOut' }}
                      >
                        <StepIcon className="h-5 w-5" aria-hidden />
                      </motion.span>
                    )}
                  </AnimatePresence>
                </span>
                <div>
                  <p
                    className={[
                      'font-display text-base font-semibold transition-colors',
                      state === 'waiting' && 'text-text-muted',
                      state === 'active' && 'text-text-primary',
                      state === 'complete' && 'text-text-primary',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                  >
                    {step.title}
                  </p>
                  <p className="mt-1 text-sm text-text-secondary">
                    {step.description}
                  </p>
                </div>
              </li>
            )
          })}
        </ul>

        {/* Progress bar */}
        <div className="mt-8" aria-hidden>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-elevated">
            <motion.div
              className="h-full bg-accent"
              style={{ width: `${progress}%` }}
              transition={{ duration: 0.3, ease: 'linear' }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between font-mono text-[11px] uppercase tracking-wider text-text-muted">
            <AnimatePresence mode="wait">
              <motion.span
                key={messageIndex}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.2 }}
              >
                {allComplete ? 'Analysis complete' : STATUS_MESSAGES[messageIndex]}
              </motion.span>
            </AnimatePresence>
            <span>{Math.round(progress)}%</span>
          </div>
        </div>

        {/* Long-hint at 30s */}
        <AnimatePresence>
          {showLongHint && !allComplete && !error ? (
            <motion.div
              key="long-hint"
              {...fadeIn}
              className="mt-4 flex items-center gap-2 text-text-muted"
            >
              <Clock className="h-3.5 w-3.5" aria-hidden />
              <span className="text-xs">
                This document is taking longer than usual.
              </span>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {/* Start over */}
        {!allComplete && !error ? (
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={handleStartOver}
              className="text-xs text-text-secondary underline-offset-4 transition-colors hover:text-text-primary hover:underline"
            >
              Start over
            </button>
          </div>
        ) : null}
      </Card>

      {/* Error card */}
      <AnimatePresence>
        {error ? (
          <motion.div key="error" {...slideUp} className="mt-4">
            <Card className="!p-4 border-l-4 border-l-false">
              <div className="flex items-start gap-3">
                <AlertCircle
                  className="h-5 w-5 shrink-0 text-false"
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                    Analysis failed
                  </p>
                  <p className="mt-1 break-words text-sm text-text-secondary">
                    {error}
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <Button variant="primary" onClick={handleRetry}>
                      Retry
                    </Button>
                    <button
                      type="button"
                      onClick={handleStartOver}
                      className="text-xs text-text-secondary underline-offset-4 transition-colors hover:text-text-primary hover:underline"
                    >
                      Start over
                    </button>
                  </div>
                </div>
              </div>
            </Card>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  )
}
