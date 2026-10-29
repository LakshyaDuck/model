# Plan

## Inputs and outputs

- **Input** — every video in the current session, handed to `pipeline(videos)` in
  `backend/src/backend/processing.py` after the Process button starts the job.
  Each entry has `asset_id`, `kind`, `original_filename`, `stored_path`, and
  `mime`.
- **Output** — a 3D model as a `.glb` file.

## Where to implement

`pipeline()` in `backend/src/backend/processing.py` is the ownership point. It
receives the session's videos and must return the `PIPELINE_DONE` signal when it
finishes; the job runner treats any other return value as a failure.

Today it calls `extract_frames()` in `backend/src/backend/extract_frames.py` for
each video, which writes blur-filtered stills and a CSV report into
`DATA_DIR/sessions/<session_id>/extracted_frames/` and returns that directory.
It then runs `extract_features()` and `match_features()` from
`feature_extraction.py` / `feature_matching.py` over those frames, writing the
COLMAP database to
`DATA_DIR/sessions/<session_id>/reconstruction/colmap/<run_id>/database.db`.
