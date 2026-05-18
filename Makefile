COMPOSE_FILE = docker/docker-compose.yml
COMPOSE_GPU = -f docker/docker-compose.yml -f docker/docker-compose.cuda.yml

.PHONY: dev dev-cuda build up down logs clean

# Development (CPU)
dev:
	docker compose -f $(COMPOSE_FILE) up --build -d
	@echo "Frontend: http://localhost:3001"
	@echo "Backend:  http://localhost:8000"
	@echo "Flower:   http://localhost:5555"

# Development (GPU)
dev-cuda:
	docker compose $(COMPOSE_GPU) up --build -d

# Build images
build:
	docker compose -f $(COMPOSE_FILE) build

# Start services
up:
	docker compose -f $(COMPOSE_FILE) up -d

# Stop services
down:
	docker compose -f $(COMPOSE_FILE) down

# View logs
logs:
	docker compose -f $(COMPOSE_FILE) logs -f

# Clean all data
clean:
	docker compose -f $(COMPOSE_FILE) down -v
	rm -rf backend/data
	@echo "All data removed"

# Backend development (without Docker)
backend-dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Celery worker (without Docker)
worker-dev:
	cd backend && celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1

# Frontend development (without Docker)
frontend-dev:
	cd frontend && npm run dev

# Install backend dependencies
backend-install:
	cd backend && pip install -r requirements.txt

# Install frontend dependencies
frontend-install:
	cd frontend && npm install
