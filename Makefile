SHELL := powershell.exe

.PHONY: venv install run worker db-refresh redis-local dev docker-up docker-down clean train train-yolo

venv:
	py -3.11 -m venv venv
	@echo "Virtual environment created with Python 3.11."

install: venv
	.\venv\Scripts\pip install --upgrade pip
	.\venv\Scripts\pip install --only-binary=:all: -r requirements.txt

run:
	.\venv\Scripts\uvicorn app.main:app

worker:
	.\venv\Scripts\celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo

# Rebuild the database from scratch (drops all tables and recreates them)
db-refresh:
	@echo "Rebuilding database..."
	@.\venv\Scripts\python -c "from app.database import engine; from app.models import Base; Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)"
	@echo "Database rebuilt successfully!"

# Spins up a lightweight standalone Redis container for local dev
redis-local:
	-docker run -d --name smiley-redis -p 6379:6379 redis:latest
	-docker start smiley-redis

# Local multi-process development with local Redis broker
dev: redis-local
	Start-Process powershell -ArgumentList "-NoExit", "-Command", "make run"
	Start-Process powershell -ArgumentList "-NoExit", "-Command", "make worker"

# Containerized stack orchestration using Docker Compose
docker-down:
	docker compose down
docker-up:
	docker compose up --build

clean:
	rm -rf __pycache__
	rm -rf venv
	-docker stop smiley-redis
	-docker rm smiley-redis

# Model training
# Train the proof-of-concept model using local directories
train:
	.\venv\Scripts\python -m app.training.train_model \
		--positive-dir training_images/positive \
		--negative-dir training_images/negative \
		--output-path saved_models/smiley_v1.pkl

train-yolo:
	.\venv\Scripts\python -m app.training.train_yolo --epochs 25