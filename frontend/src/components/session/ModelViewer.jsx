import { useCallback, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import Button from '../ui/Button.jsx'
import Loading from '../ui/Loading.jsx'
import ProgressBar from '../ui/ProgressBar.jsx'
import { formatBytes } from '../../lib/format.js'

// The viewer only displays the GLB produced by the backend. It never builds or
// reconstructs geometry; it renders, orbits, and disposes the loaded scene.

class ModelLoadError extends Error {
  constructor(kind, message, { status = 0 } = {}) {
    super(message)
    this.name = 'ModelLoadError'
    this.kind = kind
    this.status = status
  }
}

const ERROR_TITLES = {
  unavailable: 'Model unavailable',
  not_ready: 'Model not ready',
  network: 'Connection error',
  invalid: 'Model loading failed',
  http: 'Model loading failed',
  webgl: '3D view unavailable',
}

const RETRYABLE = new Set(['not_ready', 'network', 'invalid', 'http'])

async function fetchModel(url, signal, onProgress) {
  let response
  try {
    response = await fetch(url, { signal, headers: { accept: 'model/gltf-binary' } })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ModelLoadError(
      'network',
      'Could not reach the backend to download the GLB. Check the connection and try again.',
    )
  }

  if (!response.ok) {
    if (response.status === 404) {
      throw new ModelLoadError(
        'not_ready',
        'The backend reports that this model is not ready yet. Run processing and wait for the job to produce a GLB.',
        { status: 404 },
      )
    }
    throw new ModelLoadError(
      'http',
      `The backend could not serve the model (HTTP ${response.status}).`,
      { status: response.status },
    )
  }

  const total = Number(response.headers.get('content-length')) || 0

  if (!response.body) {
    const buffer = await response.arrayBuffer()
    onProgress(buffer.byteLength, buffer.byteLength)
    return buffer
  }

  const reader = response.body.getReader()
  const chunks = []
  let loaded = 0

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    loaded += value.byteLength
    onProgress(loaded, total)
  }

  const merged = new Uint8Array(loaded)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.byteLength
  }
  return merged.buffer
}

function applyWireframe(root, enabled) {
  root.traverse((node) => {
    if (!node.isMesh || !node.material) return
    const materials = Array.isArray(node.material) ? node.material : [node.material]
    for (const material of materials) {
      if ('wireframe' in material) {
        material.wireframe = enabled
        material.needsUpdate = true
      }
    }
  })
}

function fitCamera(camera, controls, object) {
  object.updateWorldMatrix(true, true)
  const box = new THREE.Box3().setFromObject(object)
  if (box.isEmpty()) {
    throw new ModelLoadError('invalid', 'The GLB contains no visible geometry to display.')
  }

  const size = box.getSize(new THREE.Vector3())
  const center = box.getCenter(new THREE.Vector3())
  const maxDimension = Math.max(size.x, size.y, size.z)
  if (!Number.isFinite(maxDimension) || maxDimension <= 0) {
    throw new ModelLoadError('invalid', 'The GLB has an invalid bounding volume.')
  }

  const fov = (camera.fov * Math.PI) / 180
  const distance = (maxDimension / 2 / Math.tan(fov / 2)) * 1.6
  const position = center
    .clone()
    .add(new THREE.Vector3(distance * 0.8, distance * 0.55, distance * 0.8))

  camera.near = Math.max(distance / 1000, 0.001)
  camera.far = Math.max(distance * 100, 10)
  camera.position.copy(position)
  camera.updateProjectionMatrix()

  controls.target.copy(center)
  controls.minDistance = distance * 0.05
  controls.maxDistance = distance * 10
  controls.update()

  return {
    position,
    target: center.clone(),
    near: camera.near,
    far: camera.far,
    minDistance: controls.minDistance,
    maxDistance: controls.maxDistance,
  }
}

function disposeObject(root, geometries, materials, textures) {
  root.traverse((node) => {
    if (node.geometry && !geometries.has(node.geometry)) {
      geometries.add(node.geometry)
      node.geometry.dispose()
    }
    const nodeMaterials = node.material
      ? Array.isArray(node.material)
        ? node.material
        : [node.material]
      : []
    for (const material of nodeMaterials) {
      if (materials.has(material)) continue
      materials.add(material)
      for (const value of Object.values(material)) {
        if (value && value.isTexture && !textures.has(value)) {
          textures.add(value)
          value.dispose()
        }
      }
      material.dispose()
    }
  })
}

function ViewerMessage({ kind, message, onRetry, fullscreenError }) {
  return (
    <div className="absolute inset-0 z-20 grid place-items-center bg-neutral-950/80 p-6">
      <div className="w-full max-w-sm rounded-xl border border-white/10 bg-neutral-900/90 p-6 text-center">
        <h3 className="text-sm font-semibold text-white">{ERROR_TITLES[kind] || 'Model unavailable'}</h3>
        <p className="mt-2 text-sm text-neutral-400">{message}</p>
        {fullscreenError && <p className="mt-2 text-xs text-amber-300">{fullscreenError}</p>}
        {onRetry && (
          <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    </div>
  )
}

export default function ModelViewer({
  src,
  downloadHref,
  downloadFilename = 'scene.glb',
  className = '',
}) {
  const containerRef = useRef(null)
  const hostRef = useRef(null)
  const cameraRef = useRef(null)
  const controlsRef = useRef(null)
  const modelRef = useRef(null)
  const initialViewRef = useRef(null)

  const [attempt, setAttempt] = useState(0)
  const [phase, setPhase] = useState('loading')
  const [progress, setProgress] = useState({ loaded: 0, total: 0 })
  const [error, setError] = useState(null)
  const [wireframe, setWireframe] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [fullscreenError, setFullscreenError] = useState(null)

  const wireframeRef = useRef(wireframe)

  useEffect(() => {
    wireframeRef.current = wireframe
  }, [wireframe])

  useEffect(() => {
    if (!src) return undefined
    const container = hostRef.current
    if (!container) return undefined

    let cancelled = false
    const controller = new AbortController()
    let renderer = null
    let scene = null
    let camera = null
    let controls = null
    let model = null
    let observer = null

    const fail = (failure) => {
      if (cancelled) return
      setPhase('error')
      setError({
        kind: failure instanceof ModelLoadError ? failure.kind : 'invalid',
        message: failure?.message || 'The model could not be loaded.',
      })
    }

    try {
      renderer = new THREE.WebGLRenderer({ antialias: true })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
      renderer.outputColorSpace = THREE.SRGBColorSpace
      renderer.setClearColor(0x0b0b0c, 1)
      renderer.setSize(container.clientWidth || 640, container.clientHeight || 420, false)
      renderer.domElement.style.display = 'block'
      renderer.domElement.style.width = '100%'
      renderer.domElement.style.height = '100%'
      container.appendChild(renderer.domElement)
    } catch {
      queueMicrotask(() =>
        fail(
          new ModelLoadError(
            'webgl',
            'This browser could not create a WebGL context for the 3D viewer.',
          ),
        ),
      )
      return () => {
        cancelled = true
        controller.abort()
      }
    }

    scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0b0b0c)

    camera = new THREE.PerspectiveCamera(
      50,
      (container.clientWidth || 640) / (container.clientHeight || 420),
      0.01,
      1000,
    )
    cameraRef.current = camera

    scene.add(new THREE.HemisphereLight(0xffffff, 0x1f1f24, 1.5))
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.2)
    keyLight.position.set(4, 6, 3)
    scene.add(keyLight)
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.9)
    fillLight.position.set(-4, -2, -3)
    scene.add(fillLight)

    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.screenSpacePanning = true
    controlsRef.current = controls

    const resize = () => {
      if (cancelled || !renderer) return
      const width = container.clientWidth || 1
      const height = container.clientHeight || 1
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }

    observer = new ResizeObserver(resize)
    observer.observe(container)
    resize()

    renderer.setAnimationLoop(() => {
      controls.update()
      renderer.render(scene, camera)
    })

    const loader = new GLTFLoader()
    ;(async () => {
      try {
        const buffer = await fetchModel(src, controller.signal, (loaded, total) => {
          if (!cancelled) setProgress({ loaded, total })
        })
        if (cancelled) return

        let gltf
        try {
          gltf = await loader.parseAsync(buffer, '')
        } catch (parseError) {
          throw new ModelLoadError(
            'invalid',
            `The GLB could not be parsed: ${parseError?.message || 'invalid file'}.`,
          )
        }
        if (cancelled) return

        model = gltf.scene
        modelRef.current = model
        applyWireframe(model, wireframeRef.current)
        scene.add(model)
        initialViewRef.current = fitCamera(camera, controls, model)

        setProgress({ loaded: buffer.byteLength, total: buffer.byteLength })
        setPhase('ready')
      } catch (failure) {
        if (cancelled || failure?.name === 'AbortError') return
        fail(failure)
      }
    })()

    return () => {
      cancelled = true
      controller.abort()

      if (observer) observer.disconnect()
      if (renderer) {
        renderer.setAnimationLoop(null)
        renderer.dispose()
        renderer.forceContextLoss()
        if (renderer.domElement.parentNode === container) {
          container.removeChild(renderer.domElement)
        }
      }
      if (controls) controls.dispose()
      if (model) {
        scene.remove(model)
        disposeObject(model, new Set(), new Set(), new Set())
      }
      if (modelRef.current === model) modelRef.current = null
      if (cameraRef.current === camera) cameraRef.current = null
      if (controlsRef.current === controls) controlsRef.current = null
      initialViewRef.current = null
    }
  }, [src, attempt])

  useEffect(() => {
    if (modelRef.current) applyWireframe(modelRef.current, wireframe)
  }, [wireframe])

  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === containerRef.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  const retry = useCallback(() => {
    setError(null)
    setProgress({ loaded: 0, total: 0 })
    setPhase('loading')
    setAttempt((value) => value + 1)
  }, [])

  const resetCamera = useCallback(() => {
    const view = initialViewRef.current
    const camera = cameraRef.current
    const controls = controlsRef.current
    if (!view || !camera || !controls) return
    camera.position.copy(view.position)
    camera.near = view.near
    camera.far = view.far
    camera.updateProjectionMatrix()
    controls.target.copy(view.target)
    controls.minDistance = view.minDistance
    controls.maxDistance = view.maxDistance
    controls.update()
  }, [])

  const toggleFullscreen = useCallback(async () => {
    const node = containerRef.current
    if (!node) return
    setFullscreenError(null)
    try {
      if (document.fullscreenElement === node) await document.exitFullscreen()
      else await node.requestFullscreen()
    } catch {
      setFullscreenError('Fullscreen is not available in this browser.')
    }
  }, [])

  const percent =
    progress.total > 0 ? Math.round((progress.loaded / progress.total) * 100) : null
  const ready = Boolean(src) && phase === 'ready'
  const loading = Boolean(src) && phase === 'loading'
  const failed = Boolean(src) && phase === 'error'

  return (
    <div
      ref={containerRef}
      data-model-viewer=""
      className={`relative overflow-hidden rounded-xl border border-white/10 bg-neutral-950 ${
        isFullscreen ? 'h-screen w-screen rounded-none border-0' : 'h-[480px]'
      } ${className}`}
    >
      <div ref={hostRef} className="absolute inset-0" aria-hidden="true" />

      {ready && (
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-3 bg-gradient-to-b from-black/60 to-transparent p-3">
          <span className="rounded-full border border-white/15 bg-black/50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-neutral-300 backdrop-blur">
            Scene GLB
          </span>
        </div>
      )}

      <div className="absolute right-3 top-3 z-30 flex max-w-[calc(100%-1.5rem)] flex-wrap justify-end gap-2">
        {ready && (
          <Button variant="secondary" size="sm" onClick={resetCamera} className="backdrop-blur">
            Reset view
          </Button>
        )}
        {ready && (
          <Button
            variant={wireframe ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setWireframe((value) => !value)}
            aria-pressed={wireframe}
            className="backdrop-blur"
          >
            {wireframe ? 'Wireframe on' : 'Wireframe'}
          </Button>
        )}
        {ready && (
          <Button
            variant="secondary"
            size="sm"
            onClick={toggleFullscreen}
            className="backdrop-blur"
          >
            {isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          </Button>
        )}
        {src && downloadHref && (
          <Button
            href={downloadHref}
            download={downloadFilename}
            variant="secondary"
            size="sm"
            className="backdrop-blur"
          >
            Download GLB
          </Button>
        )}
      </div>

      {ready && (
        <p className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-black/50 px-2.5 py-1 text-[11px] text-neutral-400 backdrop-blur">
          Left-drag rotate · Scroll zoom · Right-drag pan
        </p>
      )}

      {!src && (
        <ViewerMessage
          kind="unavailable"
          message="Processing has not reported a model path for this session, so there is no GLB to display."
          fullscreenError={fullscreenError}
        />
      )}

      {loading && (
        <div className="absolute inset-0 z-20 grid place-items-center bg-neutral-950/70 p-6">
          <div className="w-full max-w-sm text-center">
            <p className="text-sm font-medium text-white">Loading model…</p>
            {percent === null ? (
              <Loading label="Downloading GLB from the backend" className="mt-4 justify-center" />
            ) : (
              <div className="mt-4">
                <ProgressBar
                  value={progress.loaded}
                  max={progress.total || 1}
                  label={`Downloading GLB · ${formatBytes(progress.loaded)} of ${formatBytes(progress.total)}`}
                />
                <p className="mt-2 text-xs text-neutral-500">{percent}% received</p>
              </div>
            )}
          </div>
        </div>
      )}

      {failed && (
        <ViewerMessage
          kind={error?.kind || 'invalid'}
          message={error?.message || 'The model could not be loaded.'}
          onRetry={RETRYABLE.has(error?.kind) ? retry : undefined}
          fullscreenError={fullscreenError}
        />
      )}
    </div>
  )
}
