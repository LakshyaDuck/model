"""COLMAP dense reconstruction with a CPU fallback.

The primary path mirrors the COLMAP CLI::

    colmap image_undistorter --image_path frames_clean \\
        --input_path sparse/0 --output_path dense
    colmap patch_match_stereo --workspace_path dense
    colmap stereo_fusion --workspace_path dense \\
        --output_path dense/fused.ply

Patch-match stereo is CUDA-only in COLMAP/pycolmap, and the PyPI wheels are not
built with CUDA. When ``pycolmap`` cannot do it, the same undistorted workspace
is handed to OpenMVS instead::

    InterfaceCOLMAP -i dense -o dense/scene.mvs --image-folder dense/images
    DensifyPointCloud dense/scene.mvs

OpenMVS runs its dense reconstruction on the CPU (or GPU when its build supports
it) and writes ``dense/scene_dense.ply``. ``run_dense_reconstruction`` picks the
best available backend and returns the point-cloud path.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import pycolmap

logger = logging.getLogger(__name__)

FUSED_FILENAME = "fused.ply"
OPENMVS_SCENE_FILENAME = "scene.mvs"
OPENMVS_DENSE_FILENAME = "scene_dense.ply"
OPENMVS_TOOLS = ("InterfaceCOLMAP", "DensifyPointCloud")


def _colmap_dense_available() -> bool:
    return bool(pycolmap.has_cuda)


def openmvs_available() -> bool:
    """True when the OpenMVS dense-reconstruction tools are on ``PATH``."""
    return all(shutil.which(tool) for tool in OPENMVS_TOOLS)


def dense_available() -> bool:
    """True when either dense backend can run in this environment."""
    return _colmap_dense_available() or openmvs_available()


def _run_tool(command: list[str], *, cwd: Path, log_path: Path) -> None:
    logger.info("running %s", " ".join(command))
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"$ {' '.join(command)}\n")
        log.flush()
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"OpenMVS tool not found: {command[0]}") from exc
    if result.returncode != 0:
        detail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise RuntimeError(
            f"{command[0]} failed with exit code {result.returncode}; "
            f"see {log_path}:\n{detail.strip()}"
        )


def _run_colmap_dense(
    images: Path,
    model: Path,
    dense: Path,
) -> Path:
    dense.mkdir(parents=True, exist_ok=True)

    logger.info(
        "undistorting images from %s with model %s into %s", images, model, dense
    )
    pycolmap.undistort_images(
        output_path=str(dense),
        input_path=str(model),
        image_path=str(images),
    )

    logger.info("running COLMAP patch-match stereo in %s", dense)
    pycolmap.patch_match_stereo(workspace_path=str(dense))

    fused_path = dense / FUSED_FILENAME
    logger.info("fusing depth maps into %s", fused_path)
    pycolmap.stereo_fusion(
        output_path=str(fused_path),
        workspace_path=str(dense),
        output_type="ply",
    )

    if not fused_path.is_file():
        raise RuntimeError(f"COLMAP stereo fusion produced no point cloud at {fused_path}")
    return fused_path


def _run_openmvs_dense(
    images: Path,
    model: Path,
    dense: Path,
) -> Path:
    dense.mkdir(parents=True, exist_ok=True)

    logger.info(
        "using OpenMVS to densify %s with model %s into %s",
        images,
        model,
        dense,
    )
    pycolmap.undistort_images(
        output_path=str(dense),
        input_path=str(model),
        image_path=str(images),
    )

    scene_path = dense / OPENMVS_SCENE_FILENAME
    log_path = dense / "openmvs.log"
    _run_tool(
        [
            "InterfaceCOLMAP",
            "-i",
            str(dense),
            "-o",
            str(scene_path),
            "--image-folder",
            str(dense / "images"),
        ],
        cwd=dense,
        log_path=log_path,
    )
    if not scene_path.is_file():
        raise RuntimeError(f"InterfaceCOLMAP produced no scene at {scene_path}")

    logger.info("running OpenMVS DensifyPointCloud in %s", dense)
    _run_tool(["DensifyPointCloud", str(scene_path)], cwd=dense, log_path=log_path)

    dense_path = dense / OPENMVS_DENSE_FILENAME
    if not dense_path.is_file():
        raise RuntimeError(
            f"OpenMVS DensifyPointCloud produced no point cloud at {dense_path}"
        )
    return dense_path


def run_dense_reconstruction(
    images_dir: str | Path,
    sparse_model_path: str | Path,
    dense_dir: str | Path,
) -> Path:
    """Run the densest reconstruction available for one sparse model.

    ``images_dir`` is the same frame directory that was used for the sparse
    model. ``sparse_model_path`` is a numbered model directory such as
    ``sparse/0``. The undistorted workspace and point cloud are written under
    ``dense_dir``; the point-cloud path is returned.

    COLMAP patch-match stereo is used when ``pycolmap`` was built with CUDA,
    otherwise OpenMVS densifies on the CPU. If the COLMAP attempt fails and
    OpenMVS is available, OpenMVS is used as a fallback. Raises
    ``FileNotFoundError`` when an input is missing and ``RuntimeError`` when no
    backend is available or the chosen backend produces no point cloud.
    """
    images = Path(images_dir)
    model = Path(sparse_model_path)
    dense = Path(dense_dir)

    if not images.is_dir():
        raise FileNotFoundError(f"image directory not found: {images}")
    if not model.is_dir():
        raise FileNotFoundError(f"COLMAP model directory not found: {model}")

    if _colmap_dense_available():
        try:
            return _run_colmap_dense(images, model, dense)
        except Exception as exc:  # noqa: BLE001 - fall back to CPU when CUDA fails
            if not openmvs_available():
                raise
            logger.warning(
                "COLMAP dense reconstruction failed (%s); falling back to OpenMVS",
                exc,
            )
    if openmvs_available():
        return _run_openmvs_dense(images, model, dense)

    raise RuntimeError(
        "dense reconstruction needs either a CUDA-enabled pycolmap build or "
        "OpenMVS (InterfaceCOLMAP and DensifyPointCloud) on PATH"
    )
