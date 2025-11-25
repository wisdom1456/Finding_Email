#!/bin/bash
# Google Cloud Run Deployment Script for Legal Portal

set -e  # Exit on error

# Configuration
PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"
SERVICE_NAME="legal-portal"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Legal Portal - Google Cloud Deployment${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if logged in
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo -e "${YELLOW}Not logged into gcloud. Running authentication...${NC}"
    gcloud auth login
fi

# Check if PROJECT_ID is set
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: GOOGLE_CLOUD_PROJECT environment variable not set${NC}"
    echo "Set it with: export GOOGLE_CLOUD_PROJECT=your-project-id"
    exit 1
fi

# Set the project
echo -e "${YELLOW}Setting project to: ${PROJECT_ID}${NC}"
gcloud config set project "${PROJECT_ID}"

# Enable required APIs
echo -e "${YELLOW}Enabling required Google Cloud APIs...${NC}"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    aiplatform.googleapis.com \
    speech.googleapis.com \
    storage-api.googleapis.com

# Build the Docker image using Cloud Build
echo -e "${YELLOW}Building Docker image using Cloud Build...${NC}"
gcloud builds submit --tag "${IMAGE_NAME}:latest" .

# Deploy to Cloud Run
echo -e "${YELLOW}Deploying to Cloud Run...${NC}"
gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE_NAME}:latest" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 3600 \
    --max-instances 10 \
    --min-instances 0 \
    --set-env-vars "ENVIRONMENT=production" \
    --service-account "${SERVICE_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" || \
    echo -e "${YELLOW}Note: Service account may need to be created. Using default...${NC}"

# Get the service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region "${REGION}" \
    --format 'value(status.url)')

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Service URL: ${SERVICE_URL}${NC}"
echo -e "${GREEN}Region: ${REGION}${NC}"
echo -e "${GREEN}========================================${NC}"

# Display logs command
echo -e "${YELLOW}To view logs, run:${NC}"
echo "gcloud run services logs tail ${SERVICE_NAME} --region ${REGION}"

# Display update command
echo -e "${YELLOW}To update the service, run:${NC}"
echo "./deploy.sh"

