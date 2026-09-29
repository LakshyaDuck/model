import { useCallback, useEffect, useRef, useState } from 'react'

const VIDEO_TYPES = [
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=vp8,opus',
  'video/webm;codecs=h264,opus',
  'video/webm',
  'video/mp4',
]

function buildRecorder(stream) {
  for (const options of VIDEO_TYPES.map((mimeType) => ({ mimeType }))) {
    try {
      return new MediaRecorder(stream, options)
    } catch {
      continue
    }
  }

  try {
    return new MediaRecorder(stream)
  } catch {
    return null
  }
}

export function useRecorder(stream, onFinished) {
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const onFinishedRef = useRef(onFinished)
  const [isRecording, setIsRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState(null)

  useEffect(() => {
    onFinishedRef.current = onFinished
  }, [onFinished])

  useEffect(() => {
    if (!isRecording) return
    const id = setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => clearInterval(id)
  }, [isRecording])

  const reset = useCallback(() => {
    recorderRef.current = null
    setIsRecording(false)
    setElapsed(0)
  }, [])

  const stop = useCallback(() => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') return

    try {
      recorder.stop()
    } catch {
      chunksRef.current = []
      reset()
    }
  }, [reset])

  const start = useCallback(() => {
    setError(null)

    if (!stream) {
      setError('Camera is not running.')
      return
    }
    if (typeof MediaRecorder === 'undefined') {
      setError('Video recording is not supported in this browser.')
      return
    }
    if (recorderRef.current?.state === 'recording') return

    const recorder = buildRecorder(stream)
    if (!recorder) {
      setError('Could not start a recorder for this camera.')
      return
    }

    const type = recorder.mimeType || 'video/webm'
    chunksRef.current = []

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data)
    }
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type })
      chunksRef.current = []
      reset()
      if (blob.size > 0) {
        onFinishedRef.current?.(blob)
      } else {
        setError('Recording produced no data.')
      }
    }
    recorder.onerror = (event) => {
      chunksRef.current = []
      reset()
      setError(event.error?.message ?? 'Recording failed.')
    }

    try {
      recorder.start(1000)
    } catch (err) {
      chunksRef.current = []
      setError(err.message)
      return
    }

    recorderRef.current = recorder
    setIsRecording(true)
    setElapsed(0)
  }, [reset, stream])

  return { isRecording, elapsed, error, start, stop }
}
