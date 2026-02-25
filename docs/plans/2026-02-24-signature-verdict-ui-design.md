# Design: Inline Signature Verdict UI in VerificationHub

**Date:** 2026-02-24
**Status:** Approved

## Summary

Add inline signature verdict buttons (Signed ✓ / Not Signed ✗ / Unclear…) to the VerificationHub document viewer modal footer, so attorneys can review a PDF and record their verdict without leaving the modal.

## Architecture

All changes are contained in a single file: `frontend/src/lib/components/VerificationHub.svelte`.

No new components, no backend changes. The `/api/documents/{id}/verify` PATCH endpoint already accepts `signature_verification: "signed" | "not_signed" | "unknown"` and `signature_verification_notes: string`.

## Components

### State additions (~line 52, near `viewingDocument`)

```typescript
let verdictSaving = $state(false);
let verdictNotes = $state('');
let showNotesInput = $state(false);
```

### Generalized handler

Replace the existing `handleMarkSigned(doc)` with `handleSetVerdict(verdict, notes?)`:

```typescript
async function handleSetVerdict(verdict: 'signed' | 'not_signed' | 'unknown', notes?: string) {
    if (!viewingDocument) return;
    verdictSaving = true;
    try {
        const { session } = await getSecureSession();
        const response = await fetch(`${getApiUrl()}/api/documents/${viewingDocument.id}/verify`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.access_token}` },
            body: JSON.stringify({
                is_verified: Boolean(viewingDocument.is_verified),
                is_flagged_as_junk: Boolean(viewingDocument.is_flagged_as_junk),
                signature_verification: verdict,
                ...(notes ? { signature_verification_notes: notes } : {}),
            }),
        });
        if (!response.ok) throw new Error('Failed to save signature verdict');
        // Optimistic local update so buttons reflect immediately
        if (!viewingDocument.metadata) viewingDocument.metadata = {};
        viewingDocument.metadata.signature_verification = { status: verdict, notes: notes || '' };
        showNotesInput = false;
        verdictNotes = '';
        const label = verdict === 'signed' ? 'Signed' : verdict === 'not_signed' ? 'Not Signed' : 'Unclear';
        toastStore.success(`Marked as ${label}`);
        await onDocumentsUpdated();
    } catch (error: any) {
        toastStore.error(error.message);
    } finally {
        verdictSaving = false;
    }
}
```

Keep `handleMarkSigned(doc)` as a thin wrapper calling `handleSetVerdict('signed')` so existing `DocumentCard` `onMarkSigned` callbacks continue to work unchanged.

## Data Flow

1. User clicks "View" on a DocumentCard → `viewingDocument` set, modal opens
2. Footer reads `viewingDocument.metadata?.signature_verification?.status` to show current verdict state
3. User clicks "Signed ✓" → `handleSetVerdict('signed')` → API PATCH → optimistic update + toast + list refresh
4. User clicks "Not Signed ✗" → `handleSetVerdict('not_signed')` → same
5. User clicks "Unclear…" → `showNotesInput = true`, notes textarea appears
6. User types notes, clicks "Save" → `handleSetVerdict('unknown', verdictNotes)`
7. User can dismiss notes input without saving via "Cancel"

## UI / Footer Layout

```
[ ✓ Signed ] [ ✗ Not Signed ] [ ? Unclear… ]                [Close]
                        ↓ when Unclear active:
[ ─────────────────────────────────────────── ]
[ Notes: [_________________________] [Save] [Cancel] ]
```

- **Signed ✓**: green ring/bg when current status is `signed`
- **Not Signed ✗**: red ring/bg when current status is `not_signed`
- **Unclear…**: amber ring/bg when current status is `unknown`
- Buttons disabled while `verdictSaving = true`
- Notes input only appears when "Unclear…" is clicked and not yet saved

## Error Handling

- `verdictSaving` boolean prevents double-submit
- On API failure: `toastStore.error()` (existing pattern)
- On success: `toastStore.success()` + optimistic metadata update

## Testing

1. Open VerificationHub, click View on any document
2. Click "Signed ✓" → toast appears, button highlights green, DocumentCard badge updates
3. Reopen viewer for same doc → "Signed ✓" button is pre-highlighted
4. Click "Not Signed ✗" → updates to red
5. Click "Unclear…" → notes input appears; type text, click Save → updates to amber with notes stored
6. Click "Unclear…" then "Cancel" → no API call, no state change
7. Existing "Mark Signed" button on DocumentCard still works (calls `handleMarkSigned` → wrapper)
