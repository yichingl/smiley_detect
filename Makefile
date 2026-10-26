SHELL := powershell.exe

.PHONY: venv install run worker db-refresh db-upgrade redis-local dev docker-up docker-down clean train train-yolo

API_HOST ?= 127.0.0.1
API_PORT ?= 8000

venv:
	py -3.11 -m venv venv
	@echo "Virtual environment created with Python 3.11."
	Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", ". .\venv\Scripts\Activate.ps1"

install: venv
	.\venv\Scripts\pip install --upgrade pip
	.\venv\Scripts\pip install --only-binary=:all: -r requirements.txt

run:
	.\venv\Scripts\uvicorn app.main:app --host $(API_HOST) --port $(API_PORT)

worker:
	.\venv\Scripts\celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo

# Rebuild the database from scratch (drops all tables and recreates them)
db-refresh:
	@echo "Rebuilding database..."
	@.\venv\Scripts\python -c "from app.database import engine; from app.models import Base; Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)"
	@echo "Database rebuilt successfully!"

# Safely add missing columns to an existing database without dropping data
db-upgrade:
	.\venv\Scripts\python -m app.migrations

# Use a separate Redis port so local and Docker workers never consume each other's tasks.
redis-local:
	@if (docker container ls -a --format "{{.Names}}" | Select-String -Quiet "^smiley-redis-local$$") { docker start smiley-redis-local } else { docker run -d --name smiley-redis-local -p 127.0.0.1:6380:6379 redis:latest }

# Local development runs on separate ports and a separate broker from Docker Compose.
dev: redis-local
	Start-Process powershell -ArgumentList "-NoExit", "-Command", "$$env:REDIS_URL='redis://localhost:6380/0'; make run API_HOST=127.0.0.1 API_PORT=8001"
	Start-Process powershell -ArgumentList "-NoExit", "-Command", "$$env:REDIS_URL='redis://localhost:6380/0'; make worker"
	Start-Process powershell -WorkingDirectory (Join-Path (Get-Location) 'frontend') -ArgumentList "-NoExit", "-Command", "$$env:API_PROXY_TARGET='http://localhost:8001'; npm run dev -- --host 127.0.0.1 --port 5174"

# Containerized stack orchestration using Docker Compose
docker-down:
	docker compose down
docker-up:
	docker compose up --build

clean:
	rm -rf __pycache__
	rm -rf venv
	-docker stop smiley-redis-local
	-docker rm smiley-redis-local

# Model training
# Train the proof-of-concept model using local directories
train:
	.\venv\Scripts\python -m app.training.train_model \
		--positive-dir training_images/positive \
		--negative-dir training_images/negative \
		--output-path saved_models/smiley_v1.pkl

train-yolo:
	.\venv\Scripts\python -m app.training.train_yolo --epochs 15