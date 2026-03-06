# Smart EML Processor: PDF Attachment Extraction & Thread Dedup

**Date:** 2026-03-05
**Status:** Approved

## Problem

Clio imports upload EML files but not their PDF attachments. Image attachments (JPG/PNG) are uploaded as standalone documents, but PDFs inside EMLs are lost entirely. Additionally, email threads create redundant documents — reply emails contain the full prior thread in their body, and forwarded emails create exact duplicates.

**Escribano case example:** 17 EMLs across 4 threads. 2 PDF attachments (`Documents Needed to Proceed.pdf`, `Attaching a Document Instructions.pdf`) exist only inside EMLs — never uploaded as standalone docs. The "Second Follow Up" thread has 10 emails with body sizes 1,350 to 19,996 chars; the longest contains all earlier content. 4 large ~33MB EMLs are identical forwards carrying the same 11 photo attachments.

## Decision

**Approach A: Extract-and-Dedup at processing time.** PDF attachments become first-class documents. Thread dedup persists via `is_flagged_as_junk` flags.

## Design

### 1. EML Processor — Attachment Extraction

**File:** `src/legal_portal/services/file_processors/eml_processor.py`

Enhance the MIME part walk to extract PDF attachments:

- Walk all MIME parts. For each part with `Content-Disposition: attachment` or inline with a filename:
  - If `application/pdf`: extract bytes and filename, include in `ProcessedDocument.metadata["attachments"]` as `[{"filename": str, "content_type": str, "bytes": bytes, "content_hash": str}]`
  - If image type: compute `content_hash` only (for dedup reference), add to `metadata["attachment_hashes"]`
- Email body extraction (text/plain, html2text fallback) stays unchanged
- `ProcessedDocument.metadata` gains: `attachments` (PDF dicts), `attachment_hashes` (all content hashes), `body_hash` (SHA-256 of plain text body)

### 2. Attachment Upload with Dedup

**Files:** `analysis.py` (`_extract_deferred_documents`), `documents.py` (upload endpoint)

After EML processing:

1. Query case documents: `SELECT id, metadata->>'content_hash' FROM documents WHERE case_id = ?`
2. For each PDF attachment:
   - Compute SHA-256 of raw bytes as `content_hash`
   - If `content_hash` exists in case → skip
   - Otherwise: upload to Supabase storage, create document row:
     - `file_name`: original attachment filename
     - `file_type`: `application/pdf`
     - `extraction_method`: `eml_attachment`
     - `metadata`: `{"parent_email_id": "<eml-doc-id>", "content_hash": "<sha256>"}`
     - `status`: `PENDING`
   - Run PDF extraction (Cloud Run OCR or local `process_pdf`)

### 3. Email Thread Dedup

**File:** `analysis.py` (new function `_dedup_email_threads`)

Runs as a batch step after all EMLs in a case are processed:

1. **Group by thread:** Strip `Re:`, `Fwd:`, `FW:` prefixes from subject, lowercase, group by normalized subject
2. **Within each thread group:** Sort by body length descending
3. **Longest email = canonical version** (contains full thread history)
4. **Shorter emails in same thread:** Check if body is substring of canonical body (accounting for `>` quoting). If yes → `is_flagged_as_junk = True`, `metadata.superseded_by = <canonical-doc-id>`, `metadata.junk_reason = "superseded_by_later_reply"`
5. **Exact duplicates** (same `body_hash`): Keep one, flag rest with `junk_reason = "exact_duplicate"`

### 4. Existing Cases

- New cases: runs automatically during deferred extraction
- Existing cases (e.g., Escribano): re-process EMLs by re-downloading raw bytes from storage, extracting attachments, running thread dedup
- Flagged-as-junk emails hidden from analysis; users can unflag

### 5. Files Changed

| File | Change |
|---|---|
| `eml_processor.py` | Add PDF attachment extraction to MIME walk |
| `analysis.py` (`_extract_deferred_documents`) | Upload PDF attachments with dedup check after EML processing |
| `analysis.py` (new `_dedup_email_threads`) | Thread grouping + junk flagging |
| `documents.py` (upload endpoint) | Same attachment extraction for direct EML uploads |

### 6. What is NOT Changed

- `data_models.py` — `is_flagged_as_junk` and `metadata` JSONB already exist
- Image attachments — not extracted (already uploaded as standalone docs by Clio)
- `analyze_image_with_vision()` — photo analysis, not OCR, unchanged
- `batch_vision_processor.py` — already dead code per OCR microservice plan
