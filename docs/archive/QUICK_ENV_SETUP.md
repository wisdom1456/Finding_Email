# 🚀 Quick Environment Setup

## What Was Added

✅ **PIN Authentication** - App now requires PIN `0101` to access
✅ **Environment Variable Support** - Configurable via Cloud Run
✅ **Setup Scripts** - Easy configuration tools

---

## ⚡ Quick Setup (3 Steps)

### Step 1: Run the Configuration Script

```bash
./configure_env.sh
```

This will prompt you for:
- OpenAI API Key
- Access PIN (default: 0101)

**OR manually set variables:**

```bash
gcloud run services update legal-portal \
    --region us-central1 \
    --set-env-vars "\
APP_ACCESS_PIN=0101,\
ENVIRONMENT=production,\
LOG_LEVEL=INFO,\
GOOGLE_CLOUD_PROJECT=brflorida,\
OPENAI_API_KEY=your-actual-key-here"
```

### Step 2: Wait for Deployment

The build is currently running. Check status:

```bash
gcloud builds list --limit=1
```

### Step 3: Test the App

Visit: https://legal-portal-vdgt5dqjfa-uc.a.run.app

You'll see the PIN screen. Enter: **0101**

---

## 📋 Required Environment Variables

| Variable | Value | Where to Get |
|----------|-------|--------------|
| `APP_ACCESS_PIN` | `0101` | Your choice |
| `OPENAI_API_KEY` | `sk-proj-...` | https://platform.openai.com/api-keys |
| `GOOGLE_CLOUD_PROJECT` | `brflorida` | Your GCP project |

---

## 🔐 Security Note

The PIN provides basic access control. For production:
- Change default PIN from `0101`
- Use Secret Manager for API keys
- Enable Cloud Run authentication for additional security

---

## 📖 Full Documentation

See `ENV_SETUP_GUIDE.md` for complete details on:
- All available environment variables
- Secret Manager setup
- Security best practices
- Troubleshooting

---

## ✅ Verify Setup

```bash
# Check if variables are set
gcloud run services describe legal-portal \
    --region us-central1 \
    --format="yaml(spec.template.spec.containers[0].env)"

# View logs
gcloud run services logs tail legal-portal --region us-central1
```

---

**Current Status:**
- ✅ Code pushed to GitHub
- 🔄 Cloud Build triggered automatically
- ⏳ Waiting for deployment (2-4 minutes)
- 📍 URL: https://legal-portal-vdgt5dqjfa-uc.a.run.app

