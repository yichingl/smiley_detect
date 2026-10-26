import os
import time
from pathlib import Path

from ultralytics import YOLO

from app.celery_app import celery_app
from app.database import SessionLocal
import app.repositories as repo
from app.models import DetectionResult, InferenceImage, InferenceTask

CONFIDENCE_THRESHOLD = 0.75


def get_active_model_name() -> str:
    """Return the newest trained YOLO model name if one exists; otherwise fall back to the base model."""
    project_root = Path(__file__).resolve().parent.parent
    model_dir = project_root / "saved_models"
    candidate_paths = sorted(model_dir.glob("*/weights/best.pt"), key=lambda p: p.stat().st_mtime, reverse=True)

    if candidate_paths:
        return candidate_paths[0].parent.parent.name

    return "yolov8n.pt"


def get_active_model_path() -> str:
    """Return the path to the newest trained YOLO weights if one exists; otherwise use the base model."""
    project_root = Path(__file__).resolve().parent.parent
    model_dir = project_root / "saved_models"
    candidate_paths = sorted(model_dir.glob("*/weights/best.pt"), key=lambda p: p.stat().st_mtime, reverse=True)

    if candidate_paths:
        return str(candidate_paths[0])

    return "yolov8n.pt"


def get_model_path(model_name: str) -> Path | None:
    """Resolve a saved model run to its best checkpoint without accepting paths."""
    if not model_name or Path(model_name).name != model_name or model_name in {".", ".."}:
        return None

    project_root = Path(__file__).resolve().parent.parent
    model_path = project_root / "saved_models" / model_name / "weights" / "best.pt"
    return model_path if model_path.is_file() else None


MODEL_NAME = get_active_model_name()
MODEL_PATH = get_active_model_path()


def run_localization_inference(image_path: str, model_path: str | None = None) -> list[dict]:
    """
    Runs YOLO inference on the image to find smiley bounding boxes.
    Returns a list of dicts containing coordinates and confidence scores.
    """
    model_to_use = model_path or MODEL_PATH

    if not os.path.exists(model_to_use) and model_to_use != "yolov8n.pt":
        return [{"error": f"Model at {model_to_use} not found."}]

    model = YOLO(model_to_use)
    results = model(image_path, conf=CONFIDENCE_THRESHOLD, verbose=False)

    detections = []
    for r in results:
        boxes = r.boxes
        for box in boxes:
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
def process_sample_image(task_identifier: str, task_id: int, model_name: str):
    """Simulate a long-running image classification or processing task."""

    db = SessionLocal()
    model_path = get_model_path(model_name)
    if model_path is None:
        repo.update_inference_task(db, task_id, "FAILURE", model_name=model_name)
        db.close()
        return {"error": f"Model run '{model_name}' was not found or has no best checkpoint."}

    inference_image = repo.get_inference_image_by_task_id(db, task_id)
    if inference_image is None:
        db.close()
        raise RuntimeError(
            f"Task {task_id} has no associated image in this worker's database. "
            "The API and worker must use the same DATABASE_URL and REDIS_URL."
        )

    time.sleep(6)
    print("Starting Processing")
    task_update: InferenceTask | None = repo.update_inference_task(
        db,
        task_id,
        "PROCESSING",
        model_name=model_name
    )

    time.sleep(6)
    image_path = inference_image.filepath
    detected_locations = run_localization_inference(image_path, str(model_path))

    print("Detections...")
    for detection in detected_locations:
        if isinstance(detection, dict) and "error" in detection:
            print(detection)
            continue
        print(detection)

    for box in detected_locations:
        if isinstance(box, dict) and "error" in box:
            continue
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

    print("Processed")
    time.sleep(6)

    try:
        task_update = repo.update_inference_task(db, task_id, "SUCCESS", model_name=model_name)
    except Exception:
        task_update = repo.update_inference_task(db, task_id, "FAILURE", model_name=model_name)

    print(f"Completed {task_update.task_status}")

    if not task_update:
        return {"error": f"Task ID {task_identifier} not found in database."}

    db.refresh(task_update)
    result = {
        "status": task_update.task_status,
        "task_identifier": task_update.task_identifier,
        "model_name": task_update.model_name
    }
    db.close()
    return result
