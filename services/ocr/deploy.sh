#!/bin/bash
set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
SERVICE_NAME="ocr-service"
REPO_NAME="legal-portal"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}"

echo "=== Enabling APIs ==="
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    vision.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com

echo "=== Creating Artifact Registry repo ==="
gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Legal Portal containers" \
    2>/dev/null || true

echo "=== Building and pushing image ==="
gcloud builds submit --tag "${IMAGE}:latest" .

echo "=== Creating secrets (idempotent) ==="
# Raw JSON - NOT base64
cat "${GOOGLE_CREDENTIALS_JSON_FILE:?Set path to SA key}" | \
    gcloud secrets create google-vision-key \
    --data-file=- 2>/dev/null || \
    echo "Secret google-vision-key already exists"

echo -n "${OCR_SERVICE_TOKEN:?Set OCR_SERVICE_TOKEN}" | \
    gcloud secrets create ocr-service-token \
    --data-file=- 2>/dev/null || \
    echo "Secret ocr-service-token already exists"

echo "=== Granting secret access ==="
PROJECT_NUMBER=$(
    gcloud projects describe "${PROJECT_ID}" \
    --format='value(projectNumber)'
)
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for SECRET in google-vision-key ocr-service-token; do
    gcloud secrets add-iam-policy-binding "${SECRET}" \
        --member="serviceAccount:${SA}" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet
done

echo "=== Deploying to Cloud Run ==="
gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE}:latest" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --ingress=all \
    --memory 2Gi \
    --cpu 2 \
    --timeout 180 \
    --max-instances 10 \
    --min-instances 1 \
    --concurrency 4 \
    --set-env-vars "LOG_LEVEL=INFO" \
    --set-secrets \
    "GOOGLE_CREDENTIALS_JSON=google-vision-key:latest,\
OCR_SERVICE_TOKEN=ocr-service-token:latest"

echo "=== Service URL ==="
gcloud run services describe "${SERVICE_NAME}" \
    --region "${REGION}" \
    --format 'value(status.url)'
