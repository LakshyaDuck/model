const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function uploadCapture(blob, filename) {
  const form = new FormData()
  form.append('file', blob, filename)

  const response = await fetch(`${API_URL}/upload`, {
    method: 'POST',
    body: form,
  })

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`)
  }

  return response.json()
}
