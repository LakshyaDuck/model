import { Link } from 'react-router-dom'
import hero from '../assets/hero.png'

// The demo intentionally lives entirely in the browser. It never creates a session,
// stores an owner token, or calls the API, so it cannot be mistaken for a real
// authenticated capture.
const DEMO_SESSION = {
  id: 'demo-session-01',
  source: 'Bundled sample',
  mode: 'Read-only demo',
}

const DEMO_ASSETS = [
  {
    id: 'demo-preview',
    filename: 'sample-room.png',
    kind: 'photo',
    status: 'sample',
    src: hero,
  },
]

function Demo() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-fuchsia-600 to-pink-500 flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl shadow-2xl p-10 flex flex-col max-w-2xl w-full">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
          <div>
            <h1 className="text-3xl font-extrabold text-gray-800 mb-2">Demo workspace</h1>
            <p className="text-gray-500">Explore the PC interface without a phone.</p>
          </div>
          <Link
            to="/"
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded-xl text-sm font-semibold text-gray-700"
          >
            ← Back to scanning
          </Link>
        </div>

        <div
          role="status"
          className="bg-amber-50 border border-amber-300 text-amber-900 rounded-xl p-4 text-sm mb-6"
        >
          <p className="font-bold uppercase tracking-wide mb-1">Demo mode — sample data</p>
          <p>
            This workspace uses bundled sample content. It is not a real capture and
            nothing here is uploaded, processed, or saved to a session.
          </p>
        </div>

        <section className="grid gap-3 sm:grid-cols-3">
          <div className="bg-pink-50 rounded-xl p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-fuchsia-700">Session</p>
            <p className="text-sm text-gray-700 break-all">{DEMO_SESSION.id}</p>
          </div>
          <div className="bg-pink-50 rounded-xl p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-fuchsia-700">Source</p>
            <p className="text-sm text-gray-700">{DEMO_SESSION.source}</p>
          </div>
          <div className="bg-pink-50 rounded-xl p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-fuchsia-700">Mode</p>
            <p className="text-sm text-gray-700">{DEMO_SESSION.mode}</p>
          </div>
        </section>

        <section className="mt-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">
            Sample images ({DEMO_ASSETS.length})
          </h2>
          <ul className="space-y-2">
            {DEMO_ASSETS.map((asset) => (
              <li key={asset.id} className="flex items-center gap-3 bg-gray-50 rounded-lg p-3">
                <img
                  src={asset.src}
                  alt="Bundled sample preview"
                  className="w-16 h-16 object-contain rounded bg-white border border-gray-200 p-1"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm truncate text-gray-700">{asset.filename}</p>
                  <p className="text-[11px] text-gray-400">
                    {asset.kind} · {asset.status}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">3D model</h2>
          <div className="border-2 border-dashed border-gray-200 bg-gray-50 rounded-xl p-6 text-center">
            <img
              src={hero}
              alt=""
              className="w-20 h-20 object-contain mx-auto mb-2 opacity-70"
            />
            <p className="text-sm text-gray-600">
              No reconstructed GLB is bundled with this demo.
            </p>
            <p className="text-xs text-gray-400 mt-1">
              A real session shows its <code>scene.glb</code> here after processing.
            </p>
          </div>
        </section>

        <div className="mt-6 rounded-xl bg-pink-50 p-4 text-sm text-gray-600">
          Want to test a real capture?{' '}
          <Link to="/" className="font-semibold text-fuchsia-700 hover:underline">
            Start a new scan
          </Link>{' '}
          and pair your phone.
        </div>
      </div>
    </div>
  )
}

export default Demo
