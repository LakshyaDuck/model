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

// GLB URLs for Three.js GLTFLoader; the owner token rides in the query because
// loader requests do not share the app's Authorization header.
export const modelUrl = (sessionId, ownerToken) =>
  withToken(`/api/sessions/${sessionId}/model`, ownerToken)

export const collisionModelUrl = (sessionId, ownerToken) =>
  withToken(`/api/sessions/${sessionId}/model/collision`, ownerToken)

// Process-button: starts/fetches the OpenCV pass over a session's photos + videos.
// Owner-token endpoints, so the token rides in the Authorization header.
export async function startProcessing(sessionId, ownerToken) {
  const response = await fetch(`/api/sessions/${sessionId}/process`, {
    method: 'POST',
    headers: { authorization: `Bearer ${ownerToken}` },
  })
  if (!response.ok) throw new Error(`could not start processing (${response.status})`)
  return response.json()
}

export async function processingStatus(sessionId, ownerToken) {
  const response = await fetch(`/api/sessions/${sessionId}/process`, {
    headers: { authorization: `Bearer ${ownerToken}` },
  })
  if (!response.ok) throw new Error(`could not read processing status (${response.status})`)
  return response.json()
}

// Absolute so tus-js-client never resolves it against the /phone/:token route.
export const tusEndpoint = `${window.location.origin}/files/`
