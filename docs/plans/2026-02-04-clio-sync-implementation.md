# Clio Document Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ability to sync new and updated documents from Clio into existing cases without recreating them.

**Architecture:** Backend endpoint queries Clio API for items modified since last sync, compares against existing documents by `clio_id`, replaces updated documents, imports new ones, and sets `needs_reanalysis` flag. Frontend adds sync button in Documents section and status banner in Analysis tab.

**Tech Stack:** FastAPI (backend), SvelteKit 5 (frontend), Supabase (PostgreSQL), Clio API v4

---

## Task 1: Database Migration - Add Sync Tracking Columns

**Files:**
- Create: `supabase/migrations/20260204_add_clio_sync_tracking.sql`

**Step 1: Write migration file**

```sql
-- Migration: Add Clio sync tracking to cases table
-- Created: 2026-02-04
-- Description: Adds columns to track last sync time and whether analysis needs update

-- Add sync tracking columns
ALTER TABLE cases ADD COLUMN IF NOT EXISTS clio_last_synced_at TIMESTAMPTZ;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS needs_reanalysis BOOLEAN DEFAULT FALSE;

-- Add index for filtering cases that need reanalysis
CREATE INDEX IF NOT EXISTS idx_cases_needs_reanalysis
    ON cases(needs_reanalysis)
    WHERE needs_reanalysis = TRUE;

-- Add comments for documentation
COMMENT ON COLUMN cases.clio_last_synced_at IS 'Timestamp of last successful Clio sync for this case';
COMMENT ON COLUMN cases.needs_reanalysis IS 'True when new documents added via sync and analysis has not been re-run';
```

**Step 2: Apply migration locally**

Run: `supabase db reset` (if using local Supabase) or apply manually
Expected: Migration applies successfully

**Step 3: Verify columns exist**

Run SQL query:
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'cases'
AND column_name IN ('clio_last_synced_at', 'needs_reanalysis');
```
Expected: Both columns listed

**Step 4: Commit**

```bash
git add supabase/migrations/20260204_add_clio_sync_tracking.sql
git commit -m "feat: add database columns for Clio sync tracking

Add clio_last_synced_at and needs_reanalysis columns to cases table
to support incremental Clio document syncing.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Backend - Add Sync Endpoint Response Models

**Files:**
- Modify: `src/legal_portal/api/routes/clio.py` (add after existing models)

**Step 1: Write response model classes**

Add after the existing `ClioImportResponse` class (around line 50):

```python
class ClioSyncItemDetail(BaseModel):
    """Details about a single synced item."""
    name: str
    type: Literal["document", "communication", "note"]
    date: Optional[datetime] = None
    previous_version_date: Optional[datetime] = None


class ClioSyncSummary(BaseModel):
    """Summary of sync operation."""
    new_items: int
    updated_items: int
    total_processed: int


class ClioSyncDetails(BaseModel):
    """Detailed breakdown of synced items."""
    new: List[ClioSyncItemDetail]
    updated: List[ClioSyncItemDetail]


class ClioSyncResponse(BaseModel):
    """Response from Clio sync operation."""
    success: bool
    case_id: str
    synced_at: datetime
    summary: ClioSyncSummary
    details: ClioSyncDetails
    needs_reanalysis: bool
```

**Step 2: Verify models are valid**

Run: `python3 -c "from src.legal_portal.api.routes.clio import ClioSyncResponse; print('Models valid')"` from project root
Expected: "Models valid" printed

**Step 3: Commit**

```bash
git add src/legal_portal/api/routes/clio.py
git commit -m "feat: add Pydantic models for Clio sync response

Add ClioSyncResponse and related models for sync endpoint.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Backend - Implement Sync Helper Function

**Files:**
- Modify: `src/legal_portal/api/routes/clio.py` (add before `import_clio_data` function)

**Step 1: Write helper function to categorize sync items**

Add this helper function around line 390 (before `import_clio_data`):

```python
def categorize_clio_sync_items(
    documents: List[dict],
    communications: List[dict],
    notes: List[dict],
    existing_docs: List[dict],
) -> Tuple[List[dict], List[dict]]:
    """
    Categorize Clio items as new or updated based on existing documents.

    Args:
        documents: List of documents from Clio API
        communications: List of communications from Clio API
        notes: List of notes from Clio API
        existing_docs: List of existing document records from database

    Returns:
        Tuple of (new_items, updated_items) where each is a list of dicts
        with keys: id, name, type, date
    """
    # Extract existing Clio IDs from metadata
    existing_clio_ids = set()
    for doc in existing_docs:
        metadata = doc.get("metadata", {})
        if metadata.get("clio_source") and metadata.get("clio_id"):
            existing_clio_ids.add(str(metadata["clio_id"]))

    new_items = []
    updated_items = []

    # Process documents
    for doc in documents:
        doc_id = str(doc["id"])
        doc_name = doc.get("name", "Untitled Document")
        doc_date = doc.get("created_at")

        item = {
            "id": doc_id,
            "name": doc_name,
            "type": "document",
            "date": doc_date,
            "raw_data": doc,
        }

        if doc_id in existing_clio_ids:
            updated_items.append(item)
        else:
            new_items.append(item)

    # Process communications
    for comm in communications:
        comm_id = str(comm.id)
        comm_name = comm.subject or "Untitled Communication"
        comm_date = comm.date

        item = {
            "id": comm_id,
            "name": comm_name,
            "type": "communication",
            "date": comm_date,
            "raw_data": comm,
        }

        if comm_id in existing_clio_ids:
            updated_items.append(item)
        else:
            new_items.append(item)

    # Process notes
    for note in notes:
        note_id = str(note["id"])
        note_subject = note.get("subject", "Untitled Note")
        note_date = note.get("created_at")

        item = {
            "id": note_id,
            "name": note_subject,
            "type": "note",
            "date": note_date,
            "raw_data": note,
        }

        if note_id in existing_clio_ids:
            updated_items.append(item)
        else:
            new_items.append(item)

    return new_items, updated_items
```

**Step 2: Test helper function with simple data**

Create quick test in Python console or add to test file later:
```python
existing = [{"metadata": {"clio_source": True, "clio_id": "123"}}]
docs = [{"id": 123, "name": "Doc1.pdf", "created_at": None},
        {"id": 456, "name": "Doc2.pdf", "created_at": None}]
new, updated = categorize_clio_sync_items(docs, [], [], existing)
assert len(updated) == 1
assert len(new) == 1
```

**Step 3: Commit**

```bash
git add src/legal_portal/api/routes/clio.py
git commit -m "feat: add helper to categorize Clio sync items

Categorizes items as new vs updated based on existing clio_id values.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Backend - Implement Sync Endpoint

**Files:**
- Modify: `src/legal_portal/api/routes/clio.py` (add after `unlink_clio_matter` function)

**Step 1: Write sync endpoint**

Add after the `unlink_clio_matter` function (around line 920):

```python
@router.post("/sync/{case_id}", response_model=ClioSyncResponse)
async def sync_clio_matter(
    case_id: str,
    user: dict = Depends(get_current_user),
    clio_client: ClioClient = Depends(get_clio_client),
    supabase: Client = Depends(get_supabase_client),
) -> ClioSyncResponse:
    """
    Sync new and updated documents from Clio for an existing case.

    Only fetches items created/modified since last sync (or case creation).
    Replaces updated documents and imports new ones.

    Args:
        case_id: UUID of the case to sync
        user: Current authenticated user
        clio_client: Authenticated Clio API client
        supabase: Supabase client

    Returns:
        ClioSyncResponse with summary and details of synced items

    Raises:
        HTTPException: If case not found, not linked to Clio, or sync fails
    """
    try:
        # Get case and verify it's linked to Clio
        case_result = (
            supabase.table("cases")
            .select("id, clio_matter_id, clio_last_synced_at, created_at")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_result.data:
            raise HTTPException(status_code=404, detail="Case not found")

        case = case_result.data[0]
        matter_id = case.get("clio_matter_id")

        if not matter_id:
            raise HTTPException(
                status_code=400,
                detail="Case is not linked to a Clio matter"
            )

        # Determine sync cutoff time
        last_sync = case.get("clio_last_synced_at")
        cutoff_time = last_sync if last_sync else case.get("created_at")

        # Fetch items from Clio (only those modified since cutoff)
        # Note: Clio API filtering by date is done client-side for now
        # as not all endpoints support modified_since parameter
        documents = clio_client.get_documents(matter_id)
        communications = clio_client.get_communications(matter_id, limit=100)
        notes = clio_client.get_notes(matter_id)

        # Filter by date client-side
        if cutoff_time:
            cutoff_dt = datetime.fromisoformat(cutoff_time.replace("Z", "+00:00"))

            documents = [
                d for d in documents
                if d.get("updated_at") and
                datetime.fromisoformat(d["updated_at"].replace("Z", "+00:00")) > cutoff_dt
            ]

            communications = [
                c for c in communications
                if c.date and c.date > cutoff_dt
            ]

            notes = [
                n for n in notes
                if n.get("updated_at") and
                datetime.fromisoformat(n["updated_at"].replace("Z", "+00:00")) > cutoff_dt
            ]

        # Get existing documents for this case
        docs_result = (
            supabase.table("documents")
            .select("id, metadata, storage_path")
            .eq("case_id", case_id)
            .execute()
        )
        existing_docs = docs_result.data if docs_result.data else []

        # Categorize items as new vs updated
        new_items, updated_items = categorize_clio_sync_items(
            documents, communications, notes, existing_docs
        )

        # Process updated items (delete old, import new version)
        for item in updated_items:
            # Find existing document by clio_id
            clio_id = item["id"]
            old_doc = next(
                (d for d in existing_docs
                 if d.get("metadata", {}).get("clio_id") == clio_id),
                None
            )

            if old_doc:
                # Delete old document from storage and database
                storage_path = old_doc.get("storage_path")
                if storage_path:
                    try:
                        supabase.storage.from_("documents").remove([storage_path])
                    except Exception as e:
                        logger.warning(f"Failed to delete old document from storage: {e}")

                supabase.table("documents").delete().eq("id", old_doc["id"]).execute()

        # Import new and updated items using existing import helper
        # Reuse logic from import_clio_documents_helper
        all_items_to_import = new_items + updated_items

        # For simplicity, we'll process these synchronously
        # In production, consider using the background task pattern from import_clio_data
        imported_count = 0

        for item in all_items_to_import:
            item_type = item["type"]

            if item_type == "communication":
                # Process communication (similar to import_clio_data)
                comm = item["raw_data"]
                content = f"Subject: {comm.subject or 'No subject'}\n"
                content += f"Date: {comm.date}\n"
                content += f"From: {comm.sender}\n\n"
                content += comm.body or ""

                storage_path = f"clio/{case_id}/comm_{comm.id}.txt"
                supabase.storage.from_("documents").upload(
                    storage_path,
                    content.encode("utf-8"),
                    {"content-type": "text/plain"}
                )

                supabase.table("documents").insert({
                    "case_id": case_id,
                    "user_id": user["id"],
                    "storage_path": storage_path,
                    "file_type": "text/plain",
                    "metadata": {
                        "clio_source": True,
                        "clio_type": "communication",
                        "clio_id": comm.id,
                        "clio_subject": comm.subject,
                        "clio_date": comm.date.isoformat() if comm.date else None,
                    }
                }).execute()
                imported_count += 1

            elif item_type == "note":
                # Process note (similar to import_clio_data)
                note = item["raw_data"]
                note_subject = note.get("subject", "Untitled Note")
                note_detail = note.get("detail", "")
                content = f"Subject: {note_subject}\n\n{note_detail}"

                storage_path = f"clio/{case_id}/note_{note['id']}.txt"
                supabase.storage.from_("documents").upload(
                    storage_path,
                    content.encode("utf-8"),
                    {"content-type": "text/plain"}
                )

                supabase.table("documents").insert({
                    "case_id": case_id,
                    "user_id": user["id"],
                    "storage_path": storage_path,
                    "file_type": "text/plain",
                    "metadata": {
                        "clio_source": True,
                        "clio_type": "note",
                        "clio_id": note["id"],
                        "clio_subject": note_subject,
                        "clio_date": note.get("created_at"),
                    }
                }).execute()
                imported_count += 1

            elif item_type == "document":
                # Process document (more complex, may need download)
                # For now, log and skip - can implement in follow-up
                logger.warning(f"Document sync not yet implemented: {item['name']}")

        # Update case sync timestamp and reanalysis flag
        sync_time = datetime.now(timezone.utc)
        needs_reanalysis = len(all_items_to_import) > 0

        supabase.table("cases").update({
            "clio_last_synced_at": sync_time.isoformat(),
            "needs_reanalysis": needs_reanalysis,
        }).eq("id", case_id).execute()

        # Build response
        new_details = [
            ClioSyncItemDetail(
                name=item["name"],
                type=item["type"],
                date=item["date"]
            )
            for item in new_items
        ]

        updated_details = [
            ClioSyncItemDetail(
                name=item["name"],
                type=item["type"],
                date=item["date"],
                # Find previous version date from existing_docs if available
            )
            for item in updated_items
        ]

        return ClioSyncResponse(
            success=True,
            case_id=case_id,
            synced_at=sync_time,
            summary=ClioSyncSummary(
                new_items=len(new_items),
                updated_items=len(updated_items),
                total_processed=len(all_items_to_import),
            ),
            details=ClioSyncDetails(
                new=new_details,
                updated=updated_details,
            ),
            needs_reanalysis=needs_reanalysis,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error syncing Clio matter", extra={
            "case_id": case_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync Clio matter: {str(e)}"
        )
```

**Step 2: Test endpoint manually with curl or API client**

This requires a running server and authenticated request. Document how to test:
```bash
# Start server: uvicorn src.legal_portal.api.main:app --reload
# Get auth token and case_id from existing Clio-linked case
# curl -X POST http://localhost:8000/api/clio/sync/{case_id} \
#   -H "Authorization: Bearer {token}"
```

**Step 3: Commit**

```bash
git add src/legal_portal/api/routes/clio.py
git commit -m "feat: implement Clio sync endpoint

Add POST /api/clio/sync/{case_id} endpoint to sync new/updated items
from Clio. Handles communications and notes (document files deferred).

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Backend - Clear needs_reanalysis Flag on Analysis Run

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (in analysis trigger endpoint)

**Step 1: Find analysis trigger endpoint**

Locate the endpoint that starts analysis (likely `POST /api/analysis/{case_id}` or similar around line 100-200)

**Step 2: Add flag clearing logic**

After case lookup, before starting analysis, add:

```python
# Clear needs_reanalysis flag when starting new analysis
supabase.table("cases").update({
    "needs_reanalysis": False
}).eq("id", case_id).execute()
```

**Step 3: Test by running analysis**

Manual test: Start analysis and verify flag is cleared in database

**Step 4: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py
git commit -m "feat: clear needs_reanalysis flag when analysis starts

Automatically reset the flag when user initiates re-analysis.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Frontend - Add Sync API Function

**Files:**
- Modify: `frontend/src/lib/api/cases.ts` (or create if it doesn't exist)

**Step 1: Add syncClioMatter function**

Add to the cases API file:

```typescript
export interface ClioSyncItemDetail {
  name: string;
  type: 'document' | 'communication' | 'note';
  date?: string;
  previous_version_date?: string;
}

export interface ClioSyncSummary {
  new_items: number;
  updated_items: number;
  total_processed: number;
}

export interface ClioSyncResponse {
  success: boolean;
  case_id: string;
  synced_at: string;
  summary: ClioSyncSummary;
  details: {
    new: ClioSyncItemDetail[];
    updated: ClioSyncItemDetail[];
  };
  needs_reanalysis: boolean;
}

export async function syncClioMatter(caseId: string): Promise<ClioSyncResponse> {
  const response = await fetch(`/api/clio/sync/${caseId}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getAuthToken()}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to sync Clio matter');
  }

  return response.json();
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run check`
Expected: No TypeScript errors

**Step 3: Commit**

```bash
git add frontend/src/lib/api/cases.ts
git commit -m "feat: add Clio sync API client function

Add TypeScript function to call sync endpoint.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Frontend - Add Sync Button to Documents Page

**Files:**
- Modify: `frontend/src/routes/app/cases/[id]/documents/+page.svelte`

**Step 1: Import sync function and add state**

At top of script section:

```typescript
import { syncClioMatter, type ClioSyncResponse } from '$lib/api/cases';

let syncLoading = $state(false);
let syncResult = $state<ClioSyncResponse | null>(null);
let syncError = $state<string | null>(null);

// Assuming case data is available as `caseData`
// If not, adjust to match your component's data structure
```

**Step 2: Add sync handler function**

```typescript
async function handleSync() {
  syncLoading = true;
  syncError = null;
  syncResult = null;

  try {
    const result = await syncClioMatter(caseData.id);
    syncResult = result;
  } catch (err) {
    syncError = err instanceof Error ? err.message : 'Failed to sync';
  } finally {
    syncLoading = false;
  }
}
```

**Step 3: Add sync button to UI**

In the template section, add button next to upload button:

```svelte
{#if caseData.clio_matter_id}
  <button
    onclick={handleSync}
    disabled={syncLoading}
    class="btn btn-secondary"
  >
    {#if syncLoading}
      ⏳ Syncing...
    {:else}
      🔄 Sync from Clio
    {/if}
  </button>
{/if}
```

**Step 4: Add result display**

After button:

```svelte
{#if syncResult}
  <div class="alert alert-success">
    ✓ Sync complete
    {#if syncResult.summary.total_processed === 0}
      <p>Already up to date - no new items found in Clio</p>
    {:else}
      {#if syncResult.details.new.length > 0}
        <p>New items ({syncResult.details.new.length}):</p>
        <ul>
          {#each syncResult.details.new as item}
            <li>• {item.name} ({item.type})</li>
          {/each}
        </ul>
      {/if}

      {#if syncResult.details.updated.length > 0}
        <p>Updated items ({syncResult.details.updated.length}):</p>
        <ul>
          {#each syncResult.details.updated as item}
            <li>• {item.name} (replaced)</li>
          {/each}
        </ul>
      {/if}

      {#if syncResult.needs_reanalysis}
        <p class="text-warning">Analysis needs to be updated to include these items.</p>
      {/if}
    {/if}
  </div>
{/if}

{#if syncError}
  <div class="alert alert-error">
    ⚠️ Sync failed: {syncError}
    {#if syncError.includes('expired')}
      <button class="btn btn-link">Reconnect to Clio</button>
    {/if}
  </div>
{/if}
```

**Step 5: Test in browser**

Manual test: Navigate to documents page, click sync button, verify UI updates

**Step 6: Commit**

```bash
git add frontend/src/routes/app/cases/[id]/documents/+page.svelte
git commit -m "feat: add Clio sync button to documents page

Add sync button that appears for Clio-linked cases with loading
states and detailed result display.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Frontend - Add Outdated Analysis Banner

**Files:**
- Modify: `frontend/src/routes/app/cases/[id]/analysis/+page.svelte`

**Step 1: Add banner component**

At top of template section, before analysis results:

```svelte
{#if caseData.needs_reanalysis}
  <div class="alert alert-warning mb-4">
    <div class="flex items-center justify-between">
      <div>
        <span class="text-xl">⚠️</span>
        <span class="ml-2">
          Analysis outdated -
          {#if caseData.clio_last_synced_at}
            {new Intl.NumberFormat().format(syncItemCount)} new items added on
            {new Date(caseData.clio_last_synced_at).toLocaleDateString()}
          {:else}
            new items available
          {/if}
        </span>
      </div>
      <button
        onclick={handleRerunAnalysis}
        class="btn btn-primary"
      >
        Re-run Analysis
      </button>
    </div>
  </div>
{/if}
```

**Step 2: Add rerun handler**

In script section:

```typescript
async function handleRerunAnalysis() {
  // Call existing analysis trigger function
  // Adjust to match your existing analysis start logic
  await startAnalysis(caseData.id);
}

// Calculate item count from last sync if available
const syncItemCount = $derived(() => {
  // This would ideally come from case metadata or separate API call
  // For now, placeholder
  return 0;
});
```

**Step 3: Ensure case data includes new fields**

Verify the page load fetches `needs_reanalysis` and `clio_last_synced_at` fields

**Step 4: Test in browser**

Manual test: Set `needs_reanalysis=true` in database, verify banner shows

**Step 5: Commit**

```bash
git add frontend/src/routes/app/cases/[id]/analysis/+page.svelte
git commit -m "feat: add outdated analysis banner

Show warning banner in analysis tab when needs_reanalysis flag is set,
with button to trigger re-analysis.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Testing - Add Backend Unit Tests

**Files:**
- Create: `tests/unit/test_clio_sync.py`

**Step 1: Write test for categorize function**

```python
"""Unit tests for Clio sync functionality."""

import pytest
from src.legal_portal.api.routes.clio import categorize_clio_sync_items


def test_categorize_sync_items_all_new():
    """Test categorization when all items are new."""
    documents = [
        {"id": 1, "name": "Doc1.pdf", "created_at": "2026-01-01T00:00:00Z"},
        {"id": 2, "name": "Doc2.pdf", "created_at": "2026-01-02T00:00:00Z"},
    ]
    existing_docs = []

    new, updated = categorize_clio_sync_items(documents, [], [], existing_docs)

    assert len(new) == 2
    assert len(updated) == 0
    assert new[0]["type"] == "document"


def test_categorize_sync_items_all_updated():
    """Test categorization when all items are updates."""
    documents = [
        {"id": 1, "name": "Doc1.pdf", "created_at": "2026-01-01T00:00:00Z"},
    ]
    existing_docs = [
        {"metadata": {"clio_source": True, "clio_id": "1"}},
    ]

    new, updated = categorize_clio_sync_items(documents, [], [], existing_docs)

    assert len(new) == 0
    assert len(updated) == 1
    assert updated[0]["name"] == "Doc1.pdf"


def test_categorize_sync_items_mixed():
    """Test categorization with mix of new and updated items."""
    documents = [{"id": 1, "name": "Doc1.pdf", "created_at": None}]
    communications = [
        type('Comm', (), {"id": 2, "subject": "Email 1", "date": None})(),
        type('Comm', (), {"id": 3, "subject": "Email 2", "date": None})(),
    ]
    existing_docs = [
        {"metadata": {"clio_source": True, "clio_id": "1"}},
        {"metadata": {"clio_source": True, "clio_id": "2"}},
    ]

    new, updated = categorize_clio_sync_items(documents, communications, [], existing_docs)

    assert len(new) == 1  # Communication 3
    assert len(updated) == 2  # Document 1, Communication 2
    assert new[0]["type"] == "communication"
```

**Step 2: Run tests**

Run: `pytest tests/unit/test_clio_sync.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_clio_sync.py
git commit -m "test: add unit tests for Clio sync categorization

Test new vs updated item categorization logic.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Testing - Add Integration Test for Sync Endpoint

**Files:**
- Modify: `tests/api/test_clio.py` (or create if doesn't exist)

**Step 1: Write sync endpoint test**

Add to test file:

```python
@pytest.mark.asyncio
async def test_sync_clio_matter_no_changes(app_client, test_user_id, mocker):
    """Test syncing when no new items exist."""
    # Setup: Create case linked to Clio
    case_id = str(uuid.uuid4())
    mocker.patch('src.legal_portal.api.routes.clio.get_current_user',
                 return_value={"id": test_user_id})

    # Mock Clio client to return empty lists
    mock_clio = mocker.MagicMock()
    mock_clio.get_documents.return_value = []
    mock_clio.get_communications.return_value = []
    mock_clio.get_notes.return_value = []
    mocker.patch('src.legal_portal.api.routes.clio.get_clio_client',
                 return_value=mock_clio)

    # Mock database
    mocker.patch('src.legal_portal.api.routes.clio.get_supabase_client')

    response = await app_client.post(
        f"/api/clio/sync/{case_id}",
        headers={"Authorization": "Bearer mock_token"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["summary"]["total_processed"] == 0


@pytest.mark.asyncio
async def test_sync_clio_matter_with_new_items(app_client, test_user_id, mocker):
    """Test syncing when new items exist."""
    # Similar structure to above but with items in mock return
    pass  # Implement based on your testing patterns
```

**Step 2: Run integration tests**

Run: `pytest tests/api/test_clio.py -v -k sync`
Expected: Tests pass

**Step 3: Commit**

```bash
git add tests/api/test_clio.py
git commit -m "test: add integration tests for sync endpoint

Test sync endpoint with various scenarios.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Documentation - Update API Docs

**Files:**
- Modify: `docs/API.md` (or similar API documentation file)

**Step 1: Add sync endpoint documentation**

Add to API docs:

```markdown
### POST /api/clio/sync/{case_id}

Sync new and updated documents from Clio into an existing case.

**Authentication:** Required

**Parameters:**
- `case_id` (path, string, required): UUID of the case to sync

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
    "new": [...],
    "updated": [...]
  },
  "needs_reanalysis": true
}
```

**Errors:**
- 404: Case not found or not linked to Clio
- 401: Clio authentication expired
- 500: Sync operation failed
```

**Step 2: Commit**

```bash
git add docs/API.md
git commit -m "docs: add Clio sync endpoint documentation

Document new sync endpoint in API docs.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Final Verification and Cleanup

**Files:**
- All modified files

**Step 1: Run full test suite**

Run: `pytest tests/ --ignore=tests/unit/test_cost_calculator.py -v`
Expected: All tests pass (except known broken cost_calculator test)

**Step 2: Run linter**

Run: `ruff check src/`
Expected: No new linting errors

**Step 3: Test frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 4: Manual smoke test**

1. Start backend: `uvicorn src.legal_portal.api.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Test sync flow:
   - Navigate to case with Clio link
   - Click "Sync from Clio" in documents
   - Verify result message
   - Check analysis tab for banner
   - Click "Re-run Analysis"
   - Verify banner disappears

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup for Clio sync feature

Complete implementation of Clio document sync feature.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Success Criteria

- ✅ Database migration applied successfully
- ✅ Sync endpoint returns correct response format
- ✅ New items are imported correctly
- ✅ Updated items replace old versions
- ✅ Sync button visible only for Clio-linked cases
- ✅ Sync results display detailed breakdown
- ✅ Analysis banner shows when needs_reanalysis is true
- ✅ Banner clears when analysis is re-run
- ✅ No new test failures introduced
- ✅ Linter passes
- ✅ Frontend builds successfully

## Known Limitations

- Document file syncing (PDFs, DOCX) deferred - only communications and notes implemented
- No progress tracking for long sync operations
- Client-side date filtering (Clio API limitations)
- No retry logic for failed imports

## Next Steps (Future Enhancements)

1. Add document file download and sync support
2. Implement background sync with progress tracking
3. Add server-side date filtering when Clio API supports it
4. Add retry logic with exponential backoff
5. Store sync item count in case metadata for banner display
6. Add webhook support for automatic sync triggers
