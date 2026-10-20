from celery import Celery

# Initialize Celery with Redis as both the broker and result backend
celery_app = Celery(
    "smiles_worker", # name of celery app
    broker="redis://localhost:6379/0", # point celery to redis message broker
    backend="redis://localhost:6379/0", # background task will save values here so API can check here later
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
)