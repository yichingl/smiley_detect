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
        raise FileNotFoundError(f"Model artifact not found at {MODEL_PATH}. Please run 'make train' first.")

    # 1. Load trained model
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
        
    # 2. Open image and convert to grayscale
    img = Image.open(image_path).convert('L')
    img_width, img_height = img.size
    # TODO - also need to resize image to the right size for this processing
    
    detections = []

    # Sliding window parameters
    patch_size = 64  # Must match the training image size (64x64)
    stride = 32      # Step size for sliding window
    
    # 3. Scan image regions
    for y in range(0, img_height - patch_size + 1, stride):
        for x in range(0, img_width - patch_size + 1, stride):
            # Crop patch
            box = (x, y, x + patch_size, y + patch_size)
            patch = img.crop(box)
            
            # Flatten and reshape for model prediction
            features = np.array(patch).flatten().reshape(1, -1)
            
            # Predict
            prediction = model.predict(features)[0]
            probabilities = model.predict_proba(features)
            confidence = float(np.max(probabilities))
            
            # If classified as positive smiley with high confidence
            if prediction == 1 and confidence >= CONFIDENCE_THRESHOLD:
                detections.append({
                    "x_min": x,
                    "y_min": y,
                    "x_max": x + patch_size,
                    "y_max": y + patch_size,
                    "confidence": confidence
                })
                
    # TODO Simple Non-Maximum Suppression (NMS) or overlapping filter can be added here 
    # if multiple adjacent windows trigger on the same smiley face.

    # TODO translate the coordinates back to the original image that haven't been resized 
    
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

