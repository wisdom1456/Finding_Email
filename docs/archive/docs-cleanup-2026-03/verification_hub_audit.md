# Verification Hub - Forensic Audit & Production-Ready Plan

## A. Executive Summary

The verification hub has a solid foundation but suffers from one critical design flaw: **almost nothing is auto-populated before the hub**. Document type, key facts, notes, related documents, and signature expectations are mostly blank when attorneys see them. The system does excellent work during the *analysis pipeline* (pass1/pass2), but that work happens AFTER verification, meaning attorneys are asked to manually classify and enrich documents that the AI will classify anyway moments later.

**The core fix is simple: move lightweight classification BEFORE the verification hub, not after it.**

Current state:
- Upload/import extracts text (OCR/PDF/email parsing) - this works well
- A basic IMAGE/TEXT classification runs on upload - too crude to be useful
- `document_type_label` is referenced in the frontend but **never set by the backend** - every document shows "needs type"
- Key facts are never pre-populated - always shows "Needs: key facts"
- Notes are always empty - always shows "Needs: notes"
- Related documents are always empty - fully manual
- Signature detection works for PDFs (digital sigs + text markers) but doesn't run on images
- The "star" is actually a 3-state relevance toggle (critical/supporting/background) - not a star/favorite
- The "Auto-detect" dropdown option just means "no manual override" - it's not a button that triggers detection

**Bottom line**: The hub is asking attorneys to do work that should be automated. Fix the pipeline ordering and 80% of the manual review burden disappears.

---

## B. Current Behavior Map

### Upload/Import Flow
```
File Upload/Clio Import
  -> DocumentProcessor.process_and_upload() [validation, compression, storage]
  -> classify_document_type() [IMAGE vs TEXT only - too crude]
  -> Immediate text extraction (PDF/EML/DOCX/image OCR)
  -> Signature detection (PDF only via _detect_pdf_signature)
  -> Document saved to Supabase with status: ready | extraction_failed | needs_review
  -> [STOP - no further classification happens]

Verification Hub loads documents
  -> Shows "Needs: type, key facts, notes" for virtually every document
  -> Attorney must manually set type, review, verify

Analysis Pipeline (triggered after verification)
  -> Pass 1: Full AI analysis with document_type, summary, key dates, parties, etc.
  -> Document Registry Service: infers signature_expected, instrument_hints, authority_level
  -> Pass 2: Synthesis, gap analysis
  -> Results displayed
```

**The gap**: Between text extraction and the verification hub, NO classification happens. The AI classification only runs during the full analysis pipeline, which runs AFTER the hub.

### Files Involved
| Component | File | Purpose |
|-----------|------|---------|
| Upload endpoint | `src/legal_portal/api/routes/documents.py:147-599` | Upload, extract text, basic IMAGE/TEXT classify |
| Clio import | `src/legal_portal/api/routes/cases.py:862` | Same classify_document_type call |
| IMAGE/TEXT classifier | `src/legal_portal/api/routes/documents.py:1367-1417` | Only returns "IMAGE" or "TEXT" |
| PDF signature detect | `src/legal_portal/services/file_processors/pdf_processor.py:226-304` | Detects digital sigs + text markers |
| Document registry | `src/legal_portal/services/document_registry_service.py` | Full classification - but only runs during analysis |
| Verification Hub UI | `frontend/src/lib/components/VerificationHub.svelte` | Main hub component (~1700 lines) |
| Document Card | `frontend/src/lib/components/DocumentCard.svelte` | Individual doc card with all fields |
| Signature Review Panel | `frontend/src/lib/components/SignatureReviewPanel.svelte` | Slide-out signature review |
| Document Review Panel | `frontend/src/lib/components/DocumentReviewPanel.svelte` | Side-by-side PDF + text review |
| Triage Dashboard | `frontend/src/lib/components/TriageDashboard.svelte` | Summary chips + progress bar |
| Attention Scoring | `frontend/src/lib/utils/documentSorting.ts` | Computes attention needs per doc |
| Key Facts Chips | `frontend/src/lib/components/KeyFactsChips.svelte` | Editable fact pills |
| Document Relationships | `frontend/src/lib/components/DocumentRelationships.svelte` | Manual doc linking |
| Verify endpoint | `src/legal_portal/api/routes/documents.py:1007` | PATCH to update verification state |

---

## C. What Each Field/Control Currently Does

### 1. Auto-detect (Document Type Dropdown)
**Code**: `DocumentCard.svelte:332-353`
**Current behavior**: A `<select>` dropdown on each card. The first option is labeled "Auto-detect" but it's just the empty/default value meaning "no manual override." It does NOT trigger any AI detection.
**What it should do**: This should either (a) be pre-populated with a real detected type, or (b) have a button that triggers lightweight AI classification.
**Verdict**: **RENAME and AUTO-POPULATE**. The label "Auto-detect" is misleading. The dropdown should show the system-detected type as the default, and only allow manual override.

### 2. Notes
**Code**: `DocumentCard.svelte:584-597` (textarea in expanded panel)
**Current behavior**: Empty textarea. Saved to `metadata.attorney_enrichment.attorney_notes` via PATCH. Only visible when card is expanded.
**Who uses it**: Attorneys are expected to type free-form notes. In practice, almost no one will.
**Downstream use**: Passed to analysis pipeline in `json_processing_service.py:619` as enrichment context.
**Verdict**: **DOWNGRADE TO OPTIONAL**. Should not count as "needs attention." Auto-generate a 1-line summary from extracted text instead. Keep the textarea for optional attorney override.

### 3. Related Documents
**Code**: `DocumentRelationships.svelte` (manual "Link to..." dropdown)
**Current behavior**: Fully manual. Attorney must click "Link to...", select a document from dropdown, choose relationship type (modifies/relates to/supersedes/supports), and click Add. Never auto-suggested.
**Downstream use**: Passed to analysis but rarely populated.
**Verdict**: **AUTO-SUGGEST, REMOVE FROM REQUIRED**. The system should infer related docs from filenames (e.g., email threads share subjects, contracts + addendums share names). Manual linking should remain as override but not be a required field.

### 4. The Star Icon (Relevance Toggle)
**Code**: `DocumentCard.svelte:357-372`
**Current behavior**: A 3-state toggle cycling through: critical (gold star) -> supporting (gray star) -> background (outline star). Saved to `metadata.attorney_enrichment.relevance_level`.
**Is it clear?**: No. Looks like a favorite/bookmark. The cycling behavior is not obvious. No tooltip explains the 3 states well.
**Downstream use**: Minimal. Used in attention scoring (`documentSorting.ts`) but doesn't strongly influence analysis.
**Verdict**: **KEEP BUT REDESIGN**. Rename to explicit labels or use a dropdown. Or remove entirely and let the AI determine relevance during analysis. The current star UX is confusing.

### 5. Skip
**Code**: `DocumentCard.svelte:548-554`
**Current behavior**: Sets document status to 'skipped'. Document is excluded from analysis. Only shown for non-ready, non-skipped docs.
**Verdict**: **KEEP**. Useful for attorneys to dismiss irrelevant files.

### 6. Preview
**Code**: `DocumentCard.svelte:557-564`
**Current behavior**: Opens document preview (PDF viewer, image viewer, or text display). Only shown when `storage_path` exists.
**Verdict**: **KEEP**. Essential for review.

### 7. Signature Review Recommended
**Code**: `DocumentCard.svelte:197-269`
**Current behavior**: Shows a badge based on two sources:
  1. `metadata.signature_detection` (from PDF processor) - checks actual PDF signature data
  2. `metadata.signature_verification` (from attorney manual review) - overrides detection
  3. Filename-based heuristic (`requiresSignatureReview()`) - checks for keywords like "contract", "agreement", "lease"

If no detection data exists but filename matches keywords, shows "Signature review recommended."
**Problem**: Shows on EVERY document with "contract" or "agreement" in the name, even if it's already signed or is a photo of a contract. The filename heuristic is too aggressive.
**Verdict**: **REFINE TRIGGERS**. Should only show when: (a) document is a PDF/DOCX AND (b) signature is expected AND (c) detection says not_detected or unknown. Photos, emails, and receipts should never trigger this.

### 8. Mark Signed
**Code**: `DocumentCard.svelte:538-546`, `VerificationHub.svelte:281-305`
**Current behavior**: Button appears when filename matches signature keywords AND signature status isn't already "signed." Sends PATCH with `signature_verification: 'signed'`.
**Problem**:
  - Only appears based on filename keywords, not actual document analysis
  - Doesn't open a preview or ask for confirmation details
  - The `handleMarkSigned` function in VerificationHub passes `is_verified: Boolean(doc.is_verified)` and `is_flagged_as_junk: Boolean(doc.is_flagged_as_junk)` alongside the signature verification - this is fragile and unnecessary
**Verdict**: **REWORK**. Move to the SignatureReviewPanel workflow (which already has a good UI with preview + keyboard shortcuts). The standalone button is too easy to click accidentally.

### 9. Document Type Field
**Code**: `DocumentCard.svelte:332-353`
**Current behavior**: Dropdown with hardcoded options: Contract, Addendum, Inspection Report, Disclosure, Correspondence, Invoice/Receipt, Photo/Media, Legal Filing, Other. Default is "Auto-detect" (empty string).
**Problem**: `document_type_label` is NEVER SET by the backend. The dropdown always starts empty. The backend's `classify_document_type()` only returns "IMAGE" or "TEXT" and stores it in `metadata.classification`, not `metadata.document_type_label`.
**Verdict**: **FIX THE PIPELINE**. Add a classification step that sets `document_type_label` from filename/content analysis before the hub loads.

### 10. Key Facts Field
**Code**: `KeyFactsChips.svelte`, `DocumentCard.svelte:571-581`
**Current behavior**: Shows pill-shaped chips with fact key/value pairs. Supports editing and confirmation. Only visible when expanded. Data lives in `metadata.attorney_enrichment.key_facts`.
**Problem**: Key facts are NEVER auto-generated before the hub. They only get populated if the attorney manually enters them, or after the full analysis pipeline runs.
**Verdict**: **AUTO-POPULATE FROM TEXT EXTRACTION**. After text is extracted, run a lightweight extraction pass to pull dates, amounts, party names, addresses from the text. Show these as unconfirmed chips that attorneys can confirm or edit.

---

## D. Root-Cause Findings

### D1. "Needs: type, key facts, notes" shown for every document

**Root cause**: `documentSorting.ts:53-77` (`getAttentionNeeds()`) checks:
- `metadata.document_type` or `attorney_enrichment.document_type_override` - both are always empty
- `attorney_enrichment.key_facts` with entries - always empty
- `attorney_enrichment.attorney_notes` - always empty

Since NONE of these are ever pre-populated, EVERY document shows "Needs: type, key facts, notes."

**Severity**: CRITICAL. This is the #1 UX failure. Makes the hub look broken.

**Fix**: Add a lightweight classification pass after text extraction that populates `document_type`, `key_facts`, and optionally a system-generated note/summary.

### D2. Auto-detect doesn't run early enough

**Root cause**: The only classification that runs at upload time is `classify_document_type()` (`documents.py:1367-1417`) which returns "IMAGE" or "TEXT." The real document type classification happens in the analysis pipeline (Pass 1), which runs AFTER verification.

**Severity**: HIGH. Attorneys are doing work the AI will do anyway.

**Fix**: Add a "fast classification" step that runs immediately after text extraction, using filename + extracted text snippet + MIME type to assign a document type.

### D3. Notes as a required attention item

**Root cause**: `documentSorting.ts:44-45` penalizes documents without `attorney_notes` with +10 attention score.

**Severity**: MEDIUM. Notes should be optional enrichment, not a required field.

**Fix**: Remove notes from the attention scoring. Or auto-generate a 1-line system note from the first sentence of extracted text.

### D4. Related documents is fully manual

**Root cause**: No backend logic exists to suggest related documents. The frontend has the UI but it's 100% manual.

**Severity**: MEDIUM. For email threads (shared subject line) and contract+addendum pairs, relationships are obvious and should be inferred.

**Fix**: After all documents are uploaded, run a lightweight grouping pass: match by subject line (emails), by filename similarity, and by cross-references in text.

### D5. Star behavior is ambiguous

**Root cause**: The star icon cycles through 3 unlabeled states. Users expect it to be a bookmark/favorite toggle.

**Severity**: LOW-MEDIUM. Confusing but not blocking.

**Fix**: Either replace with explicit labels or remove entirely and let AI determine relevance.

### D6. Signature review on wrong file types

**Root cause**: `DocumentCard.svelte:197-216` `requiresSignatureReview()` checks ONLY the filename for keywords. It doesn't check file type, so a photo named "Contract_photo.jpg" or an email thread about contracts will trigger "Signature review recommended."

**Severity**: MEDIUM. False positives create noise.

**Fix**: Add file type check. Only PDFs, DOCXs, and scanned document images should be eligible for signature review. Emails, generic photos (IMG_*), and small images should be excluded.

### D7. `document_type_label` is a phantom field

**Root cause**: The frontend reads `doc.metadata?.document_type_label` (TriageDashboard.svelte:36, VerificationHub.svelte:190, DocumentCard.svelte:339) but no backend code EVER sets this field. It's always undefined.

**Severity**: CRITICAL. This is why the "Needs Classification" count is always equal to total documents.

**Fix**: Either set `document_type_label` in the backend during upload/extraction, or change the frontend to read from a field that IS set.

---

## E. Fast Initial Classification Strategy

### Proposed: 3-Tier Classification

#### Tier 1: Instant (at upload, 0ms, no API calls)
Based on filename + extension + MIME type + file size:

```python
def fast_classify(filename: str, mime_type: str, file_size: int, source: str) -> dict:
    """Returns initial classification without any API calls."""
    name_lower = filename.lower()

    # Email
    if name_lower.endswith('.eml') or mime_type == 'message/rfc822':
        return {"document_type": "correspondence", "confidence": "high", "signature_eligible": False}

    # Photos from cameras
    if re.match(r'^(img_|dsc_|photo_|pic[_ ]?\d|image\d|wp_|\d{10,})', name_lower):
        return {"document_type": "photo_media", "confidence": "high", "signature_eligible": False}

    # Intake forms
    if 'intake' in name_lower and ('form' in name_lower or name_lower.endswith('.pdf')):
        return {"document_type": "intake_form", "confidence": "high", "signature_eligible": True}

    # Contracts / agreements
    if any(w in name_lower for w in ['contract', 'agreement', 'lease', 'addendum', 'amendment']):
        return {"document_type": "contract", "confidence": "medium", "signature_eligible": True}

    # Inspection reports
    if 'inspection' in name_lower or 'report' in name_lower:
        return {"document_type": "inspection_report", "confidence": "medium", "signature_eligible": False}

    # Disclosures
    if 'disclosure' in name_lower:
        return {"document_type": "disclosure", "confidence": "medium", "signature_eligible": True}

    # Invoices / receipts
    if any(w in name_lower for w in ['invoice', 'receipt', 'bill', 'payment']):
        return {"document_type": "invoice_receipt", "confidence": "medium", "signature_eligible": False}

    # Default by mime type
    if mime_type.startswith('image/'):
        return {"document_type": "photo_media", "confidence": "low", "signature_eligible": False}

    return {"document_type": "other", "confidence": "low", "signature_eligible": name_lower.endswith('.pdf')}
```

#### Tier 2: After Text Extraction (~0-2s, no additional API calls)
Uses first 500 chars of extracted text + filename to refine:

```python
def refine_classification(initial: dict, extracted_text: str, filename: str) -> dict:
    """Refine classification using extracted text snippet."""
    snippet = extracted_text[:500].lower()

    # Check text content for type clues
    if 'this agreement' in snippet or 'hereby agree' in snippet:
        initial["document_type"] = "contract"
        initial["confidence"] = "high"
        initial["signature_eligible"] = True
    elif 'inspection' in snippet and 'report' in snippet:
        initial["document_type"] = "inspection_report"
        initial["confidence"] = "high"
    elif any(w in snippet for w in ['invoice', 'total due', 'amount owed']):
        initial["document_type"] = "invoice_receipt"
        initial["confidence"] = "high"
    elif 'dear ' in snippet or 'from:' in snippet or 'subject:' in snippet:
        initial["document_type"] = "correspondence"
        initial["confidence"] = "high"
        initial["signature_eligible"] = False

    # Extract key facts from text
    key_facts = extract_quick_facts(extracted_text)
    initial["key_facts"] = key_facts

    return initial
```

#### Tier 3: Optional AI-Assisted (deferred, only for low-confidence items)
A cheap GPT-5-mini call with the first 1000 chars for documents where Tier 1+2 confidence is "low":

```
Classify this legal document. Return JSON with document_type, key_facts (dates, amounts, parties), and 1-sentence summary.
```

**Cost**: ~$0.001 per document. Only runs for ~20% of uploads.

### What NOT to do:
- Don't run full Pass 1 analysis at upload time - too expensive and slow
- Don't use Google Vision just for classification - OCR is already done, use the text
- Don't try to auto-detect relationships at upload time for individual files - wait until all docs are uploaded

---

## F. Signature Detection Recommendation

### Current State
1. **PDF processor** (`pdf_processor.py:226-304`): Detects digital signatures (PDF /Type/Sig) and text markers ("Signed by:", "Signature:", DocuSign markers). Works well for PDFs.
2. **Document registry** (`document_registry_service.py:96-141`): Infers `signature_expected` from filename + doc type. Only runs during full analysis.
3. **Frontend filename check** (`DocumentCard.svelte:197-216`): Hardcoded keyword list that shows "Signature review recommended" based solely on filename.

### Problems
- Images are NEVER checked for signatures (no OCR-based sig detection for .jpg/.png)
- Emails trigger signature review if subject line contains "contract"
- The frontend and backend use DIFFERENT keyword lists
- `signature_expected` is only set during analysis (too late for verification hub)

### Recommended Approach: Hybrid (Option 5)

**Layer 1: Document-structure heuristics (at upload)**
- Set `signature_eligible` based on file type + filename (Tier 1 classification above)
- Only PDFs, DOCXs, and document-like images should be eligible
- NEVER mark emails, phone photos (IMG_*), screenshots, or small images as signature-eligible

**Layer 2: PDF digital signature detection (at upload - already works)**
- Keep current `_detect_pdf_signature()` - it's good
- If digital sig detected: auto-set `signed_status = 'signed'`, `signed_confidence = 'high'`

**Layer 3: Text-based clues (after text extraction)**
- Run `_extract_text_signature_markers()` on all signature-eligible documents
- If markers found: `signed_status = 'signed'`, `signed_confidence = 'medium'`
- If no markers and signature expected: `signed_status = 'review_required'`

**Layer 4: AI visual classification (deferred, only for review_required)**
- Only for documents where signature is expected but detection is inconclusive
- Use GPT-4o Vision on the last 2 pages of the PDF
- Prompt: "Does this document page contain a handwritten signature, printed name in a signature block, or e-signature? Return yes/no/unclear."
- Cost: ~$0.02 per document, only ~10% of uploads

**Layer 5: Human-in-the-loop (SignatureReviewPanel)**
- Keep existing panel but only show documents where status is 'review_required'
- Pre-filter: exclude emails, photos, receipts
- Add confidence indicator showing why review was triggered

### Recommended Schema Additions
```sql
-- Add to documents table or as a separate signature_reviews table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_status TEXT DEFAULT 'unknown'; -- 'signed', 'not_signed', 'review_required', 'unknown', 'not_applicable'
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_confidence TEXT DEFAULT 'none'; -- 'high', 'medium', 'low', 'none'
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_reason TEXT; -- Human-readable reason
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_reviewed_by UUID REFERENCES profiles(id);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_reviewed_at TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_manual_override BOOLEAN DEFAULT FALSE;
```

Currently, all this data is buried in the JSONB `metadata` column. Moving key signature fields to proper columns enables indexing and querying.

---

## G. What Should Be Auto-Populated vs Manual

| Field | Current | Recommendation | Source |
|-------|---------|---------------|--------|
| Document type | Never set | **AUTO-POPULATE** | Tier 1 filename + Tier 2 text analysis |
| Key facts (dates, amounts, parties) | Never set | **AUTO-POPULATE** | Tier 2 text extraction (regex + light NLP) |
| Notes | Empty, counts as "needs attention" | **AUTO-GENERATE** 1-line summary, keep textarea for override | First sentence of extracted text |
| Related documents | Empty, fully manual | **AUTO-SUGGEST** | Filename similarity, email thread grouping, shared references |
| Signature status | Only for PDFs | **AUTO-DETECT** for all eligible types | Tier 1-3 above |
| Relevance/star | Empty | **DEFER** to AI analysis | Don't auto-set, but also don't require it |
| Verification status | Always needs_review initially | **AUTO-VERIFY** high-confidence docs | If type=high_confidence AND text extracted AND quality=high, auto-set to ready |

### Blunt Assessments

- **Notes should NOT be required/manual.** Remove from attention scoring. Auto-generate a 1-line summary. The textarea can stay for optional attorney input.
- **Related documents should be auto-suggested.** Manual linking is a power-user feature, not a daily workflow. The system should group email threads and link contract/addendum pairs automatically.
- **The star is unclear and unnecessary in its current form.** Replace with an explicit relevance dropdown IF it's actually used in analysis. If not, remove it.
- **Verification should only focus on exceptions.** If a document has high-quality text extraction, correct type classification, and no signature issues, it should auto-advance to "ready" without attorney review.

---

## H. Verification Hub Redesign

### Target Workflow

```
1. UPLOAD/IMPORT
   -> Text extraction (existing - works well)
   -> Tier 1 fast classification (NEW - filename/MIME)
   -> Tier 2 text-based refinement (NEW - first 500 chars)
   -> Signature detection (existing for PDF + NEW for other types)
   -> Key facts extraction (NEW - dates, amounts, parties from text)
   -> Auto-generate 1-line summary note (NEW)
   -> Set document_type_label, key_facts, system_note in metadata
   -> Auto-set status = 'ready' if high confidence, else 'needs_review'

2. BATCH POST-PROCESSING (after all uploads complete)
   -> Auto-detect related documents (email thread grouping, filename similarity)
   -> Flag duplicates (existing - works)
   -> Set signature_eligible and initial signature status

3. VERIFICATION HUB (shows only what needs human attention)
   DEFAULT VIEW: Only documents where confidence < threshold
   - Exception-based review: only 20-30% of docs should need attention
   - Pre-populated fields: type, key facts, summary note, related docs
   - Attorney can confirm, edit, or override any auto-detected value

   SECTIONS:
   a. "Signature Review Needed" - docs with signature_expected + detection inconclusive
   b. "Low Confidence" - docs where type/facts couldn't be auto-detected
   c. "OCR Issues" - extraction_failed or low quality
   d. "Ready" - collapsed by default, expandable for spot-checks
   e. "Excluded/Duplicates" - collapsed, as now

4. WHAT SHOULD BE HIDDEN UNLESS NEEDED:
   - Notes field (collapsed by default, expand on click)
   - Related documents (show auto-suggested links, hide manual linking unless expanded)
   - Key facts (show chips, hide edit controls unless hovered)

5. WHAT SHOULD BE REMOVED:
   - "Needs: notes" from attention scoring
   - The misleading "Auto-detect" label on the type dropdown
   - Filename-only signature review triggering for non-document files

6. WHAT USERS CAN EDIT:
   - Document type (dropdown, pre-filled)
   - Key facts (inline edit, pre-filled)
   - Notes (optional textarea)
   - Related documents (manual add/remove)
   - Signature status (mark signed / not signed / concern)
   - Skip / Delete / Exclude from analysis
```

### Your Suspicions - Confirmed or Not

> "document type should usually already be set"

**CONFIRMED.** The pipeline gap is the root cause. Tier 1+2 classification will set type for 70-80% of documents.

> "notes should probably not be a required/manual field"

**CONFIRMED.** Notes add friction with minimal value. Auto-generate a summary, keep notes as optional.

> "related documents should probably be suggestions, not manual work"

**CONFIRMED.** Email threads and contract families can be auto-linked. Manual linking should be an override.

> "the star may be unclear or unnecessary unless it has a real workflow purpose"

**CONFIRMED.** The 3-state cycling star is confusing. Either replace with explicit UI or remove. The relevance data has minimal downstream impact currently.

---

## I. DB/Schema Changes

### New Columns on `documents` Table
```sql
-- Document classification (move from JSONB metadata to proper columns)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_type_label TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_type_confidence TEXT DEFAULT 'none'; -- high/medium/low/none
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_source TEXT DEFAULT 'none'; -- filename/text/ai/manual

-- Signature status (move from JSONB metadata to proper columns)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_status TEXT DEFAULT 'unknown';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_confidence TEXT DEFAULT 'none';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_reviewed_by UUID;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_reviewed_at TIMESTAMPTZ;

-- Auto-generated summary
ALTER TABLE documents ADD COLUMN IF NOT EXISTS system_summary TEXT;

-- Key facts (keep in JSONB metadata.key_facts for flexibility)
-- But add a flag for whether facts have been auto-extracted
ALTER TABLE documents ADD COLUMN IF NOT EXISTS facts_extracted BOOLEAN DEFAULT FALSE;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_documents_document_type_label ON documents(document_type_label);
CREATE INDEX IF NOT EXISTS idx_documents_signed_status ON documents(signed_status);
```

### Migration Plan for Existing Documents
```sql
-- Backfill document_type_label from metadata.classification for existing docs
UPDATE documents
SET document_type_label = CASE
    WHEN metadata->>'classification' = 'IMAGE' THEN 'photo_media'
    WHEN file_name ILIKE '%contract%' OR file_name ILIKE '%agreement%' THEN 'contract'
    WHEN file_name ILIKE '%intake%' THEN 'intake_form'
    WHEN file_name ILIKE '%.eml' THEN 'correspondence'
    ELSE 'other'
END,
document_type_confidence = 'low',
classification_source = 'migration'
WHERE document_type_label IS NULL;

-- Backfill signed_status from metadata.signature_detection
UPDATE documents
SET signed_status = COALESCE(
    metadata->'signature_verification'->>'status',
    metadata->'signature_detection'->>'status',
    'unknown'
),
signed_confidence = COALESCE(
    metadata->'signature_detection'->>'confidence',
    'none'
)
WHERE signed_status IS NULL OR signed_status = 'unknown';
```

---

## J. File-by-File Implementation Plan

### Phase 1: Fast Classification Layer (HIGH PRIORITY)
**Goal**: Every document gets a type + key facts before the hub.

1. **NEW FILE**: `src/legal_portal/services/fast_classifier.py`
   - `fast_classify(filename, mime_type, file_size, source)` - Tier 1
   - `refine_classification(initial, extracted_text, filename)` - Tier 2
   - `extract_quick_facts(text)` - regex extraction of dates, amounts, names
   - `generate_system_summary(text, doc_type)` - first meaningful sentence

2. **MODIFY**: `src/legal_portal/api/routes/documents.py`
   - After text extraction (line ~547), call `fast_classify()` and `refine_classification()`
   - Set `document_type_label`, `document_type_confidence`, `classification_source` in update_data
   - Set `system_summary` from first sentence of extracted text
   - Set `facts_extracted = True` if key facts found
   - Store key facts in `metadata.key_facts`

3. **MODIFY**: `src/legal_portal/api/routes/cases.py`
   - Same classification call for Clio imports (around line 862)

4. **MODIFY**: `frontend/src/lib/utils/documentSorting.ts`
   - Remove `attorney_notes` from attention scoring
   - Check `document_type_label` column instead of `metadata.document_type`
   - Check `facts_extracted` instead of `attorney_enrichment.key_facts`

5. **MODIFY**: `frontend/src/lib/components/DocumentCard.svelte`
   - Read `doc.document_type_label` instead of `doc.metadata?.document_type_label`
   - Show system_summary as default note if attorney_notes is empty
   - Fix signature review to check `doc.document_type_label` eligibility

6. **MODIFY**: `frontend/src/lib/components/TriageDashboard.svelte`
   - Update `needsTypeCount` to check `doc.document_type_label` column

### Phase 2: Signature Detection Improvements (MEDIUM PRIORITY)

7. **MODIFY**: `src/legal_portal/services/file_processors/pdf_processor.py`
   - Add `signature_expected` inference based on doc type + filename (move logic from document_registry_service)
   - Set `signature_eligible` flag

8. **MODIFY**: `src/legal_portal/api/routes/documents.py`
   - After extraction, set `signed_status` and `signed_confidence` columns
   - For images: skip signature detection unless document_type suggests it's a scanned contract

9. **MODIFY**: `frontend/src/lib/components/DocumentCard.svelte`
   - `requiresSignatureReview()`: check `doc.signed_status` and `doc.document_type_label` instead of filename keywords
   - Only show signature badges for signature-eligible document types

10. **MODIFY**: `frontend/src/lib/components/SignatureReviewPanel.svelte`
    - Add confidence indicator
    - Show reason for review trigger

### Phase 3: Auto-Relationship Detection (LOWER PRIORITY)

11. **NEW FILE**: `src/legal_portal/services/relationship_detector.py`
    - `detect_email_threads(documents)` - group by subject line
    - `detect_contract_families(documents)` - match by normalized name
    - `suggest_relationships(documents)` - combine and deduplicate

12. **MODIFY**: `src/legal_portal/api/routes/documents.py` or a new batch endpoint
    - After all uploads complete, run relationship detection
    - Store suggestions in metadata

13. **MODIFY**: `frontend/src/lib/components/DocumentRelationships.svelte`
    - Show auto-suggested relationships with "Suggested" badge
    - Allow confirm/dismiss

### Phase 4: Hub UX Cleanup (LOWER PRIORITY)

14. **MODIFY**: `frontend/src/lib/components/DocumentCard.svelte`
    - Replace star icon with explicit relevance dropdown
    - Collapse notes/relationships by default
    - Show auto-populated key facts as unconfirmed chips

15. **MODIFY**: `frontend/src/lib/components/VerificationHub.svelte`
    - Add "Signature Review Needed" as a separate triage group
    - Auto-verify high-confidence documents (ready + high quality + type set)

### What to Delete
- The misleading "Auto-detect" option label (replace with detected type name)
- Notes from attention scoring formula
- Filename-only signature review triggering (replace with proper eligibility check)

### What to Defer
- AI-based visual signature classification (Tier 3) - only build if Tier 1-2 accuracy is insufficient
- Automatic relevance scoring - let the full analysis handle this
- GPT-5-mini classification pass for low-confidence items - measure need first

---

## K. Testing Plan

### Unit Tests
1. `test_fast_classifier.py`
   - Test Tier 1 classification for all document types
   - Test with real example filenames from the user's list
   - Test edge cases: no extension, unusual MIME types, very short filenames

2. `test_signature_detection_eligibility.py`
   - Verify emails are NOT signature-eligible
   - Verify IMG_* photos are NOT signature-eligible
   - Verify contracts/agreements ARE signature-eligible
   - Test with and without existing signature_detection metadata

3. `test_relationship_detection.py`
   - Email thread grouping by subject
   - Contract + addendum matching
   - Duplicate name detection

### Integration Tests
4. Upload flow test: verify that after upload, document has `document_type_label` set
5. Clio import test: verify classification runs for imported documents
6. Verification hub test: verify triage groups are correctly populated

### Frontend Tests
7. `DocumentCard.test.ts` updates: verify type dropdown shows pre-filled value
8. `TriageDashboard.test.ts`: verify correct counts with classified documents
9. `documentSorting.test.ts`: verify notes removal from attention score

---

## L. Rollout Plan

### Phase 1 (1-2 days): Fast Classification - immediate impact
1. Create `fast_classifier.py`
2. Wire into upload and Clio import flows
3. Add `document_type_label` column + migration
4. Update frontend to read new column
5. Deploy and verify existing cases get backfilled

### Phase 2 (1-2 days): Signature Fixes - reduce noise
1. Move signature eligibility to proper columns
2. Fix frontend to use eligibility instead of filename keywords
3. Deploy

### Phase 3 (2-3 days): Auto-population - reduce manual work
1. Add key facts extraction to upload flow
2. Add system summary generation
3. Update attention scoring
4. Add relationship detection
5. Deploy

### Phase 4 (1-2 days): UX Polish
1. Star -> explicit relevance control
2. Collapse notes/relationships by default
3. Auto-verify high-confidence documents
4. Deploy

### Migration for Existing Documents
- Run backfill migration on deployment
- Existing "ready" documents with text: run Tier 2 classification in a batch job
- Existing pending documents: will be classified next time they're loaded

---

## M. Final Recommendation: What to Build Now vs Later

### BUILD NOW (Phase 1 - highest ROI)
1. **`fast_classifier.py`** - Tier 1 + Tier 2 classification
2. **`document_type_label` column** + migration + backfill
3. **Wire classification into upload/import** - documents arrive with a type
4. **Fix `getAttentionNeeds()`** - remove notes requirement, use proper type field
5. **Fix signature eligibility** - don't show "Signature review recommended" on emails/photos

These 5 changes will eliminate "Needs: type, key facts, notes" for 80%+ of documents.

### BUILD SOON (Phase 2-3 - important but less urgent)
6. Key facts auto-extraction from text
7. System summary auto-generation
8. Proper `signed_status` / `signed_confidence` columns
9. Relationship auto-detection
10. Auto-verify high-confidence documents

### DEFER (Phase 4+ - nice to have)
11. AI visual signature classification (GPT-4o Vision on last pages)
12. GPT-5-mini classification for low-confidence items
13. Star/relevance redesign
14. Full hub layout overhaul

### DELETE
- The concept of notes as a "required" attention item
- Filename-only signature review triggering on non-document files
- The phantom `document_type_label` read without write

---

## Appendix: File Classification for Example Documents

| File | Type (Tier 1) | Confidence | OCR? | Sig Review? | Auto Notes? | Related? | Hub? |
|------|--------------|------------|------|-------------|-------------|----------|------|
| Intake Form - General (Migdalia Escribano).pdf | intake_form | HIGH | Yes (PDF) | Yes | Yes (extract client name, date) | No | Brief review |
| Contractor_Contract.JPG | contract | MEDIUM (image of contract) | Yes (Vision) | Yes (after OCR) | Yes | Link to other contracts | Review needed |
| Contractor Contract.JPG | contract | MEDIUM | Yes (Vision) | Yes | Yes | Link to above | Possible duplicate |
| pic_1.jpeg - pic_4.jpeg | photo_media | HIGH | Maybe (evidence photos) | No | Minimal | Group together | Minimal review |
| pic 1.jpeg - pic 4.jpeg | photo_media | HIGH | Maybe | No | Minimal | Group together | Minimal review |
| 20260123*.eml series | correspondence | HIGH | No (text) | No | Yes (extract subject, date, sender) | Group as thread | Skip most |
| image001.png | photo_media | HIGH (email inline image) | Maybe | No | No | Link to parent email | Skip |
| IMG_0532.JPEG | photo_media | HIGH | Maybe (evidence) | No | Minimal | No | Minimal review |
| IMG_6711.PNG | photo_media | HIGH | Maybe | No | Minimal | No | Minimal review |
| IMG_3846.PNG | photo_media | HIGH | Maybe | No | Minimal | No | Minimal review |
| IMG_1360.jpg / IMG_1361.jpg | photo_media | HIGH | Maybe | No | Minimal | Group (sequential) | Minimal review |
| 78291347501__CDD820B0*.jpg | photo_media | HIGH (iPhone live photo hash) | Maybe | No | Minimal | No | Minimal review |

**Key takeaway**: Of these 23 example files:
- 10+ are email threads that should be auto-grouped and mostly skipped
- 8+ are phone photos that need minimal review
- 2-3 are actual documents (intake form, contracts) that need real review
- Only the intake form and contracts should trigger signature review

With the proposed system, attorneys would review ~3-5 documents instead of 23.
