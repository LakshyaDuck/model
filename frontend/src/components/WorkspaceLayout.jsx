import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'
import Badge from './ui/Badge.jsx'
import Button from './ui/Button.jsx'
import Card from './ui/Card.jsx'
import ConnectionBanner from './ui/ConnectionBanner.jsx'
import ErrorBanner from './ui/ErrorBanner.jsx'
import { useSession } from '../session/SessionContext.js'

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'uploads', label: 'Uploads' },
  { key: 'process', label: 'Processing' },
  { key: 'model', label: 'Model' },
]

const STATUS_COPY = {
  live: { label: 'Live', tone: 'success', dot: 'bg-emerald-400' },
  connecting: { label: 'Connecting', tone: 'warning', dot: 'bg-amber-400' },
  offline: { label: 'Reconnecting', tone: 'danger', dot: 'bg-red-400' },
  online: { label: 'Backend online', tone: 'success', dot: 'bg-emerald-400' },
  checking: { label: 'Checking backend', tone: 'warning', dot: 'bg-amber-400' },
  idle: { label: 'No session', tone: 'neutral', dot: 'bg-neutral-500' },
}

function SessionUnavailable({ sessionId, onNewScan, creating }) {
  return (
    <div className="mx-auto max-w-xl py-10">
      <Card className="p-8 text-center">
        <Badge tone="warning">Session not in memory</Badge>
        <h1 className="mt-4 text-xl font-semibold text-white">This session is not available in this tab</h1>
        <p className="mt-3 text-sm text-neutral-400">
          Owner tokens are kept in memory only and are never written to browser storage or
          the URL. Refreshing, opening a new tab, or sharing this link removes access to the
          session for security.
        </p>
        <p className="mt-3 break-all text-xs text-neutral-500">Session {sessionId}</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Button onClick={onNewScan} disabled={creating}>
            {creating ? 'Creating session…' : 'Start New Scan'}
          </Button>
          <Button to="/" variant="secondary">
            Back to home
          </Button>
        </div>
      </Card>
    </div>
  )
}

export default function WorkspaceLayout() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const { session, connection, backendStatus, creating, sessionError, createSession } =
    useSession()
  const [error, setError] = useState(null)

  const activeSession = session && session.sessionId === sessionId ? session : null
  const statusKey = activeSession
    ? connection === 'idle'
      ? 'connecting'
      : connection
    : backendStatus
  const status = STATUS_COPY[statusKey] || STATUS_COPY.checking

  const handleNewScan = async () => {
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
      <header className="sticky top-0 z-20 border-b border-white/10 bg-neutral-950/95 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="flex h-16 items-center justify-between gap-4">
            <Link to="/" className="flex items-center gap-3">
              <span className="grid h-8 w-8 place-items-center rounded-md border border-fuchsia-400/30 bg-fuchsia-500/10 text-xs font-bold text-fuchsia-300">
                NS
              </span>
              <span className="text-sm font-semibold tracking-wide text-white">Namma Space</span>
            </Link>

            <div className="hidden min-w-0 items-center gap-2 text-xs text-neutral-500 md:flex">
              <span className="uppercase tracking-wide">Session</span>
              <span className="truncate font-mono text-neutral-300">
                {activeSession ? activeSession.sessionId : sessionId}
              </span>
            </div>

            <div className="flex items-center gap-3">
              <Badge tone={status.tone}>
                <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
                {status.label}
              </Badge>
              <Button size="sm" onClick={handleNewScan} disabled={creating}>
                {creating ? 'Creating…' : 'New Scan'}
              </Button>
            </div>
          </div>

          <nav className="flex gap-1 overflow-x-auto pb-2" aria-label="Session workspace">
            {TABS.map((tab) => (
              <NavLink
                key={tab.key}
                to={`/session/${sessionId}/${tab.key}`}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-white/10 text-white'
                      : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {error && <ErrorBanner message={error} className="mb-6" />}
        {activeSession && sessionError && (
          <ErrorBanner
            message={sessionError}
            onRetry={handleNewScan}
            retryLabel="Start New Scan"
            className="mb-6"
          />
        )}
        {activeSession && connection !== 'live' && <ConnectionBanner status={connection} />}
        {activeSession ? (
          <Outlet />
        ) : (
          <SessionUnavailable sessionId={sessionId} onNewScan={handleNewScan} creating={creating} />
        )}
      </main>
    </div>
  )
}
