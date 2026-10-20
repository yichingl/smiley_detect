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
    Scans the image (or uses a sliding window/detector) to find smiley bounding boxes.
    Returns a list of dicts containing coordinates and confidence scores.
    """
    # 1. Load model
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
        
    img = Image.open(image_path).convert('L')
    img_width, img_height = img.size
    
    detections = []
    
    # (Example Proof-of-Concept Logic: 
    # For a full sliding window or using an object detector like YOLO/PyTorch, 
    # you would loop through regions or get direct coordinate outputs.)
    
    # Mocking a detected bounding box for demonstration:
    # If using YOLO, it directly returns boxes [x_min, y_min, x_max, y_max, confidence]
    
    # For now, let's simulate a detected bounding box if confidence is high:
    sample_patch = img.resize((64, 64))
    features = np.array(sample_patch).flatten().reshape(1, -1)
    
    prediction = model.predict(features)[0]
    confidence = float(np.max(model.predict_proba(features)))
    
    if prediction == 1 and confidence >= CONFIDENCE_THRESHOLD:
        detections.append({
            "x_min": 50,
            "y_min": 50,
            "x_max": 150,
            "y_max": 150,
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

    # TODO filter thorugh the coordinates and remove overlapping results
    filtered_results = detected_locations

    # save results to database
    for box in filtered_results:
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

