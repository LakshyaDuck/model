import { useState } from 'react'
import Badge from '../../components/ui/Badge.jsx'
import Button from '../../components/ui/Button.jsx'
import Card from '../../components/ui/Card.jsx'
import EmptyState from '../../components/ui/EmptyState.jsx'
import ErrorBanner from '../../components/ui/ErrorBanner.jsx'
import Loading from '../../components/ui/Loading.jsx'
import PageHeader from '../../components/ui/PageHeader.jsx'
import ProgressBar from '../../components/ui/ProgressBar.jsx'
import { formatDate } from '../../lib/format.js'
import { useSession } from '../../session/SessionContext.js'

const STATUS_TONE = {
  idle: 'neutral',
  queued: 'warning',
  running: 'accent',
  done: 'success',
  failed: 'danger',
}

function countByStatus(assets, status) {
  return assets.filter((asset) => asset.status === status).length
}

function Detail({ label, value }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="mt-1 break-words text-sm text-neutral-200">{value}</dd>
    </div>
  )
}

function StartBlockers({ blockers }) {
  if (blockers.length === 0) return null
  return (
    <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
        Before processing
      </p>
      <ul className="mt-2 space-y-1 text-sm text-neutral-400">
        {blockers.map((item) => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  )
}

export default function SessionProcess() {
  const { session, assets, job, startProcessing } = useSession()
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)

  const media = assets.filter((asset) => asset.kind === 'photo' || asset.kind === 'video')
  const photos = assets.filter((asset) => asset.kind === 'photo').length
  const videos = assets.filter((asset) => asset.kind === 'video').length
  const readyMedia = media.filter((asset) => asset.status === 'ready').length
  const uploading = countByStatus(assets, 'uploading')
  const failed = countByStatus(assets, 'failed')
  const ready = countByStatus(assets, 'ready')

  const processing = job?.status === 'queued' || job?.status === 'running'
  const status = job?.status || 'idle'
  const hasModel = Boolean(job?.model_path || job?.collision_model_path)
  const preparing = processing && job?.phase !== 'pipeline'

  const blockers = []
  if (readyMedia === 0) blockers.push('No ready photo or video assets yet.')
  if (uploading > 0) blockers.push('Uploads are still in progress.')
  if (processing) blockers.push('A processing job is already active.')
  const canStart = blockers.length === 0 && !starting && job !== null

  const handleStart = async () => {
    setError(null)
    setStarting(true)
    try {
      await startProcessing()
    } catch (err) {
      setError(err.message)
    } finally {
      setStarting(false)
    }
  }

  const outcome = (() => {
    if (job === null) return 'loading'
    if (status === 'queued' || status === 'running') return 'running'
    if (status === 'failed') return 'failed'
    if (status === 'done' && hasModel) return 'done_with_model'
    if (status === 'done') return 'done_without_model'
    return 'idle'
  })()

  return (
    <>
      <PageHeader
        eyebrow="Capture session"
        title="Processing"
        description="Prepare the captured media and run the backend reconstruction stages that are available today."
        actions={
          <Button onClick={handleStart} disabled={!canStart}>
            {starting ? 'Starting…' : processing ? 'Processing…' : 'Start processing'}
          </Button>
        }
      />

      <ErrorBanner message={error} className="mb-6" />

      {failed > 0 && (
        <div className="mb-6 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {failed} upload{failed === 1 ? '' : 's'} failed and will not be processed. Review the
          Uploads tab for the backend error on each file.
        </div>
      )}

      {videos === 0 && photos > 0 && (
        <div className="mb-6 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <strong className="font-semibold">Photo-only session.</strong> The current backend
          prepares still photos into <code>processed/images</code>, but only video-derived frames
          are passed to the reconstruction pipeline. A GLB is not guaranteed from photos alone.
          Add a video capture to run reconstruction.
        </div>
      )}

      {videos > 0 && (
        <div className="mb-6 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-neutral-400">
          Videos are the reconstruction input for the current backend pipeline. Photos are
          normalised for later use but do not currently reach COLMAP.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-white">Latest job</h2>
            <Badge tone={STATUS_TONE[status] || 'neutral'}>{status}</Badge>
          </div>

          {outcome === 'loading' && (
            <div className="mt-5 py-8">
              <Loading label="Reading the processing status…" className="justify-center" />
            </div>
          )}

          {outcome === 'idle' && (
            <div className="mt-5">
              <EmptyState
                title={assets.length === 0 ? 'No media to process' : 'Ready to process'}
                description={
                  assets.length === 0
                    ? 'Upload photos or videos from the phone before starting the processing job.'
                    : `${readyMedia} ready photo/video asset${readyMedia === 1 ? '' : 's'} available. Start processing when the capture is complete.`
                }
                action={
                  assets.length > 0 ? (
                    <Button onClick={handleStart} disabled={!canStart}>
                      Start processing
                    </Button>
                  ) : (
                    <Button to={`/session/${session.sessionId}/uploads`} variant="secondary">
                      Go to uploads
                    </Button>
                  )
                }
              />
              <StartBlockers blockers={blockers} />
            </div>
          )}

          {outcome !== 'loading' && outcome !== 'idle' && (
            <div className="mt-5 space-y-5">
              {preparing && job.total > 0 && (
                <ProgressBar
                  value={job.done}
                  max={job.total}
                  label="Uploads prepared"
                  tone={job.status === 'failed' ? 'danger' : 'accent'}
                />
              )}

              {processing && (
                <Loading
                  label={
                    job.phase === 'pipeline'
                      ? 'Reconstruction pipeline running — the backend reports coarse stage progress only.'
                      : `Preparing uploads — ${job.phase || 'working'}`
                  }
                />
              )}

              {outcome === 'done_with_model' && (
                <div className="rounded-lg border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
                  <p className="font-semibold">Processing complete — model artifact available.</p>
                  <p className="mt-1 text-emerald-200/80">
                    The backend produced a scene or collision GLB for this session.
                  </p>
                  <Button
                    to={`/session/${session.sessionId}/model`}
                    variant="secondary"
                    size="sm"
                    className="mt-3"
                  >
                    Review model
                  </Button>
                </div>
              )}

              {outcome === 'done_without_model' && (
                <div className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-200">
                  <p className="font-semibold">Processing complete — no GLB produced.</p>
                  <p className="mt-1 text-amber-200/80">
                    The job finished, but the backend did not report a scene or collision artifact.
                    This is not a successful reconstruction. Check the job message and the session
                    inputs below.
                  </p>
                </div>
              )}

              {outcome === 'failed' && (
                <div className="rounded-lg border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">
                  <p className="font-semibold">Processing failed.</p>
                  {job.error ? (
                    <p className="mt-1 break-words font-mono text-xs text-red-200/90">{job.error}</p>
                  ) : (
                    <p className="mt-1 text-red-200/80">No error detail was reported.</p>
                  )}
                </div>
              )}

              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Detail label="Status" value={status} />
                <Detail label="Phase" value={job.phase || '—'} />
                <Detail label="Ready assets" value={ready} />
                <Detail label="Uploading assets" value={uploading} />
                <Detail label="Failed assets" value={failed} />
                <Detail label="Images prepared" value={job.image_count ?? 0} />
                <Detail label="Started" value={job.started_at ? formatDate(job.started_at) : 'Not started'} />
                <Detail label="Finished" value={job.finished_at ? formatDate(job.finished_at) : 'Not finished'} />
              </dl>

              {job.message && <p className="text-sm text-neutral-300">{job.message}</p>}

              {job.output_dir && (
                <p className="break-all text-xs text-neutral-500">
                  Output directory: <span className="font-mono">{job.output_dir}</span>
                </p>
              )}

              <StartBlockers blockers={blockers} />
            </div>
          )}
        </Card>

        <Card className="h-fit p-6">
          <h2 className="text-sm font-semibold text-white">Session inputs</h2>
          <p className="mt-1 text-sm text-neutral-400">
            Processing uses stored and ready photo/video assets, then writes derived files beneath
            this session&apos;s data directory.
          </p>
          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-neutral-500">Uploads</dt>
              <dd className="text-neutral-200">{assets.length}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-neutral-500">Photos</dt>
              <dd className="text-neutral-200">{photos}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-neutral-500">Videos</dt>
              <dd className="text-neutral-200">{videos}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-neutral-500">Ready for processing</dt>
              <dd className="text-neutral-200">{readyMedia}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-neutral-500">Still uploading</dt>
              <dd className="text-neutral-200">{uploading}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-neutral-500">Output</dt>
              <dd className="break-all text-right font-mono text-xs text-neutral-200">
                {job?.output_dir || 'Not created yet'}
              </dd>
            </div>
          </dl>
        </Card>
      </div>
    </>
  )
}
