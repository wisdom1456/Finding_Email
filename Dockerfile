# Use official Python 3.11 slim base image for better performance and security
FROM python:3.11-slim

# Set build argument for environment
ARG ENVIRONMENT=production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=${ENVIRONMENT} \
    PORT=8080

# Create non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser

# Set the working directory
WORKDIR /app

# Install system dependencies and cleanup in single layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        curl \
        libmagic-dev \
        && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file first for better caching
COPY requirements.txt .

# Install Python dependencies with optimizations
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/temp && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check for Google Cloud Run
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:$PORT/_stcore/health || exit 1

# Expose port (Google Cloud Run expects PORT env var)
EXPOSE $PORT

# Run the Streamlit application with production optimizations
CMD streamlit run app/main.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.runOnSave=false \
    --server.allowRunOnSave=false \
    --server.fileWatcherType=none \
    --browser.gatherUsageStats=false \
    --global.developmentMode=false