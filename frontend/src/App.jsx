import { useCallback, useEffect, useState } from 'react'
import { useCamera } from './hooks/useCamera'
import { useObjectUrl } from './hooks/useObjectUrl'
import { useRecorder } from './hooks/useRecorder'
import { uploadCapture } from './lib/api'

function formatElapsed(seconds) {
  const mins = String(Math.floor(seconds / 60)).padStart(2, '0')
  const secs = String(seconds % 60).padStart(2, '0')
  return `${mins}:${secs}`
}

function App() {
  const { videoRef, stream, canSwitch, status, error, start, stop, switchCamera } =
    useCamera()

  const [photo, setPhoto] = useState(null)
  const [clip, setClip] = useState(null)
  const [pending, setPending] = useState(null)
  const [uploads, setUploads] = useState([])
  const [uploadError, setUploadError] = useState(null)

  const onClipReady = useCallback((result) => {
    setClip(result)
    setPending({ blob: result, filename: 'clip.webm' })
  }, [])

  const {
    isRecording,
    elapsed,
    error: recordError,
    start: startRecording,
    stop: stopRecording,
  } = useRecorder(stream, onClipReady)

  const photoUrl = useObjectUrl(photo)
  const clipUrl = useObjectUrl(clip)

  const isLive = status === 'live'

  useEffect(() => {
    if (!pending) return
    let cancelled = false
    uploadCapture(pending.blob, pending.filename)
      .then((result) => {
        if (!cancelled) setUploads((current) => [...current, result])
      })
      .catch((err) => {
        if (!cancelled) setUploadError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [pending])

  const capturePhoto = useCallback(() => {
    const video = videoRef.current
    if (!video || !isLive || video.videoWidth === 0) return

    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    canvas.toBlob((result) => {
      if (!result) return
      setPhoto(result)
      setPending({ blob: result, filename: 'photo.jpg' })
    }, 'image/jpeg', 0.92)
  }, [isLive, videoRef])

  return (
    <main>
      <h1>Camera</h1>

      {status === 'unsupported' && <p>{error}</p>}
      {status === 'error' && <p>Error: {error}</p>}
      {recordError && <p>Recording error: {recordError}</p>}

      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        width="320"
        style={{ background: '#000' }}
      />

      <div>
        {!isLive ? (
          <button type="button" onClick={() => start()}>
            Start camera
          </button>
        ) : (
          <>
            <button type="button" onClick={capturePhoto}>
              Take photo
            </button>
            <button
              type="button"
              onClick={isRecording ? stopRecording : startRecording}
            >
              {isRecording ? 'Stop recording' : 'Record video'}
            </button>
            {canSwitch && (
              <button type="button" onClick={switchCamera}>
                Switch camera
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                stopRecording()
                stop()
              }}
            >
              Stop camera
            </button>
          </>
        )}
      </div>

      {isRecording && <p>Recording {formatElapsed(elapsed)}</p>}

      {photoUrl && <img src={photoUrl} alt="Last capture" width="240" />}

      {clipUrl && <video src={clipUrl} controls width="320" />}

      {uploadError && <p>Upload error: {uploadError}</p>}

      {uploads.length > 0 && (
        <ul>
          {uploads.map((item) => (
            <li key={item.name}>
              {item.name} ({item.size} bytes)
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}

export default App
