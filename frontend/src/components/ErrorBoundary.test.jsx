import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ErrorBoundary from './ErrorBoundary'

function Boom() {
  throw new Error('Kaboom from the tree')
}

describe('ErrorBoundary', () => {
  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary>
        <div>Safe child</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText('Safe child')).toBeInTheDocument()
    expect(screen.queryByTestId('error-boundary')).toBeNull()
  })

  it('catches a render-time exception and shows the fallback', () => {
    // Silence React's own console.error from logging the unhandled error
    // twice during the test (once for the error, once for the boundary
    // catch log). We are explicitly testing the catch path.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )

    expect(screen.getByTestId('error-boundary')).toBeInTheDocument()
    expect(screen.getByTestId('error-boundary-message')).toHaveTextContent('Kaboom from the tree')
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(consoleError).toHaveBeenCalled()
    consoleError.mockRestore()
  })

  it('resets to the wrapped tree when the user clicks Try again', async () => {
    const user = userEvent.setup()
    let shouldThrow = true
    function MaybeBoom() {
      if (shouldThrow) throw new Error('Initial failure')
      return <div>Recovered</div>
    }

    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <MaybeBoom />
      </ErrorBoundary>,
    )

    expect(screen.getByTestId('error-boundary')).toBeInTheDocument()

    // Stop throwing and reset.
    shouldThrow = false
    await user.click(screen.getByRole('button', { name: /try again/i }))

    expect(screen.getByText('Recovered')).toBeInTheDocument()
    expect(screen.queryByTestId('error-boundary')).toBeNull()
    consoleError.mockRestore()
  })
})
