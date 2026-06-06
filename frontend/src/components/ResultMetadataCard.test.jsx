import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import ResultMetadataCard from './ResultMetadataCard'

describe('ResultMetadataCard', () => {
  it('renders the metadata card with input type, filename, claim counts, and processing time', () => {
    render(
      <ResultMetadataCard
        filename="shot.png"
        fileType="image"
        summary={{ total: 6, verified: 2, inaccurate: 3, false: 1 }}
        processingTimeSeconds={12.3}
      />,
    )
    const card = screen.getByTestId('result-metadata-card')
    expect(card).toBeInTheDocument()
    expect(screen.getByTestId('meta-input-type')).toHaveTextContent('Image')
    expect(screen.getByTestId('meta-filename')).toHaveTextContent('shot.png')
    expect(screen.getByTestId('meta-claims-total')).toHaveTextContent('6')
    expect(screen.getByTestId('meta-verified')).toHaveTextContent('2')
    expect(screen.getByTestId('meta-inaccurate')).toHaveTextContent('3')
    expect(screen.getByTestId('meta-false')).toHaveTextContent('1')
    expect(screen.getByTestId('meta-processing-time')).toHaveTextContent('12.3s')
  })

  it('falls back to "Document" when fileType is unset and the filename ends in .pdf', () => {
    render(
      <ResultMetadataCard
        filename="annual-report.pdf"
        summary={{ total: 1, verified: 1, inaccurate: 0, false: 0 }}
      />,
    )
    expect(screen.getByTestId('meta-input-type')).toHaveTextContent('Document')
  })

  it('shows the "not measured" fallback when no timing is provided', () => {
    render(
      <ResultMetadataCard
        filename="a.pdf"
        fileType="document"
        summary={{ total: 0, verified: 0, inaccurate: 0, false: 0 }}
      />,
    )
    expect(
      screen.getByTestId('meta-processing-time-empty'),
    ).toHaveTextContent('not measured')
  })

  it('accepts processingDurationMs and converts to seconds for display', () => {
    render(
      <ResultMetadataCard
        filename="x.png"
        fileType="image"
        summary={{ total: 0, verified: 0, inaccurate: 0, false: 0 }}
        processingDurationMs={2500}
      />,
    )
    expect(screen.getByTestId('meta-processing-time')).toHaveTextContent('2.5s')
  })
})
