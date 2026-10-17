import { useEffect, useRef, useState } from 'react'
import { BrowserQRCodeReader } from '@zxing/browser'
import { QRCodeCanvas } from 'qrcode.react'
import {
  createSession,
  eventsUrl,
  fileUrl,
  processingStatus,
  startProcessing,
  thumbUrl,
} from '../api.js'

const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
const isLoopback = ['localhost', '127.0.0.1', '::1', ''].includes(window.location.hostname)

const ASSET_EVENTS = ['asset.created', 'asset.stored', 'asset.ready', 'asset.failed']
const JOB_EVENTS = ['job.started', 'job.progress', 'job.done', 'job.failed']

const SESSION_KEY = 'namma-space.session'

function loadSavedSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveSession(session) {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  } catch {
    // storage unavailable (private mode); the session just won't survive a reload
  }
}

function Home() {
  const videoRef = useRef(null)
  const [error, setError] = useState(null)
  const [started, setStarted] = useState(false)

  const startScanning = async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError('Camera permission is not allowed. Please allow camera access in your browser settings and try again.')
      return
    }
    try {
      // This triggers the browser's camera permission prompt
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      })
      videoRef.current.srcObject = stream
      setStarted(true)

      const reader = new BrowserQRCodeReader()
      reader.decodeFromVideoElement(videoRef.current, (result) => {
        if (result) {
          // The QR now encodes the phone URL, so just follow it.
          navigateToScan(result.getText())
        }
      })
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setError('Camera permission denied. Please allow camera access in your browser settings and try again.')
      } else if (err.name === 'NotFoundError') {
        setError('No camera found on this device.')
      } else {
        setError('Could not access camera: ' + err.message)
      }
    }
  }

  useEffect(() => {
    const video = videoRef.current
    return () => {
      if (video?.srcObject) {
        video.srcObject.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  if (isMobile) {
    return (
      <div className="min-h-screen bg-fuchsia-950 text-white flex flex-col items-center p-6">
        <h1 className="text-2xl font-bold mb-4">Scan QR Code</h1>

        {!started && !error && (
          <button
            onClick={startScanning}
            className="px-6 py-3 bg-fuchsia-600 hover:bg-fuchsia-500 rounded-xl font-semibold shadow-lg"
          >
            Start Scanning
          </button>
        )}

        {error && (
          <div className="bg-red-500/20 border border-red-400 text-red-200 rounded-xl p-4 text-center max-w-md">
            {error}
            <button onClick={startScanning} className="block mx-auto mt-3 px-4 py-2 bg-fuchsia-600 rounded-lg">
              Try Again
            </button>
          </div>
        )}

        <video ref={videoRef} autoPlay playsInline className="w-full max-w-md rounded-xl border-2 border-pink-400 mt-4" />
        <p className="text-gray-400 mt-4 text-sm">Point your camera at the QR code</p>
      </div>
    )
  }

  return <Laptop />
}

function navigateToScan(text) {
  try {
    const url = new URL(text)
    if (url.origin === window.location.origin) {
      window.location.assign(url.pathname + url.search)
    } else {
      window.location.assign(url.href)
    }
  } catch {
    // not a URL; ignore
  }
}

function Laptop() {
  const [session, setSession] = useState(() => loadSavedSession())
  const [error, setError] = useState(null)
  const [assets, setAssets] = useState([])
  const [job, setJob] = useState(null)

  useEffect(() => {
    if (session) return
    let cancelled = false
    createSession()
      .then((created) => {
        if (cancelled) return
        saveSession(created)
        setSession(created)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [session])

  // Show a completion from an earlier run (the job lives in the API's memory, the
  // inputs file on disk survives a restart).
  useEffect(() => {
    if (!session) return
    let cancelled = false
    processingStatus(session.session_id, session.owner_token)
      .then((status) => {
        if (!cancelled) setJob(status)
      })
      .catch(() => {
        // a status read is not worth surfacing an error for
      })
    return () => {
      cancelled = true
    }
  }, [session])

  useEffect(() => {
    if (!session) return
    const source = new EventSource(eventsUrl(session.session_id, session.owner_token))

    const upsert = (event) => {
      const asset = JSON.parse(event.data)
      setAssets((prev) => [...prev.filter((a) => a.id !== asset.id), asset])
    }
    const remove = (event) => {
      const { id } = JSON.parse(event.data)
      setAssets((prev) => prev.filter((a) => a.id !== id))
    }

    source.addEventListener('snapshot', (event) => {
      setAssets(JSON.parse(event.data).assets)
    })
    for (const name of ASSET_EVENTS) source.addEventListener(name, upsert)
    source.addEventListener('asset.removed', remove)
    const onJob = (event) => setJob(JSON.parse(event.data))
    for (const name of JOB_EVENTS) source.addEventListener(name, onJob)
    return () => source.close()
  }, [session])

  const phoneUrl = session ? `${window.location.origin}/phone/${session.pair_token}` : ''

  const startNewSession = async () => {
    try {
      const created = await createSession()
      saveSession(created)
      setAssets([])
      setJob(null)
      setSession(created)
    } catch (err) {
      setError(err.message)
    }
  }

  const processSession = async () => {
    if (!session) return
    setError(null)
    try {
      setJob(await startProcessing(session.session_id, session.owner_token))
    } catch (err) {
      setError(err.message)
    }
  }

  const processing = job?.status === 'running' || job?.status === 'queued'

  return (
    <div className="min-h-screen bg-gradient-to-br from-fuchsia-600 to-pink-500 flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl shadow-2xl p-10 flex flex-col items-center max-w-md w-full">
        <h1 className="text-3xl font-extrabold text-gray-800 mb-2">3D Scanner</h1>
        <p className="text-gray-500 text-center mb-6">Scan this QR code with your phone to start scanning</p>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-center w-full mb-4">
            {error}
          </div>
        )}

        {isLoopback && (
          <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-xl p-4 text-sm text-center w-full mb-4">
            You opened this page on <code>localhost</code>, so the QR points at an
            address your phone cannot reach. Open the LAN address Vite printed instead
            (e.g. <code>http://192.168.x.x:5173</code>).
          </div>
        )}

        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-inner">
          {phoneUrl ? (
            <QRCodeCanvas value={phoneUrl} size={220} />
          ) : (
            <div className="w-[220px] h-[220px] flex items-center justify-center text-gray-400">
              creating session…
            </div>
          )}
        </div>

        {session && (
          <p className="text-xs text-gray-400 mt-3 break-all text-center">{phoneUrl}</p>
        )}

        <button
          onClick={startNewSession}
          className="mt-4 px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded-xl text-sm font-semibold text-gray-700"
        >
          New session
        </button>

        <div className="mt-6 text-sm text-gray-600 space-y-2 text-left w-full bg-pink-50 rounded-xl p-4">
          <p className="font-semibold text-fuchsia-700">Instructions:</p>
          <p>1. Scan the QR code using your phone.</p>
          <p>2. Capture photos and videos with your phone.</p>
          <p>3. Uploads appear here live as they arrive.</p>
          <p>4. Press Process to prepare the images for the 3D stage.</p>
        </div>

        {session && (
          <div className="mt-6 w-full">
            <h2 className="text-sm font-semibold text-gray-700 mb-2">
              Received ({assets.length})
            </h2>
            {assets.length === 0 ? (
              <p className="text-xs text-gray-400">Nothing yet — uploads appear here live.</p>
            ) : (
              <ul className="space-y-2">
                {assets.map((asset) => (
                  <li key={asset.id} className="flex items-center gap-3 bg-gray-50 rounded-lg p-2">
                    {asset.kind === 'video' ? (
                      <video
                        src={fileUrl(session.session_id, asset.id, session.owner_token)}
                        poster={asset.thumb_path ? thumbUrl(session.session_id, asset.id, session.owner_token) : undefined}
                        controls
                        playsInline
                        preload="metadata"
                        className="w-40 h-24 rounded bg-black"
                      />
                    ) : asset.kind === 'photo' && asset.thumb_path ? (
                      <img
                        src={thumbUrl(session.session_id, asset.id, session.owner_token)}
                        alt=""
                        className="w-12 h-12 object-cover rounded"
                      />
                    ) : (
                      <div className="w-12 h-12 flex items-center justify-center rounded bg-gray-200 text-xs text-gray-500">
                        {asset.kind}
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-xs truncate text-gray-700">{asset.original_filename}</p>
                      <p className="text-[11px] text-gray-400">{asset.status}</p>
                      {asset.stored_path && (
                        <p className="text-[10px] text-gray-400 break-all">/data/{asset.stored_path}</p>
                      )}
                    </div>
                    <a
                      href={fileUrl(session.session_id, asset.id, session.owner_token)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-fuchsia-600 hover:underline"
                    >
                      open
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {session && (
          <div className="mt-6 w-full">
            <button
              onClick={processSession}
              disabled={processing || assets.length === 0}
              className="w-full px-4 py-3 bg-fuchsia-600 hover:bg-fuchsia-500 disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed rounded-xl font-semibold text-white shadow"
            >
              {processing ? 'Processing…' : 'Process session'}
            </button>

            {job && job.status !== 'idle' && (
              <div className="mt-3 text-xs text-gray-600 bg-gray-50 rounded-xl p-3 space-y-1 text-left">
                <p>
                  <span className="font-semibold text-fuchsia-700">Status:</span>{' '}
                  {job.status}
                  {job.total > 0 && ` — ${job.done}/${job.total} uploads`}
                </p>
                {job.phase && <p className="text-gray-500">{job.phase}</p>}
                {job.message && <p className="text-gray-700">{job.message}</p>}
                {job.error && <p className="text-red-600 break-all">{job.error}</p>}
                {job.inputs_file && (
                  <p className="text-[10px] text-gray-400 break-all">/data/{job.inputs_file}</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default Home
