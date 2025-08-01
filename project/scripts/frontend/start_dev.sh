#!/bin/bash

# Frontend Development Server Startup Script
# Legal Document Analysis Portal - Frontend Development

set -e  # Exit on any error

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

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
if [ ! -d "$FRONTEND_DIR" ]; then
    error "Frontend directory not found at $FRONTEND_DIR"
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

log "Starting Legal Document Analysis Portal - Frontend Development Server"
log "Project Root: $PROJECT_ROOT"
log "Frontend Directory: $FRONTEND_DIR"

# Check for Python
if ! command -v python3 &> /dev/null; then
    error "Python 3 is required but not installed"
    exit 1
fi

# Check for Streamlit
if ! command -v streamlit &> /dev/null; then
    log "Streamlit not found. Installing..."
    pip3 install streamlit
fi

# Navigate to frontend directory
cd "$FRONTEND_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
log "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    log "Installing/updating Python dependencies..."
    pip install -r requirements.txt
else
    log "Installing basic Streamlit dependencies..."
    pip install streamlit requests python-multipart
fi

# Check if backend is running
BACKEND_URL="http://localhost:8000"
log "Checking if backend is running at $BACKEND_URL..."
if curl -s "$BACKEND_URL/health" > /dev/null 2>&1; then
    success "Backend is running and accessible"
else
    warning "Backend is not running at $BACKEND_URL"
    warning "Please start the backend server first:"
    warning "  cd backend && uvicorn main:app --reload --port 8000"
fi

# Set development environment variables
export ENVIRONMENT=development
export DEBUG=True
export STREAMLIT_SERVER_PORT=8501
export STREAMLIT_SERVER_ADDRESS=localhost

# Start Streamlit development server
log "Starting Streamlit development server..."
log "Frontend will be available at: http://localhost:8501"
log "Press Ctrl+C to stop the server"

# Start with development configuration
streamlit run app.py \
    --server.port 8501 \
    --server.address localhost \
    --server.headless false \
    --browser.gatherUsageStats false \
    --server.enableCORS true \
    --server.enableXsrfProtection false \
    --logger.level debug

# Cleanup
log "Shutting down development server..."
success "Frontend development server stopped"