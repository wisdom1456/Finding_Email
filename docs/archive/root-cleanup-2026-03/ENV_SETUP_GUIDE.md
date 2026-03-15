# Environment Variables Setup Guide

This guide explains all environment variables needed for the Legal Portal and how to configure them.

## 🔐 Required Environment Variables

### 1. **APP_ACCESS_PIN** (Required)
- **Purpose**: PIN code to access the application
- **Default**: `0101`
- **Example**: `APP_ACCESS_PIN=0101`

### 2. **OPENAI_API_KEY** (Required)
- **Purpose**: OpenAI API access for document processing (GPT-4o Vision)
- **Get it from**: https://platform.openai.com/api-keys
- **Example**: `OPENAI_API_KEY=sk-proj-...`

### 3. **GOOGLE_CLOUD_PROJECT** (Required for video processing)
- **Purpose**: Your Google Cloud Project ID
- **Current**: `brflorida`
- **Example**: `GOOGLE_CLOUD_PROJECT=brflorida`

---

## ⚙️ Optional Environment Variables

### Application Settings
```bash
ENVIRONMENT=production          # production, development, staging
LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
```

### Google Cloud Settings
```bash
GOOGLE_CLOUD_REGION=us-central1
GCS_BUCKET_NAME=brflorida-legal-videos
```

### Anthropic Claude (if using)
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 🚀 Setting Up in Google Cloud Run

### Method 1: Using gcloud CLI (Recommended)

```bash
# Set environment variables
gcloud run services update legal-portal \
    --region us-central1 \
    --set-env-vars "APP_ACCESS_PIN=0101" \
    --set-env-vars "ENVIRONMENT=production" \
    --set-env-vars "LOG_LEVEL=INFO" \
    --set-env-vars "GOOGLE_CLOUD_PROJECT=brflorida"
```

### Method 2: Using Google Cloud Secret Manager (Most Secure)

#### Step 1: Create Secrets
```bash
# Create secret for OpenAI API Key
echo -n "your-actual-openai-key" | gcloud secrets create openai-api-key \
    --data-file=- \
    --replication-policy="automatic"

# Create secret for Access PIN
echo -n "0101" | gcloud secrets create app-access-pin \
    --data-file=- \
    --replication-policy="automatic"
```

#### Step 2: Grant Cloud Run Access
```bash
# Get the service account email
SERVICE_ACCOUNT=$(gcloud run services describe legal-portal \
    --region us-central1 \
    --format="value(spec.template.spec.serviceAccountName)")

# Grant access to secrets
gcloud secrets add-iam-policy-binding openai-api-key \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding app-access-pin \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"
```

#### Step 3: Update Cloud Run to Use Secrets
```bash
gcloud run services update legal-portal \
    --region us-central1 \
    --set-secrets "OPENAI_API_KEY=openai-api-key:latest" \
    --set-secrets "APP_ACCESS_PIN=app-access-pin:latest" \
    --set-env-vars "ENVIRONMENT=production,LOG_LEVEL=INFO,GOOGLE_CLOUD_PROJECT=brflorida"
```

### Method 3: Using Cloud Console UI

1. Go to: https://console.cloud.google.com/run/detail/us-central1/legal-portal?project=brflorida
2. Click **"EDIT & DEPLOY NEW REVISION"**
3. Scroll to **"Variables & Secrets"**
4. Click **"+ ADD VARIABLE"** for each:
   - Name: `APP_ACCESS_PIN`, Value: `0101`
   - Name: `ENVIRONMENT`, Value: `production`
   - Name: `LOG_LEVEL`, Value: `INFO`
   - Name: `GOOGLE_CLOUD_PROJECT`, Value: `brflorida`
5. For sensitive values (API keys), click **"REFERENCE A SECRET"**:
   - Select or create secret
   - Assign to variable name
6. Click **"DEPLOY"**

---

## 📝 Local Development Setup

Create a `.env` file in the project root:

```bash
# .env (DO NOT COMMIT TO GIT)
APP_ACCESS_PIN=0101
OPENAI_API_KEY=sk-proj-your-actual-key
GOOGLE_CLOUD_PROJECT=brflorida
GOOGLE_CLOUD_REGION=us-central1
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

The app will automatically load these using `python-dotenv`.

---

## 🔒 Security Best Practices

### ✅ DO:
- Store API keys in Secret Manager for production
- Use different PINs for dev/staging/production
- Rotate API keys regularly
- Use service accounts with minimal permissions
- Enable audit logging

### ❌ DON'T:
- Commit API keys to Git
- Share API keys in plain text
- Use the same credentials across environments
- Hard-code sensitive values

---

## 🧪 Testing Your Configuration

### Check if variables are set:
```bash
gcloud run services describe legal-portal \
    --region us-central1 \
    --format="yaml(spec.template.spec.containers[0].env)"
```

### Test locally:
```bash
# Load .env file and run
./scripts/start_local_dev.sh
```

### Check logs for issues:
```bash
gcloud run services logs tail legal-portal --region us-central1
```

---

## 🆘 Troubleshooting

### Error: "OPENAI_API_KEY not found"
```bash
# Verify it's set
gcloud run services describe legal-portal \
    --region us-central1 \
    --format="value(spec.template.spec.containers[0].env)"

# Set it
gcloud run services update legal-portal \
    --region us-central1 \
    --set-env-vars "OPENAI_API_KEY=your-key"
```

### Error: "Authentication required" appears immediately
- Check `APP_ACCESS_PIN` is set correctly
- Verify it matches in both code and Cloud Run config

### Error: "Permission denied" for Google Cloud APIs
- Ensure service account has necessary roles
- Check IAM permissions in Cloud Console

---

## 📊 Current Configuration Script

Run this to set everything up at once:

```bash
#!/bin/bash
# setup_env.sh - Configure all environment variables

# Replace with your actual values
OPENAI_KEY="your-actual-openai-key"
ACCESS_PIN="0101"

# Update Cloud Run service
gcloud run services update legal-portal \
    --region us-central1 \
    --set-env-vars "\
APP_ACCESS_PIN=${ACCESS_PIN},\
ENVIRONMENT=production,\
LOG_LEVEL=INFO,\
GOOGLE_CLOUD_PROJECT=brflorida,\
GOOGLE_CLOUD_REGION=us-central1,\
OPENAI_API_KEY=${OPENAI_KEY}"

echo "✅ Environment variables configured!"
echo "🔗 Service URL: https://legal-portal-vdgt5dqjfa-uc.a.run.app"
```

---

## 📋 Quick Reference

| Variable | Required | Default | Where to Get |
|----------|----------|---------|--------------|
| `APP_ACCESS_PIN` | Yes | `0101` | Set your own |
| `OPENAI_API_KEY` | Yes | - | https://platform.openai.com/api-keys |
| `GOOGLE_CLOUD_PROJECT` | Yes | - | Google Cloud Console |
| `ENVIRONMENT` | No | `production` | - |
| `LOG_LEVEL` | No | `INFO` | - |
| `ANTHROPIC_API_KEY` | No | - | https://console.anthropic.com/ |

---

**Last Updated**: November 7, 2025
