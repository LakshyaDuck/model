export default function ProgressBar({ value = 0, max = 100, label, tone = 'accent', className = '' }) {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  const bar = {
    accent: 'bg-fuchsia-500',
    success: 'bg-emerald-500',
    danger: 'bg-red-500',
  }[tone] || 'bg-fuchsia-500'

  return (
    <div className={className}>
      {label && (
        <div className="mb-1.5 flex items-center justify-between text-xs text-neutral-400">
          <span>{label}</span>
          <span>{Math.round(percent)}%</span>
        </div>
      )}
      <div
        className="h-2 overflow-hidden rounded-full bg-white/10"
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={`h-full rounded-full transition-all ${bar}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}
