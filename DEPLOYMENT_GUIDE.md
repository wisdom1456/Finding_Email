# Legal Portal - Deployment Guide

Complete guide for deploying the Legal Portal application to Google Cloud Platform.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Environment Configuration](#environment-configuration)
4. [Deployment Methods](#deployment-methods)
5. [Post-Deployment](#post-deployment)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools
- **Google Cloud SDK** (gcloud CLI)
  ```bash
  # Install from: https://cloud.google.com/sdk/docs/install
  # Or via brew on macOS:
  brew install google-cloud-sdk
  ```

- **Docker** (for local testing)
  ```bash
  # Install from: https://docs.docker.com/get-docker/
  ```

- **Git** (for version control)
  ```bash
  git --version
  ```

### Google Cloud Services Required
- Cloud Run
- Cloud Build
- Container Registry
- Vertex AI API
- Speech-to-Text API
- Cloud Storage

---

## Initial Setup

### 1. Google Cloud Project Setup

```bash
# Login to Google Cloud
gcloud auth login

# Set your project ID
export GOOGLE_CLOUD_PROJECT="your-project-id"
gcloud config set project $GOOGLE_CLOUD_PROJECT

# Set default region (optional)
export GOOGLE_CLOUD_REGION="us-central1"
gcloud config set run/region $GOOGLE_CLOUD_REGION
```

### 2. Enable Required APIs

```bash
# Enable all necessary APIs
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    aiplatform.googleapis.com \
    speech.googleapis.com \
    storage-api.googleapis.com
```

### 3. Create Service Account (Optional but Recommended)

```bash
# Create service account
gcloud iam service-accounts create legal-portal \
    --display-name="Legal Portal Service Account"

# Grant necessary permissions
gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:legal-portal@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:legal-portal@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role="roles/speech.client"

gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:legal-portal@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"
```

### 4. Create GCS Bucket for Video Processing

```bash
# Create bucket for temporary video storage
gsutil mb -p $GOOGLE_CLOUD_PROJECT -l $GOOGLE_CLOUD_REGION gs://${GOOGLE_CLOUD_PROJECT}-legal-videos

# Set lifecycle policy to auto-delete files after 1 day
cat > lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 1}
      }
    ]
  }
}
EOF

gsutil lifecycle set lifecycle.json gs://${GOOGLE_CLOUD_PROJECT}-legal-videos
rm lifecycle.json
```

---

## Environment Configuration

### 1. Set Environment Variables

Create a `.env.production` file (DO NOT commit to git):

```bash
# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key-here

# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_REGION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# Application Configuration
ENVIRONMENT=production
LOG_LEVEL=INFO

# Optional: Anthropic Claude (if using)
ANTHROPIC_API_KEY=your-anthropic-key-here
```

### 2. Use Cloud Secret Manager (Recommended for Production)

```bash
# Create secrets
echo -n "your-openai-key" | gcloud secrets create openai-api-key \
    --data-file=- \
    --replication-policy="automatic"

echo -n "your-anthropic-key" | gcloud secrets create anthropic-api-key \
    --data-file=- \
    --replication-policy="automatic"

# Grant access to Cloud Run service account
gcloud secrets add-iam-policy-binding openai-api-key \
    --member="serviceAccount:legal-portal@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding anthropic-api-key \
    --member="serviceAccount:legal-portal@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

---

## Deployment Methods

### Method 1: Quick Deployment (Using deploy.sh Script)

**Easiest and Recommended for Most Users**

```bash
# Set your project ID
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_REGION="us-central1"  # Optional, defaults to us-central1

# Run deployment script
./deploy.sh
```

The script will:
- ✅ Authenticate with Google Cloud
- ✅ Enable required APIs
- ✅ Build Docker image using Cloud Build
- ✅ Deploy to Cloud Run
- ✅ Provide service URL

---

### Method 2: Manual Deployment (Step-by-Step)

**For more control over the deployment process**

#### Step 1: Build Docker Image

```bash
# Build locally (for testing)
docker build -t legal-portal:latest .

# Test locally
docker run -p 8080:8080 \
    -e OPENAI_API_KEY="your-key" \
    -e GOOGLE_CLOUD_PROJECT="your-project" \
    legal-portal:latest

# Or build using Cloud Build
gcloud builds submit --tag gcr.io/$GOOGLE_CLOUD_PROJECT/legal-portal:latest .
```

#### Step 2: Deploy to Cloud Run

```bash
gcloud run deploy legal-portal \
    --image gcr.io/$GOOGLE_CLOUD_PROJECT/legal-portal:latest \
    --region us-central1 \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 3600 \
    --max-instances 10 \
    --min-instances 0 \
    --set-env-vars "ENVIRONMENT=production,LOG_LEVEL=INFO" \
    --set-secrets "OPENAI_API_KEY=openai-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest"
```

#### Step 3: Verify Deployment

```bash
# Get service URL
gcloud run services describe legal-portal \
    --region us-central1 \
    --format 'value(status.url)'

# Test the endpoint
curl https://your-service-url.run.app/_stcore/health
```

---

### Method 3: Automated CI/CD (Cloud Build Triggers)

**For continuous deployment from Git**

#### Setup Build Trigger

```bash
# Connect GitHub repository (one-time setup)
gcloud alpha builds connections create github "legal-portal-repo" \
    --region=us-central1

# Create trigger for main branch
gcloud builds triggers create github \
    --name="legal-portal-deploy" \
    --repo-name="Finding_Email" \
    --repo-owner="wisdom1456" \
    --branch-pattern="^main$" \
    --build-config="cloudbuild.yaml" \
    --region=us-central1
```

Now, every push to the `main` branch will automatically:
1. Build Docker image
2. Push to Container Registry
3. Deploy to Cloud Run

---

## Post-Deployment

### 1. View Logs

```bash
# Stream logs in real-time
gcloud run services logs tail legal-portal --region us-central1

# View recent logs
gcloud run services logs read legal-portal --region us-central1 --limit 100
```

### 2. Update Configuration

```bash
# Update environment variables
gcloud run services update legal-portal \
    --region us-central1 \
    --set-env-vars "NEW_VAR=value"

# Update memory/CPU
gcloud run services update legal-portal \
    --region us-central1 \
    --memory 4Gi \
    --cpu 4

# Update secrets
gcloud run services update legal-portal \
    --region us-central1 \
    --update-secrets "OPENAI_API_KEY=openai-api-key:latest"
```

### 3. Monitor Performance

```bash
# View metrics in Cloud Console
echo "View metrics at:"
echo "https://console.cloud.google.com/run/detail/${GOOGLE_CLOUD_REGION}/legal-portal/metrics?project=${GOOGLE_CLOUD_PROJECT}"
```

### 4. Custom Domain (Optional)

```bash
# Map custom domain
gcloud run domain-mappings create \
    --service legal-portal \
    --domain your-domain.com \
    --region us-central1
```

---

## Troubleshooting

### Common Issues

#### 1. Authentication Errors

```bash
# Re-authenticate
gcloud auth login
gcloud auth application-default login

# Verify active account
gcloud auth list
```

#### 2. API Not Enabled

```bash
# Check enabled APIs
gcloud services list --enabled

# Enable missing APIs
gcloud services enable [API_NAME]
```

#### 3. Permission Denied

```bash
# Check IAM permissions
gcloud projects get-iam-policy $GOOGLE_CLOUD_PROJECT

# Add necessary roles
gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="user:your-email@domain.com" \
    --role="roles/run.admin"
```

#### 4. Container Build Fails

```bash
# Check build logs
gcloud builds list --limit 5

# View specific build
gcloud builds log [BUILD_ID]

# Test Dockerfile locally
docker build -t test-build .
```

#### 5. Service Crashes on Startup

```bash
# Check logs immediately
gcloud run services logs read legal-portal --region us-central1 --limit 50

# Common causes:
# - Missing environment variables
# - Invalid API keys
# - Port configuration (must use $PORT env var)
# - Memory limits too low
```

#### 6. High Costs

```bash
# Set max instances to control costs
gcloud run services update legal-portal \
    --region us-central1 \
    --max-instances 5

# Enable minimum instances only if needed (incurs costs when idle)
gcloud run services update legal-portal \
    --region us-central1 \
    --min-instances 0
```

---

## Cost Optimization

### Recommended Settings

```bash
# Cost-optimized deployment
gcloud run deploy legal-portal \
    --image gcr.io/$GOOGLE_CLOUD_PROJECT/legal-portal:latest \
    --region us-central1 \
    --platform managed \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --max-instances 3 \
    --min-instances 0 \
    --cpu-throttling \
    --concurrency 80
```

### Cost Breakdown
- **Cloud Run**: Pay per request (scales to zero when idle)
- **Vertex AI**: Pay per API call
- **Speech-to-Text**: Pay per minute of audio
- **Cloud Storage**: Pay per GB stored
- **Container Registry**: Storage costs for images

---

## Rollback

### Rollback to Previous Version

```bash
# List revisions
gcloud run revisions list --service legal-portal --region us-central1

# Rollback to specific revision
gcloud run services update-traffic legal-portal \
    --region us-central1 \
    --to-revisions [REVISION_NAME]=100
```

---

## Security Best Practices

1. **Never commit secrets to Git**
   - Use Cloud Secret Manager
   - Use `.env` files (add to `.gitignore`)

2. **Use IAM properly**
   - Principle of least privilege
   - Service-specific service accounts

3. **Enable authentication** (if not public)
   ```bash
   gcloud run services update legal-portal \
       --region us-central1 \
       --no-allow-unauthenticated
   ```

4. **Regular updates**
   - Keep dependencies updated
   - Monitor security advisories

---

## Support

For issues or questions:
- Check Cloud Run documentation: https://cloud.google.com/run/docs
- View application logs: `gcloud run services logs tail legal-portal`
- Contact: [Your support email/contact]

---

## Quick Reference Commands

```bash
# Deploy
./deploy.sh

# View logs
gcloud run services logs tail legal-portal --region us-central1

# Get URL
gcloud run services describe legal-portal --region us-central1 --format 'value(status.url)'

# Update service
gcloud run services update legal-portal --region us-central1 [OPTIONS]

# Delete service
gcloud run services delete legal-portal --region us-central1
```

---

**Last Updated**: November 2025
**Version**: 1.0

