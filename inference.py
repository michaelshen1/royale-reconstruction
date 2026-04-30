import cv2
import os
import numpy as np
from dataclasses import dataclass, field
from collections import deque
from typing import List, Tuple, Dict
import json
from ultralytics import YOLO
import torch

@dataclass
class TrackedObject:
    id: int
    label: str
    points: List[Tuple[float, float]] = field(default_factory=list)
    frames: List[int] = field(default_factory=list)

class ClashTracker:
    def __init__(self):
        self.objects: Dict[int, TrackedObject] = {}

    def update(self, detections, frame_idx):
        for det in detections:
        # Match the indexing the tracker expects:
        # [x1, y1, x2, y2, conf, class_id, track_id]
            x1, y1, x2, y2 = det[0:4]
            class_id = int(det[5])
            track_id = int(det[6])
        
            if track_id not in self.objects:
                # You might need to map class_id back to a name string here
                self.objects[track_id] = TrackedObject(id=track_id, label=str(class_id))
            
            # Calculate centroid to save for Blender
            centroid_x = (x1 + x2) / 2
            centroid_y = (y1 + y2) / 2
            
            self.objects[track_id].points.append((float(centroid_x), float(centroid_y)))
            self.objects[track_id].frames.append(int(frame_idx))

    def to_dict(self) -> List[Dict]:
        """Convert tracked data to a serializable dictionary."""
        return [
            {
                "id": int(obj.id),
                "label": str(obj.label),
                "path": [{"frame": int(f), "x": float(p[0]), "y": float(p[1])} 
                         for f, p in zip(obj.frames, obj.points)]
            }
            for obj in self.objects.values()
        ]

    def save_to_json(self, filename: str):
        """Save tracking data to JSON."""
        data = self.to_dict()
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"Tracking results saved to {filename}")

def preprocess_frame(frame, target_size=(576, 896)):
    """Resizes and crops the frame to match the model input size."""
    h, w = frame.shape[:2]
    # Resize keeping aspect ratio or direct resize depending on training
    # Based on notebook: 896h x 576w
    resized = cv2.resize(frame, target_size)
    return resized

def run_inference(video_path, model_path, output_json):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}")

    # Load Model
    model = YOLO(model_path)
    
    # Initialize Tracker
    tracker = ClashTracker()
    
    # Open Video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    frame_idx = 0
    print("Starting Inference...")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        # 1. Preprocessing
        processed_frame = preprocess_frame(frame)
        
        # 2. Processing (Detection & Tracking)
        results = model.track(processed_frame, persist=True, verbose=False, device=device)
        
        # 3. Postprocessing (Prepare detections for our tracker)
        boxes = results[0].boxes
        if boxes.id is not None:
            xyxy = boxes.xyxy.cpu().numpy()
            ids = boxes.id.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            cls = boxes.cls.cpu().numpy()
            
            detections = []
            for (box, track_id, score, class_id) in zip(xyxy, ids, conf, cls):
                detections.append([
                    float(box[0]), float(box[1]), float(box[2]), float(box[3]),
                    float(score),
                    int(class_id),
                    int(track_id)
                ])
                
            tracker.update(detections, frame_idx)

        frame_idx += 1
        if frame_idx % 50 == 0:
            print(f"Processed {frame_idx} frames...")

    tracker.save_to_json(output_json)
    
    cap.release()
    print("Inference Complete.")

if __name__ == "__main__":
    # Update these paths to your actual files
    VIDEO_INPUT = "vids/hog_2_6_start.mp4" 
    MODEL_WEIGHTS = "clash_yolo_4_13.pt"
    OUTPUT_FILE = "clash_royale_tracking.json"
    
    run_inference(VIDEO_INPUT, MODEL_WEIGHTS, OUTPUT_FILE)