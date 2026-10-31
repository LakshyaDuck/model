import { fileUrl, thumbUrl } from '../../api.js'
import { formatBytes, formatDate } from '../../lib/format.js'
import Badge from '../ui/Badge.jsx'
import EmptyState from '../ui/EmptyState.jsx'
import { kindLabel, STATUS_TONE, statusLabel } from './assetMeta.js'

function AssetPreview({ asset, session }) {
  const thumb = asset.thumb_path ? thumbUrl(session.sessionId, asset.id, session.ownerToken) : null

  if (asset.kind === 'video' && (asset.status === 'stored' || asset.status === 'ready')) {
    return (
      <video
        src={fileUrl(session.sessionId, asset.id, session.ownerToken)}
        poster={thumb || undefined}
        controls
        playsInline
        preload="metadata"
        className="h-full w-full bg-black object-contain"
      />
    )
  }

  if (thumb) {
    return <img src={thumb} alt="" className="h-full w-full object-cover" loading="lazy" />
  }

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-neutral-500">
      <div className="grid h-12 w-12 place-items-center rounded-lg border border-white/10 bg-white/5 text-[10px] font-semibold uppercase tracking-wide">
        {kindLabel(asset.kind).slice(0, 4)}
      </div>
      <span className="text-xs">{kindLabel(asset.kind)}</span>
    </div>
  )
}

export default function AssetGallery({
  assets,
  session,
  emptyTitle = 'No uploads yet',
  emptyDescription = 'Scan the pairing QR with your phone and send photos or videos.',
}) {
  if (assets.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />
  }

  return (
    <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {assets.map((asset) => (
        <li
          key={asset.id}
          className="overflow-hidden rounded-xl border border-white/10 bg-neutral-900/60"
        >
          <div className="relative aspect-[4/3] bg-black/50">
            <AssetPreview asset={asset} session={session} />
            <div className="absolute left-2 top-2 flex flex-wrap gap-1">
              <Badge tone="neutral">{kindLabel(asset.kind)}</Badge>
              <Badge tone={STATUS_TONE[asset.status] || 'neutral'}>
                {statusLabel(asset.status)}
              </Badge>
            </div>
          </div>

          <div className="space-y-1 p-3">
            <p className="truncate text-sm font-medium text-neutral-200" title={asset.original_filename}>
              {asset.original_filename || 'Untitled upload'}
            </p>
            <p className="text-xs text-neutral-500">
              {formatBytes(asset.size_bytes)} · {formatDate(asset.created_at)}
            </p>

            {asset.status === 'uploading' && (
              <p className="text-xs text-amber-300">Upload in progress…</p>
            )}

            {asset.status === 'failed' && (
              <p className="rounded-md border border-red-400/30 bg-red-500/10 p-2 text-xs text-red-200">
                {asset.error_reason || 'The backend rejected this upload.'}
              </p>
            )}

            {(asset.status === 'stored' || asset.status === 'ready') && (
              <a
                href={fileUrl(session.sessionId, asset.id, session.ownerToken)}
                target="_blank"
                rel="noreferrer"
                className="inline-block pt-1 text-xs font-medium text-fuchsia-300 hover:underline"
              >
                Open original
              </a>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
