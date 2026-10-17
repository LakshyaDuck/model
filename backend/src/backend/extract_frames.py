import cv2
import os
import csv
import numpy as np
import math

# Configuration
video_path = "room.mp4"
output_folder = "images"
frames_per_second = 4
minimum_keep_percentage = 25

os.makedirs(output_folder, exist_ok=True)

# Open video
video = cv2.VideoCapture(video_path)

if not video.isOpened():
    raise ValueError("Could not open video. Check the video path.")

fps = video.get(cv2.CAP_PROP_FPS)

if fps <= 0:
    video.release()
    raise ValueError("Could not read video FPS.")

frame_interval = max(1, round(fps / frames_per_second))

# Step 1: Extract frames and calculate Laplacian variance
frames = []
frame_number = 0

while True:
    success, frame = video.read()

    if not success:
        break

    if frame_number % frame_interval == 0:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = float(laplacian.var())

        frames.append((frame, variance))

    frame_number += 1

video.release()

if not frames:
    raise ValueError("No frames were extracted from the video.")

print(f"Total extracted frames: {len(frames)}")

# Step 2: Calculate adaptive threshold using the 25th percentile
scores = np.array([variance for _, variance in frames])

threshold = float(np.percentile(scores, 25))

print(f"Adaptive Laplacian threshold: {threshold:.2f}")

# Step 3: Select frames above the threshold
selected_indices = {
    i for i, (_, score) in enumerate(frames)
    if score >= threshold
}

# Step 4: Guarantee at least 25% of frames are selected
minimum_frames = math.ceil(
    len(frames) * minimum_keep_percentage / 100
)

if len(selected_indices) < minimum_frames:
    # Select the sharpest frames if the minimum is not met
    ranked_indices = sorted(
        range(len(frames)),
        key=lambda i: frames[i][1],
        reverse=True
    )

    selected_indices = set(ranked_indices[:minimum_frames])

# Step 5: Save selected frames and record all decisions
results = []
saved_count = 0

for i, (frame, score) in enumerate(frames):
    filename = f"frame_{i:04d}.jpg"

    if i in selected_indices:
        image_path = os.path.join(output_folder, filename)

        if not cv2.imwrite(image_path, frame):
            raise RuntimeError(f"Could not save {filename}")

        decision = "Accepted"
        saved_count += 1
    else:
        decision = "Rejected"

    results.append([
        filename,
        round(score, 2),
        decision
    ])

# Step 6: Save CSV report
csv_path = os.path.join(output_folder, "laplacian_variance.csv")

with open(csv_path, "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow([
        "Frame",
        "Laplacian Variance",
        "Decision"
    ])
    writer.writerows(results)

# Step 7: Print summary
print("\nFrame selection completed!")
print(f"Frames analyzed: {len(frames)}")
print(f"Frames saved: {saved_count}")
print(f"Frames rejected: {len(frames) - saved_count}")
print(f"Percentage retained: {saved_count / len(frames) * 100:.2f}%")
print(f"Sharpness report: {csv_path}")