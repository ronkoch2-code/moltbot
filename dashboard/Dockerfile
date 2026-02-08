# =============================================================================
# Moltbot Heartbeat Dashboard — Multi-stage Docker Build
# =============================================================================
# Stage 1: Build React webapp (Node.js)
# Stage 2: Bundle webapp + FastAPI backend (Python)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build React Frontend
# -----------------------------------------------------------------------------
FROM node:22-alpine AS webapp-builder

WORKDIR /build

# Install dependencies (cached layer)
COPY dashboard/webapp/package.json dashboard/webapp/package-lock.json ./
RUN npm ci

# Build webapp
COPY dashboard/webapp/ ./
RUN npm run build

# Output: /build/dist/ contains static HTML/JS/CSS bundle

# -----------------------------------------------------------------------------
# Stage 2: Python Backend + Static Files
# -----------------------------------------------------------------------------
FROM python:3.12-slim

# Create non-root user
RUN groupadd -r dashboard && useradd -r -g dashboard dashboard

WORKDIR /app

# Install Python dependencies
COPY dashboard/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Copy backend API code
COPY dashboard/api/ /app/dashboard/api/

# Copy built webapp from stage 1
COPY --from=webapp-builder /build/dist/ /app/dashboard/webapp/dist/

# Create data directory for SQLite database
RUN mkdir -p /app/data && chown -R dashboard:dashboard /app/data

# Expose FastAPI port
EXPOSE 8081

# Switch to non-root user
USER dashboard

# Run FastAPI with Uvicorn
CMD ["python", "-m", "uvicorn", "dashboard.api.main:app", "--host", "0.0.0.0", "--port", "8081"]
