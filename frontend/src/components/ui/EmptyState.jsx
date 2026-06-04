export default function EmptyState({ icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      {icon ? (
        <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-bg-border bg-bg-elevated text-text-secondary">
          {icon}
        </div>
      ) : null}
      <h2 className="font-display text-lg font-semibold text-text-primary">{title}</h2>
      {description ? (
        <p className="mt-2 max-w-sm text-sm text-text-secondary">{description}</p>
      ) : null}
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  )
}
