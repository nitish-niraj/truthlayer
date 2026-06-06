import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import ResultsDashboard from './ResultsDashboard'

vi.mock('../utils/reportGenerator', () => ({
  openReport: vi.fn(() => true),
}))

const IMAGE_RESULTS = {
  filename: 'fake-statistic.png',
  summary: { total: 6, verified: 2, inaccurate: 3, false: 1 },
  claims: [
    {
      id: 1,
      claim: 'ChatGPT has 100 million users.',
      type: 'statistic',
      source_sentence: 'ChatGPT has 100 million users.',
      verdict: 'inaccurate',
      explanation: 'Outdated figure.',
      correct_fact: '200M weekly active users as of 2024.',
      source_url: 'https://openai.com/blog/chatgpt',
    },
  ],
  processing_time_seconds: 12.3,
}

const PDF_RESULTS = {
  filename: 'annual-report.pdf',
  summary: { total: 2, verified: 1, inaccurate: 1, false: 0 },
  claims: [
    {
      id: 1,
      claim: 'OpenAI was founded in 2015.',
      type: 'date',
      source_sentence: 'OpenAI was founded in 2015.',
      verdict: 'verified',
      explanation: 'Confirmed by OpenAI.',
      correct_fact: '',
      source_url: 'https://openai.com/about',
    },
  ],
}

describe('ResultsDashboard', () => {
  it('renders the file preview card for image results', () => {
    render(
      <ResultsDashboard
        results={IMAGE_RESULTS}
        previewUrl="blob:http://localhost/img"
        fileType="image"
      />,
    )
    expect(screen.getByTestId('file-preview-image')).toBeInTheDocument()
    expect(screen.getByTestId('file-preview-filename')).toHaveTextContent(
      'fake-statistic.png',
    )
  })

  it('renders the metadata card for both image and pdf results', () => {
    const { rerender } = render(
      <ResultsDashboard
        results={IMAGE_RESULTS}
        fileType="image"
        processingTimeSeconds={12.3}
      />,
    )
    expect(screen.getByTestId('meta-input-type')).toHaveTextContent('Image')
    expect(screen.getByTestId('meta-verified')).toHaveTextContent('2')
    expect(screen.getByTestId('meta-processing-time')).toHaveTextContent('12.3s')

    rerender(<ResultsDashboard results={PDF_RESULTS} fileType="document" />)
    expect(screen.getByTestId('meta-input-type')).toHaveTextContent('Document')
    expect(screen.getByTestId('meta-verified')).toHaveTextContent('1')
  })

  it('does NOT render the file preview card for pdf results', () => {
    render(<ResultsDashboard results={PDF_RESULTS} fileType="document" />)
    expect(screen.queryByTestId('file-preview-image')).not.toBeInTheDocument()
    expect(screen.queryByTestId('file-preview-icon')).not.toBeInTheDocument()
  })

  it('shows the image empty-state when an image run produces zero claims', () => {
    render(
      <ResultsDashboard
        results={{
          filename: 'blank.png',
          summary: { total: 0, verified: 0, inaccurate: 0, false: 0 },
          claims: [],
        }}
        fileType="image"
      />,
    )
    expect(
      screen.getByText('No verifiable claims detected'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/TruthLayer could not identify any factual claims/),
    ).toBeInTheDocument()
    // The hint chips
    expect(screen.getByText('Statistics screenshots')).toBeInTheDocument()
    expect(screen.getByText('Infographics')).toBeInTheDocument()
  })

  it('shows the document empty-state when a pdf run produces zero claims', () => {
    render(
      <ResultsDashboard
        results={{
          filename: 'empty.pdf',
          summary: { total: 0, verified: 0, inaccurate: 0, false: 0 },
          claims: [],
        }}
        fileType="document"
      />,
    )
    expect(screen.getByText('No verifiable claims found')).toBeInTheDocument()
  })

  it('renders the evidence panel toggle on every claim card', () => {
    render(
      <ResultsDashboard
        results={IMAGE_RESULTS}
        fileType="image"
        previewUrl="blob:abc"
      />,
    )
    const toggles = screen.getAllByTestId('evidence-toggle')
    expect(toggles.length).toBeGreaterThan(0)
    expect(toggles[0]).toHaveTextContent('Show Evidence')
  })

  it('shows the "Image" badge in the file preview for image runs', () => {
    render(
      <ResultsDashboard
        results={IMAGE_RESULTS}
        fileType="image"
        previewUrl="blob:abc"
      />,
    )
    expect(screen.getByTestId('file-preview-badge')).toHaveTextContent('Image')
  })

  it('shows the "Document" badge in the file preview for pdf runs', () => {
    // Even though the file preview is only rendered for image runs, the
    // metadata card surfaces the input type — verify it shows "Document".
    render(<ResultsDashboard results={PDF_RESULTS} fileType="document" />)
    expect(screen.getByTestId('meta-input-type')).toHaveTextContent('Document')
  })
})
