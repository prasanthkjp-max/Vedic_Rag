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

# Build the AGPL "corresponding source" tarball served by GET /api/source. The
# image has no .git/git (stripped by .dockerignore), so bake it at build time.
# The build context already excludes secrets (.env/.api_key) and .git; we also
# drop runtime data, the corpus DBs, the books, caches and the archive itself.
RUN tar -czf /app/source.tar.gz \
      --exclude=./source.tar.gz \
      --exclude=./.git --exclude=./.env --exclude=./.api_key \
      --exclude=./node_modules --exclude=./.venv --exclude=./android \
      --exclude=./data --exclude=./books \
      --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' --exclude='*.bak' \
      --exclude='*.log' \
      --exclude=./__pycache__ --exclude='*.pyc' \
      . ; rc=$? ; if [ $rc -gt 1 ] ; then exit $rc ; fi ; echo "source.tar.gz: $(du -h /app/source.tar.gz | cut -f1)"

# Expose the port uvicorn runs on
EXPOSE 8008

# Define healthcheck to verify the app process is up and serving. Uses /api/live
# (pure process liveness) NOT /api/health, so a transiently-down dependency
# (OpenRouter/DB) doesn't mark the container unhealthy and trigger a restart while
# it can still serve charts/panchangam/PDF.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8008/api/live || exit 1

# Start the application using app.py (which runs uvicorn under the hood)
CMD ["python", "app.py"]
