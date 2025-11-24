# Duplicate Detection & Re-run Analysis Features

## Overview

Added two important features to improve document management and analysis workflow:
1. **Duplicate Detection** - Automatically detect and highlight duplicate files before upload
2. **Re-run Analysis** - Allow re-analyzing cases with updated documents

## Feature 1: Duplicate Detection

### What It Does
- Automatically detects duplicate files when you select documents for upload
- Compares both filename AND file size to identify duplicates
- Checks against:
  - Already uploaded documents in the case
  - Other files in the current selection
- Highlights duplicates with amber/yellow styling
- Prevents uploading duplicate files

### Visual Indicators

**Duplicate File Highlighted:**
- 🟡 Amber/yellow background instead of gray
- 🟡 Amber border instead of gray
- 📛 "DUPLICATE" badge next to filename
- ⚠️ Warning message at top: "X duplicate file(s) detected"
- 📊 File size shows "• Duplicate" text

**Normal File:**
- ⚪ Gray background
- ⚪ Gray border
- No duplicate badge

### How It Works

#### Detection Logic
```typescript
1. When files are selected (drag/drop or click)
2. Compare each file against:
   a) Already uploaded documents (name + size)
   b) Other files in selection (name + size)
3. Mark matching files as duplicates
4. Update UI to highlight them
```

#### During Upload
```typescript
1. Filter out duplicate files automatically
2. Upload only non-duplicate files
3. Show success message with skip count
   Example: "✅ Uploaded 3 file(s). Skipped 2 duplicate(s)."
```

### User Experience

**Scenario 1: Duplicate Already Uploaded**
1. User drags `contract.pdf` (already uploaded)
2. File appears with amber background and "DUPLICATE" badge
3. Warning shows: "⚠️ 1 duplicate file(s) detected"
4. User clicks upload
5. Duplicate is skipped automatically
6. Success message: "✅ Uploaded 0 file(s). Skipped 1 duplicate(s)."

**Scenario 2: Duplicate in Selection**
1. User selects 5 files, including two copies of `document.pdf`
2. Both copies highlight as duplicates
3. User can remove one manually (click X)
4. Or upload and system skips both duplicates

**Scenario 3: All Files Are Duplicates**
1. User selects files that are all duplicates
2. All files show amber background
3. User clicks upload
4. Error message: "All selected files are duplicates. Please select different files."
5. No upload occurs

### Benefits
- ✅ Prevents duplicate document uploads
- ✅ Saves storage space
- ✅ Keeps document list clean
- ✅ Clear visual feedback
- ✅ Automatic handling - no user decision needed
- ✅ Shows what was skipped

## Feature 2: Re-run Analysis

### What It Does
- Allows re-running analysis after uploading additional documents
- Available when analysis is completed or failed
- Uses all current documents (original + newly added)
- Creates new analysis result

### When Available

**After Successful Analysis:**
- "Re-run Analysis" button appears next to "View Results"
- Gray button with refresh icon
- Useful when:
  - New documents added after initial analysis
  - Want to include additional evidence
  - Document set has changed

**After Failed Analysis:**
- "Retry Analysis" button appears
- Green button with refresh icon
- Useful when:
  - Previous analysis encountered an error
  - API was temporarily unavailable
  - Want to try again

### Visual Indicators

**Completed Analysis:**
```
Status: [completed]
[View Results] [Re-run Analysis 🔄]
```

**Error State:**
```
Status: [error]
Error: [error message]
[Retry Analysis 🔄]
```

**Processing:**
```
Status: [processing]
🔄 Processing documents...
```

### How It Works

#### Re-run Flow
```typescript
1. User uploads new documents
2. Initial analysis completes
3. User uploads MORE documents
4. User clicks "Re-run Analysis"
5. System:
   - Fetches ALL current documents
   - Identifies intake form (from metadata)
   - Processes all documents together
   - Creates new analysis result
6. Old result is preserved (can view in DB)
7. New result becomes active
8. "View Results" button shows latest analysis
```

#### Backend Processing
- Uses same analysis endpoint: `POST /api/analysis/start`
- Processes all documents in the case
- Respects intake form metadata
- Creates new analysis_results record
- Updates case status

### User Experience

**Scenario: Adding Documents After Analysis**

1. **Initial Setup**
   - User uploads 3 documents
   - Runs analysis
   - Views results

2. **New Evidence**
   - User receives 2 additional documents
   - Uploads them to the same case
   - Documents appear in list

3. **Re-run**
   - User clicks "Re-run Analysis"
   - System processes all 5 documents
   - New results include all documents
   - User clicks "View Results" to see updated analysis

**Scenario: Retry After Error**

1. **Error Occurs**
   - Analysis fails due to temporary API issue
   - Error message displayed
   - "Retry Analysis" button appears

2. **Retry**
   - User clicks "Retry Analysis"
   - System attempts analysis again
   - Processes successfully
   - Results available

### Benefits
- ✅ No need to create new case for additional documents
- ✅ Comprehensive analysis with all evidence
- ✅ Easy recovery from errors
- ✅ Iterative document review workflow
- ✅ Keeps everything in one case
- ✅ Maintains analysis history

## Technical Implementation

### Duplicate Detection

**State:**
```typescript
let duplicateFiles = $state<Set<number>>(new Set());
```

**Detection Function:**
```typescript
function detectDuplicates() {
  const duplicates = new Set<number>();
  
  // Check against uploaded documents
  selectedFiles.forEach((file, index) => {
    const isDuplicate = documents.some(
      (doc) => doc.file_name === file.name && 
               doc.file_size === file.size
    );
    if (isDuplicate) duplicates.add(index);
  });

  // Check within selection
  selectedFiles.forEach((file, index) => {
    const hasDuplicateInSelection = selectedFiles.some(
      (otherFile, otherIndex) =>
        index !== otherIndex &&
        file.name === otherFile.name &&
        file.size === otherFile.size
    );
    if (hasDuplicateInSelection) duplicates.add(index);
  });

  duplicateFiles = duplicates;
}
```

**Upload Filter:**
```typescript
const filesToUpload = selectedFiles.filter(
  (_, index) => !duplicateFiles.has(index)
);
```

### Re-run Analysis

**Button Rendering:**
```svelte
{#if analysisStatus.status === 'completed'}
  <button onclick={startAnalysis}>
    Re-run Analysis
  </button>
{/if}

{#if analysisStatus.status === 'error'}
  <button onclick={startAnalysis}>
    Retry Analysis
  </button>
{/if}
```

**Analysis Function:**
```typescript
async function startAnalysis() {
  analyzing = true;
  const response = await fetch(
    `${PUBLIC_API_URL}/api/analysis/start`,
    {
      method: 'POST',
      body: JSON.stringify({ case_id: caseId })
    }
  );
  // Poll for completion...
}
```

## UI/UX Details

### Color Scheme

**Duplicate Detection:**
- Amber/yellow theme for warnings
- `bg-amber-50` - Light amber background
- `border-amber-300` - Amber border
- `text-amber-600` - Amber text
- `bg-amber-100` - Badge background

**Re-run Button:**
- Gray theme (secondary action)
- `border-gray-300` - Gray border
- `text-gray-700` - Gray text
- `hover:bg-gray-50` - Hover effect

**Retry Button:**
- Green theme (primary action)
- `bg-green-600` - Green background
- `hover:bg-green-700` - Hover effect
- More prominent than re-run

### Icons

**Duplicate Warning:**
- ⚠️ Warning emoji in text
- Amber file icon

**Re-run/Retry:**
- 🔄 Circular arrow (refresh icon)
- SVG path: Clockwise rotation arrows

### Spacing & Layout

**Duplicate Badge:**
- `px-2 py-1` - Small padding
- `text-xs` - Extra small text
- `rounded-full` - Fully rounded corners

**Button Group:**
- `space-x-3` - 12px gap between buttons
- `flex items-center` - Vertical alignment

## Testing Guide

### Test Duplicate Detection

1. **Upload, then upload same file again**
   - Upload `document.pdf`
   - Try to upload `document.pdf` again
   - Should show as duplicate

2. **Select duplicate files at once**
   - Select 5 files including 2 copies of same file
   - Both copies should highlight as duplicates

3. **Different size, same name**
   - Upload `report.pdf` (1MB)
   - Try to upload `report.pdf` (2MB)
   - Should NOT show as duplicate (different size)

4. **Same size, different name**
   - Upload files with different names but same size
   - Should NOT show as duplicate

5. **All duplicates**
   - Select only files that are already uploaded
   - Click upload
   - Should show error message

6. **Mix of new and duplicate**
   - Select 3 new files and 2 duplicates
   - Should upload 3, skip 2
   - Success message should show counts

### Test Re-run Analysis

1. **After successful analysis**
   - Complete analysis
   - Upload new documents
   - Click "Re-run Analysis"
   - New analysis should include all documents

2. **After error**
   - Cause analysis to fail (e.g., disconnect network)
   - "Retry Analysis" button appears
   - Fix issue
   - Click "Retry Analysis"
   - Should succeed

3. **During processing**
   - Start analysis
   - Re-run button should be disabled
   - Shows "Re-running..." text

4. **Multiple re-runs**
   - Run analysis
   - Re-run it
   - Re-run again
   - Each creates new result

## Error Handling

### Duplicate Detection
- If all files are duplicates: Show error, prevent upload
- If some duplicates: Filter and upload others, show count
- If detection fails: Continue with upload (fail-safe)

### Re-run Analysis
- Same error handling as initial analysis
- Network errors: Show in error message
- Auth errors: Redirect to login
- Backend errors: Display error message
- Can retry after any error

## Future Enhancements

### Duplicate Detection
1. **Content-based detection** - Check file hash, not just name/size
2. **Smart suggestions** - "This looks like version 2 of..."
3. **Replace option** - Replace old version with new
4. **Duplicate report** - Show where duplicates exist
5. **Batch actions** - "Remove all duplicates"

### Re-run Analysis
1. **Compare results** - Side-by-side comparison of analyses
2. **Selective re-run** - Choose which documents to include
3. **Scheduled re-run** - Auto re-run when documents added
4. **Analysis history** - View all previous analyses
5. **Incremental analysis** - Only analyze new documents
6. **Version tracking** - v1, v2, v3 of analysis

## Files Modified

- `frontend/src/routes/app/cases/[id]/+page.svelte` - Added both features

## Documentation Files

- `DUPLICATE_DETECTION_RERUN.md` - This file
- `ENHANCED_UPLOAD_FEATURES.md` - Original upload features
- `CASE_EDIT_FEATURE.md` - Case editing feature

## Summary

Both features work together to provide a robust document management system:

**Duplicate Detection** ensures:
- Clean document library
- No wasted storage
- Clear user feedback
- Automatic handling

**Re-run Analysis** enables:
- Iterative analysis workflow
- Adding documents over time
- Error recovery
- Comprehensive results

Together, they create a professional, user-friendly experience for legal document analysis. 🎉

