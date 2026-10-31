import Button from './Button.jsx'

export default function ErrorBanner({ message, onRetry, retryLabel = 'Try again', className = '' }) {
  if (!message) return null
  return (
    <div
      role="alert"
      className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200 ${className}`}
    >
      <span>{message}</span>
      {onRetry && (
        <Button variant="danger" size="sm" onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
    </div>
  )
}
