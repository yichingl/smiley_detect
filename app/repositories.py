import datetime
import os
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from app.models import InferenceImage, InferenceTask
from sqlalchemy import exists, select

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
UPLOAD_DIR = "uploaded_images"

# insert a new inference image
def create_bulk_inference_images(db: Session, files: List[UploadFile]) -> List[uuid4]:
    """Validates files, saves to disk, then inserts them into the database"""
    
    # validate inputs
    if not files:
        raise HTTPException(
            status_code=400, 
            detail="No files provided for upload.")

    for file in files:
        filename = file.filename.lower()
        ext = os.path.splitext(filename)[1]

        if file.content_type.lower() not in ALLOWED_CONTENT_TYPES or ext.lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file '{file.filename}'. Only JPG, JPEG, and PNG files are allowed.")

    upload_group_id = str(uuid4())
    image_records = []

    # save images
    for file in files:
        unique_file_id = str(uuid4())
        ext = os.path.splitext(file.filename)[1]
        saved_filename = f"{unique_file_id}{ext}"
        filepath = os.path.join(UPLOAD_DIR, saved_filename)

        contents = file.file.read()
        with open(filepath, "wb") as f:
            f.write(contents)

        record = InferenceImage(
            guid=str(uuid4()),
            name=file.filename,
            filepath=filepath,
            upload_group_id=upload_group_id
        )
        image_records.append(record)

    # save record data
    try:
        db.add_all(image_records)
        db.commit()
        for record in image_records:
            db.refresh(record)
        return image_records
    except Exception as exc:
        db.rollback()
        raise exc

# insert a new image task record as initialized
def create_inference_task(db: Session, image_guid: str) -> InferenceTask | None:

    # TODO - validate inputs
    
    # Check the existence of this image_guid and get the image id
    inference_image: InferenceImage | None = get_inference_image_by_guid(db, image_guid)
    if not inference_image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # explicitly generate a custom task ID to make the job idempotent
    task_guid = uuid4()
    task_identifier = f"img_{image_guid}_job_{task_guid}"

    try:
        new_task = InferenceTask(
            guid = str(task_guid), #type convert?
            image_id = inference_image.id,
            task_identifier = task_identifier,
            task_init_at = datetime.datetime.utcnow(),
            task_last_updated_at = datetime.datetime.utcnow(),
            task_status = "INITIALIZED",
            result = None
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        return new_task
    except Exception as exc:
        db.rollback()
        raise exc

# update the status of an existing task record
def update_inference_task(db: Session, task_id: int, status: str, result: str = None) -> InferenceTask | None :

    # TODO - validate task_id, status

    try:
        stmt = select(InferenceTask).where(InferenceTask.id == task_id)
        db_task: InferenceTask | None = db.execute(stmt).scalar_one_or_none()

        if not db_task:
            return None

        db_task.task_status = status
        db_task.result = result

        db.commit()
        db.refresh(db_task)

        return db_task

    except Exception as exc:
        db.rollback()
        raise exc

def get_inference_image_by_guid(db: Session, guid: str) -> InferenceImage | None:
    """ Get InferenceImage by guid, including tasks """
    stmt = (select(InferenceImage)
            .options(selectinload(InferenceImage.tasks))
            .where(InferenceImage.guid == guid))
    return db.scalar(stmt)

def get_inference_image_by_task_id(db: Session, task_id: int) -> InferenceImage | None:
    """ Gets the InferenceImage associated with a specific task """
    stmt = (
        select(InferenceImage)
        .join(InferenceTask, InferenceTask.image_id == InferenceImage.id)
        .where(InferenceTask.id == task_id)
    )
    return db.scalar(stmt)

# get all records TODO paginate and filter
def get_inference_images(db: Session):
    """ Get InferenceImages """
    return db.query(InferenceImage).all()

def get_task_by_id(db: Session, id: int) -> InferenceTask | None:
    """ Get InferenceTask by id """
    stmt = select(InferenceTask).where(InferenceTask.id == id)
    return db.scalar(stmt)

def get_task_by_guid(db: Session, guid: str) -> InferenceTask | None:
    """ Get InferenceTask by guid """
    stmt = select(InferenceTask).where(InferenceTask.guid == guid)
    return db.scalar(stmt)
