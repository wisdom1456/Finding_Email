#!/bin/bash

# Backend Deployment Script
# Legal Document Analysis Portal - Backend Production Deployment

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

# Deployment configuration
DEPLOYMENT_TARGET="${1:-railway}"  # Default to Railway
ENVIRONMENT="${2:-production}"     # Default to production

log "Starting Legal Document Analysis Portal - Backend Deployment"
log "Deployment Target: $DEPLOYMENT_TARGET"
log "Environment: $ENVIRONMENT"
log "Project Root: $PROJECT_ROOT"

# Validate deployment target
case $DEPLOYMENT_TARGET in
    railway|docker|heroku|fly|render)
        log "Valid deployment target: $DEPLOYMENT_TARGET"
        ;;
    *)
        error "Invalid deployment target: $DEPLOYMENT_TARGET"
        error "Supported targets: railway, docker, heroku, fly, render"
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
        warning "Make sure to configure this in your deployment platform"
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
    
    # Initialize Railway project if needed
    if [ ! -f "railway.toml" ]; then
        log "Initializing Railway project..."
        railway init
    fi
    
    # Set environment variables
    log "Setting environment variables..."
    railway variables set ENVIRONMENT=production
    railway variables set DEBUG=False
    railway variables set LOG_LEVEL=INFO
    
    # Deploy
    log "Deploying backend to Railway..."
    railway deploy
    
    # Get deployment URL
    DEPLOYMENT_URL=$(railway domain 2>/dev/null || echo "Not configured")
    
    success "Backend deployed to Railway successfully!"
    log "Deployment URL: $DEPLOYMENT_URL"
}

deploy_docker() {
    log "Building and deploying Docker container..."
    
    cd "$BUILD_DIR"
    
    # Build Docker image
    IMAGE_NAME="legal-portal-backend"
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
    
    # Run container locally for testing
    if [ "$ENVIRONMENT" = "development" ]; then
        log "Starting container locally for testing..."
        docker run -d -p 8000:8000 --name legal-portal-backend-test "$IMAGE_NAME:latest"
        sleep 5
        
        if curl -f http://localhost:8000/health > /dev/null 2>&1; then
            success "Container health check passed"
            docker stop legal-portal-backend-test
            docker rm legal-portal-backend-test
        else
            error "Container health check failed"
            docker logs legal-portal-backend-test
            docker stop legal-portal-backend-test
            docker rm legal-portal-backend-test
            exit 1
        fi
    fi
    
    success "Docker image built successfully: $IMAGE_NAME:$IMAGE_TAG"
    log "To run locally: docker run -p 8000:8000 $IMAGE_NAME:latest"
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
    
    # Set environment variables
    log "Setting Heroku environment variables..."
    heroku config:set ENVIRONMENT=production
    heroku config:set DEBUG=False
    heroku config:set LOG_LEVEL=INFO
    
    # Deploy
    git push heroku main
    
    # Get app URL
    APP_URL=$(heroku apps:info --json | grep '"web_url"' | cut -d'"' -f4)
    
    success "Backend deployed to Heroku successfully!"
    log "App URL: $APP_URL"
}

deploy_fly() {
    log "Deploying to Fly.io..."
    
    cd "$BUILD_DIR"
    
    # Check if flyctl is installed
    if ! command -v flyctl &> /dev/null; then
        error "Fly CLI not found. Install from https://fly.io/docs/hands-on/install-flyctl/"
        exit 1
    fi
    
    # Login check
    if ! flyctl auth whoami &> /dev/null; then
        log "Please login to Fly.io first:"
        flyctl auth login
    fi
    
    # Create fly.toml if it doesn't exist
    if [ ! -f "fly.toml" ]; then
        log "Initializing Fly.io app..."
        flyctl launch --no-deploy
    fi
    
    # Deploy
    log "Deploying to Fly.io..."
    flyctl deploy
    
    success "Backend deployed to Fly.io successfully!"
}

deploy_render() {
    log "Preparing for Render deployment..."
    
    cd "$BUILD_DIR"
    
    # Create render.yaml for deployment
    cat > render.yaml << 'EOF'
services:
  - type: web
    name: legal-portal-backend
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "./start.sh"
    plan: free
    envVars:
      - key: ENVIRONMENT
        value: production
      - key: DEBUG
        value: False
      - key: LOG_LEVEL
        value: INFO
    healthCheckPath: /health
EOF
    
    success "Render configuration created!"
    log "To deploy to Render:"
    log "1. Connect your GitHub repository to Render"
    log "2. Create a new Web Service"
    log "3. Point to this build directory"
    log "4. Configure environment variables in Render dashboard"
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
    fly)
        deploy_fly
        ;;
    render)
        deploy_render
        ;;
esac

# Post-deployment checks
log "Running post-deployment checks..."

# Health check (if URL is provided)
if [ -n "$DEPLOYMENT_URL" ] && [ "$DEPLOYMENT_URL" != "Not configured" ]; then
    log "Checking deployment health at $DEPLOYMENT_URL"
    sleep 30  # Wait for deployment to be ready
    
    if curl -f "$DEPLOYMENT_URL/health" > /dev/null 2>&1; then
        success "Deployment health check passed"
    else
        warning "Deployment health check failed - please verify manually"
        log "You may need to wait longer for the deployment to be ready"
    fi
else
    log "No deployment URL provided - skipping health check"
fi

# Performance check
if [ -n "$DEPLOYMENT_URL" ] && [ "$DEPLOYMENT_URL" != "Not configured" ]; then
    log "Running basic performance check..."
    RESPONSE_TIME=$(curl -o /dev/null -s -w '%{time_total}' "$DEPLOYMENT_URL/health" || echo "failed")
    if [ "$RESPONSE_TIME" != "failed" ]; then
        log "Health endpoint response time: ${RESPONSE_TIME}s"
    fi
fi

# Cleanup
log "Cleaning up temporary files..."
cd "$PROJECT_ROOT"

success "Backend deployment completed!"
log "Deployment summary:"
log "  Target: $DEPLOYMENT_TARGET"
log "  Environment: $ENVIRONMENT"
log "  Build Directory: $BUILD_DIR"

if [ -n "$DEPLOYMENT_URL" ]; then
    log "  URL: $DEPLOYMENT_URL"
    log "  Health Check: $DEPLOYMENT_URL/health"
    log "  API Docs: $DEPLOYMENT_URL/docs"
fi

log ""
log "Next steps:"
log "  1. Verify the deployment is working correctly"
log "  2. Configure environment variables if needed"
log "  3. Set up monitoring and logging"
log "  4. Configure custom domain (if applicable)"
log "  5. Set up CI/CD pipeline for automated deployments"

# Output important URLs and commands
if [ "$DEPLOYMENT_TARGET" = "railway" ]; then
    log ""
    log "Railway commands:"
    log "  railway logs        # View logs"
    log "  railway variables   # Manage environment variables"
    log "  railway status      # Check deployment status"
elif [ "$DEPLOYMENT_TARGET" = "heroku" ]; then
    log ""
    log "Heroku commands:"
    log "  heroku logs --tail  # View logs"
    log "  heroku config       # Manage environment variables"
    log "  heroku ps           # Check dyno status"
fi