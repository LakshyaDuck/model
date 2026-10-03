import { useEffect, useRef, useState } from 'react'

function CameraPic() {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const [photo, setPhoto] = useState(null)
  const [error, setError] = useState(null)

  const isSecure = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)

  useEffect(() => {
    let stream
    if (!isSecure) return
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment' } })
      .then((s) => {
        stream = s
        videoRef.current.srcObject = s
      })
      .catch((err) => setError('Camera error: ' + err.message))

    return () => {
      if (stream) stream.getTracks().forEach((t) => t.stop())
    }
  }, [isSecure])

  const takePhoto = () => {
    const video = videoRef.current
    const canvas = canvasRef.current
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    setPhoto(canvas.toDataURL('image/png'))
  }

  return (
    <div className="min-h-screen bg-fuchsia-950 text-white flex flex-col items-center p-6">
      <h1 className="text-2xl font-bold mb-4">Capture Photo</h1>
      {!isSecure && (
        <div className="bg-red-500/20 border border-red-400 text-red-200 rounded-xl p-4 text-center max-w-md mb-4">
          Camera permission is not allowed. Please allow camera access in your browser settings and try again.
        </div>
      )}
      {error && (
        <div className="bg-red-500/20 border border-red-400 text-red-200 rounded-xl p-4 text-center max-w-md mb-4">
          {error}
        </div>
      )}
      <video ref={videoRef} autoPlay playsInline className="w-full max-w-md rounded-xl border-2 border-pink-400" />
      <button
        onClick={takePhoto}
        className="mt-4 px-6 py-3 bg-fuchsia-600 hover:bg-fuchsia-500 rounded-xl font-semibold shadow-lg"
      >
        Capture
      </button>
      <p className="text-gray-400 mt-4 text-sm text-center">
        Follow the instructions given — then check your laptop for the 3D rendered image.
      </p>
      <canvas ref={canvasRef} style={{ display: 'none' }} />
      {photo && (
        <div className="mt-6 w-full max-w-md">
          <h2 className="text-lg font-semibold mb-2">Captured Photo</h2>
          <img src={photo} alt="captured" className="w-full rounded-xl border-2 border-pink-400" />
        </div>
      )}
    </div>
  )
}

export default CameraPic
