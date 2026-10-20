from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
import app.repositories as repo
from app.models import InferenceImage
import time
import pickle
import numpy as np
from PIL import Image

# Hardcoded model path for the proof of concept
MODEL_PATH = "saved_models/smiley_v1.pkl"

def run_inference(image_path: str) -> dict:
    """ return confidence TODO - need to add localization """
    # 1. Load the hardcoded model
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
        
    # 2. Preprocess input image
    img = Image.open(image_path).convert('L').resize((64, 64))
    features = np.array(img).flatten().reshape(1, -1)
    
    # 3. Predict
    prediction = model.predict(features)[0]
    confidence = float(np.max(model.predict_proba(features)))
    
    return {
        "smile_detected": bool(prediction == 1),
        "confidence": confidence,
        "model_used": MODEL_PATH
    }

@celery_app.task(name="tasks.process_sample_image")
def process_sample_image(task_identifier: str, task_id: int):
    """Simulate a long-running image classification or processing task."""
    
    db = SessionLocal() # celery must start its own instance
    
    # start processing the task
    time.sleep(6)  # Simulated processing delay
    print("Starting Processing")
    task_update: InferenceImage | None = repo.update_inference_task(db, task_id, "PROCESSING", None)

    # actually process the image
    time.sleep(6)  # Simulated processing delay
    image_path = repo.get_inference_image_by_task_id(db, task_id).filepath # TODO - throw exception if task has no image
    inference_results = run_inference(image_path)

    # process completed, save results
    print("Processed")
    print(inference_results)
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

