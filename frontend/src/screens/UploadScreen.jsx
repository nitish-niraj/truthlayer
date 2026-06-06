import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertCircle,
  CheckCircle2,
  FileImage,
  FileText,
  Search,
  ShieldCheck,
  UploadCloud,
  X,
} from 'lucide-react'

import { verifyImage, uploadPDF, describeNetworkError } from '../services/api'
import { formatBytes } from '../utils/format'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import { fadeIn, slideUp } from '../lib/motion'

const MAX_PDF_SIZE = 10 * 1024 * 1024
const MAX_IMAGE_SIZE = 5 * 1024 * 1024

const ACCEPTED_MIME = {
  'application/pdf': ['.pdf'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/webp': ['.webp'],
}

const PDF_EXTENSIONS = ['pdf']
const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp']

const FEATURES = [
  { id: 'extract', label: 'Extract Claims', Icon: FileText },
  { id: 'search', label: 'Search Live Sources', Icon: Search },
  { id: 'verify', label: 'Verify Facts', Icon: ShieldCheck },
]

function getFileType(filename = '') {
  const ext = filename.toLowerCase().split('.').pop()
  if (PDF_EXTENSIONS.includes(ext)) return 'pdf'
  if (IMAGE_EXTENSIONS.includes(ext)) return 'image'
  return 'unknown'
}

function getMaxSizeForType(type) {
  return type === 'image' ? MAX_IMAGE_SIZE : MAX_PDF_SIZE
}

function getRejectionMessage(rejection) {
  const err = rejection?.errors?.[0]
  const code = err?.code
  if (code === 'file-too-large') {
    return 'File exceeds size limit (PDF up to 10MB, images up to 5MB)'
  }
  if (code === 'file-invalid-type') {
    return 'Supported formats: PDF, PNG, JPG, JPEG, WEBP'
  }
  return err?.message ?? 'Invalid file'
}

function getApiErrorMessage(err, fileType) {
  // File-format rejections from the server use detail-as-object, not
  // detail-as-string, so the describeNetworkError envelope extraction
  // does not catch them — fall back to the parsed dropzone message first.
  if (err?.response?.data?.detail) {
    const detail = err.response.data.detail
    if (typeof detail === 'string' && detail) return detail
    if (typeof detail === 'object' && detail?.detail) return detail.detail
  }
  const generic = describeNetworkError(err)
  if (generic && generic !== 'Something went wrong. Please try again.') {
    return generic
  }
  return fileType === 'image' ? 'Unable to upload image' : 'Unable to upload PDF'
}

export default function UploadScreen({
  fileType = null,
  previewUrl = null,
  onFileAccepted,
  onUploadComplete,
  onStartProcessing,
  onImageVerified,
  onError,
}) {
  const [localFile, setLocalFile] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [verifying, setVerifying] = useState(false)

  const hasFile = Boolean(localFile) && Boolean(fileType)

  const onDrop = useCallback(
    (acceptedFiles, fileRejections) => {
      setErrorMessage(null)
      if (fileRejections && fileRejections.length > 0) {
        setErrorMessage(getRejectionMessage(fileRejections[0]))
        return
      }
      const next = acceptedFiles?.[0]
      if (!next) return
      const type = getFileType(next.name)
      if (type === 'unknown') {
        setErrorMessage('Supported formats: PDF, PNG, JPG, JPEG, WEBP')
        return
      }
      if (next.size > getMaxSizeForType(type)) {
        setErrorMessage(
          type === 'image'
            ? 'Image must be under 5MB'
            : `File must be under ${formatBytes(MAX_PDF_SIZE)}`,
        )
        return
      }
      const url = type === 'image' ? URL.createObjectURL(next) : null
      setLocalFile(next)
      onFileAccepted?.({ file: next, type, url, size: next.size })
    },
    [onFileAccepted]
  )

  const {
    getRootProps,
    getInputProps,
    isDragActive,
    isDragReject,
  } = useDropzone({
    onDrop,
    accept: ACCEPTED_MIME,
    maxSize: MAX_PDF_SIZE,
    multiple: false,
    disabled: uploading || verifying,
  })

  const handleAnalyze = async () => {
    if (!localFile || uploading || verifying) return
    setUploading(true)
    setErrorMessage(null)
    try {
      const data = await uploadPDF(localFile)
      onUploadComplete?.(data)
      onStartProcessing?.()
    } catch (err) {
      const message = getApiErrorMessage(err, 'pdf')
      setErrorMessage(message)
      onError?.(message)
    } finally {
      setUploading(false)
    }
  }

  const handleVerifyImage = async () => {
    if (!localFile || uploading || verifying) return
    setVerifying(true)
    setErrorMessage(null)
    try {
      const data = await verifyImage(localFile)
      onImageVerified?.(data)
    } catch (err) {
      const message = getApiErrorMessage(err, 'image')
      setErrorMessage(message)
      onError?.(message)
    } finally {
      setVerifying(false)
    }
  }

  const handleReset = () => {
    if (uploading || verifying) return
    setLocalFile(null)
    setErrorMessage(null)
    onFileAccepted?.({ file: null, type: null, url: null, size: null })
  }

  const dropzoneClass = [
    'cursor-pointer rounded-xl border-[1.5px] border-dashed p-12 text-center transition-all duration-200',
    isDragActive && !isDragReject
      ? 'scale-[1.01] border-accent bg-accent-dim'
      : 'border-bg-border bg-bg-surface hover:border-text-muted',
    isDragReject ? '!border-false' : '',
    uploading || verifying ? 'cursor-not-allowed opacity-60' : '',
  ].join(' ')

  const FileTypeIcon = fileType === 'image' ? FileImage : FileText
  const fileTypeLabel = fileType === 'image' ? 'Image File' : 'PDF Document'
  const isImage = fileType === 'image'

  return (
    <motion.div className="mx-auto w-full max-w-[700px]" {...slideUp}>
      <motion.header className="mb-12 text-center" {...fadeIn}>
        <h1 className="font-display text-[32px] font-semibold tracking-tight text-text-primary sm:text-[48px]">
          Upload. Verify. <span className="text-accent">Trust.</span>
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-base text-text-secondary sm:text-lg">
          Drop a PDF or image and TruthLayer will extract every factual claim,
          search live sources, and identify inaccuracies.
        </p>
      </motion.header>

      <AnimatePresence mode="wait">
        {!hasFile ? (
          <motion.div key="dropzone" {...slideUp}>
            <div {...getRootProps({ className: dropzoneClass })}>
              <input {...getInputProps()} />
              <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full border border-bg-border bg-bg-elevated text-text-secondary">
                <UploadCloud className="h-7 w-7" aria-hidden />
              </div>
              <p className="font-display text-lg font-semibold text-text-primary">
                {isDragActive ? 'Release to upload' : 'Upload a Document or Image'}
              </p>
              <p className="mt-1 text-sm text-text-secondary">or click to browse</p>
              <p className="mt-4 font-mono text-[11px] uppercase tracking-wider text-text-muted">
                Supported: PDF &middot; PNG &middot; JPG &middot; JPEG &middot; WEBP
              </p>
              <p className="mt-1 font-mono text-[11px] uppercase tracking-wider text-text-muted">
                PDF up to {formatBytes(MAX_PDF_SIZE)} &middot; Images up to {formatBytes(MAX_IMAGE_SIZE)}
              </p>
            </div>
          </motion.div>
        ) : (
          <motion.div key="selected" {...slideUp}>
            <Card>
              <div className="flex items-start gap-4">
                {isImage && previewUrl ? (
                  <div className="h-20 w-20 shrink-0 overflow-hidden rounded-md border border-bg-border bg-bg-elevated">
                    <img
                      src={previewUrl}
                      alt={localFile.name}
                      className="h-full w-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-verified/30 bg-verified-bg text-verified">
                    <CheckCircle2 className="h-6 w-6" aria-hidden />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <FileTypeIcon className="h-3.5 w-3.5 text-text-muted" aria-hidden />
                    <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                      {fileTypeLabel}
                    </p>
                  </div>
                  <p className="mt-1 truncate font-mono text-sm text-text-primary">
                    {localFile.name}
                  </p>
                  <p className="mt-0.5 font-mono text-xs text-text-secondary">
                    {formatBytes(localFile.size)}
                  </p>
                  <div className="mt-5 flex flex-wrap items-center gap-3">
                    {isImage ? (
                      <>
                        <Button
                          onClick={handleVerifyImage}
                          loading={verifying}
                          className="uppercase tracking-wider"
                        >
                          <ShieldCheck className="h-4 w-4" aria-hidden />
                          Verify Image
                        </Button>
                        <button
                          type="button"
                          onClick={handleReset}
                          disabled={verifying}
                          className="inline-flex items-center gap-1.5 text-sm text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <X className="h-3.5 w-3.5" aria-hidden />
                          Choose different file
                        </button>
                      </>
                    ) : (
                      <>
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
                          className="inline-flex items-center gap-1.5 text-sm text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <X className="h-3.5 w-3.5" aria-hidden />
                          Choose different file
                        </button>
                      </>
                    )}
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
