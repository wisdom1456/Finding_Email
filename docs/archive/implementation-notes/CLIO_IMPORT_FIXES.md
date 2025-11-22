# Clio Import Fixes & Document Display Improvements

## Issues Fixed

### 1. ✅ Import Error: 'dict' object has no attribute 'id'
**Problem**: The import endpoint was treating notes and documents as objects when they're actually dictionaries returned from the Clio API.

**Solution**: Updated `src/legal_portal/api/routes/clio.py` to properly access dictionary keys:
- Changed `note.id` → `note['id']`
- Changed `note.subject` → `note.get('subject', 'No Subject')`
- Changed `note.detail` → `note.get('detail', '')`
- Changed `doc.name` → `doc.get('name', 'Untitled Document')`
- Changed `doc.id` → `doc['id']`
- Added proper error handling with `.get()` for optional fields

### 2. ✅ Clio Section Moved Above Documents
**User Request**: "Can we move the import from clio section above the documents so the user will use it first and then add any additional documents."

**Solution**: Reordered sections in `frontend/src/routes/app/cases/[id]/+page.svelte`:
1. **Clio Matter Import** section now appears FIRST (after case details)
2. **Documents** section appears SECOND
3. **Analysis** section remains at the bottom

**User Flow Now**:
1. User opens case
2. Sees Clio import option first (if connected)
3. Imports Clio data (communications, notes, documents)
4. Then uploads any additional documents not in Clio
5. Runs analysis on complete document set

### 3. ✅ Visual Indicators for Clio Documents
**User Request**: "Are we importing the docs from clio? If so, can we list them in the documents section. I don't want the user to manually upload the same documents as are available in clio matters."

**Solution**: Added visual indicators in the documents list:
- **Blue link icon** (🔗) appears before Clio-imported document names
- **Purple badge** shows the type: "COMMUNICATION", "NOTE", or "DOCUMENT"
- All Clio documents appear in the main documents list alongside uploaded files
- Users can clearly see what came from Clio vs. what they uploaded

## What Gets Imported from Clio

When a user imports a Clio matter, the following are saved as documents in the database:

### 1. Communications (Emails)
- Saved as `.txt` files with full content
- Status: `processed` (ready for analysis)
- Includes: subject, date, sender, body
- Badge: "COMMUNICATION"
- Icon: Blue link

### 2. Notes
- Saved as `.txt` files with note content
- Status: `processed` (ready for analysis)
- Includes: subject, detail, date
- Badge: "NOTE"
- Icon: Blue link

### 3. Documents (Metadata)
- Saved as document entries (metadata only, files not downloaded yet)
- Status: `uploaded`
- Includes: filename, content type, size
- Badge: "DOCUMENT"
- Icon: Blue link
- Contains Clio URL in metadata for future download if needed

## Document List Example

After importing from Clio, the documents section now shows:

```
Documents
─────────────────────────────────────────────────────

🔗 Clio Communication - Initial Contact Email.txt    [COMMUNICATION]
   2.4 KB • text/plain

🔗 Clio Note - Discovery Meeting Notes.txt           [NOTE]
   1.8 KB • text/plain

🔗 Contract_Agreement_2024.pdf                       [DOCUMENT]
   456 KB • application/pdf

📄 Medical_Records_Scan.pdf                          [INTAKE]
   2.1 MB • application/pdf
   (User uploaded)

📄 Additional_Evidence.docx
   89 KB • application/vnd.openxmlformats...
   (User uploaded)
```

## Benefits

1. **No Duplicate Uploads**: Users can see Clio documents in the list, preventing duplicate uploads
2. **Clear Source Tracking**: Visual indicators show what came from Clio
3. **Better Workflow**: Import from Clio first, then add supplementary documents
4. **Unified View**: All documents (Clio + uploaded) in one list
5. **Ready for Analysis**: Communications and notes are already extracted and ready

## Technical Details

### Document Metadata Structure for Clio Items

```json
{
  "clio_source": true,
  "clio_type": "communication|note|document",
  "clio_id": 12345,
  "clio_subject": "Subject Line",
  "clio_date": "2024-11-20T10:30:00Z",
  "clio_url": "https://...", // for documents only
  "clio_filename": "original.pdf" // for documents only
}
```

### Database Fields
- `storage_path`: Virtual path for Clio items (e.g., `clio/{case_id}/comm_123.txt`)
- `status`: `processed` for comms/notes, `uploaded` for documents
- `extracted_text`: Full content for comms/notes, `null` for documents

## Files Modified

1. `src/legal_portal/api/routes/clio.py`
   - Fixed dictionary access for notes and documents
   - Added proper error handling
   - Improved metadata structure

2. `frontend/src/routes/app/cases/[id]/+page.svelte`
   - Moved Clio section above Documents section
   - Added visual indicators (icon + badge) for Clio documents
   - Improved document list rendering

## Testing Checklist

- [x] Import matter with communications (should appear in documents list)
- [x] Import matter with notes (should appear in documents list)
- [x] Import matter with documents (should appear in documents list)
- [x] Visual indicators show correctly (blue link icon + purple badge)
- [x] Badge text shows correct type (COMMUNICATION, NOTE, DOCUMENT)
- [x] Clio section appears before Documents section
- [x] User can still upload additional documents after import
- [x] No duplicate upload warnings for Clio documents
- [x] Unlinking removes all Clio documents from list

## Next Steps

If you want to actually download document files from Clio (not just metadata):
1. Add background job to fetch document content from `clio_url`
2. Store in Supabase Storage
3. Update `storage_path` and `status` when complete
4. This could be done asynchronously during import or on-demand

Currently, communications and notes have full text content and are immediately available for analysis. Document files from Clio show in the list but would need to be downloaded if you want to analyze their content.

