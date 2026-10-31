import { Link } from 'react-router-dom'

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-400 focus-visible:ring-offset-2 focus-visible:ring-offset-neutral-950 disabled:pointer-events-none disabled:opacity-50'

const VARIANTS = {
  primary: 'bg-fuchsia-600 text-white hover:bg-fuchsia-500',
  secondary: 'border border-white/15 bg-neutral-900 text-neutral-100 hover:bg-neutral-800',
  ghost: 'text-neutral-300 hover:bg-white/5 hover:text-white',
  danger: 'border border-red-400/30 bg-red-500/10 text-red-200 hover:bg-red-500/20',
}

const SIZES = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-5 py-3 text-sm',
}

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  to,
  href,
  ...props
}) {
  const classes = `${BASE} ${VARIANTS[variant] || VARIANTS.primary} ${SIZES[size] || SIZES.md} ${className}`

  if (to) {
    return (
      <Link to={to} className={classes} {...props}>
        {children}
      </Link>
    )
  }
  if (href) {
    return (
      <a href={href} className={classes} {...props}>
        {children}
      </a>
    )
  }
  return (
    <button type="button" className={classes} {...props}>
      {children}
    </button>
  )
}
