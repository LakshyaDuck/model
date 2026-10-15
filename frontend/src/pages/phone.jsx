import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import * as tus from 'tus-js-client'
import { checkPair, tusEndpoint } from '../api.js'

const GUESS = {
  mov: 'video/quicktime', mp4: 'video/mp4', webm: 'video/webm', m4v: 'video/x-m4v',
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', heic: 'image/heic',
  webp: 'image/webp', pdf: 'application/pdf', json: 'application/json',
  csv: 'text/csv', txt: 'text/plain',
}

const mimeOf = (file) =>
  file.type || GUESS[(file.name.split('.').pop() || '').toLowerCase()] || ''

// crypto.randomUUID() needs a secure context; this page may be plain HTTP on the
// phone, so use a local id that always exists.
const localId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

// The gallery picker is multi-purpose, so each file labels itself.
function kindOf(file) {
  const mime = mimeOf(file)
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('image/')) return 'photo'
  return null
}

function Phone() {
  const { token } = useParams()
  const [pair, setPair] = useState(null)
  const [pairError, setPairError] = useState(null)
  const [items, setItems] = useState([])

  useEffect(() => {
    let cancelled = false
    checkPair(token)
      .then((session) => {
        if (!cancelled) setPair(session)
      })
      .catch((err) => {
        if (!cancelled) setPairError(err.reason || 'invalid')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const update = (id, patch) =>
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)))

  const send = (file, kind) => {
    if (kind === 'auto') kind = kindOf(file)
    if (!kind) {
      setItems((prev) => [
        { id: localId(), name: file.name, kind: '?', state: 'error', error: 'unsupported type', progress: 0 },
        ...prev,
      ])
      return
    }

    const id = localId()
    setItems((prev) => [{ id, name: file.name, kind, state: 'uploading', progress: 0 }, ...prev])

    const upload = new tus.Upload(file, {
      endpoint: tusEndpoint,
      metadata: { pair_token: token, kind, filename: file.name, filetype: mimeOf(file) },
      chunkSize: 4 * 1024 * 1024,
      retryDelays: [0, 1000, 3000, 5000, 10000, 20000],
      removeFingerprintOnSuccess: true,
      onProgress: (sent, total) => update(id, { progress: total ? sent / total : 0 }),
      onSuccess: () => update(id, { state: 'done', progress: 1 }),
      onError: (error) => update(id, { state: 'error', error: error.message || 'failed' }),
    })

    // Resume anything this browser already started for this file, then upload the rest.
    upload
      .findPreviousUploads()
      .then((previous) => {
        if (previous.length) upload.resumeFromPreviousUpload(previous[0])
      })
      .catch(() => {})
      .finally(() => upload.start())
  }

  const queue = (kind) => (event) => {
    for (const file of event.target.files) send(file, kind)
    event.target.value = ''
  }

  if (pairError) {
    return (
      <div className="min-h-screen bg-fuchsia-950 text-white flex flex-col items-center justify-center p-6 text-center">
        <h1 className="text-xl font-bold mb-2">Can’t start</h1>
        <p className="text-pink-200 max-w-sm">
          {pairError === 'expired'
            ? 'This QR code has expired. Close this page and scan the new one on the laptop.'
            : 'This QR code is not valid. Scan the code currently shown on the laptop.'}
        </p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-fuchsia-950 text-white flex flex-col items-center p-6">
      <h1 className="text-xl font-bold mb-1">Send to room</h1>
      <p className="text-sm text-pink-200 mb-6">
        {pair
          ? `paired · session ${pair.session_id.slice(0, 8)}…`
          : 'checking QR…'}
      </p>

      <div className="w-full max-w-md space-y-3">
        {/* Each camera input carries a single accept type: Android Chrome ignores
            capture="environment" when accept mixes image/* and video/* (Chromium #40220959). */}
        <label className="block w-full text-center px-4 py-4 bg-fuchsia-600 hover:bg-fuchsia-500 rounded-xl font-semibold shadow-lg cursor-pointer">
          Take a photo
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={queue('auto')}
          />
        </label>
        <label className="block w-full text-center px-4 py-4 bg-fuchsia-600 hover:bg-fuchsia-500 rounded-xl font-semibold shadow-lg cursor-pointer">
          Record a video
          <input
            type="file"
            accept="video/*"
            capture="environment"
            className="hidden"
            onChange={queue('auto')}
          />
        </label>
        <label className="block w-full text-center px-4 py-4 bg-fuchsia-700 hover:bg-fuchsia-600 rounded-xl font-semibold shadow-lg cursor-pointer">
          Pick from gallery (multiple)
          <input
            type="file"
            accept="image/*,video/*"
            multiple
            className="hidden"
            onChange={queue('auto')}
          />
        </label>
        <label className="block w-full text-center px-4 py-3 bg-fuchsia-800 hover:bg-fuchsia-700 rounded-xl cursor-pointer">
          Floor plan (image / PDF)
          <input
            type="file"
            accept="image/*,application/pdf"
            className="hidden"
            onChange={queue('floorplan')}
          />
        </label>
        <label className="block w-full text-center px-4 py-3 bg-fuchsia-800 hover:bg-fuchsia-700 rounded-xl cursor-pointer">
          Sensor log (.json / .csv / .txt)
          <input
            type="file"
            accept=".json,.csv,.txt,application/json"
            className="hidden"
            onChange={queue('sensor')}
          />
        </label>
      </div>

      <div className="w-full max-w-md mt-8 space-y-2">
        {items.map((item) => (
          <div key={item.id} className="bg-white/10 rounded-lg p-3">
            <div className="flex justify-between text-xs">
              <span className="truncate mr-2">{item.kind}: {item.name}</span>
              <span className={item.state === 'error' ? 'text-red-300' : 'text-pink-200'}>
                {item.state === 'error' ? item.error : item.state}
              </span>
            </div>
            <div className="mt-2 h-2 bg-white/20 rounded overflow-hidden">
              <div
                className={`h-full ${item.state === 'error' ? 'bg-red-400' : 'bg-fuchsia-400'}`}
                style={{ width: `${Math.round((item.progress || 0) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {items.some((item) => item.state === 'done') && (
        <p className="text-sm text-pink-200 mt-6 text-center">
          Sent — check the laptop to continue.
        </p>
      )}
    </div>
  )
}

export default Phone
