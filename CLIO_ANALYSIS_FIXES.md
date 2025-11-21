# Clio Document Analysis Fixes

## Issues Fixed

### ❌ Issue 1: Storage Download Error
**Problem**: Analysis endpoint tried to download ALL documents from Supabase Storage, but Clio communications and notes don't have actual files - they have `extracted_text` directly in the database.

**Error**:
```
StorageApiError: {'statusCode': 404, 'error': not_found, 'message': Object not found}
```

**Root Cause**: 
- Communications saved with path: `clio/{case_id}/comm_{id}.txt` (virtual path, no file)
- Notes saved with path: `clio/{case_id}/note_{id}.txt` (virtual path, no file)
- Analysis tried to download these non-existent files from storage

**Solution**: Updated `src/legal_portal/api/routes/analysis.py` to:
1. Check if document has `extracted_text` field
2. If yes → Use the extracted text directly (write to temp file)
3. If no → Download from Supabase Storage
4. Skip documents that fail to download (with warning)

### ❌ Issue 2: Intake Form Not Recognized from Clio
**Problem**: When importing from Clio, documents/communications/notes with "intake" in the name weren't being marked as intake forms.

**Solution**: Updated `src/legal_portal/api/routes/clio.py` to:
1. **Communications**: Check if subject contains "intake" → set `is_intake_form: true`
2. **Notes**: Check if subject contains "intake" → set `is_intake_form: true`
3. **Documents**: Check if filename contains "intake" → set `is_intake_form: true`

Also updated analysis endpoint to check both filename AND Clio subject for "intake" keyword.

## Changes Made

### 1. Analysis Endpoint (`src/legal_portal/api/routes/analysis.py`)

**Before**:
```python
for doc in documents:
    storage_path = doc["storage_path"]
    file_data = supabase.storage.from_("documents").download(storage_path)
    # ... write file ...
```

**After**:
```python
for doc in documents:
    storage_path = doc["storage_path"]
    temp_path = os.path.join(temp_dir, doc['file_name'])
    
    # Check if document has extracted_text (Clio comms/notes or already processed)
    if doc.get('extracted_text'):
        print(f"  - Using extracted text for: {doc['file_name']}")
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(doc['extracted_text'])
    else:
        try:
            file_data = supabase.storage.from_("documents").download(storage_path)
            with open(temp_path, 'wb') as f:
                f.write(file_data)
        except Exception as e:
            print(f"  - Warning: Failed to download {doc['file_name']}: {e}")
            continue  # Skip this document
    
    # Enhanced intake form detection
    is_intake = doc.get('metadata', {}).get('is_intake_form', False)
    if not is_intake:
        check_text = doc['file_name'].lower()
        if doc.get('metadata', {}).get('clio_subject'):
            check_text += ' ' + doc['metadata']['clio_subject'].lower()
        if 'intake' in check_text:
            is_intake = True
```

### 2. Clio Import Endpoint (`src/legal_portal/api/routes/clio.py`)

Added intake detection for all three types:

**Communications**:
```python
is_intake = 'intake' in comm.subject.lower() if comm.subject else False

doc_data = {
    # ...
    "metadata": {
        # ...
        "is_intake_form": is_intake,
    }
}
```

**Notes**:
```python
is_intake = 'intake' in note_subject.lower()

doc_data = {
    # ...
    "metadata": {
        # ...
        "is_intake_form": is_intake,
    }
}
```

**Documents**:
```python
is_intake = 'intake' in doc_name.lower()

doc_data = {
    # ...
    "metadata": {
        # ...
        "is_intake_form": is_intake,
    }
}
```

## How It Works Now

### Import Flow:
1. **Communications** → Saved with `extracted_text`, virtual path, intake detection
2. **Notes** → Saved with `extracted_text`, virtual path, intake detection
3. **Documents** → Downloaded, uploaded to storage, real path, intake detection

### Analysis Flow:
1. Load all documents for case
2. For each document:
   - ✅ Has `extracted_text`? → Use it directly (no download needed)
   - ❌ No `extracted_text`? → Download from storage
   - 💥 Download fails? → Skip with warning
3. Check for intake form:
   - Prioritize `metadata.is_intake_form`
   - Fall back to filename/subject containing "intake"
4. Process with AI

## Document Types Handled

| Type | Storage | Text Extraction | Intake Detection |
|------|---------|-----------------|------------------|
| **Uploaded Files** | ✅ Real file | On upload/analysis | Filename |
| **Clio Communications** | ❌ Virtual path | ✅ Immediate | Subject line |
| **Clio Notes** | ❌ Virtual path | ✅ Immediate | Subject line |
| **Clio Documents** | ✅ Real file | ✅ During import | Filename |

## Benefits

### ✅ Fixed:
- No more storage errors when analyzing Clio imports
- Analysis can process ALL imported content
- Intake forms automatically detected from Clio

### ✅ Improved:
- Graceful handling of missing files (skip with warning)
- Dual intake detection (metadata + keyword)
- Better logging for debugging

### ✅ User Experience:
- Import from Clio → Click "Start Analysis" → Works!
- Intake forms auto-detected (shows blue "INTAKE" badge)
- All communications, notes, and documents analyzed

## Testing

### Test Case 1: Import with Intake Form
```
1. Import Clio matter with communication titled "Client Intake Form"
2. Verify "INTAKE" badge shows on communication
3. Click "Start Analysis"
4. Verify analysis completes successfully
5. Verify intake form is processed first
```

### Test Case 2: Mixed Document Types
```
1. Import Clio matter with:
   - 2 communications (1 with "intake" in subject)
   - 1 note
   - 3 documents (1 PDF, 1 DOCX, 1 image)
2. Click "Start Analysis"
3. Verify all items with text are analyzed
4. Verify intake form detected correctly
```

### Test Case 3: Error Handling
```
1. Import matter with broken document link
2. Click "Start Analysis"
3. Verify analysis continues despite failed download
4. Verify other documents are analyzed
```

## Files Modified

1. **src/legal_portal/api/routes/analysis.py**
   - Use `extracted_text` when available (no download)
   - Graceful error handling for missing files
   - Enhanced intake detection (filename + subject)

2. **src/legal_portal/api/routes/clio.py**
   - Add `is_intake_form` detection for communications
   - Add `is_intake_form` detection for notes
   - Add `is_intake_form` detection for documents
   - Log intake form status during import

## Expected Behavior

### Before Fix:
```
❌ Import Clio matter
❌ Click "Start Analysis"
❌ Error: Object not found (storage path doesn't exist)
❌ Analysis fails
```

### After Fix:
```
✅ Import Clio matter
✅ Click "Start Analysis"
✅ Communications analyzed (using extracted_text)
✅ Notes analyzed (using extracted_text)
✅ Documents analyzed (downloaded from storage)
✅ Intake forms auto-detected
✅ Analysis completes successfully
```

## Ready to Test! 🎉

The fixes are complete. You should now be able to:
1. Import a Clio matter with communications, notes, and documents
2. See all items in the documents list
3. Click "Start Analysis"
4. Have the analysis complete successfully with all content analyzed
5. Intake forms automatically detected and processed first

