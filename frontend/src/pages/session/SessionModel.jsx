import { collisionModelUrl, modelUrl } from '../../api.js'
import ModelViewer from '../../components/session/ModelViewer.jsx'
import Badge from '../../components/ui/Badge.jsx'
import Button from '../../components/ui/Button.jsx'
import Card from '../../components/ui/Card.jsx'
import EmptyState from '../../components/ui/EmptyState.jsx'
import Loading from '../../components/ui/Loading.jsx'
import PageHeader from '../../components/ui/PageHeader.jsx'
import { formatDate } from '../../lib/format.js'
import { useSession } from '../../session/SessionContext.js'

const STATUS_TONE = {
  idle: 'neutral',
  queued: 'warning',
  running: 'accent',
  done: 'success',
  failed: 'danger',
}

function CollisionDownload({ href }) {
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Collision model</h2>
          <p className="mt-1 max-w-md text-sm text-neutral-400">
            The simplified mesh is available for collision and navigation work. It is not loaded
            in the viewer; the scene GLB remains the visual model.
          </p>
        </div>
        <Badge tone="neutral">Optional</Badge>
      </div>
      <p className="mt-4 break-all rounded-lg border border-white/10 bg-black/20 p-3 font-mono text-xs text-neutral-400">
        collision.glb
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button href={href} download="collision.glb">
          Download collision GLB
        </Button>
      </div>
    </Card>
  )
}

export default function SessionModel() {
  const { session, job } = useSession()

  const status = job?.status || 'idle'
  const processing = status === 'queued' || status === 'running'
  const failed = status === 'failed'
  const done = status === 'done'
  const hasScene = Boolean(job?.model_path)
  const hasCollision = Boolean(job?.collision_model_path)
  const sceneHref = modelUrl(session.sessionId, session.ownerToken)
  const collisionHref = collisionModelUrl(session.sessionId, session.ownerToken)

  return (
    <>
      <PageHeader
        eyebrow="Reconstruction"
        title="Model"
        description="Inspect the GLB produced by the backend. The viewer only displays the scene artifact — nothing is reconstructed or generated in the browser."
        actions={
          <Button to={`/session/${session.sessionId}/process`} variant="secondary">
            Processing status
          </Button>
        }
      />

      {job === null && (
        <Card className="mb-6 p-5">
          <Loading label="Reading processing status…" />
        </Card>
      )}

      {processing && (
        <Card className="mb-6 p-5">
          <Loading
            label={`The viewer will load the GLB once the backend produces it — ${job.phase || status}`}
          />
        </Card>
      )}

      {failed && (
        <div className="mb-6 rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          <p className="font-semibold">Processing failed, so no model is available.</p>
          {job.error && <p className="mt-1 break-words font-mono text-xs">{job.error}</p>}
        </div>
      )}

      {done && !hasScene && (
        <div className="mb-6 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <p className="font-semibold">
            {hasCollision
              ? 'Processing completed without a scene model.'
              : 'Processing completed without a model artifact.'}
          </p>
          <p className="mt-1 text-amber-200/80">
            A finished job is not a successful reconstruction. The backend did not report a
            <code className="mx-1">scene.glb</code> for this session, so the viewer has nothing to
            display.
            {hasCollision &&
              ' A collision GLB was produced, but it is not shown as the visual model.'}
          </p>
        </div>
      )}

      {job !== null && !hasScene && !processing && !failed && !done && (
        <EmptyState
          className="mb-6"
          title="Model unavailable"
          description="The backend has not reported a model path for this session. Upload media and run processing to produce a GLB."
          action={<Button to={`/session/${session.sessionId}/process`}>Open processing</Button>}
        />
      )}

      {hasScene && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-white">Scene model</h2>
              <p className="mt-1 text-xs text-neutral-500">
                Loaded from the backend model endpoint with the in-memory owner token.
                {job?.finished_at && ` Processed ${formatDate(job.finished_at)}.`}
              </p>
            </div>
            <Badge tone={STATUS_TONE[status] || 'neutral'}>{status}</Badge>
          </div>

          <ModelViewer
            src={sceneHref}
            downloadHref={sceneHref}
            downloadFilename="scene.glb"
          />

          <p className="break-all text-xs text-neutral-500">
            Artifact: <span className="font-mono">{job.model_path}</span>
          </p>
        </div>
      )}

      {hasCollision && (
        <div className="mt-6">
          <CollisionDownload href={collisionHref} />
        </div>
      )}

      {!hasScene && !hasCollision && !processing && !failed && job !== null && !done && (
        <p className="mt-6 text-xs text-neutral-500">
          No <span className="font-mono">scene.glb</span> or{' '}
          <span className="font-mono">collision.glb</span> path is reported for this session.
        </p>
      )}

      {hasScene && (
        <p className="mt-6 text-xs text-neutral-500">
          The GLB is served by the backend and displayed as-is. The browser does not generate or
          alter geometry, and the owner token stays in memory.
        </p>
      )}
    </>
  )
}
