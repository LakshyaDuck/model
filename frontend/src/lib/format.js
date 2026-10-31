export function formatDate(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`
}

export function shortId(value, length = 8) {
  if (!value) return '—'
  return value.length > length ? `${value.slice(0, length)}…` : value
}

// Coarse, human-readable duration for countdowns. Deliberately does not include
// days because pair tokens are short lived.
export function formatDuration(milliseconds) {
  const totalSeconds = Math.max(0, Math.round(Math.abs(milliseconds) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    return `${hours} h ${minutes % 60} min`
  }
  if (minutes > 0) return `${minutes} min ${seconds} s`
  return `${seconds} s`
}

// `now` is passed in so components can keep the value in state and stay pure.
export function formatExpiry(value, now = 0) {
  if (!value) return 'unknown'
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return 'unknown'
  const diff = time - now
  return diff > 0 ? `in ${formatDuration(diff)}` : `expired ${formatDuration(diff)} ago`
}
