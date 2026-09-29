import { useCallback, useEffect, useRef, useState } from 'react'

function isFront(device) {
  return /front|user|face/i.test(device.label)
}

export function useCamera() {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [stream, setStream] = useState(null)
  const [cameras, setCameras] = useState([])
  const [facing, setFacing] = useState('environment')
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)

  const stopTracks = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setStream(null)
  }, [])

  const stop = useCallback(() => {
    stopTracks()
    setStatus('idle')
    setError(null)
  }, [stopTracks])

  const refreshCameras = useCallback(async () => {
    const devices = await navigator.mediaDevices.enumerateDevices()
    setCameras(devices.filter((device) => device.kind === 'videoinput'))
  }, [])

  const start = useCallback(
    async (preferred = facing) => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus('unsupported')
        setError('Camera capture is not supported in this browser.')
        return null
      }

      setStatus('starting')
      setError(null)
      stopTracks()

      try {
        const next = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: preferred } },
          audio: true,
        })
        streamRef.current = next
        setStream(next)
        setFacing(preferred)
        setStatus('live')
        if (videoRef.current) videoRef.current.srcObject = next
        await refreshCameras()
        return next
      } catch (err) {
        setStatus('error')
        setError(
          err.name === 'NotAllowedError'
            ? 'Camera permission denied.'
            : err.message,
        )
        return null
      }
    },
    [facing, refreshCameras, stopTracks],
  )

  const openDevice = useCallback(
    async (device) => {
      setStatus('starting')
      setError(null)
      stopTracks()
      try {
        const next = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: device.deviceId } },
          audio: true,
        })
        streamRef.current = next
        setStream(next)
        setFacing(isFront(device) ? 'user' : 'environment')
        setStatus('live')
        if (videoRef.current) videoRef.current.srcObject = next
      } catch (err) {
        setStatus('error')
        setError(err.message)
      }
    },
    [stopTracks],
  )

  const switchCamera = useCallback(async () => {
    if (cameras.length < 2) return
    const activeId = streamRef.current
      ?.getVideoTracks()
      .at(0)
      ?.getSettings().deviceId
    const currentIndex = cameras.findIndex(
      (device) => device.deviceId === activeId,
    )
    const nextDevice = cameras[(currentIndex + 1) % cameras.length]
    return openDevice(nextDevice)
  }, [cameras, openDevice])

  useEffect(() => () => stopTracks(), [stopTracks])

  return {
    videoRef,
    stream,
    cameras,
    canSwitch: cameras.length > 1,
    status,
    error,
    start,
    stop,
    switchCamera,
  }
}
