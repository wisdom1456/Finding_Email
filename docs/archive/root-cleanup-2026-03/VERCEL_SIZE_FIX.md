# Fix: Vercel 250 MB Serverless Function Size Limit

## Error
```
Error: A Serverless Function has exceeded the unzipped maximum size of 250 MB.
```

## Root Cause
Python dependencies (PyMuPDF, Pillow, PyPDF2, python-docx) are ~100+ MB combined, pushing the function over Vercel's 250 MB limit.

## Solution Strategy

We have 3 options:

### **Option 1: Remove Heavy Dependencies (Recommended for Vercel)**

**Remove from `api/requirements.txt`:**
- PyMuPDF (~60 MB) - PDF processing
- Pillow (~20 MB) - Image processing  
- PyPDF2 (~10 MB) - PDF extraction
- python-docx (~5 MB) - Word doc processing

**How document processing will work:**
1. **Client-side extraction** - Extract text in browser before upload (preferred)
2. **Supabase Edge Functions** - Process documents separately
3. **External microservice** - Use a dedicated document processing service

**Changes needed:**
- Make imports optional in Python code
- Add graceful fallbacks when libraries aren't available
- Document extraction becomes a separate step

### **Option 2: Use Vercel Pro (Increases limit to 500 MB)**

Cost: $20/month per user

Pros:
- Keeps all functionality in one place
- No code changes needed

Cons:
- Monthly cost
- Still has a limit (might hit it again with more deps)

### **Option 3: Split into Microservices**

**Architecture:**
- Vercel: Lightweight FastAPI + auth + database
- Separate service (Railway, Fly.io, Cloud Run): Heavy document processing

Pros:
- Unlimited size for processing service
- Better scalability
- Can use more powerful instances for processing

Cons:
- More complex deployment
- Need to manage two services

## Implementing Option 1 (Recommended)

### Step 1: Update `api/requirements.txt`

Already done - removed heavy packages.

### Step 2: Make imports conditional

Update files to gracefully handle missing libraries:

```python
# Example pattern for optional imports
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

def process_pdf(file_path):
    if not HAS_PYMUPDF:
        raise ValueError(
            "PDF processing not available. "
            "Please extract text before uploading or use a processing service."
        )
    # ... existing code
```

### Step 3: Update frontend to extract text client-side

Use JavaScript libraries like:
- `pdfjs-dist` for PDFs
- Native browser APIs for images
- `mammoth.js` for Word docs

### Step 4: Test deployment

```bash
git add api/requirements.txt .vercelignore
git commit -m "fix: Reduce serverless function size for Vercel 250MB limit"
git push origin main
```

## Quick Implementation

Since your app is already deployed and working, let's do the **simplest fix first**:

### **Immediate Fix: Disable Document Upload Processing**

1. Comment out document processing imports
2. Add a flag to disable server-side extraction
3. Show users a message to extract text before upload
4. Deploy and test

### **Later: Implement Client-Side Extraction**

Add PDF.js to frontend for text extraction before upload.

## Alternative: Keep Everything, Use Layers

Create a Lambda Layer with pre-built heavy dependencies, then reference it in Vercel. This requires Vercel Pro or Enterprise.

## Recommendation

**For now:** Remove heavy dependencies, disable server-side document processing.

**Next sprint:** Add client-side document text extraction using PDF.js and other browser libraries.

**Future:** Consider microservices architecture if document processing becomes critical.

## Deployment Steps

```bash
# 1. Commit the changes
git add api/requirements.txt .vercelignore VERCEL_SIZE_FIX.md
git commit -m "fix: Reduce function size - remove heavy PDF/image libraries"

# 2. Push to trigger deployment
git push origin main

# 3. Monitor deployment in Vercel dashboard
# Should now be under 250 MB

# 4. Test basic functionality
# - Auth should work
# - Database queries should work  
# - OpenAI API should work
# - Document *upload* will work
# - Document *processing* will need client-side extraction
```

## Testing After Deployment

✅ **Should work:**
- User authentication
- Case management
- Chat feature (your original issue!)
- Letter generation
- File uploads to Supabase Storage

⚠️ **Will need updates:**
- PDF text extraction (add client-side)
- Image processing (add client-side or separate service)
- Word doc extraction (add client-side)

## Next Steps

Once deployed successfully:

1. Test the chat feature - should now work!
2. Test letter generation - should work!
3. Document any features that need client-side extraction
4. Plan Sprint 2: Add PDF.js for client-side extraction

