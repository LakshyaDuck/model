export default function Loading({ label = 'Loading…', className = '' }) {
  return (
    <div className={`flex items-center gap-3 text-sm text-neutral-400 ${className}`} role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-fuchsia-400" />
      <span>{label}</span>
    </div>
  )
}
