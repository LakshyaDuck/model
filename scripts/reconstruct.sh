#!/usr/bin/env bash
# Run a CPU sparse COLMAP reconstruction for one captured session.
#
# This is intentionally a repeatable, inspectable first worker rather than the
# final photorealistic renderer. It computes camera poses and a sparse point
# cloud; a later 3DGS/NeRF stage consumes those calibrated cameras.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: reconstruct.sh --session <session-id> [--gpu]

The session must exist in /data/sessions/<session-id>/raw and contain at least
two JPEG or PNG photos. Results are written to
/data/sessions/<session-id>/reconstruction/colmap.

By default this is CPU-safe. Pass --gpu only on a Docker host configured with
the NVIDIA Container Toolkit and a compatible COLMAP image.
EOF
}

session_id=""
use_gpu=0
while (($#)); do
  case "$1" in
    --session)
      session_id="${2:-}"
      shift 2
      ;;
    --gpu)
      use_gpu=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$session_id" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "--session must be a safe session identifier" >&2
  exit 2
fi

raw_dir="/data/sessions/$session_id/raw"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="/data/sessions/$session_id/reconstruction/colmap/$run_id"
images_dir="$output_dir/images"
database="$output_dir/database.db"
sparse_dir="$output_dir/sparse"
export_dir="$output_dir/export"

if [[ ! -d "$raw_dir" ]]; then
  echo "Capture session directory does not exist: $raw_dir" >&2
  exit 1
fi

mkdir -p "$images_dir" "$sparse_dir" "$export_dir"

shopt -s nullglob
images=("$raw_dir"/*.[Jj][Pp][Gg] "$raw_dir"/*.[Jj][Pp][Ee][Gg] "$raw_dir"/*.[Pp][Nn][Gg])
if ((${#images[@]} < 2)); then
  echo "Need at least two JPEG/PNG photos in $raw_dir; video-frame extraction and HEIC normalisation are next-stage workers." >&2
  exit 1
fi

for image in "${images[@]}"; do
  cp "$image" "$images_dir/"
done

echo "Extracting features from ${#images[@]} images (GPU: $use_gpu)"
colmap feature_extractor \
  --database_path "$database" \
  --image_path "$images_dir" \
  --ImageReader.single_camera 0 \
  --SiftExtraction.use_gpu "$use_gpu"

echo "Matching sequential capture frames"
colmap sequential_matcher \
  --database_path "$database" \
  --SiftMatching.use_gpu "$use_gpu"

echo "Estimating sparse model"
colmap mapper \
  --database_path "$database" \
  --image_path "$images_dir" \
  --output_path "$sparse_dir"

models=("$sparse_dir"/*)
if ((${#models[@]} == 0)) || [[ ! -d "${models[0]}" ]]; then
  echo "COLMAP could not estimate a model. Capture more overlap and retry." >&2
  exit 1
fi

model_dir="${models[0]}"
colmap model_converter \
  --input_path "$model_dir" \
  --output_path "$export_dir" \
  --output_type PLY

cat > "$output_dir/README.txt" <<EOF
Sparse COLMAP reconstruction completed.
Input images: ${#images[@]}
Sparse model: $model_dir
Point cloud: $export_dir/points3D.ply

This artifact provides calibrated camera poses and sparse geometry. It is not yet
the photorealistic web asset; feed it into the planned Gaussian-splat/mesh stage.
EOF

echo "Completed: $output_dir"
