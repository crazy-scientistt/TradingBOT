# Stage 1: Build frontend assets
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime with frontend dist
FROM python:3.12-slim AS runtime
WORKDIR /app

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Application code
COPY backend/ ./backend/
COPY scripts/ ./scripts/

# Frontend dist from build stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create data directory
RUN mkdir -p /data && chown 1000:1000 /data
VOLUME /data

# Non-root user
RUN useradd -r -u 1000 goldguard
USER goldguard

ENV GOLDGUARD_DATA_DIR=/data
ENV PYTHONPATH=/app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

CMD ["python", "-m", "uvicorn", "goldguard.web.app:app", \
     "--host", "0.0.0.0", "--port", "8000"]
