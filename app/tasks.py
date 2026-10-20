import os

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
import app.repositories as repo
from app.models import DetectionResult, InferenceImage
import time
import pickle
import numpy as np
from PIL import Image

# Hardcoded model path for the proof of concept
MODEL_PATH = "saved_models/smiley_v1.pkl"
CONFIDENCE_THRESHOLD = 0.75

def run_localization_inference(image_path: str) -> list[dict]:
    """
    Scans the image using a sliding window approach to find smiley bounding boxes.
    Returns a list of dicts containing coordinates and confidence scores.
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model artifact not found at {MODEL_PATH}.")

    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
        
    orig_img = Image.open(image_path).convert('L')
    orig_width, orig_height = orig_img.size
    
    detections = []
    patch_size = 64
    stride = 32
    
    # Define scaling factors for your image pyramid
    # < 1.0 shrinks the image (to find large smileys)
    # > 1.0 enlarges the image (to find small smileys)
    scales = [0.5, 0.75, 1.0, 1.25, 1.5]
    
    for scale in scales:
        # 1. Resize image for the current pyramid level
        scaled_width = int(orig_width * scale)
        scaled_height = int(orig_height * scale)
        
        # Skip if scaled image is smaller than the patch size
        if scaled_width < patch_size or scaled_height < patch_size:
            continue
            
        scaled_img = orig_img.resize((scaled_width, scaled_height), Image.Resampling.BILINEAR)
        
        # 2. Run sliding window on this scaled level
        for y in range(0, scaled_height - patch_size + 1, stride):
            for x in range(0, scaled_width - patch_size + 1, stride):
                box = (x, y, x + patch_size, y + patch_size)
                patch = scaled_img.crop(box)
                
                features = np.array(patch).flatten().reshape(1, -1)
                prediction = model.predict(features)[0]
                confidence = float(np.max(model.predict_proba(features)))
                
                if prediction == 1 and confidence >= CONFIDENCE_THRESHOLD:
                    # 3. Map coordinates *back* to the original unscaled image space
                    orig_x_min = int(x / scale)
                    orig_y_min = int(y / scale)
                    orig_x_max = int((x + patch_size) / scale)
                    orig_y_max = int((y + patch_size) / scale)
                    
                    detections.append({
                        "x_min": orig_x_min,
                        "y_min": orig_y_min,
                        "x_max": orig_x_max,
                        "y_max": orig_y_max,
                        "confidence": confidence
                    })
                    
    # Apply NMS to clean up overlapping multi-scale/multi-window boxes
    final_detections = apply_nms(detections, iou_threshold=0.3)
    return final_detections

def apply_nms(detections, iou_threshold=0.3): # TODO - this is for POC, may switch to pytorch instead
    if not detections:
        return []
    # Sort by confidence descending
    sorted_dets = sorted(detections, key=lambda d: d["confidence"], reverse=True)
    keep = []

    while sorted_dets:
        best = sorted_dets.pop(0)
        keep.append(best)
        remaining = []
        for det in sorted_dets:
            # Calculate Intersection over Union (IoU)
            inter_x1 = max(best["x_min"], det["x_min"])
            inter_y1 = max(best["y_min"], det["y_min"])
            inter_x2 = min(best["x_max"], det["x_max"])
            inter_y2 = min(best["y_max"], det["y_max"])

            inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
            best_area = (best["x_max"] - best["x_min"]) * (best["y_max"] - best["y_min"])
            det_area = (det["x_max"] - det["x_min"]) * (det["y_max"] - det["y_min"])
            union_area = best_area + det_area - inter_area

            iou = inter_area / union_area if union_area > 0 else 0
            if iou < iou_threshold:
                remaining.append(det)
        sorted_dets = remaining
    return keep

@celery_app.task(name="tasks.process_sample_image")
def process_sample_image(task_identifier: str, task_id: int):
    """Simulate a long-running image classification or processing task."""
    
    db = SessionLocal() # celery must start its own instance
    
    # start processing the task
    time.sleep(6)  # Simulated processing delay
    print("Starting Processing")
    task_update: InferenceImage | None = repo.update_inference_task(db, task_id, "PROCESSING", None)

    # get a list of high confidence coordinates
    time.sleep(6)  # Simulated processing delay
    image_path = repo.get_inference_image_by_task_id(db, task_id).filepath # TODO - throw exception if task has no image
    detected_locations = run_localization_inference(image_path)

    print("Detections...")
    for detection in detected_locations:
        print(detection)

    # save results to database
    for box in detected_locations:
        db_detection = DetectionResult(
            task_id=task_id,
            confidence=box["confidence"],
            x_min=box["x_min"],
            y_min=box["y_min"],
            x_max=box["x_max"],
            y_max=box["y_max"]
        )
        db.add(db_detection)
    db.commit()

    # process completed, save results
    print("Processed")
    time.sleep(6)  # Simulated processing delay

    try: 
        task_update = repo.update_inference_task(db, task_id, "SUCCESS", None)
    except:
        task_update = repo.update_inference_task(db, task_id, "FAILURE", None)

    print(f"Completed {task_update.task_status}")

    if not task_update:
        return {"error": f"Task ID {task_identifier} not found in database."}

    db.refresh(task_update)
    # Return ONLY serializable primitives (strings, numbers, plain dicts)
    return {
        "status": task_update.task_status,
        "task_identifier": task_update.task_identifier
    }

