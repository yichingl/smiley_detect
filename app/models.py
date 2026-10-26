from enum import IntEnum

from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
import datetime

from sqlalchemy.orm import relationship

Base = declarative_base()


class SavedStatus(IntEnum):
    UNSAVED = 0
    TRAINING = 1
    VALIDATION = 2


class InferenceImage(Base):
    __tablename__ = "inference_images"
    id = Column(Integer, primary_key=True, index=True)
    guid = Column(String, index=True) #guid
    name = Column(String)
    filepath = Column(String)
    upload_group_id = Column(String) #guid
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)
    tasks = relationship("InferenceTask", back_populates="image", cascade="all, delete")

class InferenceTask(Base):
    __tablename__ = "inference_tasks"
    __table_args__ = (
        CheckConstraint("saved IN (0, 1, 2)", name="ck_inference_tasks_saved"),
    )
    id = Column(Integer, primary_key=True, index=True)
    guid = Column(String, index=True) #guid
    image_id = Column(Integer, ForeignKey("inference_images.id"), nullable = False)
    task_identifier = Column(String, index=True, nullable=True) # this is the celery task id
    task_init_at = Column(DateTime, nullable=True)
    task_last_updated_at = Column(DateTime, nullable=True)
    task_status = Column(String, default="PENDING") # TODO - define types for security here
    model_name = Column(String, nullable=True)
    saved = Column(Integer, nullable=False, default=SavedStatus.UNSAVED.value, server_default="0")
    result = Column(Text, nullable=True)  # TODO - turn this into Detections table
    image = relationship("InferenceImage", back_populates="tasks")# Relationship to bounding box detections
    detections = relationship("DetectionResult", back_populates="task", cascade="all, delete-orphan")

class DetectionResult(Base):
    __tablename__ = "detection_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("inference_tasks.id"), nullable=False)
    
    # Bounding box coordinates and confidence
    confidence = Column(Float, nullable=False)
    x_min = Column(Integer, nullable=False)
    y_min = Column(Integer, nullable=False)
    x_max = Column(Integer, nullable=False)
    y_max = Column(Integer, nullable=False)

    task = relationship("InferenceTask", back_populates="detections")