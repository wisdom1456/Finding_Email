# Release Notes — v2.0.0
**February 5, 2026 → March 13, 2026**

## Major Features

### GPT-5.4 Model Upgrade
- Analysis, letter generation, and multi-stage processing now default to GPT-5.4, with improved reasoning and legal analysis capabilities.
- OCR and Vision extraction continue to use GPT-5.2 Vision.
- Model preferences remain configurable per-task in Settings (GPT-5.4, GPT-5 Mini, GPT-5 Nano, GPT-5.2).

### Verification Hub
- New unified document management interface replacing the previous Document Review panel.
- Triage groups: Critical, Needs Attention, Ready, Duplicates, Excluded.
- Signature review: reconciles signed vs. unsigned documents using content hints, not just filenames.
- Bulk OCR: run text extraction across all documents that need it in one action.
- Canonical document registry: tracks document identities and relationships across the case.

### Map-Reduce Gap Analysis
- Large cases (50+ documents) now use a map-reduce pipeline for more thorough gap analysis.
- Map phase uses GPT-5 Mini for per-batch processing; reduce phase uses GPT-5.4 for synthesis.
- Designed to produce more consistent results on cases with extensive documentation.

### Findings Email V2
- Findings email prompt fully rewritten with combined law + application format for stronger legal reasoning.
- Critic review pass validates structure and substance before final output.
- Polish pass improves readability while preserving legal precision.
- Automatic retry on network errors to help prevent lost work.

### Email Thread Processing
- Direct .eml file processing with full HTML email support.
- Attachment extraction from email files.
- Thread deduplication to reduce redundant content in analysis.
- Content-hash deduplication identifies exact-duplicate documents across the case.

### HEIC Image Support
- HEIC/HEIF images (common iPhone photo format) are now accepted and automatically converted to JPEG for processing.
- Requires `pillow-heif` runtime dependency.

### Small Image Filtering
- Images under 50KB (typically email signature logos, social media icons) are automatically filtered during Clio document import to reduce noise.

### Deferred Document Extraction
- Documents can now be extracted on-demand rather than all at import time, allowing faster initial case setup.

### Cloud Run OCR
- Optional Google Cloud Run OCR service integration for faster, more scalable text extraction.
- Falls back to local OCR processing if Cloud Run is unavailable or not configured.

## Reliability Improvements

### Network Auto-Recovery
- Streaming analysis, letter generation, and document processing now include automatic retry logic designed to recover from transient network interruptions.
- SSE progress polling for Vercel serverless environments helps maintain progress visibility.

### Clio Import Stability
- Improved handling of large Clio matters with many documents.
- Small image filtering reduces unnecessary processing.

### Security Hardening
- Authentication, session management, and XSS protections strengthened.
- Input sanitization improvements across the application.

## User Interface

### Results Workspace
- Results workspace persists when switching between case tabs — no need to reopen.
- Unified case + results navigation reduces context switching.

### Updated Analysis Time Estimates
- Time estimates updated to reflect current processing speeds: 1-2 min (small), 2-4 min (medium), 4-8 min (large), 10-15 min (very large 50+ doc cases).
- OCR adds approximately 30-60 seconds per document.

### Removed
- **DocumentReviewPanel** — consolidated into the Verification Hub.
- **WeasyPrint PDF generation** — removed in favor of client-side document rendering.

## Dependencies & Infrastructure
- `pillow-heif` added for HEIC image support.
- `tiktoken` made optional with lazy-import fallback.
- `httpx` added for Cloud Run OCR service communication.
- WeasyPrint dependency fully removed.

---

## Summary
This release focuses on four areas:
1. **Smarter AI** — GPT-5.4 default with map-reduce gap analysis for large cases
2. **Better Document Management** — Verification Hub, HEIC support, dedup, and deferred extraction
3. **Improved Letters** — Rewritten findings email with critic review and polish
4. **Reliability** — Network recovery, security hardening, and Clio import stability
