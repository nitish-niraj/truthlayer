import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../services/api', () => ({
  startVerify: vi.fn(() => new Promise(() => {})),
  pollVerifyUntilDone: vi.fn(() => new Promise(() => {})),
}))

import ProcessingScreen from './ProcessingScreen'

const baseUpload = { text: 'demo', pages: 2, filename: 'demo.pdf' }

describe('ProcessingScreen', () => {
  it('renders PDF-specific step labels when fileType="pdf"', () => {
    render(
      <ProcessingScreen
        uploadData={baseUpload}
        fileType="pdf"
        onResults={vi.fn()}
        onError={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const list = screen.getByTestId('processing-steps')
    expect(list).toHaveAttribute('data-file-type', 'pdf')
    const titles = screen.getAllByTestId('processing-step-title')
    expect(titles.map((el) => el.textContent)).toEqual([
      'Extracting Text',
      'Identifying Claims',
      'Searching Web',
      'Generating Verdicts',
    ])
    expect(screen.getByTestId('processing-file-type-badge')).toHaveTextContent(
      'Document',
    )
    expect(screen.getByTestId('processing-header-title')).toHaveTextContent(
      'Analyzing Document',
    )
  })

  it('renders image-specific step labels when fileType="image"', () => {
    render(
      <ProcessingScreen
        uploadData={{ ...baseUpload, filename: 'shot.png' }}
        fileType="image"
        onResults={vi.fn()}
        onError={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const list = screen.getByTestId('processing-steps')
    expect(list).toHaveAttribute('data-file-type', 'image')
    const titles = screen.getAllByTestId('processing-step-title')
    expect(titles.map((el) => el.textContent)).toEqual([
      'Analyzing Image',
      'Extracting Claims',
      'Searching Web',
      'Generating Verdicts',
    ])
    expect(screen.getByTestId('processing-file-type-badge')).toHaveTextContent(
      'Image',
    )
    expect(screen.getByTestId('processing-header-title')).toHaveTextContent(
      'Analyzing Image',
    )
  })

  it('falls back to PDF labels when fileType is omitted', () => {
    render(
      <ProcessingScreen
        uploadData={baseUpload}
        onResults={vi.fn()}
        onError={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByTestId('processing-steps')).toHaveAttribute(
      'data-file-type',
      'pdf',
    )
    expect(
      screen.getByTestId('processing-file-type-badge'),
    ).toHaveTextContent('Document')
  })
})
