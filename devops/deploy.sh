#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "=========================================="
echo " Deploying OpenSource Assist on EC2"
echo " Location: $APP_DIR"
echo "=========================================="

# 1. Ensure .env file exists
if [ ! -f .env ]; then
    echo "Warning: .env not found. Creating from .env.example..."
    cp .env.example .env
    echo "Please update .env with your production secrets (JWT_SECRET_KEY, GEMINI_API_KEY, GITHUB_TOKEN, etc.)."
fi

# 2. Pull latest git changes if inside a git repository
if [ -d .git ]; then
    echo "[1/4] Pulling latest updates from git..."
    git pull origin main || git pull origin master || echo "Git pull skipped or on custom branch."
else
    echo "[1/4] Not a git clone or git repo, skipping git pull."
fi

# 3. Build Docker images
echo "[2/4] Building production container images..."
docker compose -f docker-compose.prod.yml build

# 4. Start all services in detached mode
echo "[3/4] Starting services (PostgreSQL, Qdrant, FastAPI backend, React/Nginx frontend)..."
docker compose -f docker-compose.prod.yml up -d --remove-orphans

# 5. Verify status and health
echo "[4/4] Checking running containers..."
docker compose -f docker-compose.prod.yml ps

echo "=========================================="
echo " Deployment successful!"
echo " Web app is accessible at: http://$(curl -s ifconfig.me || echo '<EC2_PUBLIC_IP>')"
echo " API Docs accessible at:    http://$(curl -s ifconfig.me || echo '<EC2_PUBLIC_IP>')/docs"
echo "=========================================="
