import { AlertTriangle } from 'lucide-react'
import SectionHeader from '../components/ui/SectionHeader'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'

export default function ErrorScreen({ errorMessage = 'An unexpected error occurred. Please try again.', onReset }) {
  return (
    <div>
      <SectionHeader
        eyebrow="Error"
        title="Something Went Wrong"
        subtitle="The analysis could not be completed. Review the message below and try again."
      />

      <Card className="border-l-4 border-l-false">
        <div className="flex items-start gap-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-false/30 bg-false-bg text-false">
            <AlertTriangle className="h-5 w-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
              Failure detail
            </p>
            <p className="mt-1 break-words font-mono text-sm text-text-secondary">
              {errorMessage}
            </p>
            <div className="mt-5">
              <Button variant="primary" onClick={onReset}>
                Try Again
              </Button>
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}
