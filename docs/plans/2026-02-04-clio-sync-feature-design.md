# Clio Document Sync Feature Design

**Created:** 2026-02-04
**Status:** Design Complete - Ready for Implementation

## Overview

Add capability to sync new and updated documents from Clio into existing cases, with smart detection of changes and clear user feedback about what needs re-analysis.

## Requirements Summary

- Sync button located in Documents section
- Smart sync: only fetch items new or updated since last sync
- Check all Clio content types: documents, communications, notes
- Replace old versions when documents are updated (no versioning)
- Show detailed results list of what was found
- Flag analysis as "outdated" when new items are added
- User controls when to re-run analysis via banner in Analysis tab
- Simple success message when no new items found

---

## Section 1: Data Model Changes

### Cases Table - New Columns

```sql
ALTER TABLE cases ADD COLUMN clio_last_synced_at TIMESTAMPTZ;
ALTER TABLE cases ADD COLUMN needs_reanalysis BOOLEAN DEFAULT FALSE;
```

**Purpose:**
- `clio_last_synced_at`: Tracks when we last synced from Clio, used to query only new/updated items
- `needs_reanalysis`: Flag set to `true` when new documents are added, cleared when analysis is re-run

### Documents Table - Using Existing Metadata

Already tracking Clio items via metadata fields:
```python
{
  "clio_source": True,
  "clio_type": "document" | "communication" | "note",
  "clio_id": "12345",
  "clio_date": "2026-01-15T10:30:00Z"
}
```

This allows us to identify which documents came from Clio and match them by ID for updates.

---

## Section 2: Sync Algorithm

### Core Logic Flow

**1. Retrieve Clio items with timestamp filter:**
```python
last_sync = case.clio_last_synced_at or case.created_at

# Query Clio API for items modified/created after last_sync
documents = clio_client.get_documents(matter_id, modified_since=last_sync)
communications = clio_client.get_communications(matter_id, modified_since=last_sync)
notes = clio_client.get_notes(matter_id, modified_since=last_sync)
```

**2. Categorize items as NEW vs UPDATED:**
```python
existing_clio_ids = {doc.metadata.get("clio_id") for doc in current_documents}

new_items = [item for item in all_items if item.id not in existing_clio_ids]
updated_items = [item for item in all_items if item.id in existing_clio_ids]
```

**3. Process updates (replace old versions):**
- Find existing document by `clio_id` in metadata
- Delete old document record and storage file
- Import new version with same `clio_id`

**4. Process new items:**
- Import as new documents (same as initial import)

**5. Update case flags:**
```python
case.clio_last_synced_at = now()
case.needs_reanalysis = True if (new_items or updated_items) else False
```

---

## Section 3: API Endpoint

### New Endpoint: `POST /api/clio/sync/{case_id}`

**Request:**
```python
# No body needed - case_id in URL provides all context
```

**Response:**
```json
{
  "success": true,
  "case_id": "uuid",
  "synced_at": "2026-01-15T14:30:00Z",
  "summary": {
    "new_items": 3,
    "updated_items": 1,
    "total_processed": 4
  },
  "details": {
    "new": [
      {
        "name": "Medical Records.pdf",
        "type": "document",
        "date": "2026-01-14T10:00:00Z"
      },
      {
        "name": "Email from opposing counsel",
        "type": "communication",
        "date": "2026-01-15T09:30:00Z"
      }
    ],
    "updated": [
      {
        "name": "Settlement Agreement.docx",
        "type": "document",
        "date": "2026-01-15T11:00:00Z",
        "previous_version_date": "2026-01-10T14:00:00Z"
      }
    ]
  },
  "needs_reanalysis": true
}
```

**Error Cases:**
- 404: Case not found or not linked to Clio
- 401: Clio authentication expired
- 500: Clio API error

---

## Section 4: Documents Section UI

### Sync Button Placement

Located in the documents list area, appears only when case is linked to a Clio matter.

### UI Elements

**Normal State:**
```
┌─────────────────────────────────────────────────┐
│ Documents (15)                                  │
│                                                 │
│ [📄 Upload Files]  [🔄 Sync from Clio]         │
│                     └─ Only visible if case     │
│                        has clio_matter_id       │
└─────────────────────────────────────────────────┘
```

**During Sync (Loading State):**
```
[⏳ Syncing...] (disabled button with spinner)
```

**After Sync - Success with Changes:**
```
✓ Sync complete
New items (2):
• Medical Records.pdf (document)
• Email from opposing counsel (communication)

Updated items (1):
• Settlement Agreement.docx (replaced)

Analysis needs to be updated to include these items.
```

**After Sync - No Changes:**
```
✓ Already up to date - no new items found in Clio
```

**Error State:**
```
⚠️ Sync failed: Clio connection expired. Please reconnect to Clio.
[Reconnect to Clio]
```

---

## Section 5: Analysis Tab - Outdated Indicator

### Status Banner

Appears at top when `needs_reanalysis = true`:

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ Analysis outdated - 4 new items added on Jan 15, 2026   │
│                                                             │
│ [Re-run Analysis]                                           │
└─────────────────────────────────────────────────────────────┘

[Existing analysis results shown below banner...]
```

### Banner Details

- Yellow/warning color scheme (⚠️ icon)
- Shows date from `clio_last_synced_at` when items were added
- Shows count of items added (from sync summary)
- "Re-run Analysis" button triggers new analysis with all current documents
- Banner persists until user re-runs analysis

### Behavior

**When Re-run Analysis is Clicked:**
- Sets `needs_reanalysis = false`
- Starts new analysis job with all current documents (including newly synced)
- Banner disappears
- Shows normal analysis progress/results

**No Banner When:**
- `needs_reanalysis = false`
- Case not linked to Clio
- No sync has been performed yet

---

## Section 6: Implementation Details

### Backend Files to Create/Modify

1. **New Migration:** `supabase/migrations/YYYYMMDD_add_clio_sync_tracking.sql`
   - Add `clio_last_synced_at` and `needs_reanalysis` columns to cases table

2. **New Route:** `src/legal_portal/api/routes/clio.py`
   - Add `sync_clio_matter(case_id)` endpoint
   - Reuse existing `ClioClient` and import helper functions
   - Handle timestamp filtering and diff logic

3. **Modified Service:** `src/legal_portal/api/routes/cases.py`
   - Update analysis trigger to set `needs_reanalysis = false`

### Frontend Files to Modify

1. **Documents Component:** `frontend/src/routes/app/cases/[id]/documents/+page.svelte`
   - Add "Sync from Clio" button
   - Display sync results
   - Handle loading/error states

2. **Analysis Component:** `frontend/src/routes/app/cases/[id]/analysis/+page.svelte`
   - Add status banner when `needs_reanalysis = true`
   - Connect "Re-run Analysis" button

3. **API Client:** `frontend/src/lib/api/`
   - Add `syncClioMatter(caseId)` function

### Error Handling

- **Clio token expiration** → Prompt to reconnect
- **Network errors** → Show retry option
- **Partial failures** → Import what succeeded, report what failed
- **Deleted items in Clio** → Ignore (don't delete from our system)

---

## Testing Considerations

### Backend Tests
- Test sync with no changes
- Test sync with only new items
- Test sync with only updated items
- Test sync with both new and updated items
- Test token expiration handling
- Test document replacement (update flow)

### Frontend Tests
- Test sync button visibility (only when Clio linked)
- Test loading states
- Test success/error message display
- Test analysis banner appearance/dismissal
- Test re-run analysis flow

### Integration Tests
- Full sync → re-analyze flow
- Multiple syncs in sequence
- Sync during active analysis

---

## Success Criteria

- ✅ User can sync Clio documents without recreating the case
- ✅ Only new/updated items are fetched (not full re-import)
- ✅ Updated documents replace old versions cleanly
- ✅ User sees detailed list of what was synced
- ✅ Analysis tab clearly indicates when re-analysis is needed
- ✅ User controls when to re-run analysis
- ✅ Clear feedback for all states (loading, success, no changes, errors)
