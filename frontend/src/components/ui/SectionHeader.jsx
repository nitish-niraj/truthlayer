export default function SectionHeader({ title, subtitle, eyebrow }) {
  return (
    <header className="mb-8">
      {eyebrow ? (
        <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.22em] text-accent">
          {eyebrow}
        </p>
      ) : null}
      <h1 className="font-display text-2xl font-semibold tracking-tight text-text-primary sm:text-3xl">
        {title}
      </h1>
      {subtitle ? (
        <p className="mt-2 max-w-2xl text-sm text-text-secondary sm:text-base">
          {subtitle}
        </p>
      ) : null}
    </header>
  )
}
