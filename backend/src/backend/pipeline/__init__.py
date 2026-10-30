"""Reconstruction pipeline: shared paths, photo preparation, and stage modules.

Each stage module has no import-time side effects. The Process job imports
``prepare_asset``, ``pipeline``, and ``PIPELINE_DONE`` from here; the path helpers
keep the job and stages on the same session layout.
"""

from .align import align_point_cloud
from .clean_point_cloud import clean_point_cloud
from .dense_reconstruction import (
    dense_available,
    openmvs_available,
    run_dense_reconstruction,
)
from .export import COLLISION_FILENAME, SCENE_FILENAME, export_models
from .extract_frames import extract_frames
from .feature_extraction import extract_features
from .feature_matching import match_features
from .freeze import POINT_CLOUD_FILENAME, freeze_artifacts
from .mapper import run_mapper
from .mesh import reconstruct_mesh
from .model_analyzer import analyze_model
from .paths import (
    ARTIFACTS_DIRNAME,
    ARTIFACTS_VERSION,
    COLMAP_DATABASE_NAME,
    COLMAP_DIRNAME,
    DENSE_DIRNAME,
    EXTRACTED_FRAMES_DIRNAME,
    IMAGES_DIRNAME,
    INPUTS_NAME,
    PROCESSED_DIRNAME,
    RECONSTRUCTION_DIRNAME,
    SPARSE_DIRNAME,
    artifacts_dir,
    colmap_run_dir,
    extracted_frames_dir,
    images_dir,
    inputs_file,
    processed_dir,
    relative_to_data,
)
from .prepare import JPEG_QUALITY, MAX_IMAGE_DIM, prepare_asset, process_photo
from .run import PIPELINE_DONE, pipeline
from .split import split_mesh

__all__ = [
    "ARTIFACTS_DIRNAME",
    "ARTIFACTS_VERSION",
    "COLMAP_DATABASE_NAME",
    "COLMAP_DIRNAME",
    "COLLISION_FILENAME",
    "DENSE_DIRNAME",
    "EXTRACTED_FRAMES_DIRNAME",
    "IMAGES_DIRNAME",
    "INPUTS_NAME",
    "JPEG_QUALITY",
    "MAX_IMAGE_DIM",
    "PIPELINE_DONE",
    "POINT_CLOUD_FILENAME",
    "PROCESSED_DIRNAME",
    "RECONSTRUCTION_DIRNAME",
    "SCENE_FILENAME",
    "SPARSE_DIRNAME",
    "align_point_cloud",
    "analyze_model",
    "artifacts_dir",
    "clean_point_cloud",
    "colmap_run_dir",
    "dense_available",
    "export_models",
    "extract_features",
    "extract_frames",
    "extracted_frames_dir",
    "freeze_artifacts",
    "images_dir",
    "inputs_file",
    "match_features",
    "openmvs_available",
    "pipeline",
    "prepare_asset",
    "process_photo",
    "processed_dir",
    "reconstruct_mesh",
    "relative_to_data",
    "run_dense_reconstruction",
    "run_mapper",
    "split_mesh",
]
