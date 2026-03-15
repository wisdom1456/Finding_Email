# Server Restart Guide for SSE Implementation

## Quick Start

### 1. Install New Dependencies
```bash
# Install sse-starlette
pip install sse-starlette==2.1.3

# Or install all requirements
pip install -r requirements.txt
```

### 2. Restart Backend Server
```bash
# Stop the current FastAPI server (Ctrl+C if running in terminal)

# Restart it
python -m uvicorn src.legal_portal.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Rebuild Frontend (if needed)
```bash
cd frontend
npm run build
# Or for development with hot reload:
npm run dev
```

## Verification Steps

### Backend Verification

#### 1. Check if SSE endpoints are available
```bash
curl http://localhost:8000/api/progress/analysis/test-id
# Should connect and wait for events (Ctrl+C to stop)
```

#### 2. Check API docs
Open: http://localhost:8000/docs

Look for:
- `/api/progress/analysis/{analysis_id}` (GET)
- `/api/progress/clio-import/{import_id}` (GET)

#### 3. Check server logs
When starting the server, you should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
🚀 Starting Legal Document Analysis API...
INFO:     Application startup complete.
```

No errors about missing `progress` module or `sse_starlette`.

### Frontend Verification

#### 1. Check browser console
Open DevTools (F12) → Console

When starting analysis, look for:
```
Using SSE for progress updates
SSE connection established
```

Or if SSE not supported:
```
SSE not supported, using polling
```

#### 2. Check Network tab
Open DevTools (F12) → Network tab

When analysis starts, look for:
- Request to `/api/progress/analysis/{some-id}`
- Type: `eventsource` or `text/event-stream`
- Status: `200` and stays pending (streaming)

#### 3. Check upload progress
1. Go to a case detail page
2. Select files to upload
3. Click "Upload Files"
4. You should see:
   - "Uploading file 1 of X"
   - Current filename with 📄 icon
   - Progress bar animating
   - Percentage updating

#### 4. Check analysis progress
1. After uploading files
2. Click "Start Analysis"
3. You should see:
   - Progress message updating (e.g., "Extracting content from documents...")
   - Progress bar moving from 0-100%
   - Sub-step information appearing
   - Current document name if processing multiple files

## Troubleshooting

### Issue: "Module 'sse_starlette' not found"
**Solution:**
```bash
pip install sse-starlette==2.1.3
```

### Issue: "Module 'progress' not found"
**Solution:**
- Check that `/src/legal_portal/api/routes/progress.py` exists
- Restart the server with `--reload` flag

### Issue: "SSE not working in browser"
**Solution:**
1. Check browser console for errors
2. Verify the backend is running and accessible
3. Check CORS settings in `src/legal_portal/api/main.py`
4. Try in a different browser (Chrome/Firefox support SSE)

### Issue: "Progress not updating"
**Possible causes:**
1. **SSE connection failed** → Check browser console, should fall back to polling
2. **Backend not publishing events** → Check server logs for progress manager messages
3. **Frontend not subscribed** → Check `progressStore.connect()` is called

**Debug steps:**
```javascript
// In browser console while on case page:
console.log($progressStore) // Should show current progress state
```

### Issue: "Upload progress not showing"
**Check:**
1. Are `currentUploadFile`, `uploadedCount`, `totalUploadCount` being set?
2. Is `uploading` state true during upload?
3. Check browser console for JavaScript errors

## Testing the Implementation

### Test 1: File Upload Progress
1. Navigate to a case
2. Select 3-5 files
3. Click "Upload Files"
4. **Expected**: See file counter, filename, and progress bar updating

### Test 2: Analysis Progress (SSE)
1. Upload files to a case
2. Click "Start Analysis"
3. Open browser DevTools → Network
4. **Expected**: See `/api/progress/analysis/{id}` request with type `eventsource`
5. **Expected**: Progress UI updates in real-time

### Test 3: Clio Import Progress (SSE)
1. Connect to Clio
2. Search for a matter
3. Click "Create Case" or "Import"
4. **Expected**: See progress updates for fetching communications, notes, documents

### Test 4: Fallback to Polling
1. Open browser console
2. Run: `delete window.EventSource`
3. Start analysis
4. **Expected**: Console shows "SSE not supported, using polling"
5. **Expected**: Progress still updates via 5-second polling

## API Endpoints Added

### Analysis Progress Stream
```
GET /api/progress/analysis/{analysis_id}
Content-Type: text/event-stream

Response: Stream of JSON events
{
  "type": "progress",
  "message": "Analyzing documents...",
  "phase": "document_analysis",
  "percent": 45,
  "docs_processed": ["file1.pdf", "file2.pdf"],
  "current_doc": {"name": "file3.pdf", "index": 3, "total": 10},
  "sub_step": "Analyzing batch 2 of 4"
}
```

### Clio Import Progress Stream
```
GET /api/progress/clio-import/{import_id}
Content-Type: text/event-stream

Response: Stream of JSON events
(same format as analysis)
```

## Files Modified/Created

### Backend
- ✅ `src/legal_portal/services/progress_manager.py` (NEW)
- ✅ `src/legal_portal/api/routes/progress.py` (NEW)
- ✅ `src/legal_portal/api/routes/analysis.py` (MODIFIED)
- ✅ `src/legal_portal/api/routes/clio.py` (MODIFIED)
- ✅ `src/legal_portal/api/main.py` (MODIFIED)
- ✅ `requirements.txt` (MODIFIED)

### Frontend
- ✅ `frontend/src/lib/utils/sseClient.ts` (NEW)
- ✅ `frontend/src/lib/stores/progressStore.ts` (NEW)
- ✅ `frontend/src/routes/app/cases/[id]/+page.svelte` (MODIFIED)
- ✅ `frontend/src/lib/components/ClioMatterSearch.svelte` (MODIFIED)
- ✅ `frontend/src/lib/components/ProgressIndicator.svelte` (MODIFIED)

## Quick Health Check

Run this from project root:
```bash
# Check backend files exist
ls -la src/legal_portal/api/routes/progress.py
ls -la src/legal_portal/services/progress_manager.py

# Check frontend files exist
ls -la frontend/src/lib/utils/sseClient.ts
ls -la frontend/src/lib/stores/progressStore.ts

# Check import works
python -c "from legal_portal.services.progress_manager import ProgressManager; print('✅ Backend OK')"

# Check sse-starlette installed
python -c "import sse_starlette; print('✅ SSE library OK')"
```

All checks should pass with no errors.

