# 🚀 Quick Start Guide - Legal Portal Deployment

## TL;DR - Get Running in 5 Minutes

### Step 1: Fix Git Authentication (Choose ONE)

**Option A: Personal Access Token** (Easiest - 2 minutes)
```bash
# 1. Get token: https://github.com/settings/tokens (select 'repo' scope)
# 2. Run:
git remote set-url origin https://YOUR_TOKEN@github.com/wisdom1456/Finding_Email.git
git push origin tool-fork-development
```

**Option B: Use Interactive Script** (Guided)
```bash
./setup_and_deploy.sh
# Choose option 1, then follow prompts
```

### Step 2: Deploy to Google Cloud

```bash
# Set your project
export GOOGLE_CLOUD_PROJECT="your-project-id"

# Deploy
./deploy.sh
```

**Done!** Your app is now live at the URL provided.

---

## 📋 What Was Changed

Your code has been **committed locally** with these improvements:
- ✅ GPT-4o Vision API with batch processing
- ✅ Data quality validation
- ✅ Citation tracking
- ✅ Letter review service
- ✅ Enhanced document formatting

**Status**: Committed locally, needs to be pushed to GitHub

---

## 🔧 Current Situation

```
Local Git: ✅ Committed (08b03ec)
GitHub: ❌ Not pushed yet (auth issue)
Google Cloud: ⏳ Ready to deploy
```

---

## 📝 Full Documentation

| Need Help With | Read This File |
|----------------|---------------|
| GitHub authentication | `GITHUB_AUTH_SETUP.md` |
| Google Cloud deployment | `DEPLOYMENT_GUIDE.md` |
| Overall status | `DEPLOYMENT_STATUS.md` |
| Testing the app | `TESTING_GUIDE_DATA_QUALITY_IMPROVEMENTS.md` |

---

## 🆘 Troubleshooting One-Liners

```bash
# Git push fails
cat GITHUB_AUTH_SETUP.md | less

# Deploy fails
gcloud builds log $(gcloud builds list --limit 1 --format="value(id)")

# Service not starting
gcloud run services logs tail legal-portal --region us-central1

# Test locally first
docker build -t test . && docker run -p 8080:8080 -e OPENAI_API_KEY="key" test
```

---

## 💡 Interactive Setup (Recommended)

Just run this and follow the prompts:

```bash
./setup_and_deploy.sh
```

It will:
1. Fix GitHub authentication (your choice of method)
2. Push your code
3. Deploy to Google Cloud
4. Give you the live URL

---

## 📞 Quick Commands Reference

```bash
# Push to GitHub (after fixing auth)
git push origin tool-fork-development

# Deploy to Google Cloud
./deploy.sh

# View live logs
gcloud run services logs tail legal-portal --region us-central1

# Get service URL
gcloud run services describe legal-portal --region us-central1 --format 'value(status.url)'

# Test locally
docker build -t test . && docker run -p 8080:8080 test

# Update deployment
./deploy.sh  # Just run it again!
```

---

## ✅ Verification Checklist

- [ ] GitHub authentication fixed
- [ ] Code pushed to GitHub
- [ ] Google Cloud SDK installed
- [ ] Project ID set
- [ ] APIs enabled
- [ ] Service deployed
- [ ] URL accessible
- [ ] App working correctly

---

## 🎯 Your Next Command

If you haven't already, run this now:

```bash
./setup_and_deploy.sh
```

Then choose option 3 (Both) to do everything in one go!

---

**Questions?** See `DEPLOYMENT_STATUS.md` for complete details.

**Last Updated**: November 7, 2025

