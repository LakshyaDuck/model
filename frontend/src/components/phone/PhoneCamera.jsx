import { useCallback, useEffect, useRef, useState } from 'react'

// Live camera capture for the phone page.
//
// getUserMedia only exists in a secure context. A phone opening the laptop's LAN
// address over plain HTTP has no navigator.mediaDevices at all, so this component
// explains that honestly and the page keeps the native capture inputs as the
// fallback (they hand off to the phone's own camera app and work over HTTP).
//
// The camera is never started automatically: the user taps a button, which both
// avoids a surprise permission prompt and lets any failure be reported in place.

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0', ''])

function isLoopbackHost(hostname) {
  return LOOPBACK_HOSTS.has((hostname || '').toLowerCase())
}

function getSupport() {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return { supported: false, reason: 'unsupported' }
  }
  if (!window.isSecureContext) {
    return { supported: false, reason: 'insecure' }
  }
  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
    return { supported: false, reason: 'unsupported' }
  }
  return { supported: true, reason: null }
}

function describeCameraError(error) {
  switch (error?.name) {
    case 'NotAllowedError':
      return 'Camera permission was denied. Allow camera access for this site in the browser settings, then try again.'
    case 'SecurityError':
      return 'The browser blocked camera access for security reasons. Make sure this page is served over HTTPS and camera access is allowed.'
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return 'No camera was found on this device.'
    case 'NotReadableError':
    case 'TrackStartError':
      return 'The camera is already in use by another app. Close it and try again.'
    case 'OverconstrainedError':
    case 'ConstraintNotSatisfiedError':
      return 'No rear-facing camera matched the requested settings. Try again, or use the native capture button below.'
    case 'AbortError':
      return 'The camera stopped before it could start. Try again.'
    default:
      return `The camera could not start: ${error?.message || 'unknown error'}.`
  }
}

function pickVideoMime() {
  if (typeof window === 'undefined' || typeof window.MediaRecorder !== 'function') return ''
  const candidates = [
    'video/webm;codecs=vp9',
    'video/webm;codecs=vp8',
    'video/webm',
    'video/mp4;codecs=avc1',
    'video/mp4',
  ]
  return candidates.find((type) => window.MediaRecorder.isTypeSupported(type)) || ''
}

function extensionFor(mime) {
  if (mime.includes('mp4')) return 'mp4'
  if (mime.includes('webm')) return 'webm'
  return 'video'
}

function stamp() {
  const now = new Date()
  const pad = (value, size = 2) => String(value).padStart(size, '0')
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(
    now.getHours(),
  )}${pad(now.getMinutes())}${pad(now.getSeconds())}`
}

export default function PhoneCamera({ onCapture, disabled = false }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const captureHandlerRef = useRef(onCapture)
  const mountedRef = useRef(true)

  const [support] = useState(getSupport)
  const [active, setActive] = useState(false)
  const [starting, setStarting] = useState(false)
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    captureHandlerRef.current = onCapture
  }, [onCapture])

  const stopStream = useCallback(() => {
    const stream = streamRef.current
    streamRef.current = null
    if (stream) stream.getTracks().forEach((track) => track.stop())
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.onstop = null
        recorderRef.current.stop()
      }
      recorderRef.current = null
      stopStream()
    }
  }, [stopStream])

  useEffect(() => {
    if (!recording) return undefined
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [recording])

  // The <video> only exists while active, so attach the stream after React has
  // rendered it; assigning srcObject inside start() would run before the element
  // mounts and leave the preview blank.
  useEffect(() => {
    if (!active) return
    const video = videoRef.current
    const stream = streamRef.current
    if (!video || !stream) return
    video.srcObject = stream
    video.play().catch(() => {})
  }, [active])

  const start = async () => {
    setError(null)
    setNotice(null)
    if (!support.supported) return
    setStarting(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      })
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream
      setActive(true)
    } catch (err) {
      setError(describeCameraError(err))
      stopStream()
      setActive(false)
    } finally {
      if (mountedRef.current) setStarting(false)
    }
  }

  const stop = () => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.onstop = null
      recorderRef.current.stop()
    }
    recorderRef.current = null
    chunksRef.current = []
    setRecording(false)
    setElapsed(0)
    stopStream()
    setActive(false)
  }

  const emit = (file) => {
    setNotice(`Captured ${file.name}`)
    if (captureHandlerRef.current) captureHandlerRef.current(file)
  }

  const takePhoto = () => {
    setError(null)
    const video = videoRef.current
    if (!video || !video.videoWidth || !video.videoHeight) {
      setError('The camera is still warming up. Wait a moment and try again.')
      return
    }
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext('2d')
    if (!context) {
      setError('This browser could not create the image. Use the native capture button below.')
      return
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob(
      (blob) => {
        if (!mountedRef.current) return
        if (!blob) {
          setError('The photo could not be encoded. Use the native capture button below.')
          return
        }
        emit(new File([blob], `camera-photo-${stamp()}.jpg`, { type: 'image/jpeg' }))
      },
      'image/jpeg',
      0.92,
    )
  }

  const startRecording = () => {
    setError(null)
    setNotice(null)
    const stream = streamRef.current
    if (!stream) {
      setError('The camera is not running. Open the camera first.')
      return
    }
    if (typeof window.MediaRecorder !== 'function') {
      setError(
        'This browser cannot record video in the page. Use the native “Record a video” button below.',
      )
      return
    }
    const mime = pickVideoMime()
    let recorder
    try {
      recorder = mime ? new window.MediaRecorder(stream, { mimeType: mime }) : new window.MediaRecorder(stream)
    } catch (err) {
      setError(`Video recording could not start: ${err?.message || 'unsupported browser'}.`)
      return
    }

    chunksRef.current = []
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data)
    }
    recorder.onerror = (event) => {
      if (!mountedRef.current) return
      setRecording(false)
      setError(`Recording failed: ${event?.error?.message || 'unknown error'}.`)
    }
    recorder.onstop = () => {
      if (!mountedRef.current) return
      const chunks = chunksRef.current
      chunksRef.current = []
      setRecording(false)
      setElapsed(0)
      const type = recorder.mimeType || mime || 'video/webm'
      const blob = new Blob(chunks, { type })
      if (!blob.size) {
        setError('The recording was empty. Try recording again.')
        return
      }
      emit(new File([blob], `camera-video-${stamp()}.${extensionFor(type)}`, { type }))
    }

    recorderRef.current = recorder
    recorder.start(1000)
    setRecording(true)
    setElapsed(0)
  }

  const stopRecording = () => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') return
    recorder.stop()
  }

  if (!support.supported) {
    return (
      <div className="rounded-xl border border-amber-300/40 bg-amber-500/10 p-4 text-left">
        <p className="text-sm font-semibold text-amber-100">Live camera unavailable in this browser context</p>
        <p className="mt-1 text-xs leading-relaxed text-amber-200/90">
          {support.reason === 'insecure'
            ? `Browsers only expose the live camera on HTTPS or localhost. This page is open on ${
                window.location.origin
              }${
                isLoopbackHost(window.location.hostname)
                  ? ''
                  : ' over plain HTTP, so the camera API is hidden'
              }. Use “Take a photo” or “Record a video” below — those open your phone's own camera app and still upload normally.`
            : 'This browser does not provide the in-page camera API. Use “Take a photo” or “Record a video” below; they open your phone’s camera app and upload normally.'}
        </p>
        <p className="mt-2 text-xs leading-relaxed text-amber-200/70">
          To enable the live scanner on a phone, serve the frontend over HTTPS (for example run Vite
          with <code className="mx-1">HTTPS=1</code>), then reload this page.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-white/20 bg-white/10 p-4 text-left">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-white">Live camera</p>
          <p className="text-xs text-pink-200">
            {active
              ? recording
                ? `Recording… ${elapsed}s`
                : 'Camera running — point it at the room.'
              : 'Rear camera, in this page.'}
          </p>
        </div>
        {!active ? (
          <button
            type="button"
            onClick={start}
            disabled={disabled || starting}
            className="rounded-lg bg-fuchsia-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-fuchsia-500 disabled:opacity-50"
          >
            {starting ? 'Opening camera…' : 'Open live camera'}
          </button>
        ) : (
          <button
            type="button"
            onClick={stop}
            className="rounded-lg bg-fuchsia-800 px-4 py-2 text-sm font-semibold text-white hover:bg-fuchsia-700"
          >
            Stop camera
          </button>
        )}
      </div>

      {active && (
        <div className="mt-3 space-y-3">
          <div className="overflow-hidden rounded-lg bg-black">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="mx-auto block max-h-72 w-full object-contain"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={takePhoto}
              disabled={disabled || recording}
              className="flex-1 rounded-lg bg-fuchsia-600 px-4 py-3 text-sm font-semibold text-white hover:bg-fuchsia-500 disabled:opacity-50"
            >
              Take photo
            </button>
            {recording ? (
              <button
                type="button"
                onClick={stopRecording}
                className="flex-1 rounded-lg bg-red-600 px-4 py-3 text-sm font-semibold text-white hover:bg-red-500"
              >
                Stop recording
              </button>
            ) : (
              <button
                type="button"
                onClick={startRecording}
                disabled={disabled}
                className="flex-1 rounded-lg bg-fuchsia-700 px-4 py-3 text-sm font-semibold text-white hover:bg-fuchsia-600 disabled:opacity-50"
              >
                Start recording
              </button>
            )}
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 rounded-lg border border-red-300/40 bg-red-500/20 p-3 text-xs text-red-100">
          {error}
        </p>
      )}
      {notice && !error && <p className="mt-3 text-xs text-pink-200">{notice}</p>}
    </div>
  )
}
