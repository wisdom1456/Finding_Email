#!/bin/bash

# Backend Build Script
# Legal Document Analysis Portal - Backend Production Build

set -e  # Exit on any error

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
BUILD_DIR="$BACKEND_DIR/dist"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

log "Starting Legal Document Analysis Portal - Backend Build"
log "Project Root: $PROJECT_ROOT"
log "Backend Directory: $BACKEND_DIR"
log "Build Directory: $BUILD_DIR"

# Check if we're in the right directory
if [ ! -d "$BACKEND_DIR" ]; then
    error "Backend directory not found at $BACKEND_DIR"
    exit 1
fi

# Navigate to backend directory
cd "$BACKEND_DIR"

# Clean previous build
if [ -d "$BUILD_DIR" ]; then
    log "Cleaning previous build..."
    rm -rf "$BUILD_DIR"
fi

# Create build directory
mkdir -p "$BUILD_DIR"

# Check for Python and virtual environment
if [ ! -d "venv" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
log "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install/update dependencies
if [ -f "requirements.txt" ]; then
    log "Installing production dependencies..."
    pip install -r requirements.txt
else
    log "Installing basic dependencies..."
    pip install fastapi uvicorn python-multipart openai pydantic python-dotenv
fi

# Copy application files to build directory
log "Copying application files..."
cp -r . "$BUILD_DIR/"

# Remove development-only files from build
log "Removing development files from build..."
rm -rf "$BUILD_DIR/venv"
rm -rf "$BUILD_DIR/__pycache__"
rm -rf "$BUILD_DIR"/**/__pycache__
rm -rf "$BUILD_DIR/.pytest_cache"
rm -rf "$BUILD_DIR/tests"
rm -rf "$BUILD_DIR/.env"
rm -rf "$BUILD_DIR/logs"
rm -f "$BUILD_DIR"/*.log

# Create production requirements.txt
log "Generating production requirements..."
pip freeze > "$BUILD_DIR/requirements.txt"

# Create production startup script
log "Creating production startup script..."
cat > "$BUILD_DIR/start.sh" << 'EOF'
#!/bin/bash
# Production startup script for FastAPI app

# Set production environment
export ENVIRONMENT=production
export FASTAPI_HOST=0.0.0.0
export FASTAPI_PORT=${PORT:-8000}

# Start FastAPI in production mode
uvicorn main:app \
    --host $FASTAPI_HOST \
    --port $FASTAPI_PORT \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --access-log \
    --log-level info \
    --no-use-colors
EOF

chmod +x "$BUILD_DIR/start.sh"

# Create Dockerfile for containerized deployment
log "Creating Dockerfile..."
cat > "$BUILD_DIR/Dockerfile" << 'EOF'
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start application
CMD ["./start.sh"]
EOF

# Create .dockerignore
log "Creating .dockerignore..."
cat > "$BUILD_DIR/.dockerignore" << 'EOF'
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.git/
.gitignore
README.md
.env
.DS_Store
*.log
logs/
tests/
.pytest_cache/
dist/
build/
*.egg-info/
EOF

# Create Railway configuration
log "Creating Railway configuration..."
cat > "$BUILD_DIR/railway.json" << 'EOF'
{
  "build": {
    "builder": "DOCKERFILE"
  },
  "deploy": {
    "startCommand": "./start.sh",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
EOF

# Create Heroku Procfile
log "Creating Heroku Procfile..."
cat > "$BUILD_DIR/Procfile" << 'EOF'
web: uvicorn main:app --host=0.0.0.0 --port=${PORT:-8000} --workers=4
EOF

# Create production logging configuration
log "Creating production logging configuration..."
cat > "$BUILD_DIR/logging_config.py" << 'EOF'
import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logging():
    """Configure logging for production environment."""
    
    # Create logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # Console handler
            logging.StreamHandler(sys.stdout),
            # File handler with rotation
            RotatingFileHandler(
                os.path.join(log_dir, 'app.log'),
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
        ]
    )
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("openai").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)
EOF

# Optimize Python bytecode
log "Optimizing Python bytecode..."
python -m compileall "$BUILD_DIR" -b -q

# Remove source .py files (optional, keep for debugging)
# find "$BUILD_DIR" -name "*.py" -not -path "*/venv/*" -delete

# Create production environment configuration
log "Creating production environment template..."
cat > "$BUILD_DIR/.env.production.template" << 'EOF'
# Production Environment Variables Template
# Copy to .env and configure with actual values

# Application Configuration
ENVIRONMENT=production
DEBUG=False
LOG_LEVEL=INFO

# Server Configuration
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000

# Required API Keys
OPENAI_API_KEY=your-openai-api-key-here
PDFCO_API_KEY=your-pdfco-api-key-here

# Security
SECRET_KEY=your-production-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here

# Database (if implemented)
DATABASE_URL=your-database-url-here

# External Services
REDIS_URL=your-redis-url-here
SENTRY_DSN=your-sentry-dsn-here

# CORS Configuration
CORS_ORIGINS=["https://your-frontend-domain.com"]

# File Upload Configuration
MAX_FILE_SIZE=100MB
UPLOAD_DIR=/tmp/uploads

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=3600

# Monitoring
HEALTH_CHECK_ENABLED=true
METRICS_ENABLED=true
EOF

# Create build manifest
log "Creating build manifest..."
cat > "$BUILD_DIR/build-manifest.json" << EOF
{
  "buildTime": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "version": "1.0.0",
  "environment": "production",
  "buildNumber": "$(date +%Y%m%d%H%M%S)",
  "gitCommit": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
  "platform": "$(uname -s)-$(uname -m)",
  "pythonVersion": "$(python --version | cut -d' ' -f2)",
  "dependencies": "requirements.txt"
}
EOF

# Run security checks (if available)
if command -v safety &> /dev/null; then
    log "Running security checks..."
    safety check --json > "$BUILD_DIR/security-report.json" || warning "Security checks found issues"
fi

# Run code quality checks (if available)
if command -v flake8 &> /dev/null; then
    log "Running code quality checks..."
    flake8 --output-file="$BUILD_DIR/quality-report.txt" --exit-zero . || true
fi

# Calculate build size
BUILD_SIZE=$(du -sh "$BUILD_DIR" | cut -f1)

success "Backend build completed successfully!"
log "Build location: $BUILD_DIR"
log "Build size: $BUILD_SIZE"
log "Build artifacts:"
log "  - FastAPI application"
log "  - Production startup script"
log "  - Docker configuration"
log "  - Railway configuration"
log "  - Heroku configuration"
log "  - Production requirements"
log "  - Logging configuration"
log "  - Build manifest"

log "To run the production build locally:"
log "  cd $BUILD_DIR && ./start.sh"
log ""
log "To build Docker image:"
log "  cd $BUILD_DIR && docker build -t legal-portal-backend ."
log ""
log "To deploy to Railway:"
log "  Connect $BUILD_DIR to Railway and configure environment variables"
log ""
log "To deploy to Heroku:"
log "  cd $BUILD_DIR && git init && heroku create && git push heroku main"