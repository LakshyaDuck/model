const COPY = {
  connecting: 'Connecting to the capture stream…',
  offline: 'Connection lost. Events will resume automatically when the backend is reachable.',
  online: 'Backend reachable. No session is attached to this tab.',
  checking: 'Checking the backend connection…',
}

export default function ConnectionBanner({ status }) {
  if (!status || status === 'live' || status === 'idle') return null
  const tone = status === 'offline' ? 'border-red-400/30 bg-red-500/10 text-red-200' : 'border-amber-400/30 bg-amber-500/10 text-amber-200'
  return (
    <div className={`mb-6 rounded-xl border px-4 py-3 text-sm ${tone}`} role="status">
      {COPY[status] || COPY.connecting}
    </div>
  )
}
