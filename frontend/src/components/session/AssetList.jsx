import { fileUrl, thumbUrl } from '../../api.js'
import { formatBytes, formatDate } from '../../lib/format.js'
import Badge from '../ui/Badge.jsx'
import EmptyState from '../ui/EmptyState.jsx'
import { kindLabel, STATUS_TONE, statusLabel } from './assetMeta.js'

export default function AssetList({
  assets,
  session,
  limit,
  emptyTitle = 'No uploads yet',
  emptyDescription = 'Scan the QR code with your phone and send photos or videos.',
}) {
  if (assets.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />
  }

  const ordered = [...assets].reverse()
  const visible = limit ? ordered.slice(0, limit) : ordered

  return (
    <ul className="divide-y divide-white/5">
      {visible.map((asset) => {
        const hasFile = asset.status === 'stored' || asset.status === 'ready'
        return (
          <li key={asset.id} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
            {asset.kind === 'video' && hasFile ? (
              <video
                src={fileUrl(session.sessionId, asset.id, session.ownerToken)}
                poster={
                  asset.thumb_path
                    ? thumbUrl(session.sessionId, asset.id, session.ownerToken)
                    : undefined
                }
                controls
                playsInline
                preload="metadata"
                className="h-14 w-20 shrink-0 rounded-md bg-black object-cover"
              />
            ) : asset.thumb_path ? (
              <img
                src={thumbUrl(session.sessionId, asset.id, session.ownerToken)}
                alt=""
                className="h-14 w-14 shrink-0 rounded-md object-cover"
              />
            ) : (
              <div className="grid h-14 w-14 shrink-0 place-items-center rounded-md border border-white/10 bg-white/5 text-[10px] uppercase text-neutral-400">
                {kindLabel(asset.kind).slice(0, 4)}
              </div>
            )}

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-neutral-200">{asset.original_filename}</p>
              <p className="text-xs text-neutral-500">
                {kindLabel(asset.kind)} · {formatBytes(asset.size_bytes)} ·{' '}
                {formatDate(asset.created_at)}
              </p>
              {asset.status === 'uploading' && (
                <p className="text-xs text-amber-300">Upload in progress…</p>
              )}
              {asset.error_reason && <p className="text-xs text-red-300">{asset.error_reason}</p>}
            </div>

            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge tone={STATUS_TONE[asset.status] || 'neutral'}>
                {statusLabel(asset.status)}
              </Badge>
              {hasFile && (
                <a
                  href={fileUrl(session.sessionId, asset.id, session.ownerToken)}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-fuchsia-300 hover:underline"
                >
                  Open
                </a>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
