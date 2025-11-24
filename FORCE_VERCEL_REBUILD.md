# Force Vercel to Rebuild Python Dependencies

## Problem

Vercel is using a cached version of the Python environment that **doesn't have the new dependencies** we uncommented in `requirements.txt`.

The logs show it's still trying to import `html2text` but failing, even though we uncommented it in the requirements file.

## Solution: Force Clean Rebuild

### Option 1: Redeploy Without Cache (Recommended)

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Open your `finding-emails` project
3. Click **Deployments** tab
4. Find the latest deployment
5. Click the **⋯** (three dots) menu
6. Click **Redeploy**
7. **❗ IMPORTANT:** **UNCHECK** "Use existing Build Cache"
8. Click **Redeploy** to confirm

This will force Vercel to:
- ✅ Reinstall all Python dependencies from scratch
- ✅ Pick up the new `html2text`, `python-docx`, `PyMuPDF` packages
- ✅ Build a fresh serverless function

### Option 2: Add a Dummy Commit (Alternative)

If the UI method doesn't work, you can trigger a fresh build by making a small change:

```bash
# Make a trivial change to force rebuild
echo "# Force rebuild" >> api/index.py
git add api/index.py
git commit -m "Force Vercel rebuild - clear Python dependency cache"
git push
```

Then in Vercel, still use **Redeploy without cache**.

### Option 3: Delete and Redeploy (Nuclear Option)

If nothing else works:

1. Go to Vercel Dashboard → Deployments
2. Delete the recent failed deployments
3. Go to Settings → General
4. Scroll to "Delete Project" (DON'T DO THIS)
5. Instead, just trigger a new deployment from git

## Why This Happened

Vercel's Python runtime caches:
1. **Installed packages** - Stored between deployments for speed
2. **Build artifacts** - Reused if `requirements.txt` hasn't "changed"

Even though we changed `requirements.txt`, Vercel might not detect it as a meaningful change if:
- The file was edited but the cache key didn't update
- The build system used a cached layer

## Verification After Rebuild

Once the rebuild completes (2-3 minutes), check the logs:

**Good Log (success):**
```
Installing collected packages: html2text, python-docx, PyMuPDF...
Successfully installed html2text-2020.1.16
```

**Bad Log (still failing):**
```
ModuleNotFoundError: No module named 'html2text'
```

If you still see the bad log after a clean rebuild, then there's a different issue.

## Alternative: Check Vercel Build Logs

1. Go to Deployments → Latest deployment
2. Click **Building** or **Build Logs**
3. Look for the Python install section
4. Verify it says: `Installing html2text>=2020.1.16`

If it doesn't show this line, then `requirements.txt` isn't being read correctly.

## Current Status

- ✅ Code changes committed and pushed
- ✅ `requirements.txt` updated with uncommented dependencies
- ❌ Vercel still using cached build without new dependencies
- 🔄 **NEXT STEP:** Redeploy without cache

---

**DO THIS NOW:**
1. Go to Vercel Dashboard
2. Find latest deployment
3. Click ⋯ → Redeploy
4. **UNCHECK "Use existing Build Cache"**
5. Click Redeploy

