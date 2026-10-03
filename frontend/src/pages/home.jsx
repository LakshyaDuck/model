import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BrowserQRCodeReader } from '@zxing/browser'
import { QRCodeCanvas } from 'qrcode.react'

const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)

function Home() {
  const videoRef = useRef(null)
  const navigate = useNavigate()
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
          console.log('Scanned:', result.getText())
          navigate(isMobile ? '/camerapic' : '/_3Drendering')
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-fuchsia-600 to-pink-500 flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl shadow-2xl p-10 flex flex-col items-center max-w-md w-full">
        <h1 className="text-3xl font-extrabold text-gray-800 mb-2">3D Scanner</h1>
        <p className="text-gray-500 text-center mb-6">Scan this QR code with your phone to start scanning</p>

        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-inner">
          <QRCodeCanvas value="have to add session id send by backend" size={220} />
        </div>

        <div className="mt-6 text-sm text-gray-600 space-y-2 text-left w-full bg-pink-50 rounded-xl p-4">
          <p className="font-semibold text-fuchsia-700">Instructions:</p>
          <p>1. Scan the QR code using your phone.</p>
          <p>2. Capture the photo using your phone.</p>
          <p>3. Follow the instructions given on your phone.</p>
          <p>4. Here you will see the 3D rendered image of the photo.</p>
        </div>
      </div>
    </div>
  )
}

export default Home
