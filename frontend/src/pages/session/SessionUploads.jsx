import { useState } from 'react'
import AssetGallery from '../../components/session/AssetGallery.jsx'
import { FILTERS, KIND_LABELS } from '../../components/session/assetMeta.js'
import Badge from '../../components/ui/Badge.jsx'
import Button from '../../components/ui/Button.jsx'
import Card from '../../components/ui/Card.jsx'
import EmptyState from '../../components/ui/EmptyState.jsx'
import ErrorBanner from '../../components/ui/ErrorBanner.jsx'
import Loading from '../../components/ui/Loading.jsx'
import PageHeader from '../../components/ui/PageHeader.jsx'
import { useSession } from '../../session/SessionContext.js'

const CONNECTION_COPY = {
  live: { label: 'Live updates', tone: 'success' },
  connecting: { label: 'Connecting', tone: 'warning' },
  offline: { label: 'Polling fallback', tone: 'warning' },
  idle: { label: 'No session', tone: 'neutral' },
}

export default function SessionUploads() {
  const {
    session,
    assets,
    assetsLoading,
    assetsError,
    connection,
    refreshManifest,
  } = useSession()
  const [filter, setFilter] = useState('all')

  const counts = {
    all: assets.length,
    photo: assets.filter((asset) => asset.kind === 'photo').length,
    video: assets.filter((asset) => asset.kind === 'video').length,
    floorplan: assets.filter((asset) => asset.kind === 'floorplan').length,
    sensor: assets.filter((asset) => asset.kind === 'sensor').length,
  }
  const uploading = assets.filter((asset) => asset.status === 'uploading').length
  const ready = assets.filter((asset) => asset.status === 'ready').length
  const failed = assets.filter((asset) => asset.status === 'failed').length
  const filtered = filter === 'all' ? assets : assets.filter((asset) => asset.kind === filter)
  const connectionState = CONNECTION_COPY[connection] || CONNECTION_COPY.idle
  const isLoading = assetsLoading && assets.length === 0

  const handleRetry = async () => {
    try {
      await refreshManifest()
    } catch {
      // refreshManifest already publishes the error for the banner.
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Capture session"
        title="Uploads"
        description="Files arrive live from the phone. Thumbnails and videos are served from the capture API with the in-memory owner token."
        actions={
          <Button to={`/session/${session.sessionId}/overview`} variant="secondary">
            Pairing QR
          </Button>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Badge tone="neutral">{assets.length} total</Badge>
        {uploading > 0 && <Badge tone="warning">{uploading} uploading</Badge>}
        <Badge tone="success">{ready} ready</Badge>
        {failed > 0 && <Badge tone="danger">{failed} failed</Badge>}
        <Badge tone={connectionState.tone}>{connectionState.label}</Badge>
      </div>

      <ErrorBanner message={assetsError} onRetry={handleRetry} className="mb-6" />

      <div className="mb-4 flex flex-wrap gap-1" role="tablist" aria-label="Asset type filter">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={filter === item.key}
            onClick={() => setFilter(item.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === item.key
                ? 'bg-white/10 text-white'
                : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200'
            }`}
          >
            {item.label}
            <span className="ml-1.5 text-xs text-neutral-500">{counts[item.key]}</span>
          </button>
        ))}
      </div>

      <Card className="p-4 sm:p-6">
        {isLoading ? (
          <Loading label="Loading the session manifest…" className="py-10 justify-center" />
        ) : filtered.length === 0 ? (
          assets.length === 0 ? (
            <AssetGallery assets={[]} session={session} />
          ) : (
            <EmptyState
              title={`No ${KIND_LABELS[filter]?.toLowerCase() || 'matching'} uploads`}
              description="Choose another filter to see the rest of this capture session."
              action={
                <Button variant="secondary" size="sm" onClick={() => setFilter('all')}>
                  Show all uploads
                </Button>
              }
            />
          )
        ) : (
          <AssetGallery assets={filtered} session={session} />
        )}
      </Card>
    </>
  )
}
