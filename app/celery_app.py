import os

from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery with Redis as both the broker and result backend
celery_app = Celery(
    "smiles_worker", # name of celery app
    broker=redis_url, # point celery to redis message broker
    backend=redis_url, # background task will save values here so API can check here later
    include=["app.tasks"]
)
# Force this instance to be the current active app in the process context
celery_app.set_current()

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)