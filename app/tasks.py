from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
from app.repositories import update_inference_task
from app.models import InferenceImage
import time

@celery_app.task(name="tasks.process_sample_image")
def process_sample_image(task_identifier: str, task_id: int):
    """Simulate a long-running image classification or processing task."""
    
    db = SessionLocal() # celery must start its own instance
    
    # start processing the task
    time.sleep(6)  # Simulated processing delay
    print("Starting Processing")
    task_update: InferenceImage | None = update_inference_task(db, task_id, "PROCESSING", None)
    
    print("Processed")
    time.sleep(6)  # Simulated processing delay
    try: 
        task_update = update_inference_task(db, task_id, "SUCCESS", None)
    except:
        task_update = update_inference_task(db, task_id, "FAILURE", None)

    print(f"Completed {task_update.task_status}")

    if not task_update:
        return {"error": f"Task ID {task_identifier} not found in database."}

    db.refresh(task_update)
    # Return ONLY serializable primitives (strings, numbers, plain dicts)
    return {
        "status": task_update.task_status,
        "task_identifier": task_update.task_identifier
    }

