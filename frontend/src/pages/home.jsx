import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BrowserQRCodeReader } from '@zxing/browser'
import Badge from '../components/ui/Badge.jsx'
import Button from '../components/ui/Button.jsx'
import Card from '../components/ui/Card.jsx'
import ErrorBanner from '../components/ui/ErrorBanner.jsx'
import { shortId } from '../lib/format.js'
import { useSession } from '../session/SessionContext.js'

const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)

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

const WORKFLOW = [
  { title: 'Pair', copy: 'Create a session and scan the QR from a phone on the same network.' },
  { title: 'Capture', copy: 'Walk the room in slow, overlapping passes using the phone uploader.' },
  { title: 'Process', copy: 'Prepare the media and run the reconstruction stages on the backend.' },
  { title: 'Review', copy: 'Download the scene and collision GLB artifacts from the Model tab.' },
]

function Laptop() {
  const navigate = useNavigate()
  const { session, creating, createSession } = useSession()
  const [error, setError] = useState(null)

  const startNewScan = async () => {
    setError(null)
    try {
      const created = await createSession()
      navigate(`/session/${created.sessionId}/overview`)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col justify-center px-4 py-16 sm:px-6">
        <div className="grid items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
          <section>
            <Badge tone="accent">PC workspace · Room capture</Badge>
            <h1 className="mt-5 max-w-2xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Scan a room.
              <br />
              Build a digital twin.
            </h1>
            <p className="mt-5 max-w-xl text-base text-neutral-400">
              Namma Space pairs your phone with this desktop workspace for guided capture,
              live upload monitoring, processing, and model review.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" onClick={startNewScan} disabled={creating}>
                {creating ? 'Creating session…' : 'Start New Scan'}
              </Button>
              <Button size="lg" variant="secondary" to="/demo">
                Skip Scanning — Try Demo
              </Button>
            </div>

            {error && <ErrorBanner message={error} className="mt-5 max-w-xl" />}

            {session && (
              <div className="mt-6 flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm">
                <span className="text-neutral-400">Session in progress</span>
                <Link
                  to={`/session/${session.sessionId}/overview`}
                  className="font-mono text-fuchsia-300 hover:underline"
                >
                  {shortId(session.sessionId)}
                </Link>
                <Link
                  to={`/session/${session.sessionId}/overview`}
                  className="ml-auto text-sm font-medium text-neutral-200 hover:text-white"
                >
                  Return to workspace →
                </Link>
              </div>
            )}

            <p className="mt-6 text-xs text-neutral-500">
              Owner tokens stay in memory only. Refreshing this tab ends access and requires a
              new scan.
            </p>
          </section>

          <Card className="p-6">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-white">Capture workflow</h2>
              <Badge tone="neutral">4 stages</Badge>
            </div>
            <ol className="mt-5 space-y-3">
              {WORKFLOW.map((step, index) => (
                <li key={step.title} className="flex gap-3 rounded-lg border border-white/10 bg-white/[0.02] p-3">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-white/10 bg-white/5 text-xs font-semibold text-fuchsia-300">
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-neutral-200">{step.title}</p>
                    <p className="mt-0.5 text-xs leading-relaxed text-neutral-500">{step.copy}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default Home
