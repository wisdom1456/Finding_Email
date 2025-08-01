#!/bin/bash

# Frontend Build Script
# Legal Document Analysis Portal - Frontend Production Build

set -e  # Exit on any error

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BUILD_DIR="$FRONTEND_DIR/dist"

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

log "Starting Legal Document Analysis Portal - Frontend Build"
log "Project Root: $PROJECT_ROOT"
log "Frontend Directory: $FRONTEND_DIR"
log "Build Directory: $BUILD_DIR"

# Check if we're in the right directory
if [ ! -d "$FRONTEND_DIR" ]; then
    error "Frontend directory not found at $FRONTEND_DIR"
    exit 1
fi

# Navigate to frontend directory
cd "$FRONTEND_DIR"

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

# Install/update dependencies
if [ -f "requirements.txt" ]; then
    log "Installing production dependencies..."
    pip install -r requirements.txt
else
    log "Installing basic dependencies..."
    pip install streamlit requests python-multipart
fi

# Copy application files to build directory
log "Copying application files..."
cp -r src/* "$BUILD_DIR/" 2>/dev/null || true
cp app.py "$BUILD_DIR/" 2>/dev/null || true
cp -r assets "$BUILD_DIR/" 2>/dev/null || true
cp -r public/* "$BUILD_DIR/" 2>/dev/null || true

# Create production requirements.txt
log "Generating production requirements..."
pip freeze > "$BUILD_DIR/requirements.txt"

# Create production startup script
log "Creating production startup script..."
cat > "$BUILD_DIR/start.sh" << 'EOF'
#!/bin/bash
# Production startup script for Streamlit app

# Set production environment
export ENVIRONMENT=production
export STREAMLIT_SERVER_PORT=${PORT:-8501}
export STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Start Streamlit in production mode
streamlit run app.py \
    --server.port $STREAMLIT_SERVER_PORT \
    --server.address $STREAMLIT_SERVER_ADDRESS \
    --server.headless true \
    --browser.gatherUsageStats false \
    --server.enableCORS true \
    --logger.level info
EOF

chmod +x "$BUILD_DIR/start.sh"

# Create Dockerfile for containerized deployment
log "Creating Dockerfile..."
cat > "$BUILD_DIR/Dockerfile" << 'EOF'
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

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
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
EOF

# Create production environment configuration
log "Creating production configuration..."
cat > "$BUILD_DIR/.streamlit/config.toml" << 'EOF'
[server]
port = 8501
address = "0.0.0.0"
headless = true
enableCORS = true
enableXsrfProtection = false

[browser]
gatherUsageStats = false

[logger]
level = "info"

[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
EOF

mkdir -p "$BUILD_DIR/.streamlit"

# Optimize Python bytecode
log "Optimizing Python bytecode..."
python -m compileall "$BUILD_DIR" -b -q

# Create build manifest
log "Creating build manifest..."
cat > "$BUILD_DIR/build-manifest.json" << EOF
{
  "buildTime": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "version": "1.0.0",
  "environment": "production",
  "buildNumber": "$(date +%Y%m%d%H%M%S)",
  "gitCommit": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
  "platform": "$(uname -s)-$(uname -m)"
}
EOF

# Calculate build size
BUILD_SIZE=$(du -sh "$BUILD_DIR" | cut -f1)

success "Frontend build completed successfully!"
log "Build location: $BUILD_DIR"
log "Build size: $BUILD_SIZE"
log "Build artifacts:"
log "  - Streamlit application"
log "  - Production startup script"
log "  - Docker configuration"
log "  - Production requirements"
log "  - Build manifest"

log "To run the production build locally:"
log "  cd $BUILD_DIR && ./start.sh"
log ""
log "To build Docker image:"
log "  cd $BUILD_DIR && docker build -t legal-portal-frontend ."
log ""
log "To deploy to Railway:"
log "  Connect $BUILD_DIR to Railway and set PORT environment variable"