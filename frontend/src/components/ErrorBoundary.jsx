import { Component } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

import Button from './ui/Button'
import Card from './ui/Card'

/**
 * V2 Phase 5: Top-level error boundary.
 *
 * React does not bubble up render-time exceptions. Without a boundary, an
 * unhandled exception in any screen would unmount the entire app and leave
 * the user staring at a blank page. This boundary catches render errors
 * anywhere in the tree, shows a clear fallback UI, and offers a single
 * "Reload" action so the user can recover without losing their session.
 *
 * Usage: wrap the top-level screen tree in main.jsx:
 *
 *     <ErrorBoundary>
 *       <App />
 *     </ErrorBoundary>
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Log to the console so the browser dev tools pick it up. The backend
    // does not receive client errors (no error-reporting endpoint by
    // design) but the developer console is the primary surface.
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught an exception:', error, info)
  }

  handleReload = () => {
    this.setState({ error: null })
    // Force a clean re-render of the wrapped tree. A full reload would
    // also work but loses the in-memory state (results, fileType, etc.).
    if (typeof this.props.onReset === 'function') {
      this.props.onReset()
    }
  }

  handleHardReload = () => {
    if (typeof window !== 'undefined') {
      window.location.reload()
    }
  }

  render() {
    const { error } = this.state
    const { children, fallback = null } = this.props

    if (!error) return children

    if (fallback) return fallback

    return (
      <div
        role="alert"
        aria-live="assertive"
        data-testid="error-boundary"
        className="mx-auto w-full max-w-[640px] py-12"
      >
        <Card className="border-l-4 border-l-false">
          <div className="flex items-start gap-4">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-false/30 bg-false-bg text-false">
              <AlertTriangle className="h-5 w-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                Application error
              </p>
              <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">
                Something broke
              </h2>
              <p className="mt-2 text-sm text-text-secondary">
                The TruthLayer UI hit an unexpected error. Your work has
                not been lost — reloading should bring you back to the
                upload screen.
              </p>
              {error?.message ? (
                <pre
                  data-testid="error-boundary-message"
                  className="mt-4 max-h-40 overflow-auto rounded-md border border-bg-border bg-bg-base p-3 font-mono text-xs text-text-secondary"
                >
                  {String(error.message)}
                </pre>
              ) : null}
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <Button onClick={this.handleReload}>
                  <RefreshCw className="h-4 w-4" aria-hidden />
                  Try again
                </Button>
                <Button variant="outline" onClick={this.handleHardReload}>
                  Reload page
                </Button>
              </div>
            </div>
          </div>
        </Card>
      </div>
    )
  }
}
