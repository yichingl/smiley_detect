from contextlib import asynccontextmanager
import csv
import hashlib
import json
import shutil
import threading
from typing import List, Literal
from urllib.parse import quote

from uuid import uuid4
import cv2
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, Depends
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from app.database import get_db, init_db
from app.models import InferenceImage, InferenceTask, SavedStatus
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
TRAINING_IMAGE_DIR = BASE_DIR / "dataset" / "images" / "train"
TRAINING_LABEL_DIR = BASE_DIR / "dataset" / "labels" / "train"
TRAINING_CACHE_DIR = BASE_DIR / "data" / "training_rendered"
SAVED_MODELS_DIR = BASE_DIR / "saved_models"
VALIDATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TRAINING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
VALIDATION_CACHE_LOCK = threading.Lock()


class ProcessImageRequest(BaseModel):
    model_name: str


class AddTaskToDatasetRequest(BaseModel):
    split: Literal["train", "val"]


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

app.mount(
    "/training-cache",
    StaticFiles(directory=str(TRAINING_CACHE_DIR)),
    name="training_cache"
)


@app.middleware("http")
async def cache_rendered_images(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/validation-cache/", "/training-cache/")):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


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
def trigger_image_processing(
    image_guid: str,
    request: ProcessImageRequest,
    db: Session = Depends(get_db)
):
    model_name = request.model_name
    if tasks.get_model_path(model_name) is None:
        raise HTTPException(status_code=404, detail=f"Model run '{model_name}' not found or has no best checkpoint")

    # insert the task record into the dabase
    db_task_record = repo.create_inference_task(db, image_guid, model_name=model_name)

    # TODO - if failed to insert, throw

    # call background task to process image
    tasks.process_sample_image.delay(db_task_record.task_identifier, db_task_record.id, model_name)

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
        "saved": inference_task.saved,
        "result": inference_task.result,
        "detections": formatted_detections
    }


@app.post("/tasks/{task_guid}/add-to-dataset")
def add_task_to_dataset(
    task_guid: str,
    request: AddTaskToDatasetRequest,
    db: Session = Depends(get_db)
):
    task = repo.get_task_by_guid(db, task_guid)
    if not task or not task.image:
        raise HTTPException(status_code=404, detail="Task or source image not found")
    if task.task_status != "SUCCESS":
        raise HTTPException(status_code=409, detail="Only successfully completed tasks can be added to a dataset")
    if task.saved != SavedStatus.UNSAVED.value:
        raise HTTPException(status_code=409, detail="Task has already been saved to a dataset")

    source_path = (BASE_DIR / task.image.filepath).resolve()
    upload_dir = UPLOAD_DIR.resolve()
    if not source_path.is_relative_to(upload_dir) or not source_path.is_file():
        raise HTTPException(status_code=404, detail="Source image file not found in uploads")

    image = cv2.imread(str(source_path))
    if image is None:
        raise HTTPException(status_code=500, detail="Failed to decode source image")
    image_height, image_width = image.shape[:2]

    split_dirs = {
        "train": (TRAINING_IMAGE_DIR, TRAINING_LABEL_DIR),
        "val": (VALIDATION_IMAGE_DIR, VALIDATION_LABEL_DIR)
    }
    image_dir, label_dir = split_dirs[request.split]
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"{request.split} dataset directories not found")

    extension = source_path.suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail="Source image format is not supported for training")

    filename = f"inference_{uuid4().hex}{extension}"
    destination_image = image_dir / filename
    destination_label = label_dir / f"{Path(filename).stem}.txt"
    temporary_image = destination_image.with_name(f".{destination_image.name}.tmp")
    temporary_label = destination_label.with_name(f".{destination_label.name}.tmp")

    label_lines = []
    for detection in task.detections:
        x_min = max(0, min(image_width, detection.x_min))
        y_min = max(0, min(image_height, detection.y_min))
        x_max = max(0, min(image_width, detection.x_max))
        y_max = max(0, min(image_height, detection.y_max))
        if x_max <= x_min or y_max <= y_min:
            continue

        x_center = ((x_min + x_max) / 2) / image_width
        y_center = ((y_min + y_max) / 2) / image_height
        box_width = (x_max - x_min) / image_width
        box_height = (y_max - y_min) / image_height
        label_lines.append(f"0 {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}")

    try:
        shutil.copyfile(source_path, temporary_image)
        temporary_label.write_text(
            "\n".join(label_lines) + ("\n" if label_lines else ""),
            encoding="utf-8"
        )
        temporary_image.replace(destination_image)
        temporary_label.replace(destination_label)
    except OSError as exc:
        temporary_image.unlink(missing_ok=True)
        temporary_label.unlink(missing_ok=True)
        destination_image.unlink(missing_ok=True)
        destination_label.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to save image and labels to the dataset") from exc

    task.saved = SavedStatus.TRAINING.value if request.split == "train" else SavedStatus.VALIDATION.value
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        destination_image.unlink(missing_ok=True)
        destination_label.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to update task saved status") from exc

    return {
        "split": request.split,
        "image": filename,
        "label": destination_label.name,
        "detection_count": len(label_lines),
        "saved": task.saved
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
            "model_name": task.model_name,
            "saved": task.saved
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
    return _get_dataset_images(
        split="validation",
        image_dir=VALIDATION_IMAGE_DIR,
        label_dir=VALIDATION_LABEL_DIR,
        cache_dir=VALIDATION_CACHE_DIR,
        cache_url_prefix="/validation-cache",
        refresh=refresh
    )


@app.get("/training-images")
def get_training_images(refresh: bool = False):
    return _get_dataset_images(
        split="training",
        image_dir=TRAINING_IMAGE_DIR,
        label_dir=TRAINING_LABEL_DIR,
        cache_dir=TRAINING_CACHE_DIR,
        cache_url_prefix="/training-cache",
        refresh=refresh
    )


@app.get("/models")
def get_model_runs():
    if not SAVED_MODELS_DIR.is_dir():
        return {"runs": []}

    metric_columns = {
        "train_box_loss": "train/box_loss",
        "val_box_loss": "val/box_loss",
        "precision": "metrics/precision(B)",
        "recall": "metrics/recall(B)",
        "map50": "metrics/mAP50(B)",
        "map50_95": "metrics/mAP50-95(B)"
    }
    runs = []
    run_dirs = [path for path in SAVED_MODELS_DIR.iterdir() if path.is_dir()]
    run_dirs.sort(
        key=lambda path: (
            -((path / "weights" / "best.pt").stat().st_mtime if (path / "weights" / "best.pt").is_file() else 0),
            path.name.casefold()
        )
    )
    for run_dir in run_dirs:
        note_path = run_dir / "note.txt"
        try:
            note = note_path.read_text(encoding="utf-8").strip() if note_path.is_file() else None
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read note for model run: {run_dir.name}") from exc

        epochs = []
        results_path = run_dir / "results.csv"
        if results_path.is_file():
            try:
                with results_path.open("r", encoding="utf-8", newline="") as results_file:
                    reader = csv.DictReader(results_file)
                    missing_columns = set(metric_columns.values()) - set(reader.fieldnames or [])
                    if missing_columns:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Missing metrics in {run_dir.name}/results.csv: {', '.join(sorted(missing_columns))}"
                        )

                    for row_number, row in enumerate(reader, start=2):
                        try:
                            epoch = int(row["epoch"])
                            values = {
                                key: float(row[column])
                                for key, column in metric_columns.items()
                            }
                        except (KeyError, TypeError, ValueError) as exc:
                            raise HTTPException(
                                status_code=500,
                                detail=f"Invalid metric value in {run_dir.name}/results.csv:{row_number}"
                            ) from exc
                        epochs.append({"epoch": epoch, **values})
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"Failed to read results for model run: {run_dir.name}") from exc

        best_epoch = max(
            epochs,
            key=lambda epoch: 0.1 * epoch["map50"] + 0.9 * epoch["map50_95"],
            default=None
        )
        runs.append({
            "name": run_dir.name,
            "note": note or None,
            "available": (run_dir / "weights" / "best.pt").is_file(),
            "best_epoch": best_epoch["epoch"] if best_epoch else None,
            "epochs": epochs
        })

    return {"runs": runs}


def _get_dataset_images(
    split: str,
    image_dir: Path,
    label_dir: Path,
    cache_dir: Path,
    cache_url_prefix: str,
    refresh: bool
):
    if not image_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"{split.capitalize()} image directory not found")

    image_paths = sorted(
        (
            path for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ),
        key=lambda path: path.name.casefold()
    )
    if not image_paths:
        return {"source": "ground_truth_labels", "images": []}

    signature_data = {
        "source": f"ground_truth_labels_v1:{split}",
        "images": [
            {
                "name": path.name,
                "size": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "label_size": (
                    (label_dir / f"{path.stem}.txt").stat().st_size
                    if (label_dir / f"{path.stem}.txt").is_file()
                    else None
                ),
                "label_mtime_ns": (
                    (label_dir / f"{path.stem}.txt").stat().st_mtime_ns
                    if (label_dir / f"{path.stem}.txt").is_file()
                    else None
                )
            }
            for path in image_paths
        ]
    }
    signature = hashlib.sha256(
        json.dumps(signature_data, sort_keys=True).encode("utf-8")
    ).hexdigest()
    manifest_path = cache_dir / "manifest.json"

    with VALIDATION_CACHE_LOCK:
        if manifest_path.is_file() and not refresh:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached_images = manifest.get("images", [])
            if (
                manifest.get("signature") == signature
                and all((cache_dir / image["filename"]).is_file() for image in cached_images)
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
                raise HTTPException(status_code=500, detail=f"Failed to decode {split} image: {image_path.name}")

            image_height, image_width = image.shape[:2]
            label_path = label_dir / f"{image_path.stem}.txt"
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
                raise HTTPException(status_code=500, detail=f"Failed to encode {split} image: {image_path.name}")

            (cache_dir / filename).write_bytes(encoded_image.tobytes())
            rendered_images.append({
                "name": image_path.name,
                "filename": filename,
                "image_url": f"{cache_url_prefix}/{quote(filename)}?v={cache_version}",
                "detection_count": detection_count
            })

        current_filenames = {image["filename"] for image in rendered_images}
        for cached_file in cache_dir.glob("*.jpg"):
            if cached_file.name not in current_filenames:
                cached_file.unlink()

        manifest = {
            "signature": signature,
            "images": rendered_images
        }
        temporary_manifest = cache_dir / "manifest.tmp"
        temporary_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        temporary_manifest.replace(manifest_path)

        return {
            "source": "ground_truth_labels",
            "images": rendered_images
        }