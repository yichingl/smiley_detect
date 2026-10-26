from contextlib import asynccontextmanager
import hashlib
import json
import threading
from typing import List
from urllib.parse import quote

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
VALIDATION_IMAGE_DIR = BASE_DIR / "dataset" / "images" / "val"
VALIDATION_LABEL_DIR = BASE_DIR / "dataset" / "labels" / "val"
VALIDATION_CACHE_DIR = BASE_DIR / "data" / "validation_rendered"
VALIDATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
VALIDATION_CACHE_LOCK = threading.Lock()

# 4. Ensure the directory physically exists
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 5. Mount static files using the absolute path string
app.mount(
    "/uploaded_images",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="uploaded_images"
)

app.mount(
    "/validation-cache",
    StaticFiles(directory=str(VALIDATION_CACHE_DIR)),
    name="validation_cache"
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


@app.get("/validation-images")
def get_validation_images(refresh: bool = False):
    if not VALIDATION_IMAGE_DIR.is_dir():
        raise HTTPException(status_code=500, detail="Validation image directory not found")

    image_paths = sorted(
        (
            path for path in VALIDATION_IMAGE_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ),
        key=lambda path: path.name.casefold()
    )
    if not image_paths:
        return {"source": "ground_truth_labels", "images": []}

    signature_data = {
        "source": "ground_truth_labels_v1",
        "images": [
            {
                "name": path.name,
                "size": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "label_size": (
                    (VALIDATION_LABEL_DIR / f"{path.stem}.txt").stat().st_size
                    if (VALIDATION_LABEL_DIR / f"{path.stem}.txt").is_file()
                    else None
                ),
                "label_mtime_ns": (
                    (VALIDATION_LABEL_DIR / f"{path.stem}.txt").stat().st_mtime_ns
                    if (VALIDATION_LABEL_DIR / f"{path.stem}.txt").is_file()
                    else None
                )
            }
            for path in image_paths
        ]
    }
    signature = hashlib.sha256(
        json.dumps(signature_data, sort_keys=True).encode("utf-8")
    ).hexdigest()
    manifest_path = VALIDATION_CACHE_DIR / "manifest.json"

    with VALIDATION_CACHE_LOCK:
        if manifest_path.is_file() and not refresh:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached_images = manifest.get("images", [])
            if (
                manifest.get("signature") == signature
                and all((VALIDATION_CACHE_DIR / image["filename"]).is_file() for image in cached_images)
            ):
                return {
                    "source": "ground_truth_labels",
                    "images": cached_images
                }

        cache_version = uuid4().hex
        rendered_images = []
        for index, image_path in enumerate(image_paths):
            image = cv2.imread(str(image_path))
            if image is None:
                raise HTTPException(status_code=500, detail=f"Failed to decode validation image: {image_path.name}")

            image_height, image_width = image.shape[:2]
            label_path = VALIDATION_LABEL_DIR / f"{image_path.stem}.txt"
            detection_count = 0
            if label_path.is_file():
                try:
                    label_lines = label_path.read_text(encoding="utf-8").splitlines()
                except OSError as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to read validation label file: {label_path.name}"
                    ) from exc

                for line_number, line in enumerate(label_lines, start=1):
                    if not line.strip():
                        continue
                    fields = line.split()
                    if len(fields) != 5:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Invalid YOLO label format in {label_path.name}:{line_number}"
                        )

                    try:
                        class_value = float(fields[0])
                        center_x, center_y, box_width, box_height = map(float, fields[1:])
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Non-numeric YOLO label in {label_path.name}:{line_number}"
                        ) from exc

                    if (
                        not class_value.is_integer()
                        or class_value < 0
                        or not all(0 <= value <= 1 for value in (center_x, center_y, box_width, box_height))
                    ):
                        raise HTTPException(
                            status_code=500,
                            detail=f"Out-of-range YOLO label in {label_path.name}:{line_number}"
                        )

                    class_id = int(class_value)
                    x_min = max(0, round((center_x - box_width / 2) * image_width))
                    y_min = max(0, round((center_y - box_height / 2) * image_height))
                    x_max = min(image_width - 1, round((center_x + box_width / 2) * image_width))
                    y_max = min(image_height - 1, round((center_y + box_height / 2) * image_height))
                    cv2.rectangle(image, (x_min, y_min), (x_max, y_max), (0, 0, 255), 2)
                    label = f"Class {class_id}"
                    text_pos = (x_min, max(y_min - 8, 15))
                    cv2.putText(image, label, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    detection_count += 1

            filename = f"{index:04d}-{image_path.stem}.jpg"
            success, encoded_image = cv2.imencode(".jpg", image)
            if not success:
                raise HTTPException(status_code=500, detail=f"Failed to encode validation image: {image_path.name}")

            (VALIDATION_CACHE_DIR / filename).write_bytes(encoded_image.tobytes())
            rendered_images.append({
                "name": image_path.name,
                "filename": filename,
                "image_url": f"/validation-cache/{quote(filename)}?v={cache_version}",
                "detection_count": detection_count
            })

        current_filenames = {image["filename"] for image in rendered_images}
        for cached_file in VALIDATION_CACHE_DIR.glob("*.jpg"):
            if cached_file.name not in current_filenames:
                cached_file.unlink()

        manifest = {
            "signature": signature,
            "images": rendered_images
        }
        temporary_manifest = VALIDATION_CACHE_DIR / "manifest.tmp"
        temporary_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        temporary_manifest.replace(manifest_path)

        return {
            "source": "ground_truth_labels",
            "images": rendered_images
        }