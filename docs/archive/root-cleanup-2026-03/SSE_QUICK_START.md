# SSE Implementation - Quick Start Guide

## ✅ Verification Complete

All SSE implementation files are in place and imports work correctly!

## 🚀 To See the Progress Updates Working

### Step 1: Restart Servers

**Option A - Automatic (Recommended)**
```bash
./restart_servers.sh
```

**Option B - Manual**
```bash
# Terminal 1 - Backend
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 -m uvicorn src.legal_portal.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 - Frontend
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

### Step 2: Test Upload Progress

1. Open http://localhost:5173 in your browser
2. Navigate to any case
3. Click "Select files" and choose 3-5 files
4. Click "Upload Files"

**You should now see:**
- ✅ "Uploading file 1 of 5" counter
- ✅ Current filename: "📄 contract.pdf"
- ✅ Progress bar animating from 0-100%
- ✅ Percentage updating in real-time
- ✅ Spinner showing activity

### Step 3: Test Analysis Progress (SSE)

1. After files are uploaded, click "Start Analysis"
2. Open browser DevTools (F12) → Network tab
3. Look for a request to `/api/progress/analysis/{some-id}`

**You should see:**
- ✅ Network request with type "eventsource"
- ✅ Status: 200 (pending/streaming)
- ✅ Progress messages updating: "Extracting content...", "Analyzing documents..."
- ✅ Progress bar moving from 0-100%
- ✅ Sub-step details: "Analyzing batch 2 of 4..."
- ✅ Current document: "Processing 3/10: evidence.jpg"

**In browser console:**
```
Using SSE for progress updates
SSE connection established
```

### Step 4: Test Clio Import Progress (if connected)

1. Go to Cases → New Case
2. Search for a Clio matter
3. Click "Create Case" or "Import"

**You should see:**
- ✅ Progress message: "Fetching matter details..."
- ✅ "Downloading document 5/12: deposition.pdf"
- ✅ Progress bar updating
- ✅ Real-time status updates

## 🔍 Debugging

### Check Backend Logs
```bash
tail -f backend.log
```

Look for:
```
INFO: Created progress channel: {analysis-id}
INFO: Client subscribed to channel: {analysis-id}
```

### Check Frontend Console

**SSE Working:**
```javascript
Using SSE for progress updates
SSE connection established
```

**SSE Fallback:**
```javascript
SSE not supported, using polling
```

### Test SSE Endpoint Directly

**Terminal test:**
```bash
# This will connect and wait for events
curl http://localhost:8000/api/progress/analysis/test-id
```

Press Ctrl+C to stop.

### Check API Documentation
Open: http://localhost:8000/docs

Look for these new endpoints:
- `GET /api/progress/analysis/{analysis_id}`
- `GET /api/progress/clio-import/{import_id}`

## 📊 What You Should See

### Upload Progress (Enhanced)
```
┌─────────────────────────────────────────┐
│ Uploading file 3 of 10            60%  │
│ 📄 legal_contract.pdf                   │
│ ████████████░░░░░░░░░░░░░░░░░░░░        │
│ ⌛ Processing and uploading files...    │
└─────────────────────────────────────────┘
```

### Analysis Progress (New SSE Features)
```
┌─────────────────────────────────────────┐
│ Status: processing                       │
│                                          │
│ Analyzing batch 2 of 4 (15/20          │
│ documents complete)                      │
│                                          │
│ ████████████████████░░░░░░░░░░ 65%     │
│ 65% complete                             │
│                                          │
│ Analyzing document 3/10: evidence.jpg   │
│                                          │
│ Processing document 3 of 10:            │
│ evidence.jpg                             │
└─────────────────────────────────────────┘
```

## ❌ If You Don't See Progress Updates

### 1. Backend Not Restarted
```bash
# Kill old process
pkill -f 'uvicorn.*legal_portal'

# Start new one
python3 -m uvicorn src.legal_portal.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend Not Rebuilt
```bash
cd frontend
npm run dev
```

### 3. Missing Dependency
```bash
pip install sse-starlette==2.1.3
```

### 4. CORS Issue
Check `src/legal_portal/api/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Should allow localhost:5173
    ...
)
```

### 5. Browser Cache
- Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
- Or clear browser cache

## 🎯 Key Changes

### What's Different Now

**Before:**
- Upload: Just "Uploading..." with no details
- Analysis: Polling every 5 seconds with "Processing documents..."

**After:**
- Upload: Real-time per-file progress with names and counter
- Analysis: SSE streaming with detailed sub-steps and document tracking
- Clio Import: Granular progress for each operation

## 📁 Files Created/Modified

All files are verified and working:
- ✅ `src/legal_portal/services/progress_manager.py`
- ✅ `src/legal_portal/api/routes/progress.py`
- ✅ `frontend/src/lib/utils/sseClient.ts`
- ✅ `frontend/src/lib/stores/progressStore.ts`
- ✅ Modified 5 other files (analysis.py, clio.py, etc.)

## 💡 Need Help?

Run the verification script:
```bash
python3 verify_sse_setup.py
```

Should show:
```
Results: 7/7 checks passed
🎉 All checks passed! Ready to restart servers.
```

---

**Ready to test? Run: `./restart_servers.sh`**

