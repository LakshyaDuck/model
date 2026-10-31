export default function EmptyState({ title, description, action, className = '' }) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-xl border border-dashed border-white/15 bg-neutral-900/40 px-6 py-12 text-center ${className}`}
    >
      <div className="mb-3 h-10 w-10 rounded-lg border border-white/10 bg-white/5" aria-hidden="true" />
      <h3 className="text-sm font-semibold text-neutral-200">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-neutral-400">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
