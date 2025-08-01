#!/bin/bash

# Backend Development Server Startup Script
# Legal Document Analysis Portal - Backend Development

set -e  # Exit on any error

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

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

# Check if we're in the right directory
if [ ! -d "$BACKEND_DIR" ]; then
    error "Backend directory not found at $BACKEND_DIR"
    exit 1
fi

# Environment setup
ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    warning ".env file not found. Creating from template..."
    if [ -f "$PROJECT_ROOT/config/.env.template" ]; then
        cp "$PROJECT_ROOT/config/.env.template" "$ENV_FILE"
        warning "Please edit .env file with your API keys before continuing"
    else
        error "Environment template not found"
        exit 1
    fi
fi

log "Starting Legal Document Analysis Portal - Backend Development Server"
log "Project Root: $PROJECT_ROOT"
log "Backend Directory: $BACKEND_DIR"

# Check for Python
if ! command -v python3 &> /dev/null; then
    error "Python 3 is required but not installed"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
log "Python version: $PYTHON_VERSION"

# Navigate to backend directory
cd "$BACKEND_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
log "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
log "Upgrading pip..."
pip install --upgrade pip

# Install/update dependencies
if [ -f "requirements.txt" ]; then
    log "Installing/updating Python dependencies..."
    pip install -r requirements.txt
else
    log "Installing basic FastAPI dependencies..."
    pip install fastapi uvicorn python-multipart openai pydantic python-dotenv
fi

# Load environment variables
if [ -f "$ENV_FILE" ]; then
    log "Loading environment variables from $ENV_FILE"
    set -a  # Automatically export all variables
    source "$ENV_FILE"
    set +a  # Stop auto-exporting
fi

# Validate required environment variables
REQUIRED_ENV_VARS=("OPENAI_API_KEY")
for var in "${REQUIRED_ENV_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        warning "Environment variable $var is not set"
        warning "Please configure your .env file with required API keys"
    else
        success "Environment variable $var is configured"
    fi
done

# Set development environment variables
export ENVIRONMENT=development
export DEBUG=True
export LOG_LEVEL=DEBUG
export FASTAPI_HOST=localhost
export FASTAPI_PORT=8000

# Check if port is already in use
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    warning "Port 8000 is already in use. Attempting to kill existing process..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Create logs directory
mkdir -p logs

# Start FastAPI development server with hot reload
log "Starting FastAPI development server..."
log "Backend will be available at: http://localhost:8000"
log "API documentation at: http://localhost:8000/docs"
log "OpenAPI schema at: http://localhost:8000/openapi.json"
log "Press Ctrl+C to stop the server"

# Start with development configuration
uvicorn main:app \
    --host localhost \
    --port 8000 \
    --reload \
    --reload-dir . \
    --reload-exclude "*.pyc" \
    --reload-exclude "__pycache__" \
    --reload-exclude "venv" \
    --reload-exclude "logs" \
    --log-level debug \
    --access-log \
    --use-colors

# Cleanup
log "Shutting down development server..."
success "Backend development server stopped"