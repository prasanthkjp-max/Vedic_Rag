# Use python 3.12 slim as base image (matches host Python version 3.12)
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
# - tesseract-ocr and language packs (eng, san) for Sanskrit and English OCR ingestion
# - build-essential for compiling native extensions (like uharfbuzz, ReportLab, and pyswisseph)
# - curl for container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-san \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Copy requirements file first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create directories for static files, database storage, and PDF books
RUN mkdir -p /app/static /app/data /app/books

# Copy the rest of the application files (filtered via .dockerignore)
COPY . .

# Expose the port uvicorn runs on
EXPOSE 8008

# Define healthcheck to verify backend availability
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8008/api/health || exit 1

# Start the application using app.py (which runs uvicorn under the hood)
CMD ["python", "app.py"]
