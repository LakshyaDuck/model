# Plan

## Inputs and outputs

- **Input** — every video in the current session, handed to `pipeline(videos)` in
  `backend/src/backend/pipeline/run.py` after the Process button starts the job.
  Each entry has `asset_id`, `kind`, `original_filename`, `stored_path`, and
  `mime`.
- **Output** — a 3D model as a `.glb` file.

## Where to implement

`pipeline()` in `backend/src/backend/pipeline/run.py` is the ownership point. It
receives the session's videos and must return the `PIPELINE_DONE` signal when it
finishes; the job runner treats any other return value as a failure. The Process
job manager in `backend/src/backend/processing.py` normalizes photos through
`pipeline/prepare.py`, writes `processed/inputs.json`, then calls `pipeline()`.

Today it calls the stages in `backend/src/backend/pipeline/`: `extract_frames()`
for each video writes blur-filtered stills and a CSV report into
`DATA_DIR/sessions/<session_id>/extracted_frames/` and returns that directory.
It then runs `extract_features()`, `match_features()`, `run_mapper()`,
`analyze_model()`, and `run_dense_reconstruction()` over those frames, writing the
COLMAP database to
`DATA_DIR/sessions/<session_id>/reconstruction/colmap/<run_id>/database.db`, the
sparse model to the sibling `sparse/` directory, and each dense point cloud to
`dense/<model_id>/` (`fused.ply` via COLMAP patch-match stereo when `pycolmap` has
CUDA, otherwise `scene_dense.ply` via OpenMVS). Model statistics are logged. Dense
reconstruction is skipped with a warning only when neither a CUDA-enabled
`pycolmap` nor the OpenMVS tools (`InterfaceCOLMAP`, `DensifyPointCloud`) are
available. The first dense result is then frozen by `freeze_artifacts()` into
`DATA_DIR/sessions/<session_id>/artifacts/v1/`, containing `fused.ply` and a
`poses/` COLMAP TXT export. `clean_point_cloud()` removes statistical and radius
outliers and voxel-downsamples that cloud into `artifacts/v1/cleaned.ply`.
`align_point_cloud()` segments the dominant plane and rotates the cloud so the
plane normal is +Z, writing `artifacts/v1/aligned.ply`. `reconstruct_mesh()` runs
Poisson surface reconstruction (`depth=9`), drops the lowest 5% density vertices,
and writes `artifacts/v1/mesh.ply`. `split_mesh()` keeps that full-detail mesh as
`artifacts/v1/visual.ply` and writes a 15,000-triangle Quadric-decimated mesh with
sub-1% connected clusters removed as `artifacts/v1/collision.ply`. Finally,
`export_models()` writes `artifacts/v1/scene.glb` (the visual mesh, including
vertex colours when present) and `artifacts/v1/collision.glb`.
