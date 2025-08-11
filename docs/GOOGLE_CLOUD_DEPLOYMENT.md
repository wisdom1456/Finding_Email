---
title: Google Cloud Deployment
version: 1.0
last_updated: 2025-08-11
owner: @franklin
status: canonical
---
# Google Cloud Deployment Guide

This document explains how to deploy the Legal Document Analysis Portal to Google Cloud Container Registry (`gcr.io/brflorida/legal-portal`) using the automated CI/CD pipeline.

## Overview

The application is deployed to Google Cloud using:
- **Google Container Registry (GCR)**: `gcr.io/brflorida/legal-portal`
- **Google Cloud Run**: Serverless container platform
- **GitHub Actions**: Automated CI/CD pipeline

## Prerequisites

### 1. Google Cloud Project Setup

1. **Project ID**: `brflorida`
2. **Enable required APIs**:
   ```bash
   gcloud services enable containerregistry.googleapis.com
   gcloud services enable run.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable speech.googleapis.com
   gcloud services enable aiplatform.googleapis.com
   gcloud services enable storage.googleapis.com
   ```

### 2. Service Account Configuration

Create a service account with the following roles:
```bash
gcloud iam service-accounts create github-actions \
    --display-name="GitHub Actions CI/CD"

gcloud projects add-iam-policy-binding brflorida \
    --member="serviceAccount:github-actions@brflorida.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding brflorida \
    --member="serviceAccount:github-actions@brflorida.iam.gserviceaccount.com" \
    --role="roles/containerregistry.serviceAgent"

gcloud projects add-iam-policy-binding brflorida \
    --member="serviceAccount:github-actions@brflorida.iam.gserviceaccount.com" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding brflorida \
    --member="serviceAccount:github-actions@brflorida.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"
```

Generate service account key:
```bash
gcloud iam service-accounts keys create github-actions-key.json \
    --iam-account=github-actions@brflorida.iam.gserviceaccount.com
```

### 3. GitHub Secrets Configuration

Add the following secrets to your GitHub repository (`Settings > Secrets and variables > Actions`):

| Secret Name | Description | Value |
|-------------|-------------|-------|
| `GCP_SA_KEY` | Service Account JSON Key | Contents of `github-actions-key.json` |

## Deployment Workflow

### Automatic Deployment

The deployment is triggered automatically:
- **Staging**: Push to `develop` branch → Deploy to `legal-portal-staging`
- **Production**: Push to `main` branch → Deploy to `legal-portal-production`

### Manual Deployment

Trigger manual deployment via GitHub Actions:
1. Go to **Actions** tab in GitHub
2. Select **Deploy to Google Cloud Container Registry**
3. Click **Run workflow**
4. Choose environment: `staging` or `production`

## Container Registry Details

### Image Naming Convention
```
gcr.io/brflorida/legal-portal:latest          # Production (main branch)
gcr.io/brflorida/legal-portal:staging         # Staging (develop branch)
gcr.io/brflorida/legal-portal:pr-123          # PR builds
gcr.io/brflorida/legal-portal:abc123def       # Git SHA tags
```

### Image Management
- **Retention**: Keep 10 most recent images per tag
- **Cleanup**: Automatic cleanup of old images during deployment
- **Security**: Container vulnerability scanning with Trivy

## Cloud Run Configuration

### Staging Environment
- **Service Name**: `legal-portal-staging`
- **URL**: `https://legal-portal-staging-[hash]-uc.a.run.app`
- **Resources**: 2 CPU, 2Gi memory
- **Scaling**: 0-10 instances
- **Authentication**: Allow unauthenticated

### Production Environment
- **Service Name**: `legal-portal-production`
- **URL**: `https://legal-portal-production-[hash]-uc.a.run.app`
- **Resources**: 4 CPU, 4Gi memory
- **Scaling**: 1-20 instances (min 1 for warm start)
- **Authentication**: Allow unauthenticated

## Environment Variables

The following environment variables are set automatically:

```bash
# Application Environment
ENVIRONMENT=production|staging

# Google Cloud Configuration
GCP_PROJECT_ID=brflorida
GOOGLE_APPLICATION_CREDENTIALS=/app/service-account.json

# Container Configuration
PORT=8080
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
```

## Monitoring and Health Checks

### Health Check Endpoint
```
GET /_stcore/health
```

### Monitoring Features
- **Container health checks**: 30s interval, 10s timeout
- **Service URL validation**: Post-deployment verification
- **Security scanning**: Vulnerability assessment with Trivy
- **Log aggregation**: Google Cloud Logging integration

## Custom Domain Setup (Optional)

To set up a custom domain:

1. **Map domain to Cloud Run**:
   ```bash
   gcloud run domain-mappings create \
       --service=legal-portal-production \
       --domain=portal.brflorida.com \
       --region=us-central1
   ```

2. **Configure DNS**:
   - Add CNAME record pointing to `ghs.googlehosted.com`
   - Wait for SSL certificate provisioning (15-60 minutes)

## Rollback Procedure

### Automatic Rollback
If health checks fail, the deployment automatically fails and maintains the previous version.

### Manual Rollback
```bash
# List recent revisions
gcloud run revisions list --service=legal-portal-production --region=us-central1

# Rollback to specific revision
gcloud run services update-traffic legal-portal-production \
    --to-revisions=legal-portal-production-00042-abc=100 \
    --region=us-central1
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Verify `GCP_SA_KEY` secret is properly configured
   - Check service account permissions

2. **Container Build Failures**
   - Review build logs in GitHub Actions
   - Check Dockerfile syntax and dependencies

3. **Deployment Failures**
   - Verify Cloud Run API is enabled
   - Check resource quotas and limits

4. **Health Check Failures**
   - Review application logs in Cloud Run console
   - Verify Streamlit health endpoint is accessible

### Log Access

**GitHub Actions Logs**:
```
GitHub Repository > Actions > Workflow Run > Job Details
```

**Cloud Run Logs**:
```bash
gcloud logs read "resource.type=cloud_run_revision AND resource.labels.service_name=legal-portal-production" --limit=50
```

**Container Registry Logs**:
```bash
gcloud logs read "resource.type=gce_instance AND protoPayload.serviceName=containerregistry.googleapis.com" --limit=20
```

## Security Considerations

### Container Security
- **Non-root user**: Container runs as `appuser` (UID 1000)
- **Minimal base image**: Python 3.11 slim with only required dependencies
- **Vulnerability scanning**: Trivy security scan on every build
- **Secrets management**: Environment variables for sensitive data

### Network Security
- **HTTPS only**: SSL/TLS encryption enforced
- **IAM authentication**: Service account-based access control
- **VPC integration**: Can be configured for private networking

### Compliance
- **PII protection**: Automatic sanitization of sensitive data
- **Audit logging**: Comprehensive logging for compliance tracking
- **Backup strategy**: Container images preserved with retention policy

## Cost Optimization

### Cloud Run Pricing
- **CPU allocation**: Pay per request, optimized for legal workloads
- **Memory usage**: Right-sized for document processing requirements
- **Scaling**: Automatic scale-to-zero for cost efficiency

### Container Registry
- **Storage costs**: Automatic cleanup reduces storage costs
- **Network egress**: Optimized image layers reduce transfer costs

### Monitoring Costs
Monitor usage via Google Cloud Console to optimize resource allocation and costs.

## Support

For deployment issues:
1. Check GitHub Actions logs for build/deployment errors
2. Review Cloud Run service logs for runtime issues
3. Contact the development team with specific error messages and timestamps

---

**Last Updated**: 2025-08-11  
**Next Review**: 2025-09-11