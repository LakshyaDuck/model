// Thin client for the backend API. In dev, Vite proxies /api and /files to the
// backend and tusd, so every URL here stays same-origin.

export class PairError extends Error {
  constructor(reason) {
    super(reason) // 'expired' | 'invalid'
    this.reason = reason
  }
}

export async function createSession() {
  const response = await fetch('/api/sessions', { method: 'POST' })
  if (!response.ok) throw new Error(`could not create session (${response.status})`)
  return response.json()
}

export async function checkPair(token) {
  const response = await fetch(`/api/pair/${encodeURIComponent(token)}`)
  if (response.status === 410) throw new PairError('expired')
  if (!response.ok) throw new PairError('invalid')
  return response.json()
}

const withToken = (path, ownerToken) => `${path}?token=${encodeURIComponent(ownerToken)}`

export const eventsUrl = (sessionId, ownerToken) =>
  withToken(`/api/sessions/${sessionId}/events`, ownerToken)

export const fileUrl = (sessionId, assetId, ownerToken) =>
  withToken(`/api/sessions/${sessionId}/assets/${assetId}/file`, ownerToken)

export const thumbUrl = (sessionId, assetId, ownerToken) =>
  withToken(`/api/sessions/${sessionId}/assets/${assetId}/thumb`, ownerToken)

// Absolute so tus-js-client never resolves it against the /phone/:token route.
export const tusEndpoint = `${window.location.origin}/files/`
