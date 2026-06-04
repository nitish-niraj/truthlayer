import { forwardRef } from 'react'
import { Loader2 } from 'lucide-react'

const VARIANTS = {
  primary:
    'bg-accent text-black hover:bg-accent-hover hover:shadow-[0_0_20px_var(--accent-dim)]',
  secondary:
    'bg-bg-elevated text-text-primary border border-bg-border hover:border-text-muted',
  ghost:
    'bg-transparent text-text-secondary hover:text-text-primary hover:bg-bg-elevated',
  outline:
    'bg-transparent text-text-primary border border-bg-border hover:border-accent hover:text-accent',
}

const Button = forwardRef(function Button(
  {
    children,
    onClick,
    disabled = false,
    loading = false,
    variant = 'primary',
    type = 'button',
    className = '',
    ...rest
  },
  ref
) {
  const isDisabled = disabled || loading
  return (
    <button
      ref={ref}
      type={type}
      onClick={onClick}
      disabled={isDisabled}
      className={[
        'inline-flex items-center justify-center gap-2 rounded-md px-5 py-2.5 text-sm font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant] || VARIANTS.primary,
        className,
      ].join(' ')}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
      {children}
    </button>
  )
})

export default Button
