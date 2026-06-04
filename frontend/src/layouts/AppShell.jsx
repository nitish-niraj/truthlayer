import { Activity } from 'lucide-react'

export default function AppShell({ children }) {
  return (
    <div className="min-h-full bg-bg-base text-text-primary">
      <header className="sticky top-0 z-40 h-14 border-b border-bg-border bg-bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-full max-w-[1100px] items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-full bg-accent animate-pulse-glow"
            />
            <span className="font-display text-[18px] font-semibold tracking-tight text-text-primary">
              TruthLayer
            </span>
          </div>
          <div className="hidden items-center gap-2 text-text-muted sm:flex">
            <Activity className="h-3.5 w-3.5" aria-hidden />
            <span className="font-sans text-[12px] uppercase tracking-[0.18em]">
              AI Fact Verification Engine
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1100px] px-6 pb-16 pt-20 sm:pt-24">
        {children}
      </main>
    </div>
  )
}
