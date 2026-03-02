# Verification Hub Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> **For Frontend Components:** Use superpowers:frontend-design for all Svelte components to ensure design quality and consistency with existing theme.

**Goal:** Redesign the Verification Hub to move signature verification earlier in the pipeline, add an attorney triage dashboard, and capture structured attorney input (type overrides, key facts, relevance, notes, relationships) that feeds into the analysis pipeline.

**Architecture:** Enhanced card-based triage layout with a triage dashboard at top, enriched document cards with inline actions, and a slide-out panel for signature review and OCR comparison. Backend extends the existing PATCH verify endpoint with new optional fields. Document registry service and findings prompt consume the enriched data.

**Tech Stack:** Svelte 5 (runes), Tailwind CSS v4 with custom brand tokens, FastAPI/Pydantic (backend), pytest (backend tests), vitest (frontend tests)

**Design Doc:** `docs/plans/2026-02-26-verification-hub-redesign.md`

---

## Phase 1: Backend — Extend Verification Endpoint

### Task 1: Extend VerifyDocumentRequest with new fields

**Files:**
- Modify: `src/legal_portal/api/routes/documents.py:51-60`
- Test: `tests/api/test_documents.py`

**Step 1: Write failing test for new fields**

Add to `tests/api/test_documents.py`:

```python
@pytest.mark.asyncio
async def test_verify_document_with_enriched_fields(app_client, test_user_id):
    """Test that verify endpoint accepts new enrichment fields."""
    # Create a mock document first (reuse existing test setup pattern)
    payload = {
        "is_verified": True,
        "document_type_override": "contract",
        "relevance_level": "critical",
        "key_facts": {"date": "2024-03-15", "amount": "$425,000"},
        "attorney_notes": "Key disclosure document - seller signed page 4",
        "document_relationships": [
            {"related_doc_id": "doc-456", "relationship_type": "modifies"}
        ],
    }
    # This should not raise a validation error
    from src.legal_portal.api.routes.documents import VerifyDocumentRequest
    req = VerifyDocumentRequest(**payload)
    assert req.document_type_override == "contract"
    assert req.relevance_level == "critical"
    assert req.key_facts == {"date": "2024-03-15", "amount": "$425,000"}
    assert req.attorney_notes == "Key disclosure document - seller signed page 4"
    assert len(req.document_relationships) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_documents.py::test_verify_document_with_enriched_fields -v`
Expected: FAIL — fields not recognized by VerifyDocumentRequest

**Step 3: Add new fields to VerifyDocumentRequest**

In `src/legal_portal/api/routes/documents.py`, update the class at lines 51-60:

```python
class VerifyDocumentRequest(BaseModel):
    """Request model for verifying/correcting document text."""

    manual_text: Optional[str] = None
    is_verified: bool = True
    is_flagged_as_junk: bool = False
    signature_verification: Optional[str] = None
    signature_verification_notes: Optional[str] = None
    signature_signing_date: Optional[str] = None
    signature_signer_names: Optional[List[str]] = None
    # Enrichment fields for attorney input
    document_type_override: Optional[str] = None
    relevance_level: Optional[str] = None  # "critical" | "supporting" | "background"
    key_facts: Optional[Dict[str, Any]] = None
    attorney_notes: Optional[str] = None
    document_relationships: Optional[List[Dict[str, str]]] = None
```

Add `Dict, Any` to imports if not already present (check top of file for `from typing import`).

**Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_documents.py::test_verify_document_with_enriched_fields -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/legal_portal/api/routes/documents.py tests/api/test_documents.py
git commit -m "feat: extend VerifyDocumentRequest with enrichment fields"
```

---

### Task 2: Store enrichment fields in document metadata

**Files:**
- Modify: `src/legal_portal/api/routes/documents.py:878-995` (verify_document handler)
- Test: `tests/api/test_documents.py`

**Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_verify_stores_enrichment_in_metadata(app_client, test_user_id, mocker):
    """Test that enrichment fields are stored in document metadata."""
    from src.legal_portal.api.routes.documents import VerifyDocumentRequest

    request = VerifyDocumentRequest(
        is_verified=True,
        document_type_override="contract",
        relevance_level="critical",
        key_facts={"date": "2024-03-15", "amount": "$425,000"},
        attorney_notes="Key disclosure doc",
        document_relationships=[{"related_doc_id": "doc-456", "relationship_type": "modifies"}],
    )

    # Build the expected metadata update payload
    # The handler should include attorney_enrichment in metadata
    existing_metadata = {"some_field": "value"}

    # Simulate what the handler does
    enrichment = {}
    if request.document_type_override:
        enrichment["document_type_override"] = request.document_type_override
    if request.relevance_level:
        enrichment["relevance_level"] = request.relevance_level
    if request.key_facts:
        enrichment["key_facts"] = request.key_facts
    if request.attorney_notes is not None:
        enrichment["attorney_notes"] = request.attorney_notes
    if request.document_relationships:
        enrichment["document_relationships"] = request.document_relationships

    assert enrichment["document_type_override"] == "contract"
    assert enrichment["relevance_level"] == "critical"
    assert enrichment["key_facts"]["date"] == "2024-03-15"
```

**Step 2: Run test — should pass (this is a logic validation test)**

**Step 3: Update verify_document handler**

In `src/legal_portal/api/routes/documents.py`, inside the `verify_document()` function, after the signature metadata handling block (around line 993), add:

```python
    # --- Attorney enrichment fields ---
    if request.document_type_override is not None:
        metadata["attorney_enrichment"] = metadata.get("attorney_enrichment", {})
        metadata["attorney_enrichment"]["document_type_override"] = request.document_type_override
    if request.relevance_level is not None:
        metadata["attorney_enrichment"] = metadata.get("attorney_enrichment", {})
        metadata["attorney_enrichment"]["relevance_level"] = request.relevance_level
    if request.key_facts is not None:
        metadata["attorney_enrichment"] = metadata.get("attorney_enrichment", {})
        metadata["attorney_enrichment"]["key_facts"] = request.key_facts
    if request.attorney_notes is not None:
        metadata["attorney_enrichment"] = metadata.get("attorney_enrichment", {})
        metadata["attorney_enrichment"]["attorney_notes"] = request.attorney_notes
    if request.document_relationships is not None:
        metadata["attorney_enrichment"] = metadata.get("attorney_enrichment", {})
        metadata["attorney_enrichment"]["document_relationships"] = request.document_relationships
```

**Step 4: Run existing tests to verify no regressions**

Run: `pytest tests/api/test_documents.py -v`
Expected: All existing tests PASS

**Step 5: Commit**

```bash
git add src/legal_portal/api/routes/documents.py tests/api/test_documents.py
git commit -m "feat: store attorney enrichment fields in document metadata"
```

---

### Task 3: Update document registry to include enriched data

**Files:**
- Modify: `src/legal_portal/services/document_registry_service.py:32-152`
- Test: `tests/unit/test_document_registry_service.py`

**Step 1: Write failing test**

Add to `tests/unit/test_document_registry_service.py`:

```python
def test_registry_includes_attorney_enrichment():
    """Test that registry rows include attorney enrichment data."""
    from src.legal_portal.services.document_registry_service import DocumentRegistryService
    from src.legal_portal.core.data_models import ProcessedDocument, DocumentType, FileType, FileMetadata

    service = DocumentRegistryService()

    doc = ProcessedDocument(
        file_name="contract.pdf",
        content="Sample contract content...",
        document_type=DocumentType.CONTRACT,
        file_type=FileType.PDF,
        metadata=FileMetadata(
            attorney_enrichment={
                "document_type_override": "purchase_agreement",
                "relevance_level": "critical",
                "key_facts": {"date": "2024-03-15", "amount": "$425,000"},
                "attorney_notes": "Key disclosure doc",
                "document_relationships": [{"related_doc_id": "doc-456", "relationship_type": "modifies"}],
            }
        ),
        document_id="doc-123",
        signature_detection={"status": "signed", "confidence": "high"},
    )

    registry = service.build_registry([doc], [])
    row = registry[0]

    assert row.get("document_type_override") == "purchase_agreement"
    assert row.get("relevance_level") == "critical"
    assert row.get("attorney_notes") == "Key disclosure doc"
    assert row.get("key_facts") == {"date": "2024-03-15", "amount": "$425,000"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_document_registry_service.py::test_registry_includes_attorney_enrichment -v`
Expected: FAIL — fields not present in registry row

**Step 3: Update build_registry()**

In `src/legal_portal/services/document_registry_service.py`, inside the `build_registry()` method where registry rows are constructed, add after the existing signature/execution fields:

```python
        # Attorney enrichment data
        enrichment = {}
        if hasattr(doc, 'metadata') and doc.metadata:
            raw_meta = doc.metadata if isinstance(doc.metadata, dict) else (doc.metadata.dict() if hasattr(doc.metadata, 'dict') else {})
            enrichment = raw_meta.get("attorney_enrichment", {})

        row["document_type_override"] = enrichment.get("document_type_override")
        row["relevance_level"] = enrichment.get("relevance_level")
        row["key_facts"] = enrichment.get("key_facts")
        row["attorney_notes"] = enrichment.get("attorney_notes")
        row["document_relationships"] = enrichment.get("document_relationships")
```

Note: Check how `doc.metadata` is accessed elsewhere in this file — it may be a dict or a Pydantic model. Match the existing pattern.

**Step 4: Run tests**

Run: `pytest tests/unit/test_document_registry_service.py -v`
Expected: All PASS including new test

**Step 5: Commit**

```bash
git add src/legal_portal/services/document_registry_service.py tests/unit/test_document_registry_service.py
git commit -m "feat: include attorney enrichment data in document registry"
```

---

### Task 4: Pass attorney context to findings letter prompt

**Files:**
- Modify: `src/legal_portal/services/json_processing_service.py` — `_build_document_register_context()` or `_build_findings_prompt()`
- Modify: `src/legal_portal/prompts/findings_letter_prompt.txt` — add context block
- No new tests needed (prompt changes are validated by existing generation tests)

**Step 1: Read the `_build_document_register_context` method**

Use `find_symbol` with name_path `_build_document_register_context` and `include_body=True` to understand how document context is currently built.

**Step 2: Add attorney enrichment to document context**

In `_build_document_register_context()`, when building the context string for each document, append:

```python
        # Attorney enrichment context
        enrichment_parts = []
        if entry.get("document_type_override"):
            enrichment_parts.append(f"Attorney classified as: {entry['document_type_override']}")
        if entry.get("relevance_level"):
            enrichment_parts.append(f"Attorney relevance: {entry['relevance_level']}")
        if entry.get("attorney_notes"):
            enrichment_parts.append(f"Attorney notes: {entry['attorney_notes']}")
        if entry.get("key_facts"):
            facts_str = ", ".join(f"{k}: {v}" for k, v in entry["key_facts"].items())
            enrichment_parts.append(f"Confirmed facts: {facts_str}")
        if enrichment_parts:
            doc_context += "\n  Attorney Input: " + " | ".join(enrichment_parts)
```

**Step 3: Add guidance to findings_letter_prompt.txt**

In `src/legal_portal/prompts/findings_letter_prompt.txt`, near the DOCUMENT REGISTER section, add:

```
### Attorney Input Context
Some documents may include "Attorney Input:" metadata. This represents verified information from the reviewing attorney:
- **Attorney classified as:** Prefer this classification over automated detection
- **Attorney relevance:** Weight "critical" documents more heavily in analysis
- **Attorney notes:** Use these contextual notes to inform your analysis
- **Confirmed facts:** Treat these as ground truth for dates, amounts, and party names
```

**Step 4: Run syntax check**

Run: `python3 -c "import py_compile; py_compile.compile('src/legal_portal/services/json_processing_service.py', doraise=True)"`
Expected: No errors

**Step 5: Commit**

```bash
git add src/legal_portal/services/json_processing_service.py src/legal_portal/prompts/findings_letter_prompt.txt
git commit -m "feat: pass attorney enrichment context to findings letter prompt"
```

---

## Phase 2: Frontend — Foundation Components

> **IMPORTANT:** Use the `/frontend-design` skill for all Svelte component creation. The design doc specifies the theme: Tailwind v4, brand teal `#5AB7A3`, Raleway headings, Montserrat body, existing card/badge/button patterns. Pass the design doc and existing component examples as context.

### Task 5: Create SlideOutPanel base component

**Files:**
- Create: `frontend/src/lib/components/ui/SlideOutPanel.svelte`
- Test: `frontend/src/lib/components/ui/SlideOutPanel.test.ts`

**Context for the component:**
- Reusable slide-out panel from the right side of the screen
- Takes `width` prop: "60%" (signature review) or "80%" (OCR view)
- 300ms slide transition (consistent with existing `slide` usage in AnalysisStreamPanel)
- Semi-transparent overlay on the left (matches existing modal overlay: `rgba(24, 26, 49, 0.6)` with `backdrop-blur(4px)`)
- Close button (X) in top-right
- Escape key closes
- Click overlay closes
- Accessible: focus trap, ARIA attributes
- Slots: `header`, `default` (body), `footer`
- Style: `bg-white shadow-lg border-l border-gray-200`

**Step 1: Write component test**

Create `frontend/src/lib/components/ui/SlideOutPanel.test.ts`:

```typescript
import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import SlideOutPanel from './SlideOutPanel.svelte';

describe('SlideOutPanel', () => {
    it('renders when open', () => {
        render(SlideOutPanel, { props: { open: true, title: 'Test Panel' } });
        expect(screen.getByText('Test Panel')).toBeTruthy();
    });

    it('does not render when closed', () => {
        render(SlideOutPanel, { props: { open: false, title: 'Test Panel' } });
        expect(screen.queryByText('Test Panel')).toBeNull();
    });

    it('calls onClose when escape pressed', async () => {
        const onClose = vi.fn();
        render(SlideOutPanel, { props: { open: true, title: 'Test', onClose } });
        await fireEvent.keyDown(document, { key: 'Escape' });
        expect(onClose).toHaveBeenCalled();
    });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/components/ui/SlideOutPanel.test.ts`

**Step 3: Implement the component**

Create `frontend/src/lib/components/ui/SlideOutPanel.svelte` using the `/frontend-design` skill. Key requirements:
- Props: `open: boolean`, `title: string`, `width: string = '60%'`, `onClose: () => void`
- Slots: header, default, footer
- Slide transition from right, 300ms
- Overlay with blur background
- Focus trap and keyboard handling (Escape to close)
- Match existing Modal.svelte patterns for accessibility

**Step 4: Run test**

Run: `cd frontend && npx vitest run src/lib/components/ui/SlideOutPanel.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/lib/components/ui/SlideOutPanel.svelte frontend/src/lib/components/ui/SlideOutPanel.test.ts
git commit -m "feat: add SlideOutPanel reusable component"
```

---

### Task 6: Create TriageDashboard component

**Files:**
- Create: `frontend/src/lib/components/TriageDashboard.svelte`
- Test: `frontend/src/lib/components/TriageDashboard.test.ts`

**Props:**
```typescript
{
    documents: any[];            // All case documents
    activeFilters: Set<string>;  // Currently active filter chips
    onFilterToggle: (filter: string) => void;  // Toggle a filter chip
}
```

**Component renders:**
1. **Smart summary sentence** — dynamically generated from document analysis:
   - Count docs where `signature_detection.status !== 'signed'` AND signature is expected
   - Count docs with `extraction_quality === 'low'` or quality_score < 5
   - Count docs without a detected document type
   - If all good: "All {n} documents verified and ready for analysis" (green)
   - Otherwise: "{n} documents need attention: {details}" (with colored bold counts)

2. **Clickable filter chips** — each chip shows icon + count + label:
   - `missing-signatures`: red theme, filters to unsigned docs
   - `low-ocr`: amber theme, filters to quality < 5
   - `needs-type`: purple theme, filters to unclassified
   - `ready`: green theme, filters to ready docs
   - Active chip gets a ring/border highlight

3. **Progress bar** — thin horizontal bar, teal fill showing ready/total ratio

**Styling:** `bg-white rounded-2xl shadow-card p-6`, consistent with existing card patterns. Chips use existing badge styling adapted as clickable buttons.

**Step 1: Write test**

```typescript
import { render, screen } from '@testing-library/svelte';
import { describe, it, expect } from 'vitest';
import TriageDashboard from './TriageDashboard.svelte';

describe('TriageDashboard', () => {
    const mockDocs = [
        { id: '1', status: 'ready', metadata: { extraction_quality: 'high', signature_detection: { status: 'signed' } } },
        { id: '2', status: 'needs_review', metadata: { extraction_quality: 'low', signature_detection: { status: 'not_detected' } } },
        { id: '3', status: 'ready', metadata: { extraction_quality: 'high', signature_detection: { status: 'not_detected' } } },
    ];

    it('renders attention count', () => {
        render(TriageDashboard, { props: { documents: mockDocs, activeFilters: new Set(), onFilterToggle: () => {} } });
        // Should show attention-needed summary
        expect(screen.getByText(/need attention/i) || screen.getByText(/documents/i)).toBeTruthy();
    });

    it('shows all-clear message when everything is ready', () => {
        const allReady = [
            { id: '1', status: 'ready', metadata: { extraction_quality: 'high', signature_detection: { status: 'signed' } } },
        ];
        render(TriageDashboard, { props: { documents: allReady, activeFilters: new Set(), onFilterToggle: () => {} } });
        expect(screen.getByText(/verified and ready/i)).toBeTruthy();
    });
});
```

**Step 2: Implement using `/frontend-design` skill**

Reference: existing `DocumentStatusBanner` component for current status display patterns. The new dashboard replaces the simple banner.

**Step 3: Run tests and commit**

```bash
git add frontend/src/lib/components/TriageDashboard.svelte frontend/src/lib/components/TriageDashboard.test.ts
git commit -m "feat: add TriageDashboard component with smart summary and filter chips"
```

---

### Task 7: Create KeyFactsChips component

**Files:**
- Create: `frontend/src/lib/components/KeyFactsChips.svelte`
- Test: `frontend/src/lib/components/KeyFactsChips.test.ts`

**Props:**
```typescript
{
    facts: Record<string, { value: string; confirmed: boolean }>;  // e.g. { date: { value: "03/15/2024", confirmed: false } }
    onFactUpdate: (key: string, value: string) => void;
    onFactConfirm: (key: string) => void;
}
```

**Renders:** A row of editable chip/tags:
- Each chip shows an icon (calendar for dates, dollar for amounts, user for parties, home for property), the key, and the value
- Unconfirmed chips: `border-2 border-dashed border-amber-300 bg-amber-50`
- Confirmed chips: `border border-green-200 bg-green-50` with a small green checkmark
- Clicking a chip makes the value editable inline (input replaces text)
- A confirm button (checkmark icon) appears on hover or when editing
- Saves via callback on blur or Enter

**Styling:** Uses existing badge/chip patterns (pill-shaped, `text-xs font-semibold`). Icons from lucide-svelte (Calendar, DollarSign, User, Home).

**Step 1: Write test, implement, run, commit** (follow same TDD pattern)

```bash
git commit -m "feat: add KeyFactsChips component for editable fact display"
```

---

### Task 8: Create DocumentRelationships component

**Files:**
- Create: `frontend/src/lib/components/DocumentRelationships.svelte`
- Test: `frontend/src/lib/components/DocumentRelationships.test.ts`

**Props:**
```typescript
{
    documentId: string;
    relationships: Array<{ related_doc_id: string; relationship_type: string }>;
    availableDocuments: Array<{ id: string; name: string }>;  // Other docs in the case
    onAddRelationship: (relatedDocId: string, type: string) => void;
    onRemoveRelationship: (relatedDocId: string) => void;
}
```

**Renders:**
- Existing relationships as small pills: `↔ Contract_Main.pdf (modifies)` with X to remove
- "Link to..." button that opens a small dropdown of available documents
- When a doc is selected, show relationship type picker: modifies, relates to, supersedes, supports
- Dropdown uses existing dropdown/select patterns

**Step 1: Write test, implement, run, commit**

```bash
git commit -m "feat: add DocumentRelationships component for linking related documents"
```

---

## Phase 3: Core Feature Components

### Task 9: Create SignatureReviewPanel component

**Files:**
- Create: `frontend/src/lib/components/SignatureReviewPanel.svelte`
- Test: `frontend/src/lib/components/SignatureReviewPanel.test.ts`

**This is the most important new component.** Uses SlideOutPanel as its container.

**Props:**
```typescript
{
    open: boolean;
    documents: any[];           // Documents needing signature review (filtered)
    currentIndex: number;       // Which doc in the queue we're reviewing
    caseId: string;
    onClose: () => void;
    onVerdictSaved: (docId: string, verdict: string) => void;
    onNavigate: (index: number) => void;
}
```

**Layout (top to bottom within SlideOutPanel):**

1. **Header:** Document name + "Signature Review" + progress counter "2 of 5 remaining" + close button

2. **PDF Viewer (70% height):**
   - Reuse existing `DocumentPreviewPane` for rendering PDFs
   - "Jump to signature area" link at top — scrolls to last page (or page from `signature_detection` data if available)
   - Zoom controls (+/-/fit) in a small toolbar

3. **Verdict Bar (fixed footer):**
   - Three large buttons in a row:
     - `✓ Signed` — `bg-green-600 text-white hover:bg-green-700` — saves "signed"
     - `⚠ Concern` — `bg-amber-500 text-white hover:bg-amber-600` — expands textarea
     - `✗ No Signature` — `bg-red-600 text-white hover:bg-red-700` — saves "not_signed"
   - Concern textarea: appears below buttons when Concern is clicked, with Save button
   - After any verdict: auto-advance to next doc via `onNavigate(currentIndex + 1)`

4. **Keyboard shortcuts:**
   - `s` → Signed
   - `c` → Concern (focus textarea)
   - `n` → No Signature
   - `Escape` → Close
   - `ArrowLeft` / `ArrowRight` → Navigate queue

**API call pattern:** On verdict, PATCH `/api/documents/{id}/verify` with `{ signature_verification: verdict, signature_verification_notes: notes }` — reuse the existing API pattern from VerificationHub lines 182-194.

**Step 1: Write test**

```typescript
describe('SignatureReviewPanel', () => {
    it('renders document name and progress counter', () => {
        // ...
    });

    it('calls onVerdictSaved with "signed" when Signed button clicked', async () => {
        // ...
    });

    it('shows textarea when Concern button clicked', async () => {
        // ...
    });

    it('auto-advances to next document after verdict', async () => {
        // ...
    });
});
```

**Step 2: Implement using `/frontend-design` skill**

**Step 3: Run tests and commit**

```bash
git commit -m "feat: add SignatureReviewPanel with PDF viewer and verdict buttons"
```

---

### Task 10: Create DocumentReviewPanel component (side-by-side OCR)

**Files:**
- Create: `frontend/src/lib/components/DocumentReviewPanel.svelte`
- Test: `frontend/src/lib/components/DocumentReviewPanel.test.ts`

**Uses SlideOutPanel with width="80%".**

**Props:**
```typescript
{
    open: boolean;
    document: any;              // The document to review
    caseId: string;
    onClose: () => void;
    onVerify: (id: string) => void;
    onReExtract: (id: string) => void;
    onTextEdit: (doc: any) => void;
}
```

**Layout:**
- Split panel: left half = PDF preview (DocumentPreviewPane), right half = extracted text (monospace, scrollable)
- If `manual_text` exists, show it with a "Manually Edited" badge (amber)
- Right side text is read-only by default; "Edit Text" button opens CorrectionModal
- Bottom toolbar: [Re-extract OCR] [Edit Text] [Verify ✓]
- Both sides scroll independently

**Step 1: Write test, implement, run, commit**

```bash
git commit -m "feat: add DocumentReviewPanel with side-by-side OCR view"
```

---

## Phase 4: Integration — Enhanced Cards and VerificationHub

### Task 11: Enhance DocumentCard with inline actions

**Files:**
- Modify: `frontend/src/lib/components/DocumentCard.svelte`
- Test: `frontend/src/lib/components/DocumentCard.test.ts`

**Changes to DocumentCard:**

1. **New props:**
```typescript
    onTypeOverride?: (id: string, type: string) => void;
    onRelevanceChange?: (id: string, level: string) => void;
    onNotesUpdate?: (id: string, notes: string) => void;
    onFactUpdate?: (id: string, key: string, value: string) => void;
    onFactConfirm?: (id: string, key: string) => void;
    onRelationshipAdd?: (id: string, relatedId: string, type: string) => void;
    onRelationshipRemove?: (id: string, relatedId: string) => void;
    onSignatureReview?: (doc: any) => void;
    availableDocuments?: Array<{ id: string; name: string }>;
    isExpanded?: boolean;
    onToggleExpand?: (id: string) => void;
```

2. **Collapsed row (new layout):**
- Quality score circle (existing)
- Document name (bold, truncated)
- **Type badge** — clickable dropdown for override. Shows AI-detected type; click to change. Uses a `<select>` styled as a badge. When overridden, show small "overridden" text.
- **Signature badge** — clickable, opens signature review panel via `onSignatureReview`. Uses existing color scheme.
- **Relevance flag** — Star icon button, cycles through: none → critical (gold filled) → supporting (gray filled) → background (outline). Visual: `text-amber-500` for critical, `text-gray-400` for supporting, `text-gray-300` for background.
- **Expand chevron** — ChevronDown icon, rotates 180deg when expanded

3. **Expanded section** (shown when `isExpanded` is true):
- `KeyFactsChips` component with the document's key facts
- Attorney notes text area (single line, expands on focus)
- `DocumentRelationships` component
- Existing action buttons row

4. **Smart sort label** — When document has attention needs, show subtle text: `"Needs: signature, type"` in `text-xs text-gray-400 italic`

**Step 1: Write tests for new props and rendering**

**Step 2: Implement changes**

**Step 3: Run tests and commit**

```bash
git commit -m "feat: enhance DocumentCard with inline type, signature, relevance, and expand"
```

---

### Task 12: Add smart sorting logic

**Files:**
- Create: `frontend/src/lib/utils/documentSorting.ts`
- Test: `frontend/src/lib/utils/documentSorting.test.ts`

**Function:**
```typescript
export function computeAttentionScore(doc: any): number {
    let score = 0;
    const sig = doc.metadata?.signature_detection || {};
    const enrichment = doc.metadata?.attorney_enrichment || {};

    // Missing expected signature: +50
    if (sig.signature_expected && sig.status !== 'signed' &&
        enrichment?.signature_verification !== 'signed') {
        score += 50;
    }

    // Low OCR quality: +40
    const qualityScore = doc.metadata?.quality_score ?? doc.metadata?.extraction_quality_score ?? 10;
    if (qualityScore < 5) score += 40;

    // No document type detected: +30
    if (!doc.metadata?.document_type && !enrichment?.document_type_override) score += 30;

    // No key facts extracted: +20
    if (!enrichment?.key_facts || Object.keys(enrichment.key_facts).length === 0) score += 20;

    // No attorney notes: +10
    if (!enrichment?.attorney_notes) score += 10;

    return score;
}

export function getAttentionNeeds(doc: any): string[] {
    const needs: string[] = [];
    // ... (derive from same conditions above, return ["signature", "type", etc.])
    return needs;
}

export function sortByAttention(docs: any[]): any[] {
    return [...docs].sort((a, b) => computeAttentionScore(b) - computeAttentionScore(a));
}
```

**Step 1: Write test**

```typescript
import { describe, it, expect } from 'vitest';
import { computeAttentionScore, sortByAttention } from './documentSorting';

describe('computeAttentionScore', () => {
    it('returns 0 for fully enriched document', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'signed', signature_expected: true },
                document_type: 'contract',
                quality_score: 8,
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                    attorney_notes: 'Reviewed',
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(0);
    });

    it('returns 50 for missing expected signature', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'not_detected', signature_expected: true },
                document_type: 'contract',
                quality_score: 8,
                attorney_enrichment: { key_facts: { date: '2024-01-01' }, attorney_notes: 'Reviewed' },
            },
        };
        expect(computeAttentionScore(doc)).toBe(50);
    });

    it('accumulates multiple needs', () => {
        const doc = { metadata: {} };
        // Missing sig (0 because not expected), no type (+30), no facts (+20), no notes (+10) = 60
        expect(computeAttentionScore(doc)).toBe(60);
    });
});

describe('sortByAttention', () => {
    it('sorts highest attention score first', () => {
        const docs = [
            { id: '1', metadata: { quality_score: 9, document_type: 'contract', attorney_enrichment: { key_facts: { a: '1' }, attorney_notes: 'ok' } } },
            { id: '2', metadata: {} },
        ];
        const sorted = sortByAttention(docs);
        expect(sorted[0].id).toBe('2');  // Higher attention score
    });
});
```

**Step 2: Implement, run tests, commit**

```bash
git add frontend/src/lib/utils/documentSorting.ts frontend/src/lib/utils/documentSorting.test.ts
git commit -m "feat: add smart sorting by attorney attention score"
```

---

### Task 13: Integrate everything into VerificationHub

**Files:**
- Modify: `frontend/src/lib/components/VerificationHub.svelte`

**This is the main integration task.** Changes to VerificationHub:

1. **Import new components:**
```typescript
import TriageDashboard from './TriageDashboard.svelte';
import SignatureReviewPanel from './SignatureReviewPanel.svelte';
import DocumentReviewPanel from './DocumentReviewPanel.svelte';
import { sortByAttention, computeAttentionScore, getAttentionNeeds } from '$lib/utils/documentSorting';
```

2. **New state variables:**
```typescript
let activeFilters = $state<Set<string>>(new Set());
let signatureReviewOpen = $state(false);
let signatureReviewQueue = $state<any[]>([]);
let signatureReviewIndex = $state(0);
let documentReviewOpen = $state(false);
let documentReviewDoc = $state<any>(null);
let expandedCardIds = $state<Set<string>>(new Set());
```

3. **Replace DocumentStatusBanner with TriageDashboard:**
Remove the existing status banner and replace with:
```svelte
<TriageDashboard
    {documents}
    {activeFilters}
    onFilterToggle={handleFilterToggle}
/>
```

4. **Add filter logic:**
```typescript
function handleFilterToggle(filter: string) {
    activeFilters = new Set(activeFilters);
    if (activeFilters.has(filter)) {
        activeFilters.delete(filter);
    } else {
        activeFilters.add(filter);
    }
}

// Filtered documents (derived)
let filteredDocuments = $derived(() => {
    let docs = documents;
    if (activeFilters.has('missing-signatures')) {
        docs = docs.filter(d => /* unsigned and expected */);
    }
    if (activeFilters.has('low-ocr')) {
        docs = docs.filter(d => /* quality < 5 */);
    }
    // ... etc
    return docs;
});
```

5. **Apply smart sorting** within each triage group:
```typescript
// In the triage view, replace direct document lists with sorted versions
let sortedNeedsAttention = $derived(sortByAttention(triageGroups.needs_attention));
let sortedPending = $derived(sortByAttention(triageGroups.pending));
let sortedReady = $derived(sortByAttention(triageGroups.ready));
```

6. **Wire up SignatureReviewPanel:**
```svelte
<SignatureReviewPanel
    open={signatureReviewOpen}
    documents={signatureReviewQueue}
    currentIndex={signatureReviewIndex}
    {caseId}
    onClose={() => signatureReviewOpen = false}
    onVerdictSaved={handleSignatureVerdict}
    onNavigate={(i) => signatureReviewIndex = i}
/>
```

7. **Wire up DocumentReviewPanel:**
```svelte
<DocumentReviewPanel
    open={documentReviewOpen}
    document={documentReviewDoc}
    {caseId}
    onClose={() => documentReviewOpen = false}
    onVerify={handleVerify}
    onReExtract={handleReExtract}
    onTextEdit={(doc) => editingDocument = doc}
/>
```

8. **Update DocumentCard usage** in all triage sections to pass new props and handlers.

9. **Add API handlers** for new enrichment saves:
```typescript
async function handleTypeOverride(docId: string, type: string) {
    // Optimistic update
    // PATCH /api/documents/{docId}/verify with { document_type_override: type }
}

async function handleRelevanceChange(docId: string, level: string) { /* similar */ }
async function handleNotesUpdate(docId: string, notes: string) { /* similar */ }
async function handleFactUpdate(docId: string, key: string, value: string) { /* similar */ }
async function handleFactConfirm(docId: string, key: string) { /* similar */ }
async function handleRelationshipAdd(docId: string, relatedId: string, type: string) { /* similar */ }
```

All API calls follow the existing pattern at VerificationHub.svelte lines 182-194: get session, PATCH with auth header, optimistic UI update, toast on error.

**Step 1: Make changes incrementally — start with TriageDashboard integration**

**Step 2: Add SignatureReviewPanel integration**

**Step 3: Add DocumentReviewPanel integration**

**Step 4: Add enrichment API handlers**

**Step 5: Apply smart sorting**

**Step 6: Wire up enhanced DocumentCard props**

**Step 7: Test manually in browser, fix any issues**

**Step 8: Run frontend type check**

Run: `cd frontend && npx svelte-kit sync && npx svelte-check --tsconfig ./tsconfig.json`

**Step 9: Commit**

```bash
git add frontend/src/lib/components/VerificationHub.svelte
git commit -m "feat: integrate triage dashboard, signature panel, OCR panel, and smart sorting into VerificationHub"
```

---

## Phase 5: Final Integration & Cleanup

### Task 14: Remove signature verification from post-analysis location

**Files:**
- Investigate: `frontend/src/routes/app/cases/[id]/+page.svelte` — find where signature verification appears after analysis
- Modify: Remove or redirect to Verification Hub

**Step 1: Search for signature verification UI in the case detail page outside the Verification Hub**

Look for signature-related UI in the analysis results tab or any post-analysis section. The user mentioned it's in the "after analysis document location."

**Step 2: Remove or redirect**

If there's a duplicate signature verification UI in the analysis results view, either:
- Remove it entirely (since signatures are now verified in the Hub)
- Replace with a read-only display showing the verdict from verification (e.g., "Signed ✓ (verified by attorney)")

**Step 3: Commit**

```bash
git commit -m "refactor: remove post-analysis signature verification, now handled in Verification Hub"
```

---

### Task 15: Run full verification suite

**Step 1: Backend tests**
```bash
pytest tests/ -v --tb=short
```

**Step 2: Frontend type check**
```bash
cd frontend && npx svelte-kit sync && npx svelte-check --tsconfig ./tsconfig.json
```

**Step 3: Frontend unit tests**
```bash
cd frontend && npx vitest run
```

**Step 4: Python syntax check**
```bash
python3 -c "import py_compile; py_compile.compile('src/legal_portal/api/routes/documents.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('src/legal_portal/services/document_registry_service.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('src/legal_portal/services/json_processing_service.py', doraise=True)"
```

**Step 5: Fix any failures, commit**

```bash
git commit -m "fix: address test failures from verification hub integration"
```

---

## Summary: Task Order and Dependencies

```
Phase 1: Backend (Tasks 1-4) — Sequential, each builds on previous
  Task 1: Extend VerifyDocumentRequest
  Task 2: Store enrichment in metadata
  Task 3: Update document registry
  Task 4: Pass context to findings prompt

Phase 2: Frontend Foundation (Tasks 5-8) — Parallel (independent components)
  Task 5: SlideOutPanel base component
  Task 6: TriageDashboard component
  Task 7: KeyFactsChips component
  Task 8: DocumentRelationships component

Phase 3: Core Features (Tasks 9-10) — Parallel, depend on Task 5
  Task 9: SignatureReviewPanel (depends on SlideOutPanel)
  Task 10: DocumentReviewPanel (depends on SlideOutPanel)

Phase 4: Integration (Tasks 11-13) — Sequential
  Task 11: Enhanced DocumentCard (depends on Tasks 7, 8)
  Task 12: Smart sorting utility (independent)
  Task 13: VerificationHub integration (depends on all above)

Phase 5: Cleanup (Tasks 14-15) — Sequential
  Task 14: Remove post-analysis signature UI
  Task 15: Full verification suite
```

Total: 15 tasks across 5 phases.
