from contextlib import asynccontextmanager
from typing import List

from uuid import uuid4
from sqlalchemy.orm import Session
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from app.database import get_db, init_db
from app.models import InferenceImage, InferenceTask
import app.repositories as repo
import app.tasks as tasks

app = FastAPI(
    title="SmileyDetect API",
    description ="API for classifying and localizing smiley faces",
    version="1.0.0"
)

# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    init_db()  # Creates the database and tables (like smiley_app.db) on startup
    yield
    # --- Shutdown Logic (optional) ---
    # Put any cleanup code here if needed when the app stops

# Pass the lifespan function into your FastAPI application instance
app = FastAPI(lifespan=lifespan)

# Welcome message
@app.get("/")
def read_root():
    return {"message": "Hello smiley!"}

@app.post("/upload-single-image/")
async def upload_single_image(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    created_record_guids = repo.create_bulk_inference_images(db, [file])
    return {
        "images": created_record_guids,
        "count": len(created_record_guids)
    }

@app.post("/upload-images/")
async def upload_images(
    imgs: List[UploadFile] = File(...),  # Must include File(...)
    db: Session = Depends(get_db)):
    created_record_guids = repo.create_bulk_inference_images(db, imgs)
    return {
        "images": created_record_guids,
        "count": len(created_record_guids)
    }

# Start an inference task on a specific image
@app.post("/process-image/{image_guid}")
def trigger_image_processing(image_guid: str, db: Session = Depends(get_db)):

    # insert the task record into the dabase
    db_task_record = repo.create_inference_task(db, image_guid)

    # TODO - if failed to insert, throw

    # call background task to process image
    task = tasks.process_sample_image.delay(db_task_record.task_identifier, db_task_record.id)

    # update status to PENDING
    db_task_update = repo.update_inference_task(db, db_task_record.id, "PENDING")

    # TODO - if task failed to start, record to db

    return {
        "task_guid": db_task_update.guid,
        "task_identifier": db_task_update.task_identifier,
        "status": db_task_update.task_status
    }

@app.get("/task-details/{task_guid}")
def get_task_details(task_guid: str, db: Session = Depends(get_db)):
    
    # Fetch task with eagerly loaded detections
    inference_task: InferenceTask | None = repo.get_task_by_guid(db, task_guid)
    if not inference_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Format the related detection rows into a clean list of dictionaries
    formatted_detections = [
        {
            "id": det.id,
            "confidence": det.confidence,
            "x_min": det.x_min,
            "y_min": det.y_min,
            "x_max": det.x_max,
            "y_max": det.y_max
        }
        for det in inference_task.detections
    ]
    
    return {
        "task_guid": inference_task.guid,
        "task_identifier": inference_task.task_identifier,
        "task_status": inference_task.task_status,
        "task_init_at": inference_task.task_init_at,
        "task_last_updated_at": inference_task.task_last_updated_at,
        "result": inference_task.result,
        "detections": formatted_detections
    }

@app.get("/images")
def get_images(db: Session = Depends(get_db)): # TODO paginate and filter
    db_result: List[InferenceImage] | None = repo.get_inference_images(db)
    return db_result
