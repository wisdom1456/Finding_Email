#!/bin/bash

# Frontend Deployment Script
# Legal Document Analysis Portal - Frontend Production Deployment

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

# Deployment configuration
DEPLOYMENT_TARGET="${1:-railway}"  # Default to Railway
ENVIRONMENT="${2:-production}"     # Default to production

log "Starting Legal Document Analysis Portal - Frontend Deployment"
log "Deployment Target: $DEPLOYMENT_TARGET"
log "Environment: $ENVIRONMENT"
log "Project Root: $PROJECT_ROOT"

# Validate deployment target
case $DEPLOYMENT_TARGET in
    railway|docker|heroku|vercel)
        log "Valid deployment target: $DEPLOYMENT_TARGET"
        ;;
    *)
        error "Invalid deployment target: $DEPLOYMENT_TARGET"
        error "Supported targets: railway, docker, heroku, vercel"
        exit 1
        ;;
esac

# Check if build exists
if [ ! -d "$BUILD_DIR" ]; then
    warning "Build directory not found. Running build first..."
    "$SCRIPT_DIR/build.sh"
fi

# Pre-deployment checks
log "Running pre-deployment checks..."

# Check environment variables
REQUIRED_ENV_VARS=("OPENAI_API_KEY")
for var in "${REQUIRED_ENV_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        warning "Environment variable $var is not set"
    fi
done

# Check build manifest
if [ -f "$BUILD_DIR/build-manifest.json" ]; then
    BUILD_VERSION=$(cat "$BUILD_DIR/build-manifest.json" | grep '"version"' | cut -d'"' -f4)
    BUILD_TIME=$(cat "$BUILD_DIR/build-manifest.json" | grep '"buildTime"' | cut -d'"' -f4)
    log "Deploying version: $BUILD_VERSION (built: $BUILD_TIME)"
else
    warning "Build manifest not found"
fi

# Deployment functions
deploy_railway() {
    log "Deploying to Railway..."
    
    cd "$BUILD_DIR"
    
    # Check if railway CLI is installed
    if ! command -v railway &> /dev/null; then
        error "Railway CLI not found. Install with: npm install -g @railway/cli"
        exit 1
    fi
    
    # Login check
    if ! railway whoami &> /dev/null; then
        log "Please login to Railway first:"
        railway login
    fi
    
    # Deploy
    log "Deploying frontend to Railway..."
    railway deploy
    
    success "Frontend deployed to Railway successfully!"
}

deploy_docker() {
    log "Building and deploying Docker container..."
    
    cd "$BUILD_DIR"
    
    # Build Docker image
    IMAGE_NAME="legal-portal-frontend"
    IMAGE_TAG="${ENVIRONMENT}-$(date +%Y%m%d%H%M%S)"
    
    log "Building Docker image: $IMAGE_NAME:$IMAGE_TAG"
    docker build -t "$IMAGE_NAME:$IMAGE_TAG" .
    docker tag "$IMAGE_NAME:$IMAGE_TAG" "$IMAGE_NAME:latest"
    
    # Push to registry (if configured)
    if [ -n "$DOCKER_REGISTRY" ]; then
        log "Pushing to Docker registry: $DOCKER_REGISTRY"
        docker tag "$IMAGE_NAME:$IMAGE_TAG" "$DOCKER_REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
        docker push "$DOCKER_REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
        docker push "$DOCKER_REGISTRY/$IMAGE_NAME:latest"
    fi
    
    success "Docker image built successfully: $IMAGE_NAME:$IMAGE_TAG"
    log "To run locally: docker run -p 8501:8501 $IMAGE_NAME:latest"
}

deploy_heroku() {
    log "Deploying to Heroku..."
    
    cd "$BUILD_DIR"
    
    # Check if heroku CLI is installed
    if ! command -v heroku &> /dev/null; then
        error "Heroku CLI not found. Install from https://devcenter.heroku.com/articles/heroku-cli"
        exit 1
    fi
    
    # Login check
    if ! heroku whoami &> /dev/null; then
        log "Please login to Heroku first:"
        heroku login
    fi
    
    # Create Procfile for Heroku
    echo "web: streamlit run app.py --server.port=\$PORT --server.address=0.0.0.0" > Procfile
    
    # Initialize git repo if needed
    if [ ! -d ".git" ]; then
        git init
        git add .
        git commit -m "Initial commit for Heroku deployment"
    fi
    
    # Create or use existing Heroku app
    if [ -n "$HEROKU_APP_NAME" ]; then
        heroku git:remote -a "$HEROKU_APP_NAME"
    else
        warning "HEROKU_APP_NAME not set. Creating new app..."
        heroku create
    fi
    
    # Deploy
    git push heroku main
    
    success "Frontend deployed to Heroku successfully!"
}

deploy_vercel() {
    log "Deploying to Vercel..."
    
    cd "$BUILD_DIR"
    
    # Check if vercel CLI is installed
    if ! command -v vercel &> /dev/null; then
        error "Vercel CLI not found. Install with: npm install -g vercel"
        exit 1
    fi
    
    # Create vercel.json configuration
    cat > vercel.json << 'EOF'
{
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app.py"
    }
  ],
  "env": {
    "STREAMLIT_SERVER_HEADLESS": "true",
    "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"
  }
}
EOF
    
    # Deploy
    log "Deploying frontend to Vercel..."
    vercel --prod
    
    success "Frontend deployed to Vercel successfully!"
}

# Execute deployment based on target
case $DEPLOYMENT_TARGET in
    railway)
        deploy_railway
        ;;
    docker)
        deploy_docker
        ;;
    heroku)
        deploy_heroku
        ;;
    vercel)
        deploy_vercel
        ;;
esac

# Post-deployment checks
log "Running post-deployment checks..."

# Health check (if URL is provided)
if [ -n "$DEPLOYMENT_URL" ]; then
    log "Checking deployment health at $DEPLOYMENT_URL"
    sleep 30  # Wait for deployment to be ready
    
    if curl -f "$DEPLOYMENT_URL" > /dev/null 2>&1; then
        success "Deployment health check passed"
    else
        warning "Deployment health check failed - please verify manually"
    fi
fi

# Cleanup
log "Cleaning up temporary files..."
cd "$PROJECT_ROOT"

success "Frontend deployment completed!"
log "Deployment summary:"
log "  Target: $DEPLOYMENT_TARGET"
log "  Environment: $ENVIRONMENT"
log "  Build Directory: $BUILD_DIR"

if [ -n "$DEPLOYMENT_URL" ]; then
    log "  URL: $DEPLOYMENT_URL"
fi

log ""
log "Next steps:"
log "  1. Verify the deployment is working correctly"
log "  2. Configure environment variables if needed"
log "  3. Set up monitoring and logging"
log "  4. Configure custom domain (if applicable)"