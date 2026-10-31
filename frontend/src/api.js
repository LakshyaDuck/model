// Thin client for the backend API. In dev, Vite proxies /api and /files to the
// backend and tusd, so every URL here stays same-origin.
//
// This module is the single boundary between React components and the capture
// API: request construction, auth headers, timeouts, and error parsing live here.

export class ApiError extends Error {
  constructor(message, { status = 0, detail = null, code = 'error', cause } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.code = code
    if (cause) this.cause = cause
  }
}

const STATUS_MESSAGES = {
  400: 'The backend rejected this request.',
  401: 'The owner token for this session is missing or invalid. Start a new scan to continue.',
  403: 'This action is not allowed for the current session.',
  404: 'This session does not exist on the backend, or the requested resource is missing.',
  409: 'The request conflicts with the current session state.',
  410: 'This resource has expired and can no longer be used.',
  422: 'The backend could not accept these values.',
  429: 'Too many requests. Wait a moment and try again.',
  500: 'The backend reported an internal error.',
  502: 'The backend is unreachable through the development proxy.',
  503: 'The backend is starting up or unavailable. Try again shortly.',
  504: 'The backend did not respond in time.',
}

const STATUS_CODES = {
  401: 'unauthorized',
  404: 'not_found',
  410: 'gone',
}

function messageForStatus(status, detail) {
  // 401 and 410 are terminal for this tab: say what happened and what to do
  // next, keeping the backend detail for debugging.
  if (status === 401) {
    return `Session access denied: the owner token is missing or invalid. Start a new scan to continue.${
      detail ? ` (${detail})` : ''
    }`
  }
  if (status === 410) {
    return `This link has expired and can no longer be used.${detail ? ` (${detail})` : ''}`
  }
  if (detail) return detail
  return STATUS_MESSAGES[status] || `Request failed (${status}).`
}

// Reads the contract's `{ "detail": "..." }` error body without assuming it is
// JSON. Falls back to status text when a proxy or gateway returns HTML.
async function parseErrorResponse(response) {
  let detail = null
  try {
    const type = response.headers.get('content-type') || ''
    if (type.includes('application/json')) {
      const body = await response.json()
      const raw = body?.detail ?? body?.message ?? body?.error
      detail = typeof raw === 'string' ? raw : raw ? JSON.stringify(raw) : null
    }
  } catch {
    detail = null
  }
  return new ApiError(messageForStatus(response.status, detail), {
    status: response.status,
    detail,
    code: STATUS_CODES[response.status] || 'http_error',
  })
}

/**
 * Fetch helper with owner-token auth, timeout, abort support, and consistent
 * error parsing. Callers can pass their own AbortSignal to cancel a request.
 */
export async function request(path, options = {}) {
  const {
    method = 'GET',
    ownerToken,
    body,
    signal,
    timeoutMs = 15000,
    headers = {},
  } = options

  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  const relayAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', relayAbort, { once: true })
  }

  try {
    const response = await fetch(path, {
      method,
      body,
      signal: controller.signal,
      headers: {
        accept: 'application/json',
        ...(body ? { 'content-type': 'application/json' } : {}),
        ...(ownerToken ? { authorization: `Bearer ${ownerToken}` } : {}),
        ...headers,
      },
    })

    if (!response.ok) throw await parseErrorResponse(response)
    if (response.status === 204) return null

    const type = response.headers.get('content-type') || ''
    return type.includes('application/json') ? response.json() : response.text()
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error.name === 'AbortError') {
      if (timedOut) {
        throw new ApiError('The backend did not respond in time. Check the connection and try again.', {
          status: 0,
          code: 'timeout',
          cause: error,
        })
      }
      throw new ApiError('The request was cancelled.', { status: 0, code: 'aborted', cause: error })
    }
    throw new ApiError(
      'Could not reach the backend. Check that the capture service is running.',
      { status: 0, code: 'network_error', cause: error },
    )
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', relayAbort)
  }
}

// The backend health route is /healthz (not /health). Vite proxies it in dev.
export async function checkHealth() {
  return request('/healthz', { timeoutMs: 4000 })
}

export async function createSession() {
  // Explicit user action only: never call this from a mount effect.
  return request('/api/sessions', { method: 'POST', timeoutMs: 20000 })
}

export async function getManifest(sessionId, ownerToken, options = {}) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/manifest`, {
    ownerToken,
    ...options,
  })
}

export async function rotatePairToken(sessionId, ownerToken, options = {}) {
  // Rotation immediately invalidates the previous pair token.
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/pair-token`, {
    method: 'POST',
    ownerToken,
    ...options,
  })
}

export class PairError extends Error {
  constructor(reason, { status, detail } = {}) {
    super(reason) // 'expired' | 'invalid'
    this.name = 'PairError'
    this.reason = reason
    this.status = status
    this.detail = detail
  }
}

export async function checkPair(token, options = {}) {
  try {
    return await request(`/api/pair/${encodeURIComponent(token)}`, {
      timeoutMs: 10000,
      ...options,
    })
  } catch (error) {
    if (error.status === 410) {
      throw new PairError('expired', { status: 410, detail: error.detail })
    }
    if (error.status === 404) {
      throw new PairError('invalid', { status: 404, detail: error.detail })
    }
    // Network and 5xx failures surface as an ApiError so the phone page can show
    // a real transport problem instead of claiming the QR code is invalid.
    throw error
  }
}

const withToken = (path, ownerToken) => `${path}?token=${encodeURIComponent(ownerToken)}`

export const eventsUrl = (sessionId, ownerToken) =>
  withToken(`/api/sessions/${encodeURIComponent(sessionId)}/events`, ownerToken)

export const fileUrl = (sessionId, assetId, ownerToken) =>
  withToken(
    `/api/sessions/${encodeURIComponent(sessionId)}/assets/${encodeURIComponent(assetId)}/file`,
    ownerToken,
  )

export const thumbUrl = (sessionId, assetId, ownerToken) =>
  withToken(
    `/api/sessions/${encodeURIComponent(sessionId)}/assets/${encodeURIComponent(assetId)}/thumb`,
    ownerToken,
  )

// GLB URLs for Three.js GLTFLoader; the owner token rides in the query because
// loader requests do not share the app's Authorization header.
export const modelUrl = (sessionId, ownerToken) =>
  withToken(`/api/sessions/${encodeURIComponent(sessionId)}/model`, ownerToken)

export const collisionModelUrl = (sessionId, ownerToken) =>
  withToken(`/api/sessions/${encodeURIComponent(sessionId)}/model/collision`, ownerToken)

// Process-button: starts/fetches the OpenCV pass over a session's photos + videos.
export async function startProcessing(sessionId, ownerToken, options = {}) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/process`, {
    method: 'POST',
    ownerToken,
    ...options,
  })
}

export async function processingStatus(sessionId, ownerToken, options = {}) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/process`, {
    ownerToken,
    ...options,
  })
}

// Absolute so tus-js-client never resolves it against the /phone/:token route.
export const tusEndpoint = `${window.location.origin}/files/`
