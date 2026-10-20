from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
import datetime

from sqlalchemy.orm import relationship

Base = declarative_base()

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
    id = Column(Integer, primary_key=True, index=True)
    guid = Column(String, index=True) #guid
    image_id = Column(Integer, ForeignKey("inference_images.id"), nullable = False)
    task_identifier = Column(String, index=True, nullable=True) # this is the celery task id
    task_init_at = Column(DateTime, nullable=True)
    task_last_updated_at = Column(DateTime, nullable=True)
    task_status = Column(String, default="PENDING") # TODO - define types for security here
    result = Column(Text, nullable=True)  # TODO - turn this into Detections table
    image = relationship("InferenceImage", back_populates="tasks")