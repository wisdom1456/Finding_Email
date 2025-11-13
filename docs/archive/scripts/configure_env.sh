#!/bin/bash
# Quick script to configure environment variables for Legal Portal

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}   Legal Portal - Environment Setup${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not installed${NC}"
    exit 1
fi

# Get current configuration
PROJECT_ID="brflorida"
REGION="us-central1"
SERVICE_NAME="legal-portal"

echo -e "${YELLOW}Current Configuration:${NC}"
echo "  Project: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Service: $SERVICE_NAME"
echo ""

# Prompt for OpenAI API Key
echo -e "${YELLOW}Enter your OpenAI API Key:${NC}"
echo "(Get it from: https://platform.openai.com/api-keys)"
read -sp "OpenAI API Key: " OPENAI_KEY
echo ""

if [ -z "$OPENAI_KEY" ]; then
    echo -e "${RED}Error: OpenAI API Key is required${NC}"
    exit 1
fi

# Prompt for PIN
echo ""
echo -e "${YELLOW}Enter Access PIN (default: 0101):${NC}"
read -p "Access PIN [0101]: " ACCESS_PIN
ACCESS_PIN=${ACCESS_PIN:-0101}

# Confirm
echo ""
echo -e "${YELLOW}Will set the following environment variables:${NC}"
echo "  APP_ACCESS_PIN=$ACCESS_PIN"
echo "  OPENAI_API_KEY=sk-...${OPENAI_KEY: -4}"
echo "  ENVIRONMENT=production"
echo "  LOG_LEVEL=INFO"
echo "  GOOGLE_CLOUD_PROJECT=$PROJECT_ID"
echo ""
read -p "Continue? [y/N]: " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${RED}Cancelled${NC}"
    exit 0
fi

# Update Cloud Run service
echo ""
echo -e "${YELLOW}Updating Cloud Run service...${NC}"

gcloud run services update $SERVICE_NAME \
    --region $REGION \
    --project $PROJECT_ID \
    --set-env-vars "\
APP_ACCESS_PIN=${ACCESS_PIN},\
ENVIRONMENT=production,\
LOG_LEVEL=INFO,\
GOOGLE_CLOUD_PROJECT=${PROJECT_ID},\
GOOGLE_CLOUD_REGION=${REGION},\
OPENAI_API_KEY=${OPENAI_KEY}" \
    --quiet

echo ""
echo -e "${GREEN}✅ Environment variables configured successfully!${NC}"
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region $REGION \
    --project $PROJECT_ID \
    --format='value(status.url)')

echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}   Setup Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "Service URL: ${YELLOW}${SERVICE_URL}${NC}"
echo -e "Access PIN: ${YELLOW}${ACCESS_PIN}${NC}"
echo ""
echo "Wait 1-2 minutes for the new revision to deploy, then test your app!"
echo ""

