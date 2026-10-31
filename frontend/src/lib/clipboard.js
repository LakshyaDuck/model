// Clipboard access needs a secure context in modern browsers. Fall back to the
// legacy selection trick so the action also works on plain-HTTP LAN addresses,
// which is how the laptop workspace is often opened.
export async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }

  const area = document.createElement('textarea')
  area.value = value
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.top = '0'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const copied = document.execCommand('copy')
  document.body.removeChild(area)
  if (!copied) throw new Error('Copy is not available in this browser.')
}
