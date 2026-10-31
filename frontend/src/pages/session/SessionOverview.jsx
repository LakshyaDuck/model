import { useEffect, useState } from 'react'
import { QRCodeCanvas } from 'qrcode.react'
import AssetList from '../../components/session/AssetList.jsx'
import Badge from '../../components/ui/Badge.jsx'
import Button from '../../components/ui/Button.jsx'
import Card from '../../components/ui/Card.jsx'
import CopyButton from '../../components/ui/CopyButton.jsx'
import ErrorBanner from '../../components/ui/ErrorBanner.jsx'
import PageHeader from '../../components/ui/PageHeader.jsx'
import { formatDate, formatExpiry, shortId } from '../../lib/format.js'
import { useSession } from '../../session/SessionContext.js'

const PAGE_LOADED_AT = Date.now()

function isLoopbackHost(hostname) {
  const host = (hostname || '').toLowerCase().replace(/^\[|\]$/g, '')
  return (
    host === '' ||
    host === 'localhost' ||
    host === '127.0.0.1' ||
    host === '::1' ||
    host === '0.0.0.0'
  )
}

// Resolve the pairing target without trusting a single stored URL:
// - keep the backend's path (/m/<token>) so /m and /phone stay consistent
// - correct a loopback-only stored origin to this page's origin
// - surface any other origin mismatch instead of silently overriding it
function phoneTarget(rawUrl, pairToken) {
  const pageOrigin = window.location.origin
  const pageLoopback = isLoopbackHost(window.location.hostname)
  const fallbackPath = `/m/${encodeURIComponent(pairToken || '')}`

  let parsed = null
  if (rawUrl) {
    try {
      parsed = new URL(rawUrl, pageOrigin)
    } catch {
      parsed = null
    }
  }

  return {
    path: parsed ? `${parsed.pathname}${parsed.search}` : fallbackPath,
    pageOrigin,
    pageLoopback,
    backendOrigin: parsed ? parsed.origin : pageOrigin,
    backendLoopback: parsed ? isLoopbackHost(parsed.hostname) : pageLoopback,
    hasBackendUrl: Boolean(parsed),
  }
}

function Stat({ label, value, hint }) {
  return (
    <Card className="p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
      {hint && <p className="mt-1 text-xs text-neutral-500">{hint}</p>}
    </Card>
  )
}

export default function SessionOverview() {
  const { session, assets, job, rotatePairing } = useSession()
  const [now, setNow] = useState(PAGE_LOADED_AT)
  const [rotating, setRotating] = useState(false)
  const [pairError, setPairError] = useState(null)

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const target = phoneTarget(session.phoneUrl, session.pairToken)
  const correctedLoopback = target.backendLoopback && !target.pageLoopback
  // The QR must always point at the origin the phone is actually going to open,
  // which is this page's origin. Relying on the backend's configured origin is
  // what made the phone load the old backend dev page / a stale address.
  const usePageOrigin = true
  const phoneOrigin = usePageOrigin ? target.pageOrigin : target.backendOrigin
  const phoneUrl = `${phoneOrigin}${target.path}`
  const phoneLoopback = (() => {
    try {
      return isLoopbackHost(new URL(phoneUrl).hostname)
    } catch {
      return false
    }
  })()
  const originMismatch =
    !usePageOrigin &&
    target.hasBackendUrl &&
    !target.backendLoopback &&
    target.backendOrigin !== target.pageOrigin &&
    !target.pageLoopback
  const pairActive = new Date(session.pairExpiresAt).getTime() > now
  const photos = assets.filter((asset) => asset.kind === 'photo').length
  const videos = assets.filter((asset) => asset.kind === 'video').length
  const jobLabel = job?.status && job.status !== 'idle' ? job.status : 'idle'

  const handleRotate = async () => {
    setPairError(null)
    setRotating(true)
    try {
      await rotatePairing()
    } catch (err) {
      setPairError(err.message)
    } finally {
      setRotating(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Capture session"
        title="Overview"
        description="Pair a phone, review incoming media, and hand the session to processing when the capture is complete."
        actions={
          <>
            <Button to={`/session/${session.sessionId}/uploads`} variant="secondary">
              View uploads
            </Button>
            <Button to={`/session/${session.sessionId}/process`}>Open processing</Button>
          </>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Uploads" value={assets.length} hint={`Session ${shortId(session.sessionId)}`} />
            <Stat label="Photos" value={photos} hint="Still-image capture" />
            <Stat label="Videos" value={videos} hint="Frame extraction source" />
            <Stat label="Processing" value={jobLabel} hint={job?.phase || 'No job started'} />
          </div>

          <Card className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-white">Session details</h2>
                <p className="mt-1 text-sm text-neutral-400">
                  This ID identifies the session to the backend. The owner token that unlocks it
                  stays in memory only.
                </p>
              </div>
              <Badge tone="neutral">Capture</Badge>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-black/20 p-3">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-neutral-500">
                Session ID
              </span>
              <code className="min-w-0 flex-1 break-all font-mono text-sm text-neutral-200">
                {session.sessionId}
              </code>
              <CopyButton value={session.sessionId} label="Copy ID" copiedLabel="ID copied" />
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-white">Capture checklist</h2>
                <p className="mt-1 text-sm text-neutral-400">
                  Follow one perimeter loop with 70–80% overlap, then add a second pass from a
                  different height.
                </p>
              </div>
              <Badge tone={assets.length > 0 ? 'success' : 'neutral'}>
                {assets.length > 0 ? 'Media received' : 'Waiting for phone'}
              </Badge>
            </div>
            <ol className="mt-5 grid gap-3 text-sm text-neutral-400 sm:grid-cols-2">
              <li className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                1. Scan the pairing QR with your phone.
              </li>
              <li className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                2. Capture photos or videos from the phone page.
              </li>
              <li className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                3. Confirm every upload in the Uploads tab.
              </li>
              <li className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                4. Run processing and review the model artifact.
              </li>
            </ol>
          </Card>

          <Card className="p-6">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-white">Recent uploads</h2>
              <Button to={`/session/${session.sessionId}/uploads`} variant="ghost" size="sm">
                View all
              </Button>
            </div>
            <AssetList
              assets={assets}
              session={session}
              limit={3}
              emptyTitle="Nothing received yet"
              emptyDescription="Keep this page open; uploads appear here automatically as the phone sends them."
            />
          </Card>
        </div>

        <Card className="h-fit p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-white">Phone pairing</h2>
              <p className="mt-1 text-sm text-neutral-400">Scan to open the upload page.</p>
            </div>
            <Badge tone={pairActive ? 'success' : 'warning'}>
              {pairActive ? 'Active' : 'Expired'}
            </Badge>
          </div>

          <div className="mt-5 flex justify-center rounded-xl bg-white p-4">
            <QRCodeCanvas value={phoneUrl} size={208} bgColor="#ffffff" fgColor="#171717" />
          </div>

          <div className="mt-4 rounded-lg border border-white/10 bg-black/20 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-500">
              Pairing link
            </p>
            <p className="mt-1 break-all font-mono text-[11px] leading-relaxed text-neutral-300">
              {phoneUrl}
            </p>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <CopyButton
              value={phoneUrl}
              label="Copy pairing link"
              copiedLabel="Link copied"
              variant="secondary"
              className="flex-1"
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRotate}
              disabled={rotating}
              className="flex-1"
            >
              {rotating ? 'Rotating…' : 'Rotate link'}
            </Button>
          </div>

          <p className="mt-3 text-xs text-neutral-500">
            Rotating immediately invalidates the previous link. Share the new QR or link with the
            phone.
          </p>

          <div className="mt-4 space-y-1 border-t border-white/10 pt-4 text-center text-xs">
            <p className="text-neutral-400">
              Expires {formatDate(session.pairExpiresAt)}{' '}
              <span className={pairActive ? 'text-neutral-500' : 'text-amber-300'}>
                ({formatExpiry(session.pairExpiresAt, now)})
              </span>
            </p>
          </div>

          {pairError && <ErrorBanner message={pairError} className="mt-4" />}

          {correctedLoopback && (
            <div className="mt-4 rounded-lg border border-sky-400/30 bg-sky-500/10 p-3 text-xs text-sky-200">
              The saved pairing link pointed at <code>localhost</code>, which a phone cannot open.
              The QR and link above use this page&apos;s address (<code>{target.pageOrigin}</code>).
              Set <code>PUBLIC_BASE_URL</code> to that origin so the saved link is correct too.
            </div>
          )}

          {originMismatch && (
            <div className="mt-4 rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-200">
              <p>
                The saved pairing link pointed at <code>{target.backendOrigin}</code>, but this
                page is open from <code>{target.pageOrigin}</code>. The QR above uses this
                page&apos;s address; update <code>PUBLIC_BASE_URL</code> to match for a correct
                saved link.
              </p>
            </div>
          )}

          {phoneLoopback && (
            <div className="mt-4 rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-200">
              This pairing link resolves to <code>localhost</code>, so a phone cannot reach it.
              Open the workspace using the laptop&apos;s LAN address (or set{' '}
              <code>PUBLIC_BASE_URL</code> to it) and scan again.
            </div>
          )}

          {!pairActive && (
            <div className="mt-4 rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-200">
              This pairing token has expired. Rotate the link to issue a fresh one, or start a New
              Scan for a new session.
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
