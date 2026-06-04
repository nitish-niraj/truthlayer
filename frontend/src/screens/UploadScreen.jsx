import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Search,
  ShieldCheck,
  UploadCloud,
} from 'lucide-react'

import { uploadPDF } from '../services/api'
import { formatBytes } from '../utils/format'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import { fadeIn, slideUp } from '../lib/motion'

const MAX_FILE_SIZE = 10 * 1024 * 1024

const FEATURES = [
  { id: 'extract', label: 'Extract Claims', Icon: FileText },
  { id: 'search', label: 'Search Live Sources', Icon: Search },
  { id: 'verify', label: 'Verify Facts', Icon: ShieldCheck },
]

function getRejectionMessage(rejection) {
  const code = rejection?.errors?.[0]?.code
  if (code === 'file-too-large') return 'File exceeds 10MB limit'
  if (code === 'file-invalid-type') return 'Only PDF files are supported'
  return rejection?.errors?.[0]?.message ?? 'Invalid file'
}

function getApiErrorMessage(err) {
  if (err?.response?.data?.detail) return err.response.data.detail
  if (err?.code === 'ERR_NETWORK') return 'Server unavailable'
  if (err?.message) return err.message
  return 'Unable to upload PDF'
}

export default function UploadScreen({
  onUploadComplete,
  onStartProcessing,
  onError,
}) {
  const [file, setFile] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)
  const [uploading, setUploading] = useState(false)

  const onDrop = useCallback((acceptedFiles, fileRejections) => {
    setErrorMessage(null)
    if (fileRejections && fileRejections.length > 0) {
      setErrorMessage(getRejectionMessage(fileRejections[0]))
      return
    }
    const next = acceptedFiles?.[0]
    if (next) setFile(next)
  }, [])

  const {
    getRootProps,
    getInputProps,
    isDragActive,
    isDragReject,
  } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxSize: MAX_FILE_SIZE,
    multiple: false,
    disabled: uploading,
  })

  const handleAnalyze = async () => {
    if (!file || uploading) return
    setUploading(true)
    setErrorMessage(null)
    try {
      const data = await uploadPDF(file)
      onUploadComplete?.(data)
      onStartProcessing?.()
    } catch (err) {
      const message = getApiErrorMessage(err)
      setErrorMessage(message)
      onError?.(message)
    } finally {
      setUploading(false)
    }
  }

  const handleReset = () => {
    if (uploading) return
    setFile(null)
    setErrorMessage(null)
  }

  const dropzoneClass = [
    'cursor-pointer rounded-xl border-[1.5px] border-dashed p-12 text-center transition-all duration-200',
    isDragActive && !isDragReject
      ? 'scale-[1.01] border-accent bg-accent-dim'
      : 'border-bg-border bg-bg-surface hover:border-text-muted',
    isDragReject ? '!border-false' : '',
    uploading ? 'cursor-not-allowed opacity-60' : '',
  ].join(' ')

  return (
    <motion.div className="mx-auto w-full max-w-[700px]" {...slideUp}>
      <motion.header className="mb-12 text-center" {...fadeIn}>
        <h1 className="font-display text-[32px] font-semibold tracking-tight text-text-primary sm:text-[48px]">
          Upload. Verify. <span className="text-accent">Trust.</span>
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-base text-text-secondary sm:text-lg">
          Drop a PDF and TruthLayer will extract every factual claim, search live
          sources, and identify inaccuracies.
        </p>
      </motion.header>

      <AnimatePresence mode="wait">
        {!file ? (
          <motion.div key="dropzone" {...slideUp}>
            <div {...getRootProps({ className: dropzoneClass })}>
              <input {...getInputProps()} />
              <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full border border-bg-border bg-bg-elevated text-text-secondary">
                <UploadCloud className="h-7 w-7" aria-hidden />
              </div>
              <p className="font-display text-lg font-semibold text-text-primary">
                {isDragActive ? 'Release to upload' : 'Drop your PDF here'}
              </p>
              <p className="mt-1 text-sm text-text-secondary">or click to browse</p>
              <p className="mt-4 font-mono text-[11px] uppercase tracking-wider text-text-muted">
                Supports PDF files up to {formatBytes(MAX_FILE_SIZE)}
              </p>
            </div>
          </motion.div>
        ) : (
          <motion.div key="selected" {...slideUp}>
            <Card>
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-verified/30 bg-verified-bg text-verified">
                  <CheckCircle2 className="h-6 w-6" aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                    Ready to analyze
                  </p>
                  <p className="mt-1 truncate font-mono text-sm text-text-primary">
                    {file.name}
                  </p>
                  <p className="mt-0.5 font-mono text-xs text-text-secondary">
                    {formatBytes(file.size)}
                  </p>
                  <div className="mt-5 flex flex-wrap items-center gap-3">
                    <Button
                      onClick={handleAnalyze}
                      loading={uploading}
                      className="uppercase tracking-wider"
                    >
                      Analyze Document
                    </Button>
                    <button
                      type="button"
                      onClick={handleReset}
                      disabled={uploading}
                      className="text-sm text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Choose different file
                    </button>
                  </div>
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {errorMessage ? (
          <motion.div key="error" {...slideUp} className="mt-4">
            <Card className="!p-4 border-l-4 border-l-false">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 shrink-0 text-false" aria-hidden />
                <p className="text-sm text-text-secondary">{errorMessage}</p>
              </div>
            </Card>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <motion.ul
        className="mt-10 flex flex-wrap items-center justify-center gap-3"
        {...fadeIn}
      >
        {FEATURES.map((f) => {
          const Icon = f.Icon
          return (
            <li
              key={f.id}
              className="inline-flex items-center gap-2 rounded-full border border-bg-border bg-bg-surface px-4 py-2"
            >
              <Icon className="h-3.5 w-3.5 text-accent" aria-hidden />
              <span className="text-xs font-medium text-text-secondary">
                {f.label}
              </span>
            </li>
          )
        })}
      </motion.ul>
    </motion.div>
  )
}
