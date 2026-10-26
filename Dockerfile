# 1. Base Image: Start with an official lightweight Python runtime
FROM python:3.11-slim

# 2. Working Directory: Set the default directory inside the container
WORKDIR /app

# 3. Environment Variables: Optimize Python behavior for containers
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 4. System Dependencies: Install build tools and OpenCV runtime libraries
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 5. Dependencies: Copy requirements first to leverage Docker's caching layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Project Code: Copy the rest of your application code into the container
COPY . .

# 7. Default Command: Define what runs when the container starts (FastAPI by default)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]