# ZIP File Visualization Enhancement

## Overview
Enhanced the file upload interface to better visualize ZIP files and their extracted contents, making it clear which files came from which ZIP archive and how they will be processed.

## Changes Made

### 1. Enhanced File Upload Display (`ui_components.py`)

#### New Function: `_display_uploaded_files_list()`
Created a new function that provides detailed visualization of uploaded files with special handling for ZIP files.

**Features:**
- **ZIP File Highlighting**: ZIP files are displayed with a yellow background (`#fff3cd`) and a gold left border (`#ffc107`)
- **Hierarchical Display**: Extracted files are shown indented under their parent ZIP file with a "↳" indicator
- **File Status Icons**:
  - 📦 for ZIP files
  - ✓ for files that will be processed
  - ⏭️ for files that will be skipped (video/audio)
  - 📄 for regular files
  - ⚠️ for errors

#### Visual Hierarchy
```
📦 documents.zip (2.5 MB)                    ← Yellow highlighted
   ✓ ↳ intake_form.pdf                       ← Indented, will be processed
   ✓ ↳ medical_records.docx                  ← Indented, will be processed
   ⏭️ ↳ video_evidence.mp4                   ← Indented, will be skipped
   ℹ️ ↳ 2 file(s) will be processed, 1 file(s) will be skipped
```

### 2. Enhanced File Preparation Display (`main.py`)

#### Updated `prepare_files_for_analysis()`
Enhanced the ZIP extraction process to provide real-time feedback with visual hierarchy.

**Improvements:**
- Yellow-highlighted extraction message when processing ZIP files
- Shows first 5 extracted files with indentation during extraction
- Displays count of additional files if more than 5
- Color-coded summary:
  - Green for successfully extracted files
  - Gray for skipped video/audio files

#### During Extraction Display
```
📦 Extracting: documents.zip                 ← Yellow highlighted
   ✓ ↳ intake_form.pdf                       ← Shows first 5 files
   ✓ ↳ medical_records.docx
   ✓ ↳ police_report.pdf
   ... and 3 more file(s)                     ← Indicates more files
   ℹ️ 6 file(s) extracted and will be processed, 2 video/audio file(s) skipped
```

### 3. Custom CSS Styling

Added CSS classes for consistent styling:

```css
.zip-file {
    background-color: #fff3cd;        /* Yellow background */
    padding: 8px 12px;
    border-radius: 4px;
    margin: 4px 0;
    border-left: 4px solid #ffc107;   /* Gold left border */
    font-weight: 600;                  /* Bold text */
}

.extracted-file {
    padding: 4px 12px 4px 32px;       /* Indented 32px */
    margin: 2px 0;
    color: #666;                       /* Gray text */
    font-size: 0.9em;                  /* Slightly smaller */
}

.regular-file {
    padding: 4px 12px;
    margin: 2px 0;
}
```

## User Experience Improvements

### Before
```
✅ 3 file(s) ready for upload
```
- No indication of what files were uploaded
- No way to see ZIP contents before processing
- No indication of which files would be skipped

### After
```
📋 Files to be processed:

📦 case_documents.zip (2.5 MB)               ← Yellow highlighted
   ✓ ↳ intake_form.pdf
   ✓ ↳ medical_records.docx
   ⏭️ ↳ video_evidence.mp4 (will be skipped - video/audio)
   ℹ️ ↳ 2 file(s) will be processed, 1 file(s) will be skipped

📄 additional_document.pdf (1.2 MB)
```

## Benefits

1. **Transparency**: Users can see exactly what files are in their ZIP archives before processing
2. **Clarity**: Clear visual hierarchy shows parent-child relationships
3. **Feedback**: Users know which files will be processed and which will be skipped
4. **Error Prevention**: Invalid ZIP files are clearly marked with error messages
5. **Yellow Highlighting**: ZIP files stand out visually, making them easy to identify
6. **Indentation**: Clear visual indication that extracted files came from the ZIP

## Technical Details

### File Type Detection
- Supports ZIP file detection via `.endswith('.zip')`
- Added "zip" to the accepted file types in the file uploader
- Handles both uppercase and lowercase extensions

### ZIP Content Preview
- Uses `zipfile.ZipFile` to peek into ZIP contents before extraction
- Filters out hidden files (starting with `.` or `__MACOSX`)
- Excludes directory entries (ending with `/`)
- Identifies video/audio files that will be skipped

### Video/Audio File Extensions Detected
```python
video_audio_extensions = [
    '.mov', '.mp4', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v',  # Video
    '.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.wma', '.aiff',  # Audio
]
```

### Error Handling
- Handles `BadZipFile` exceptions for corrupted ZIP files
- Displays user-friendly error messages
- Cleans up temporary files even if errors occur

## Files Modified

1. `src/legal_portal/ui/components/ui_components.py`
   - Updated `_show_manual_upload_section()` to add ZIP to accepted types
   - Added call to `_display_uploaded_files_list()`
   - Created new `_display_uploaded_files_list()` function

2. `src/legal_portal/ui/main.py`
   - Enhanced `prepare_files_for_analysis()` ZIP extraction section
   - Added visual feedback during extraction
   - Shows extracted file list with indentation
   - Improved summary messages

## Testing Recommendations

1. **Test with various ZIP files:**
   - Empty ZIP files
   - ZIP files with only documents
   - ZIP files with mixed content (documents + videos)
   - ZIP files with nested directories
   - Corrupted/invalid ZIP files

2. **Test with large ZIP files:**
   - Verify performance with 100+ files
   - Check that file list truncation works correctly

3. **Test visual appearance:**
   - Verify yellow highlighting is visible
   - Check indentation alignment
   - Confirm icons display correctly
   - Test on different screen sizes

4. **Test mixed uploads:**
   - ZIP files + regular files together
   - Multiple ZIP files in one upload
   - Verify each ZIP's contents are shown separately

## Future Enhancements

Potential improvements for future iterations:

1. **Nested ZIP Support**: Show nested ZIP files within ZIP files
2. **File Size Display**: Show individual file sizes for extracted files
3. **Selective Extraction**: Allow users to exclude specific files from ZIP processing
4. **Preview Content**: Show first few lines of text files
5. **Download Filtered ZIP**: Create a new ZIP excluding skipped files
6. **Drag & Drop Reordering**: Allow users to reorder files for processing priority

## Conclusion

This enhancement significantly improves the user experience when working with ZIP files by:
- Making ZIP files highly visible with yellow highlighting
- Showing clear parent-child relationships through indentation
- Providing transparency about which files will be processed
- Giving immediate feedback about file processing status

The hierarchical visualization makes it immediately clear which files came from which ZIP archive, improving user confidence and reducing confusion during the upload process.


