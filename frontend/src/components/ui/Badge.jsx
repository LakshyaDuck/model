const TONES = {
  neutral: 'border-white/15 bg-white/5 text-neutral-300',
  accent: 'border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-200',
  success: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  warning: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  danger: 'border-red-400/30 bg-red-500/10 text-red-200',
}

export default function Badge({ children, tone = 'neutral', className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide ${TONES[tone] || TONES.neutral} ${className}`}
    >
      {children}
    </span>
  )
}
