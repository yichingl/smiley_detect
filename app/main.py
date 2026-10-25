from contextlib import asynccontextmanager
from typing import List

from uuid import uuid4
import cv2
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, Depends
from app.database import get_db, init_db
from app.models import InferenceImage, InferenceTask
import app.repositories as repo
import app.tasks as tasks
from pathlib import Path

# 1. Define the lifespan context manager first
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    init_db()  # Creates the database and tables on startup
    yield
    # --- Shutdown Logic (optional) ---

# 2. Initialize FastAPI ONCE with metadata and the lifespan
app = FastAPI(
    title="SmileyDetect API",
    description="API for classifying and localizing smiley faces",
    version="1.0.0",
    lifespan=lifespan
)

# 3. Establish the absolute path to your project root
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploaded_images"

# 4. Ensure the directory physically exists
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 5. Mount static files using the absolute path string
app.mount(
    "/uploaded_images",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="uploaded_images"
)

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

    model_name = tasks.get_active_model_name()

    # insert the task record into the dabase
    db_task_record = repo.create_inference_task(db, image_guid, model_name=model_name)

    # TODO - if failed to insert, throw

    # call background task to process image
    task = tasks.process_sample_image.delay(db_task_record.task_identifier, db_task_record.id)

    # update status to PENDING
    db_task_update = repo.update_inference_task(db, db_task_record.id, "PENDING", model_name=model_name)

    # TODO - if task failed to start, record to db

    return {
        "task_guid": db_task_update.guid,
        "task_identifier": db_task_update.task_identifier,
        "status": db_task_update.task_status,
        "model_name": db_task_update.model_name
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
        "model_name": inference_task.model_name,
        "result": inference_task.result,
        "detections": formatted_detections
    }

@app.get("/images")
def get_images(db: Session = Depends(get_db)): # TODO paginate and filter
    db_result: List[InferenceImage] | None = repo.get_inference_images(db)
    return db_result

@app.get("/images/{image_guid}/tasks")
async def get_tasks_for_image(image_guid: str, db: Session = Depends(get_db)):
    # Query database for image by guid
    image = db.query(InferenceImage).filter(InferenceImage.guid == image_guid).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Fetch associated tasks
    tasks = db.query(InferenceTask).filter(InferenceTask.image_id == image.id).all()
    
    # Return list of tasks with guid, detection count, and status
    task_list = [
        {
            "guid": task.guid,
            "detection_count": len(task.detections),
            "task_status": task.task_status,
            "model_name": task.model_name
        }
        for task in tasks
    ]
    
    return {
        "tasks": task_list
    }

@app.get("/tasks/{task_guid}/rendered-image")
def get_rendered_image(task_guid: str, db: Session = Depends(get_db)):
    # 1. Retrieve the task and its related image/detections using your repository
    task = repo.get_task_by_guid(db, task_guid)
    if not task or not task.image:
        raise HTTPException(status_code=404, detail="Task or image not found")
    
    # 2. Resolve the full absolute path to the image on disk
    image_path = BASE_DIR / task.image.filepath
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    # 3. Read the image using OpenCV
    img = cv2.imread(str(image_path))
    if img is None:
        raise HTTPException(status_code=500, detail="Failed to decode image")

    # 4. Loop through each detection and draw the bounding box & confidence label
    for det in task.detections:
        pt1 = (int(det.x_min), int(det.y_min))
        pt2 = (int(det.x_max), int(det.y_max))
        
        # Draw red rectangle (OpenCV uses BGR: Blue=0, Green=0, Red=255)
        cv2.rectangle(img, pt1, pt2, (0, 0, 255), 2)
        
        # Format and draw the confidence label above the box
        label = f"{det.confidence * 100:.1f}%"
        text_pos = (pt1[0], max(pt1[1] - 8, 15))
        cv2.putText(img, label, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

    # 5. Encode the processed image back into bytes (JPEG format)
    success, encoded_image = cv2.imencode('.jpg', img)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to encode processed image")

    # 6. Return the image directly as an HTTP response
    return Response(content=encoded_image.tobytes(), media_type="image/jpeg")