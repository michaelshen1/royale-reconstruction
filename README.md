# Royale Reconstruction

A computer vision pipeline that takes Clash Royale gameplay footage (2D) and recreates it in a 3D environment.

## Overview

Royale Reconstruction uses a fine-tuned YOLOv8 model and ByteTrack multi-object tracking to detect and track units in Clash Royale gameplay videos. The tracked movement paths are then exported to Blender, where 3D models are animated along those paths to produce a full 3D reconstruction of the match.

## Pipeline

```
Clash Royale video (.mp4)
        │
        ▼
  YOLOv8 Detection          ← fine-tuned on CR assets (clash_yolo_4_13.pt)
        │
        ▼
  ByteTrack Tracking         ← assigns persistent IDs to each unit
        │
        ▼
  Centroid Path Export       ← clash_royale_tracking.json / game_tracks.json
        │
        ▼
  Blender 3D Reconstruction  ← blender.py animates 3D models along tracked paths
        │
        ▼
    output_video.mp4
```

## Repository Structure

```
royale-reconstruction/
├── inference.py              # YOLO + ByteTrack inference on video
├── inference.ipynb           # Notebook version of inference
├── blender.py                # Blender Python script for 3D reconstruction
├── finetune.ipynb            # Fine-tuning YOLOv8 on Clash Royale assets
├── gen_sprite_frames.ipynb   # Sprite sheet frame extraction
│
├── clash_yolo_4_13.pt        # Fine-tuned YOLO model weights
├── finetuned_clash.pt        # Alternate fine-tuned weights
├── yolo26n.pt                # Base YOLOv8 nano weights
│
├── ClashRoyale_detection_fixed.yaml  # Dataset config for training
├── data.yaml                 # YOLO data config
├── bytetrack.yaml            # ByteTrack tracker config
│
├── clash_royale_tracking.json  # Tracking output (per-unit centroid paths)
├── game_tracks.json            # Processed game track data for Blender
│
├── cr-assets-png/            # Clash Royale sprite assets (PNG)
├── wizard_3d_model/          # 3D model(s) used in reconstruction
├── arena/                    # Arena geometry assets
├── vids/                     # Input gameplay videos
├── output_frames/            # Raw output frames
└── scaled_output_frames/     # Scaled output frames
```

## Setup

**Requirements:**
- Python 3.10+
- [Blender](https://www.blender.org/) (for 3D reconstruction step)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

**Install dependencies:**

```bash
# With uv (recommended)
uv sync

# Or with pip
pip install ultralytics opencv-python torch numpy
```

## Usage

### Step 1 — Run inference on a gameplay video

```bash
python inference.py
```

By default this reads from `vids/hog_2_6_start.mp4`, runs detection and tracking, and writes centroid paths to `clash_royale_tracking.json`. To use a different video, update the paths at the bottom of `inference.py`:

```python
VIDEO_INPUT = "vids/your_video.mp4"
MODEL_WEIGHTS = "clash_yolo_4_13.pt"
OUTPUT_FILE = "clash_royale_tracking.json"
```

### Step 2 — Reconstruct in Blender

Open Blender and run `blender.py` via the Blender scripting panel. The script reads the tracking JSON and animates 3D models along the detected unit paths.

### Fine-tuning (optional)

To retrain or fine-tune the detection model on new Clash Royale assets, open and run `finetune.ipynb`. The dataset config is defined in `ClashRoyale_detection_fixed.yaml`.

## Tech Stack

| Component | Tool |
|---|---|
| Object Detection | YOLOv8 (Ultralytics) |
| Multi-Object Tracking | ByteTrack |
| 3D Reconstruction | Blender (Python API) |
| Inference Acceleration | MPS (Apple Silicon) / CPU |
| Package Management | uv |

## Notes

- The model was trained on Clash Royale sprite assets and may not generalize to heavily modified UI overlays or unusual camera angles.
- Inference runs on MPS (Apple Silicon GPU) if available, falling back to CPU.
- Blender must be launched separately; `blender.py` is intended to run inside Blender's Python environment, not as a standalone script.
