import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import FilePreviewCard from './FilePreviewCard'

describe('FilePreviewCard', () => {
  it('renders an image preview thumbnail when previewUrl is provided', () => {
    render(
      <FilePreviewCard
        filename="fake-statistic.png"
        fileType="image"
        previewUrl="blob:http://localhost/abc"
      />,
    )
    const img = screen.getByTestId('file-preview-image').querySelector('img')
    expect(img).toBeInTheDocument()
    expect(img).toHaveAttribute('src', 'blob:http://localhost/abc')
    expect(img).toHaveAttribute('alt', 'fake-statistic.png')
    expect(screen.getByTestId('file-preview-filename')).toHaveTextContent(
      'fake-statistic.png',
    )
  })

  it('falls back to an icon placeholder when no previewUrl is provided for an image', () => {
    render(<FilePreviewCard filename="missing-preview.png" fileType="image" />)
    expect(screen.getByTestId('file-preview-icon')).toBeInTheDocument()
    expect(screen.queryByTestId('file-preview-image')).not.toBeInTheDocument()
    expect(screen.getByTestId('file-preview-filename')).toHaveTextContent(
      'missing-preview.png',
    )
  })

  it('renders a PDF preview with icon and filename', () => {
    render(
      <FilePreviewCard
        filename="annual-report.pdf"
        fileType="document"
        pages={12}
        fileSize={1024 * 1024}
        formatBytes={(b) => `${b} B`}
      />,
    )
    expect(screen.getByTestId('file-preview-icon')).toBeInTheDocument()
    expect(screen.queryByTestId('file-preview-image')).not.toBeInTheDocument()
    expect(screen.getByTestId('file-preview-filename')).toHaveTextContent(
      'annual-report.pdf',
    )
    expect(screen.getByTestId('file-preview-format')).toHaveTextContent(
      'PDF Document',
    )
  })

  it('shows the "Image" badge for image files', () => {
    render(
      <FilePreviewCard
        filename="x.png"
        fileType="image"
        previewUrl="blob:abc"
      />,
    )
    const badge = screen.getByTestId('file-preview-badge')
    expect(badge).toHaveTextContent('Image')
  })

  it('shows the "Document" badge for PDF files', () => {
    render(<FilePreviewCard filename="x.pdf" fileType="document" />)
    const badge = screen.getByTestId('file-preview-badge')
    expect(badge).toHaveTextContent('Document')
  })

  it('infers the file type from the filename when fileType is not given', () => {
    render(<FilePreviewCard filename="chart.jpg" previewUrl="blob:abc" />)
    const badge = screen.getByTestId('file-preview-badge')
    expect(badge).toHaveTextContent('Image')
  })
})
