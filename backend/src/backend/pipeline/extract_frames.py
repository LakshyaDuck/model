"""Blur-filtered frame extraction from one capture video.

``extract_frames`` is the single callable in this module and has no import-time
side effects: it samples a video at a fixed rate, scores every sampled frame by
Laplacian variance, keeps the sharp frames (adaptive 25th-percentile threshold,
with a guaranteed minimum keep ratio), writes them as JPEGs, and records every
decision in a CSV report.

The Process job calls it from ``run.pipeline`` for each video in the session.
"""

from __future__ import annotations

import csv
import logging
import math
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_FRAMES_PER_SECOND = 4
DEFAULT_MINIMUM_KEEP_PERCENTAGE = 25


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    *,
    prefix: str,
    frames_per_second: float = DEFAULT_FRAMES_PER_SECOND,
    minimum_keep_percentage: float = DEFAULT_MINIMUM_KEEP_PERCENTAGE,
) -> Path:
    """Extract the sharp frames of ``video_path`` into ``output_dir``.

    Frames are named ``<prefix>_frame_NNNN.jpg`` and every sampled frame's score
    and decision is written to ``<prefix>_laplacian_variance.csv``, so the output
    directory can hold frames from several videos without collisions.

    ``output_dir`` is created when missing. Returns ``output_dir``.

    Raises ``ValueError`` when the video cannot be opened, its FPS is
    unreadable, or it yields no sampled frames. The caller decides whether that
    skips the video or fails the job.
    """
    output = Path(output_dir)
    video = cv2.VideoCapture(str(video_path))

    if not video.isOpened():
        raise ValueError(f"could not open video: {video_path}")

    try:
        fps = video.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            raise ValueError(f"could not read video FPS: {video_path}")

        frame_interval = max(1, round(fps / frames_per_second))

        # Step 1: extract frames and calculate Laplacian variance
        frames: list[tuple["np.ndarray", float]] = []
        frame_number = 0

        while True:
            success, frame = video.read()
            if not success:
                break

            if frame_number % frame_interval == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                laplacian = cv2.Laplacian(gray, cv2.CV_64F)
                frames.append((frame, float(laplacian.var())))

            frame_number += 1
    finally:
        video.release()

    if not frames:
        raise ValueError(f"no frames were extracted from the video: {video_path}")

    # Step 2: adaptive threshold at the 25th percentile
    scores = np.array([variance for _, variance in frames])
    threshold = float(np.percentile(scores, minimum_keep_percentage))

    # Step 3: select frames at or above the threshold
    selected_indices = {i for i, (_, score) in enumerate(frames) if score >= threshold}

    # Step 4: guarantee the minimum keep percentage
    minimum_frames = math.ceil(len(frames) * minimum_keep_percentage / 100)
    if len(selected_indices) < minimum_frames:
        ranked_indices = sorted(
            range(len(frames)), key=lambda i: frames[i][1], reverse=True
        )
        selected_indices = set(ranked_indices[:minimum_frames])

    # Step 5: save selected frames and record every decision
    output.mkdir(parents=True, exist_ok=True)

    results: list[list] = []
    saved_count = 0

    for i, (frame, score) in enumerate(frames):
        filename = f"{prefix}_frame_{i:04d}.jpg"

        if i in selected_indices:
            if not cv2.imwrite(str(output / filename), frame):
                raise RuntimeError(f"could not save {filename}")
            decision = "Accepted"
            saved_count += 1
        else:
            decision = "Rejected"

        results.append([filename, round(score, 2), decision])

    # Step 6: save the CSV report
    csv_path = output / f"{prefix}_laplacian_variance.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Frame", "Laplacian Variance", "Decision"])
        writer.writerows(results)

    logger.info(
        "extracted %d/%d frames from %s into %s",
        saved_count,
        len(frames),
        video_path,
        output,
    )
    return output
