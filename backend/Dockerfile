FROM python:3.12-slim

# Prevent Python from writing pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies needed for native extensions & database drivers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager for fast, deterministic installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency specifications
COPY pyproject.toml uv.lock ./

# Install project dependencies
RUN uv pip install --system --no-cache -r pyproject.toml greenlet

# Copy application source code and migrations
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY backend/ ./backend/
COPY data/ ./data/

# Create entrypoint script to run migrations before server start
RUN echo '#!/bin/sh\n\
set -e\n\
echo "Applying database migrations..."\n\
alembic upgrade head\n\
echo "Starting FastAPI server..."\n\
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
