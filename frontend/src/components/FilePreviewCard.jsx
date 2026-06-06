import { motion } from 'framer-motion'
import { FileImage, FileText, Image as ImageIcon } from 'lucide-react'

import Badge from './ui/Badge'
import Card from './ui/Card'

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg']
const PDF_EXTENSIONS = ['pdf']

function detectFileType(filename) {
  if (!filename) return 'document'
  const ext = filename.toLowerCase().split('.').pop()
  if (IMAGE_EXTENSIONS.includes(ext)) return 'image'
  if (PDF_EXTENSIONS.includes(ext)) return 'document'
  return 'document'
}

function fileTypeLabel(type) {
  if (type === 'image') return 'Image'
  return 'Document'
}

function fileTypeIcon(type) {
  return type === 'image' ? FileImage : FileText
}

const cardVariants = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
  },
}

export default function FilePreviewCard({
  filename,
  fileType,
  previewUrl = null,
  fileSize = null,
  pages = null,
  formatBytes = null,
}) {
  const resolvedType = fileType ?? detectFileType(filename)
  const Icon = fileTypeIcon(resolvedType)
  const label = fileTypeLabel(resolvedType)

  return (
    <motion.div variants={cardVariants} initial="initial" animate="animate">
      <Card>
        <div className="flex items-center gap-2">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-text-muted">
            Uploaded File
          </p>
        </div>

        <div className="mt-4 flex items-start gap-4">
          {resolvedType === 'image' && previewUrl ? (
            <div
              data-testid="file-preview-image"
              className="relative h-24 w-24 shrink-0 overflow-hidden rounded-md border border-bg-border bg-bg-elevated"
            >
              <img
                src={previewUrl}
                alt={filename ?? 'Uploaded image preview'}
                className="h-full w-full object-cover"
              />
            </div>
          ) : (
            <div
              data-testid="file-preview-icon"
              className="flex h-24 w-24 shrink-0 items-center justify-center rounded-md border border-bg-border bg-bg-elevated text-text-secondary"
            >
              {resolvedType === 'image' ? (
                <ImageIcon className="h-8 w-8" aria-hidden />
              ) : (
                <Icon className="h-8 w-8" aria-hidden />
              )}
            </div>
          )}

          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Icon className="h-3.5 w-3.5 text-text-muted" aria-hidden />
              <p
                data-testid="file-preview-filename"
                className="truncate font-mono text-sm text-text-primary"
              >
                {filename ?? 'untitled'}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Badge
                data-testid="file-preview-badge"
                variant={resolvedType === 'image' ? 'inaccurate' : 'neutral'}
                className={
                  resolvedType === 'image'
                    ? 'border-accent/30 bg-accent-dim text-accent'
                    : ''
                }
              >
                {label}
              </Badge>
              <span
                data-testid="file-preview-format"
                className="font-mono text-[11px] uppercase tracking-wider text-text-muted"
              >
                {resolvedType === 'image' ? 'Image File' : 'PDF Document'}
              </span>
              {typeof pages === 'number' ? (
                <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                  &middot; {pages} {pages === 1 ? 'page' : 'pages'}
                </span>
              ) : null}
              {typeof fileSize === 'number' && formatBytes ? (
                <span className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                  &middot; {formatBytes(fileSize)}
                </span>
              ) : null}
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  )
}
