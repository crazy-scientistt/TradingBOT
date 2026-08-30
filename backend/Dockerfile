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

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml ./
# Hatchling needs the package source present while resolving the local project.
COPY backend/goldguard ./backend/goldguard
RUN pip install --no-cache-dir .

# Application code
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY app.py main.py ./

# Frontend build artifact
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create writable data directories for SQLite
RUN mkdir -p /data /app/data && chmod 777 /data /app/data

# Non-root user
RUN useradd -r -u 1000 goldguard && \
    chown -R goldguard:goldguard /app /data /app/data
USER goldguard

ENV GOLDGUARD_DATA_DIR=/data
ENV PYTHONPATH=/app/backend:/app
ARG UI_REVISION=dev
ENV GOLDGUARD_UI_REVISION=$UI_REVISION
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health/live || exit 1

CMD ["python", "main.py"]
