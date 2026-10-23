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


from ultralytics import YOLO

# Path to your trained YOLO weights (fallback to yolov8n.pt if custom weights aren't trained yet)
MODEL_PATH = "saved_models/smiley_run-7/weights/best.pt" #TODO change this from being hardcoded
CONFIDENCE_THRESHOLD = 0.75

def run_localization_inference(image_path: str) -> list[dict]:
    """
    Runs YOLO inference on the image to find smiley bounding boxes.
    Returns a list of dicts containing coordinates and confidence scores.
    """

    if(not os.path.exists(MODEL_PATH)):
        return {"error": f"Model at {MODEL_PATH} not found."}

    model_path_to_use = MODEL_PATH # if os.path.exists(MODEL_PATH) else "yolov8n.pt"
    
    # Load the YOLO model
    model = YOLO(model_path_to_use)
    
    # Run prediction on the image
    results = model(image_path, conf=CONFIDENCE_THRESHOLD, verbose=False)
    
    detections = []
    for r in results:
        boxes = r.boxes
        for box in boxes:
            # Extract box coordinates (x_min, y_min, x_max, y_max)
            coords = box.xyxy[0].tolist()
            x_min, y_min, x_max, y_max = map(int, coords[:4])
            confidence = float(box.conf[0])
            
            detections.append({
                "x_min": x_min,
                "y_min": y_min,
                "x_max": x_max,
                "y_max": y_max,
                "confidence": confidence
            })
            
    return detections

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

