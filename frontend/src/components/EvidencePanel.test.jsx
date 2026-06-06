import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import EvidencePanel from './EvidencePanel'

const SAMPLE = {
  id: 1,
  claim: 'ChatGPT has 100M users',
  verdict: 'inaccurate',
  correct_fact: '200M weekly active users as of 2024',
  source_url: 'https://openai.com/blog/chatgpt',
  explanation: 'Outdated figure.',
}

describe('EvidencePanel', () => {
  it('renders a collapsed "Show Evidence" toggle by default', () => {
    render(<EvidencePanel claim={SAMPLE} />)
    const toggle = screen.getByTestId('evidence-toggle')
    expect(toggle).toHaveTextContent('Show Evidence')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('evidence-panel')).not.toBeInTheDocument()
  })

  it('expands to show the correct fact and a source row when toggled', async () => {
    const user = (await import('@testing-library/user-event')).default.setup()
    render(<EvidencePanel claim={SAMPLE} />)
    const toggle = screen.getByTestId('evidence-toggle')
    await user.click(toggle)
    expect(toggle).toHaveTextContent('Hide Evidence')
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('evidence-panel')).toBeInTheDocument()
    expect(screen.getByTestId('evidence-correct-fact')).toHaveTextContent(
      '200M weekly active users as of 2024',
    )
    const sources = screen.getAllByTestId('evidence-source')
    expect(sources).toHaveLength(1)
    const link = sources[0].querySelector('a')
    expect(link).toHaveAttribute('href', 'https://openai.com/blog/chatgpt')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveTextContent('Open Source')
    expect(sources[0]).toHaveTextContent('openai.com')
  })

  it('renders nothing when the claim has no evidence and no correct fact', () => {
    const empty = { id: 9, claim: 'X', verdict: 'verified' }
    const { container } = render(<EvidencePanel claim={empty} />)
    expect(container.firstChild).toBeNull()
  })

  it('supports a future evidence[] list of multiple sources', async () => {
    const user = (await import('@testing-library/user-event')).default.setup()
    const multi = {
      ...SAMPLE,
      evidence: [
        { url: 'https://a.com/x', title: 'A', domain: 'a.com' },
        { url: 'https://b.com/y', title: 'B', domain: 'b.com' },
        { url: 'https://c.com/z', title: 'C', domain: 'c.com' },
      ],
    }
    render(<EvidencePanel claim={multi} />)
    await user.click(screen.getByTestId('evidence-toggle'))
    const sources = screen.getAllByTestId('evidence-source')
    expect(sources).toHaveLength(3)
    expect(sources[0]).toHaveTextContent('a.com')
    expect(sources[1]).toHaveTextContent('b.com')
    expect(sources[2]).toHaveTextContent('c.com')
  })
})
