import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  checkHealth,
  createSession as createSessionRequest,
  eventsUrl,
  getManifest,
  processingStatus,
  rotatePairToken as rotatePairTokenRequest,
  startProcessing as startProcessingRequest,
} from '../api.js'
import { SessionContext } from './SessionContext.js'

const ASSET_EVENTS = ['asset.created', 'asset.stored', 'asset.ready', 'asset.failed']
const JOB_EVENTS = ['job.started', 'job.progress', 'job.done', 'job.failed']
const FATAL_STATUSES = new Set([401, 404, 410])

function isFatalApiError(error) {
  return error instanceof ApiError && FATAL_STATUSES.has(error.status)
}

export default function SessionProvider({ children }) {
  // ownerToken is deliberately memory-only: never localStorage/sessionStorage.
  const [session, setSession] = useState(null)
  const [assets, setAssets] = useState([])
  const [job, setJob] = useState(null)
  const [connection, setConnection] = useState('idle')
  const [backendStatus, setBackendStatus] = useState('checking')
  const [creating, setCreating] = useState(false)
  // A 401/404/410 from the API means this tab can no longer use the session.
  const [sessionError, setSessionError] = useState(null)
  // Gallery state for the initial manifest read. SSE snapshots clear loading.
  const [assetsLoading, setAssetsLoading] = useState(false)
  const [assetsError, setAssetsError] = useState(null)
  // Native EventSource retries on its own, but a blocked/proxied stream can stay
  // closed. Bumping this key recreates the stream while the connection is down.
  const [reconnectKey, setReconnectKey] = useState(0)

  const sessionId = session?.sessionId
  const ownerToken = session?.ownerToken

  const createSession = useCallback(async () => {
    setCreating(true)
    setSessionError(null)
    try {
      const created = await createSessionRequest()
      const next = {
        sessionId: created.session_id,
        ownerToken: created.owner_token,
        pairToken: created.pair_token,
        pairExpiresAt: created.pair_expires_at,
        phoneUrl: created.phone_url,
      }
      setAssets([])
      setJob(null)
      setConnection('connecting')
      setAssetsLoading(true)
      setAssetsError(null)
      setSession(next)
      return next
    } finally {
      setCreating(false)
    }
  }, [])

  const rotatePairing = useCallback(async () => {
    if (!sessionId || !ownerToken) throw new Error('No session is loaded in this tab.')
    const next = await rotatePairTokenRequest(sessionId, ownerToken)
    setSession((previous) =>
      previous
        ? {
            ...previous,
            pairToken: next.pair_token,
            pairExpiresAt: next.pair_expires_at,
            phoneUrl: next.phone_url,
          }
        : previous,
    )
    setSessionError(null)
    return next
  }, [sessionId, ownerToken])

  const refreshManifest = useCallback(async () => {
    if (!sessionId || !ownerToken) throw new Error('No session is loaded in this tab.')
    setAssetsLoading(true)
    try {
      const manifest = await getManifest(sessionId, ownerToken)
      setAssets(manifest.assets || [])
      setAssetsError(null)
      return manifest
    } catch (error) {
      if (isFatalApiError(error)) setSessionError(error.message)
      else setAssetsError(error.message)
      throw error
    } finally {
      setAssetsLoading(false)
    }
  }, [sessionId, ownerToken])

  const startProcessing = useCallback(async () => {
    if (!sessionId || !ownerToken) throw new Error('No session is loaded in this tab.')
    const next = await startProcessingRequest(sessionId, ownerToken)
    setJob(next)
    return next
  }, [sessionId, ownerToken])

  // Backend reachability is separate from the live session event stream. The shell
  // can still show a useful status before a session exists or after a refresh.
  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      try {
        await checkHealth()
        if (!cancelled) setBackendStatus('online')
      } catch {
        if (!cancelled) setBackendStatus('offline')
      }
    }

    poll()
    const timer = window.setInterval(poll, 30000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  // Seed the workspace from the manifest and the current job snapshot, then
  // follow changes through the event stream. Keyed on the identity of the
  // session only, so rotating a pair token does not restart the stream.
  useEffect(() => {
    if (!sessionId || !ownerToken) return undefined

    let cancelled = false
    // The snapshot and job events can arrive before these one-shot reads resolve.
    // In that case keep the live value instead of overwriting it with older data.
    let snapshotReceived = false
    let jobEventReceived = false

    Promise.allSettled([
      getManifest(sessionId, ownerToken),
      processingStatus(sessionId, ownerToken),
    ]).then(([manifestResult, jobResult]) => {
      if (cancelled) return
      if (manifestResult.status === 'fulfilled') {
        if (!snapshotReceived) setAssets(manifestResult.value.assets || [])
        setAssetsError(null)
      } else if (!isFatalApiError(manifestResult.reason)) {
        setAssetsError(manifestResult.reason.message)
      }
      setAssetsLoading(false)
      if (jobResult.status === 'fulfilled' && !jobEventReceived) {
        setJob(jobResult.value)
      }
      const rejected = [manifestResult, jobResult].find(
        (result) => result.status === 'rejected' && isFatalApiError(result.reason),
      )
      if (rejected) setSessionError(rejected.reason.message)
    })

    const source = new EventSource(eventsUrl(sessionId, ownerToken))

    const upsert = (event) => {
      const asset = JSON.parse(event.data)
      setAssets((previous) => {
        const index = previous.findIndex((item) => item.id === asset.id)
        if (index === -1) return [...previous, asset]
        const next = [...previous]
        next[index] = asset
        return next
      })
    }
    const remove = (event) => {
      const { id } = JSON.parse(event.data)
      setAssets((previous) => previous.filter((item) => item.id !== id))
    }
    const onJob = (event) => {
      jobEventReceived = true
      setJob(JSON.parse(event.data))
    }

    source.onopen = () => {
      if (!cancelled) setConnection('live')
    }
    source.onerror = () => {
      if (!cancelled) setConnection('offline')
    }
    source.addEventListener('snapshot', (event) => {
      snapshotReceived = true
      setAssets(JSON.parse(event.data).assets)
      setAssetsLoading(false)
      setAssetsError(null)
    })
    for (const name of ASSET_EVENTS) source.addEventListener(name, upsert)
    source.addEventListener('asset.removed', remove)
    for (const name of JOB_EVENTS) source.addEventListener(name, onJob)

    return () => {
      cancelled = true
      source.close()
    }
  }, [sessionId, ownerToken, reconnectKey])

  // If the stream does not recover on its own, rebuild it after a short delay.
  useEffect(() => {
    if (!sessionId || connection !== 'offline') return undefined
    const timer = window.setTimeout(() => setReconnectKey((value) => value + 1), 8000)
    return () => window.clearTimeout(timer)
  }, [sessionId, connection, reconnectKey])

  // Polling fallback: EventSource reconnects on its own, but while it is not live
  // the manifest and processing snapshot are refreshed with exponential backoff.
  useEffect(() => {
    if (!sessionId || !ownerToken || connection === 'live') return undefined

    let cancelled = false
    let timer
    let delay = 3000

    const poll = async () => {
      try {
        const [manifest, status] = await Promise.all([
          getManifest(sessionId, ownerToken),
          processingStatus(sessionId, ownerToken),
        ])
        if (cancelled) return
        setAssets(manifest.assets || [])
        setJob(status)
        setAssetsError(null)
        setAssetsLoading(false)
        delay = 3000
      } catch (error) {
        if (cancelled) return
        if (isFatalApiError(error)) {
          setSessionError(error.message)
          return
        }
        setAssetsError('Live updates are disconnected. Retrying automatically…')
        setAssetsLoading(false)
        delay = Math.min(delay * 2, 30000)
      }
      if (!cancelled) timer = window.setTimeout(poll, delay)
    }

    timer = window.setTimeout(poll, delay)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [sessionId, ownerToken, connection])

  const value = useMemo(
    () => ({
      session,
      assets,
      assetsLoading,
      assetsError,
      job,
      connection,
      backendStatus,
      creating,
      sessionError,
      createSession,
      rotatePairing,
      refreshManifest,
      startProcessing,
    }),
    [
      session,
      assets,
      assetsLoading,
      assetsError,
      job,
      connection,
      backendStatus,
      creating,
      sessionError,
      createSession,
      rotatePairing,
      refreshManifest,
      startProcessing,
    ],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
