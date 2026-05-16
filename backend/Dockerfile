# syntax=docker/dockerfile:1.6
# Multi-stage build: compile the React dashboard, then drop its dist/ into
# the FastAPI runtime image. Single container, single port (8000) at runtime.
# Build context: repo root (see docker-compose.yml).

# ---------- Stage 1: frontend build ----------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund --loglevel=error
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: backend runtime ----------
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# Dashboard demo: run_005 experiment data (see backend/bundled-data/)
COPY backend/bundled-data /labmind-data
COPY --from=frontend /build/dist ./frontend_dist

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
