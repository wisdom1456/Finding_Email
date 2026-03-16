# Refactor Execution Plan

**Date:** 2026-03-14
**Scope:** Concrete, implementation-ready execution plan for the 3-week refactor sprint
**Prerequisite:** [Codebase Audit](./2026-03-14-codebase-audit-and-refactor-plan.md)

---

## 1. Target Architecture

### 1.1 analysis.py Decomposition (7,614 LOC → 6 modules)

The file contains 95 functions, 14 classes, and 21 endpoints. Based on the function-level audit, here is the exact decomposition:

#### Module 1: `analysis_core.py` (~1,800 LOC)

**Responsibility:** Start, cancel, status, results, and state management for analysis runs.

**Moves here:**
| Function | Lines | Type |
|----------|-------|------|
| `AnalysisRequest` | 1262-1267 | Pydantic model |
| `AnalysisResponse` | 1269-1278 | Pydantic model |
| `AnalysisCancelledError` | 530-531 | Exception |
| `_extract_deferred_documents` | 63-310 | Helper |
| `_dedup_email_threads` | 312-419 | Helper |
| `_download_and_extract_documents` | 1317-1635 | Helper |
| `process_case_background` | 1636-2354 | Core (BackgroundTask) |
| `start_analysis` | 3016-3201 | POST /start |
| `cancel_analysis` | 3205-3248 | POST /cancel/{analysis_id} |
| `cancel_case_analysis` | 3251-3300 | POST /cancel-case/{case_id} |
| `get_analysis_status` | 3303-3354 | GET /status/{case_id} |
| `get_analysis_results` | 3356-3417 | GET /results/{case_id} |
| `StreamingAnalysisSaveRequest` | 3419-3422 | Pydantic model |
| `save_streaming_analysis` | 3426-3939 | POST /stream/{case_id}/save |
| `stream_case_analysis` | 4048-4290 | GET /stream/{case_id} |
| `get_streaming_result` | 4294-4324 | GET /stream/{case_id}/result |
| `get_analysis_state` | 7525-7577 | GET /{analysis_id}/state |
| `_analysis_is_cancelled` | 534-547 | Helper |
| `_cancel_analysis` | 550-578 | Helper |
| `_update_analysis_progress` | 581-597 | Helper |
| `_get_user_ai_preferences` | 599-608 | Helper |

**Endpoints (8):**
- `POST /api/analysis/start`
- `POST /api/analysis/cancel/{analysis_id}`
- `POST /api/analysis/cancel-case/{case_id}`
- `GET /api/analysis/status/{case_id}`
- `GET /api/analysis/results/{case_id}`
- `POST /api/analysis/stream/{case_id}/save`
- `GET /api/analysis/stream/{case_id}`
- `GET /api/analysis/stream/{case_id}/result`
- `GET /api/analysis/{analysis_id}/state`

---

#### Module 2: `letter_routes.py` (~2,200 LOC)

**Responsibility:** All letter generation — findings, demand, and recommendation letters.

**Moves here:**
| Function | Lines | Type |
|----------|-------|------|
| `LetterGenerationRequest` | 1281-1304 | Pydantic model |
| `LetterGenerationResponse` | 1307-1314 | Pydantic model |
| `RecommendationLetterRequest` | 4875-4887 | Pydantic model |
| `RecommendationLetterResponse` | 4889-4896 | Pydantic model |
| `CalculateDemandAmountRequest` | 5475-5479 | Pydantic model |
| `CalculateDemandAmountResponse` | 5482-5487 | Pydantic model |
| `stream_findings_letter` | 2356-2935 | GET /{analysis_id}/letter/stream |
| `generate_letter` | 4326-4873 | POST /generate-letter |
| `generate_recommendation_letter` | 4900-5087 | POST /generate-recommendation-letter |
| `stream_recommendation_letter` | 5089-5473 | GET /{analysis_id}/recommendation-letter/stream |
| `calculate_demand_amount` | 5491-5589 | POST /calculate-demand-amount |
| `_resolve_letter_identity_context` | 622-752 | Helper |
| `_resolve_client_name_for_letter` | 754-861 | Helper |
| `_new_generation_metrics` | 464-496 | Helper |
| `_emit_generation_metrics` | 498-504 | Helper |
| `_quality_report_placeholder` | 511-528 | Helper |
| `_html_to_plain_text` | 1142-1151 | Helper |
| `_generate_eml_bytes` | 1153-1171 | Helper |
| `_store_artifact` | 1173-1193 | Helper |
| `_generate_and_store_artifacts` | 1195-1236 | Helper |
| `_attach_signed_artifact_urls` | 1238-1260 | Helper |
| `_ensure_fresh_gap_analysis_for_letter_generation` | 6346-6468 | Helper |

**Endpoints (5):**
- `GET /api/analysis/{analysis_id}/letter/stream`
- `POST /api/analysis/generate-letter`
- `POST /api/analysis/generate-recommendation-letter`
- `GET /api/analysis/{analysis_id}/recommendation-letter/stream`
- `POST /api/analysis/calculate-demand-amount`

---

#### Module 3: `gap_routes.py` (~1,600 LOC)

**Responsibility:** Gap analysis — run, resolve, stream, and all gap-related helpers.

**Moves here:**
| Function | Lines | Type |
|----------|-------|------|
| `GapBatch` | 5891-5901 | Dataclass |
| `GapAnalysisRequest` | 5591-5598 | Pydantic model |
| `GapResolutionItemRequest` | 5601-5620 | Pydantic model |
| `GapResolutionRefreshRequest` | 5623-5649 | Pydantic model |
| `_GAP_ANALYSIS_INPUT_SCHEMA_VERSION` | constant | Constant |
| `_GAP_CONTEXT_MAX_DOCS` | constant | Constant |
| `_GAP_CONTEXT_MAX_CHARS` | constant | Constant |
| `_SMALL_GROUP_MERGE_MAP` | constant | Constant |
| `_build_gap_resolution_hash` | 5652-5672 | Helper |
| `_build_supporting_document_hash` | 5674-5700 | Helper |
| `_derive_signature_detection_for_gap_doc` | 5702-5738 | Helper |
| `_fetch_case_documents_for_gap_context` | 5740-5788 | Helper |
| `_build_case_document_state_hash` | 5790-5824 | Helper |
| `_fetch_all_case_document_metadata` | 5826-5853 | Helper |
| `_build_case_document_state_hash_lightweight` | 5855-5889 | Helper |
| `_build_gap_analysis_batches` | 5917-6037 | Helper |
| `_run_gap_analysis` | 6039-6095 | Helper |
| `_build_signature_evidence` | 6097-6171 | Helper |
| `_build_document_registry_for_gap_context` | 6173-6284 | Helper |
| `_build_truncation_context` | 6286-6302 | Helper |
| `_build_gap_analysis_input_hash` | 6310-6344 | Helper |
| `_compute_resolution_document_state_hash` | 6470-6495 | Helper |
| `_parse_gap_document_summaries` | 6497-6541 | Helper |
| `_stamp_document_ids` | 6543-6585 | Helper |
| `_fetch_gap_intake_content` | 6587-6593 | Helper |
| `_collect_resolution_documents` | 6595-6634 | Helper |
| `_build_resolution_context` | 6636-6684 | Helper |
| `analyze_gaps_on_demand` | 6686-6847 | POST /analyze-gaps |
| `resolve_gaps_and_refresh` | 6850-7043 | POST /analyze-gaps/resolve |
| `analyze_gaps_streaming` | 7046-7223 | POST /analyze-gaps/stream |

**Endpoints (3):**
- `POST /api/analysis/analyze-gaps`
- `POST /api/analysis/analyze-gaps/resolve`
- `POST /api/analysis/analyze-gaps/stream`

---

#### Module 4: `chat_routes.py` (~400 LOC)

**Responsibility:** Case chat with AI assistant.

**Moves here:**
| Function | Lines | Type |
|----------|-------|------|
| `stream_chat_response` | 2937-3012 | POST /{analysis_id}/chat/stream |
| `case_chat` | 7226-7291 | POST /chat |

**Endpoints (2):**
- `POST /api/analysis/{analysis_id}/chat/stream`
- `POST /api/analysis/chat`

---

#### Module 5: `document_status_routes.py` (~500 LOC)

**Responsibility:** Document status, retry, and skip for in-progress analyses.

**Moves here:**
| Function | Lines | Type |
|----------|-------|------|
| `RetryDocumentsRequest` | 7293-7299 | Pydantic model |
| `SkipDocumentsRequest` | 7302-7308 | Pydantic model |
| `DocumentStatusResponse` | 7311-7321 | Pydantic model |
| `RecoveryActionResponse` | 7324-7330 | Pydantic model |
| `get_document_status` | 7334-7375 | GET /{analysis_id}/documents |
| `retry_failed_documents` | 7379-7448 | POST /{analysis_id}/retry |
| `skip_failed_documents` | 7451-7522 | POST /{analysis_id}/skip |

**Endpoints (3):**
- `GET /api/analysis/{analysis_id}/documents`
- `POST /api/analysis/{analysis_id}/retry`
- `POST /api/analysis/{analysis_id}/skip`

---

#### Module 6: `_analysis_helpers.py` (~600 LOC, not a router)

**Responsibility:** Shared utilities used by multiple analysis route modules.

**Moves here:**
| Function | Lines | Type |
|----------|-------|------|
| `_TRANSIENT_CODES` | constant | Constant |
| `_TRANSIENT_MESSAGES` | constant | Constant |
| `_DB_COLUMNS_CACHE` | constant | Constant (→ convert to `@lru_cache`) |
| `_SIGNATURE_*` patterns | constants | Constants (6 regex pattern sets) |
| `_HTML2TEXT_CONVERTER` | constant | Constant |
| `ARTIFACT_BUCKET`, `ARTIFACT_PREFIX`, `SIGNED_URL_TTL` | constants | Constants |
| `_is_transient_error` | 421-428 | Helper |
| `_upsert_with_retry` | 430-445 | Helper |
| `_update_case_with_retry` | 447-461 | Helper |
| `_to_sse` | 506-509 | Helper |
| `_first_non_empty_text` | 610-620 | Helper |
| `_normalize_signature_verification_status` | 863-869 | Helper |
| `_extract_signature_verification` | 871-898 | Helper |
| `_apply_signature_verification_override` | 900-957 | Helper |
| `_normalize_text_signing_date` | 959-985 | Helper |
| `_infer_signature_detection_from_text` | 987-1047 | Helper |
| `_is_pdf_like_document` | 1049-1054 | Helper |
| `_is_signature_inference_candidate` | 1056-1092 | Helper |
| `_sample_text_for_state_hash` | 1094-1104 | Helper |
| `_extract_signature_instrument_hints` | 1106-1140 | Helper |
| `_convert_statute_recommendations_recursive` | 3941-3976 | Helper |
| `_parse_currency` | 3978-3999 | Helper |
| `_extract_embedded_json` | 4001-4024 | Helper |
| `_extract_section` | 4026-4034 | Helper |
| `_extract_list_items` | 4036-4046 | Helper |
| `_hash_jsonable` | 6304-6308 | Helper |
| `_ensure_case_access` | 7579-7587 | Helper |
| `_fetch_latest_analysis_result` | 7589-7614 | Helper |

---

#### Target File Structure

```
src/legal_portal/api/routes/
├── __init__.py
├── analysis_core.py              # ~1,800 LOC — start, cancel, status, results, streaming
├── letter_routes.py              # ~2,200 LOC — findings, demand, recommendation letters
├── gap_routes.py                 # ~1,600 LOC — gap analysis run/resolve/stream
├── chat_routes.py                # ~400 LOC — case chat
├── document_status_routes.py     # ~500 LOC — document status/retry/skip
├── _analysis_helpers.py          # ~600 LOC — shared constants, retry, signature utils
├── cases.py                      # (unchanged)
├── documents.py                  # (unchanged)
├── clio.py                       # (unchanged)
├── progress.py                   # (unchanged)
├── intake.py                     # (unchanged)
├── corpus.py                     # (unchanged)
├── profile.py                    # (unchanged)
├── health.py                     # (unchanged)
└── settings.py                   # (unchanged)
```

#### Router Registration (main.py)

```python
# Before (1 router):
from legal_portal.api.routes import analysis
app.include_router(analysis.router, prefix="/api/analysis")

# After (5 routers, same prefix):
from legal_portal.api.routes import analysis_core, letter_routes, gap_routes, chat_routes, document_status_routes

app.include_router(analysis_core.router, prefix="/api/analysis")
app.include_router(letter_routes.router, prefix="/api/analysis")
app.include_router(gap_routes.router, prefix="/api/analysis")
app.include_router(chat_routes.router, prefix="/api/analysis")
app.include_router(document_status_routes.router, prefix="/api/analysis")
```

All endpoints keep the same URL paths. Zero frontend changes required.

---

### 1.2 Service Layer Target Structure

```
src/legal_portal/services/
├── __init__.py
├── analysis/
│   ├── __init__.py
│   ├── multi_stage_analyzer.py       # 4-stage analysis pipeline
│   ├── gap_analysis_service.py       # Gap detection + map-reduce
│   ├── corpus_coverage_service.py    # Statute coverage analysis
│   ├── statute_validation_service.py # Statute citation validation
│   ├── statute_recommendation_service.py # Statute recommendations
│   ├── deadline_extraction_service.py # Deadline detection
│   └── qa_service.py                # QA heuristics
│
├── documents/
│   ├── __init__.py
│   ├── main_processor.py            # Pipeline orchestrator
│   ├── document_registry_service.py  # Classification + grouping
│   ├── document_quality_validator.py # Quality validation
│   ├── content_extraction_service.py # Key fact extraction
│   ├── chunk_service.py             # Document chunking
│   ├── chunk_state_manager.py       # Chunk processing state
│   └── file_processors/             # (already exists, move as-is)
│       ├── __init__.py
│       ├── pdf_processor.py
│       ├── docx_processor.py
│       ├── eml_processor.py
│       ├── image_processor.py
│       ├── batch_vision_processor.py
│       ├── csv_processor.py
│       ├── txt_processor.py
│       ├── doc_processor.py
│       └── utils.py
│
├── letters/
│   ├── __init__.py
│   ├── demand_letter_service.py      # Demand letter generation
│   ├── recommendation_letter_service.py # Recommendation letters
│   ├── letter_strategy_service.py    # Pre-draft strategy
│   ├── letter_quality_lint_service.py # Quality rules
│   ├── letter_validation_service.py  # Validation checks
│   ├── letter_review_service.py      # AI-powered review
│   ├── fallback_generation_service.py # Graceful degradation
│   ├── citation_tracking_service.py  # Citation management
│   └── json_architecture_service.py  # Structured JSON output
│
├── integrations/
│   ├── __init__.py
│   ├── clio_context_builder.py       # Clio matter context
│   ├── clio_data_transformer.py      # Clio data mapping
│   └── case_chat_service.py          # Chat service
│
├── shared/
│   ├── __init__.py
│   ├── json_processing_service.py    # JSON repair + streaming
│   ├── document_formatter.py         # HTML/markdown formatting
│   ├── content_formatting_service.py # Content formatting
│   ├── content_generation_service.py # Content generation
│   ├── text_processing_service.py    # Text cleanup
│   ├── template_rendering_service.py # Template rendering
│   ├── prompt_and_api_service.py     # Prompt building
│   ├── file_compression_service.py   # File compression
│   └── progress_manager.py          # Progress tracking
│
└── grouping/
    ├── __init__.py
    ├── group_summarizer.py           # Group summary generation
    └── group_quality_metrics.py      # Grouping quality metrics
```

Each subdirectory `__init__.py` re-exports public classes so existing imports like `from legal_portal.services.main_processor import ...` continue to work during migration.

---

## 2. Refactor Strategy

### 2.1 Exception Handling Strategy

#### Exception Hierarchy

Create `src/legal_portal/core/exceptions.py`:

```python
"""Unified exception hierarchy for the legal portal."""


class LegalPortalError(Exception):
    """Base exception. All portal exceptions inherit from this."""

    def __init__(self, message: str, *, code: str = "INTERNAL_ERROR", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


# --- Document Processing ---

class DocumentError(LegalPortalError):
    """Base for document processing failures."""
    pass


class DocumentExtractionError(DocumentError):
    """Text extraction failed for a document."""
    pass


class DocumentValidationError(DocumentError):
    """Document failed validation (corrupt, unsupported, too large)."""
    pass


class OCRError(DocumentError):
    """OCR-specific failure (Vision API, remote OCR service)."""
    pass


# --- AI / Analysis ---

class AIError(LegalPortalError):
    """Base for AI/LLM failures."""
    pass


class AIAnalysisError(AIError):
    """Analysis-specific AI failure (replaces existing AIAnalysisError)."""
    pass


class AIRateLimitError(AIError):
    """OpenAI rate limit hit."""
    pass


class AIResponseParseError(AIError):
    """AI returned unparseable response."""
    pass


# --- Letter Generation ---

class LetterGenerationError(LegalPortalError):
    """Letter generation failed."""
    pass


class InsufficientDocumentsError(LetterGenerationError):
    """Not enough documents to generate a letter."""
    pass


# --- Database ---

class DatabaseError(LegalPortalError):
    """Database operation failed."""
    pass


class TransientDatabaseError(DatabaseError):
    """Retriable database error (502, 503, timeout)."""
    pass


# --- Integration ---

class IntegrationError(LegalPortalError):
    """External service integration failure."""
    pass


class ClioError(IntegrationError):
    """Clio API failure."""
    pass


class ClioAuthError(ClioError):
    """Clio authentication/token failure."""
    pass


# --- User Actions ---

class AnalysisCancelledError(LegalPortalError):
    """User cancelled analysis."""
    pass


class AccessDeniedError(LegalPortalError):
    """User lacks access to resource."""
    pass
```

#### Global Exception Handler

Add to `main.py`:

```python
from legal_portal.core.exceptions import (
    LegalPortalError, TransientDatabaseError, AccessDeniedError,
    DocumentValidationError, AIRateLimitError
)

@app.exception_handler(LegalPortalError)
async def portal_error_handler(request: Request, exc: LegalPortalError):
    status_map = {
        AccessDeniedError: 403,
        DocumentValidationError: 422,
        AIRateLimitError: 429,
        TransientDatabaseError: 503,
    }
    status_code = status_map.get(type(exc), 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": type(exc).__name__,
            "code": exc.code,
            "message": str(exc),
        },
    )
```

#### When to Catch vs Propagate

| Scenario | Action |
|----------|--------|
| Transient DB error with retries left | Catch, log warning, retry |
| Transient DB error, retries exhausted | Raise `TransientDatabaseError` |
| OpenAI rate limit | Raise `AIRateLimitError` (tenacity handles retry) |
| OpenAI unparseable response | Raise `AIResponseParseError` |
| PDF corrupt / unreadable | Raise `DocumentExtractionError`, mark doc as failed |
| User lacks case access | Raise `AccessDeniedError` |
| JSON parse failure in AI output | Catch, log, attempt repair via `JsonProcessingService` |
| Metrics/logging failure | Catch silently — never fail the request for telemetry |

#### Before/After Examples

**Example 1: Database retry**

```python
# BEFORE (analysis.py:430-445)
async def _upsert_with_retry(supabase, table, data, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return supabase.table(table).upsert(data).execute()
        except Exception as e:
            if _is_transient_error(e) and attempt < max_attempts - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise

# AFTER
from legal_portal.core.exceptions import TransientDatabaseError

async def upsert_with_retry(supabase, table, data, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return supabase.table(table).upsert(data).execute()
        except postgrest.APIError as e:
            if e.code in ("502", "503", "57014") and attempt < max_attempts - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise TransientDatabaseError(
                f"Database upsert failed after {max_attempts} attempts",
                code="DB_UPSERT_FAILED",
                details={"table": table, "error": str(e)},
            ) from e
```

**Example 2: PDF processing**

```python
# BEFORE (pdf_processor.py:65-67)
try:
    pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
except Exception as e:
    logger.error(f"cannot parse PDF ({e})")
    return ChunkedOCRResult(text="", ocr_status="failed")

# AFTER
from legal_portal.core.exceptions import DocumentExtractionError

try:
    pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
except (PdfReadError, ValueError) as e:
    raise DocumentExtractionError(
        f"PDF is corrupt or unreadable: {e}",
        code="PDF_CORRUPT",
        details={"filename": original_filename},
    ) from e
```

#### Logging Standards

```python
# Structured logging — no emojis, consistent format
logger.info("analysis.started", extra={"case_id": case_id, "doc_count": len(docs)})
logger.warning("db.retry", extra={"table": table, "attempt": attempt, "error": str(e)})
logger.error("ai.parse_failed", extra={"model": model, "response_length": len(raw)}, exc_info=True)

# NEVER:
logger.debug(f"AI ANALYZER: 🔍 DEBUGGING - {thing}")  # No emojis, no shouting
```

---

### 2.2 Singleton Removal Plan

#### Summary of 6 Singletons

| Singleton | Current Pattern | Callers | Migration Strategy |
|-----------|----------------|---------|-------------------|
| `_global_cache` | Module-level `global` variable | 2 | `@lru_cache` in `dependencies.py` |
| `_global_sanitizer` | Module-level instance | 4 | `@lru_cache` in `dependencies.py` |
| `GoogleVisionClient._instance` | Class `_instance` variable | 2 | `@lru_cache` in `dependencies.py` |
| `MetricsCollector._instance` | `__new__` + threading.Lock | 4 | `app.state` in lifespan |
| `ProgressManager._instance` | `__new__` | 5 | `app.state` in lifespan |
| `get_supabase_client` | `@lru_cache` (already DI) | 8+ | Already correct, just add `maxsize=1` |

#### Migration Approach

Add to `dependencies.py`:

```python
# --- New dependency providers ---

from functools import lru_cache
from legal_portal.utils.cache_manager import CacheManager
from legal_portal.utils.pii_sanitizer import PIISanitizer
from legal_portal.utils.google_vision_client import GoogleVisionClient


@lru_cache(maxsize=1)
def get_cache_manager() -> CacheManager:
    return CacheManager()


@lru_cache(maxsize=1)
def get_pii_sanitizer() -> PIISanitizer:
    return PIISanitizer()


@lru_cache(maxsize=1)
def get_vision_client() -> GoogleVisionClient:
    return GoogleVisionClient()
```

For `MetricsCollector` and `ProgressManager` (stateful, need lifecycle):

```python
# main.py lifespan
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.metrics = MetricsCollector()
    app.state.progress = ProgressManager()
    yield
    # cleanup if needed

# dependencies.py
def get_metrics(request: Request) -> MetricsCollector:
    return request.app.state.metrics

def get_progress_manager(request: Request) -> ProgressManager:
    return request.app.state.progress
```

#### Before/After: GoogleVisionClient

```python
# BEFORE (pdf_processor.py:825)
google_client = GoogleVisionClient.get_instance()
text = google_client.extract_text(image_bytes)

# AFTER — services receive client via constructor
class PDFProcessor:
    def __init__(self, vision_client: GoogleVisionClient):
        self.vision_client = vision_client

    def process_pdf(self, pdf_bytes, ...):
        text = self.vision_client.extract_text(image_bytes)

# Route handler wires it up:
@router.post("/upload")
async def upload_document(
    vision_client: GoogleVisionClient = Depends(get_vision_client),
):
    processor = PDFProcessor(vision_client)
```

#### Migration Order

1. Fix `get_supabase_client` — add `maxsize=1` (5 minutes)
2. Add `get_cache_manager`, `get_pii_sanitizer`, `get_vision_client` to `dependencies.py`
3. Add `MetricsCollector` and `ProgressManager` to `app.state` via lifespan
4. Update callers one file at a time, starting with route handlers
5. Remove singleton patterns from original classes
6. Add `get_*` to `dependencies.py` `__all__` export

---

## 3. Test Plan

### 3.1 Safety Net Tests (Before Refactoring)

These tests verify current behavior so we can detect regressions during refactoring. They test at the API boundary, not internals.

#### Backend Safety Net Tests

Create `tests/safety_net/` with these files:

```
tests/safety_net/
├── __init__.py
├── conftest.py                      # Shared fixtures for safety net
├── test_analysis_lifecycle.py       # Start → status → results → cancel
├── test_letter_generation.py        # Findings + demand + recommendation
├── test_gap_analysis.py             # Run → resolve → refresh
├── test_streaming_endpoints.py      # SSE streaming behavior
├── test_document_operations.py      # Upload → extract → verify → delete
├── test_chat.py                     # Send message → get response
└── test_document_status.py          # Status → retry → skip
```

**test_analysis_lifecycle.py (6 tests):**
```python
async def test_start_analysis_returns_202():
    """POST /api/analysis/start returns 202 with analysis_id."""

async def test_get_analysis_status_returns_current_state():
    """GET /api/analysis/status/{case_id} returns status object."""

async def test_get_analysis_results_returns_structured_data():
    """GET /api/analysis/results/{case_id} returns full results."""

async def test_cancel_analysis_marks_cancelled():
    """POST /api/analysis/cancel/{id} sets status to cancelled."""

async def test_save_streaming_analysis_persists():
    """POST /api/analysis/stream/{case_id}/save stores content."""

async def test_get_streaming_result_returns_saved():
    """GET /api/analysis/stream/{case_id}/result returns saved content."""
```

**test_letter_generation.py (5 tests):**
```python
async def test_generate_findings_letter_returns_html():
    """POST /api/analysis/generate-letter returns letter_html."""

async def test_stream_findings_letter_produces_sse():
    """GET /api/analysis/{id}/letter/stream yields SSE events."""

async def test_generate_recommendation_letter():
    """POST /api/analysis/generate-recommendation-letter returns letter."""

async def test_stream_recommendation_letter_produces_sse():
    """GET /api/analysis/{id}/recommendation-letter/stream yields SSE."""

async def test_calculate_demand_amount_returns_breakdown():
    """POST /api/analysis/calculate-demand-amount returns amount + reasoning."""
```

**test_gap_analysis.py (3 tests):**
```python
async def test_analyze_gaps_returns_findings():
    """POST /api/analysis/analyze-gaps returns gap list."""

async def test_resolve_gaps_refreshes_analysis():
    """POST /api/analysis/analyze-gaps/resolve applies resolutions."""

async def test_stream_gap_analysis_produces_sse():
    """POST /api/analysis/analyze-gaps/stream yields SSE events."""
```

#### Frontend Safety Net Tests

Create Playwright E2E tests in `frontend/tests/e2e/`:

```
frontend/tests/e2e/
├── auth.spec.ts                     # Login → session → logout
├── case-workflow.spec.ts            # Create case → upload → start analysis
├── results-display.spec.ts          # View results → tabs → gap panel
└── helpers/
    └── fixtures.ts                  # Test data helpers
```

**auth.spec.ts:**
```typescript
test('login redirects to app dashboard', async ({ page }) => { ... });
test('unauthenticated user redirected to login', async ({ page }) => { ... });
test('session persists across page reload', async ({ page }) => { ... });
```

**case-workflow.spec.ts:**
```typescript
test('create case with client name', async ({ page }) => { ... });
test('upload document shows in list', async ({ page }) => { ... });
test('start analysis shows progress', async ({ page }) => { ... });
```

### 3.2 Test Coverage Priorities (During/After Refactoring)

**24 services currently have ZERO tests.** Priority order based on risk:

| Priority | Service | LOC | Why |
|----------|---------|-----|-----|
| P0 | gap_analysis_service.py | 800+ | Core business logic, 20+ methods, 0 tests |
| P0 | json_processing_service.py | 1,200+ | Used by all letter generation, 30+ methods, 1 test |
| P0 | document_registry_service.py | 1,200+ | Classification affects all analysis, 4 tests for 30+ methods |
| P1 | case_chat_service.py | 200+ | User-facing feature |
| P1 | chunk_state_manager.py | 400+ | Manages processing state |
| P1 | progress_manager.py | 250+ | SSE streaming depends on this |
| P1 | document_formatter.py | 500+ | All letter output depends on this |
| P2 | letter_review_service.py | 350+ | Quality gate |
| P2 | content_generation_service.py | 400+ | Email/analysis output |
| P2 | fallback_generation_service.py | 300+ | Graceful degradation |

### 3.3 Test Directory Structure

```
tests/
├── conftest.py                      # Shared fixtures (existing, 625 LOC)
├── safety_net/                      # NEW: Pre-refactor safety tests
├── unit/                            # Existing unit tests (41 files)
│   └── (add new tests alongside existing)
├── api/                             # Existing API tests (16 files)
├── integration/                     # Existing integration tests (7 files)
│   └── conftest.py                  # Integration fixtures (existing)
└── e2e/                             # NEW: Playwright tests
```

**Test frameworks:**
- Backend: `pytest` + `pytest-asyncio` + `httpx.AsyncClient` (already configured)
- Frontend: `vitest` for unit tests (already configured), `playwright` for E2E (already in devDeps)

---

## 4. Risk Controls

### Phase-by-Phase Risk Analysis

#### Phase 1: Dead Code Removal (Day 1-2)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Deleting a file that's actually imported | Low | High | `grep -r "import.*filename"` before each delete |
| Breaking CI by removing a test dependency | Low | Medium | Run full test suite after each batch of deletions |

**Rollback:** `git revert` the commit. All changes are pure deletions.

**Safety indicator:** Full test suite passes. No import errors on `python -c "from legal_portal.api.main import app"`.

---

#### Phase 2: Documentation Cleanup (Day 2-3)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Deleting a doc someone references | Low | Low | Docs are not code; can be restored from git |

**Rollback:** `git revert`.

**Safety indicator:** No broken doc links in README.md.

---

#### Phase 3: Exception Hierarchy + Shared Utilities (Day 4-6)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| New exception types change HTTP status codes | Medium | Medium | Safety net tests verify status codes |
| Retry logic changes break error recovery | Medium | High | Test transient error scenarios explicitly |

**Rollback:** `git revert` the exception hierarchy commit. Old `except Exception` blocks still work.

**Safety indicator:** All existing tests pass. Manual test: trigger a transient DB error and verify retry behavior.

---

#### Phase 4: Split analysis.py (Day 7-11) — HIGHEST RISK

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Import cycle between new modules | Medium | High | `_analysis_helpers.py` has no router imports |
| Endpoint URL changes | Low | Critical | All routers use same prefix; verify with `app.openapi()` |
| Shared state (`_DB_COLUMNS_CACHE`) breaks | Medium | Medium | Move to `_analysis_helpers.py`, accessed by all modules |
| Missing function in wrong module | Medium | Medium | Run `python -c "from legal_portal.api.main import app"` after each file move |

**Rollback strategy:**
1. Keep `analysis.py` in place during development
2. Create new modules alongside it
3. Move functions one category at a time (gaps first, then letters, then chat, then doc status, then core)
4. After each category, run safety net tests
5. Only delete from `analysis.py` after the new module's tests pass
6. Final step: delete empty `analysis.py`

**Safety indicators:**
- `pytest tests/safety_net/` passes after each module extraction
- `curl localhost:8000/openapi.json | python -c "import sys,json; routes=[r['path'] for r in json.load(sys.stdin)['paths']]; print(len(routes))"` returns same count before and after
- Frontend smoke test: start analysis, view results, generate letter

---

#### Phase 5: Service Layer Reorganization (Day 12-13)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Import paths change, callers break | High | Medium | Add re-exports in `services/__init__.py` |
| Circular imports from new subdirectory structure | Medium | High | Audit import graph before moving |

**Rollback:** `git revert`. File moves are easy to undo.

**Safety indicator:** Full test suite passes. `python -c "from legal_portal.services.main_processor import process_case_documents"` works.

---

#### Phase 6: data_models.py Split (Day 14)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 100+ import statements need updating | High | Medium | Keep `data_models.py` as re-export shim |
| Pydantic model forward references break | Medium | Medium | Use `from __future__ import annotations` |

**Rollback:** `git revert`. Models file is self-contained.

**Safety indicator:** `mypy src/legal_portal/core/` passes. All tests pass.

---

#### Phase 7: Frontend Component Extraction (Day 15-17)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| State shared between components incorrectly | High | High | Extract one section at a time; test manually |
| Event handlers disconnected | Medium | High | Check every `on:click` and callback prop |
| CSS scoping issues | Medium | Low | Svelte scopes CSS by default |

**Rollback:** `git revert`. Frontend changes are visual — easy to verify.

**Safety indicator:** Manual test each page: upload, verify, analyze, view results, generate letter, chat. Playwright E2E if available.

---

#### Phase 8: Singleton Migration (Day 18)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Service not initialized at request time | Medium | High | `@lru_cache` ensures lazy init |
| Tests that relied on global state break | Medium | Medium | Update test fixtures |

**Rollback:** `git revert`. Singletons still work; DI is additive.

**Safety indicator:** Full test suite passes. Manual smoke test of analysis pipeline.

---

## 5. Execution Timeline

### 3-Week Sprint: Day-by-Day Plan

#### Week 1: Foundation (Days 1-5)

**Day 1 — Dead Code Removal**
- [ ] Delete `src/legal_portal/core/email_generator_core.py`
- [ ] Delete `src/legal_portal/config/config_manager.py` (verify no live imports first)
- [ ] Delete `src/legal_portal/config/auth_config.yaml`
- [ ] Delete root-level `test_gap_fix.py`
- [ ] Delete ~15 orphaned scripts (`debug_create_case.py`, `create_mock_session.py`, `verify_sse_setup.py`, `verify_google_vision.py`, `verify_letter_structure.py`, `test_current_letter.py`, `verify_sse_setup.py`, `check_progress.sh`, `check_constraints.sh`, `test_vercel_env.sh`, etc.)
- [ ] Remove unused frontend icon imports (grep for imported-but-unused)
- [ ] Remove `thinkingTime` dead variable from `AnalysisStreamPanel.svelte`
- [ ] Clean `.worktrees/feature/` empty directory
- [ ] **Checkpoint:** `pytest` passes, `python -c "from legal_portal.api.main import app"` works
- [ ] **Commit:** "chore: remove dead code and orphaned scripts"

**Day 2 — Documentation Cleanup**
- [ ] Delete ~22 root-level one-off fix/Vercel .md files
- [ ] Merge `ENV_SETUP_GUIDE.md` into `START_HERE.md`
- [ ] Merge `RESTART_*.md` into `LAUNCH_APP.md`
- [ ] Merge `TESTING_VALIDATION_GUIDE.md` into `TESTING_GUIDE.md`
- [ ] Archive 9 implementation summary .md files to `docs/archive/`
- [ ] Consolidate 7 letter docs into `docs/LETTER_GENERATION.md`
- [ ] Update `.env.example` with all current variables documented
- [ ] **Checkpoint:** `ls *.md | wc -l` shows ~15 files (down from 48)
- [ ] **Commit:** "docs: consolidate documentation, remove one-off fix files"

**Day 3 — Safety Net Tests**
- [ ] Create `tests/safety_net/conftest.py` with analysis fixtures
- [ ] Write `test_analysis_lifecycle.py` (6 tests)
- [ ] Write `test_letter_generation.py` (5 tests)
- [ ] Write `test_gap_analysis.py` (3 tests)
- [ ] Write `test_document_status.py` (3 tests)
- [ ] Write `test_chat.py` (2 tests)
- [ ] **Checkpoint:** All 19 safety net tests pass
- [ ] **Commit:** "test: add safety net tests for analysis API"

**Day 4 — Exception Hierarchy**
- [ ] Create `src/legal_portal/core/exceptions.py` with full hierarchy
- [ ] Add global exception handler to `main.py`
- [ ] Convert 10 highest-risk `except Exception` blocks in `analysis.py`
- [ ] Convert 5 in `documents.py`
- [ ] Convert 5 in `pdf_processor.py`
- [ ] **Checkpoint:** Safety net tests pass. No new 500 errors.
- [ ] **Commit:** "refactor: introduce exception hierarchy, convert 20 broad catches"

**Day 5 — Shared Utilities Extraction**
- [ ] Extract `_is_transient_error`, `_upsert_with_retry`, `_update_case_with_retry` from `analysis.py`, `documents.py`, `cases.py` into `api/middleware/retry.py`
- [ ] Extract signature-related helpers from `analysis.py` into `_analysis_helpers.py`
- [ ] Move `IMAGE_HANDLING_INSTRUCTIONS` from `main_processor.py` to `config/prompts_and_settings.json`
- [ ] **Checkpoint:** Safety net tests pass. `grep -r "_is_transient_error" src/` shows only 1 definition.
- [ ] **Commit:** "refactor: extract shared retry logic and analysis helpers"

**Milestone: Foundation complete. Codebase is cleaner, has safety tests, and shared utilities are consolidated.**

---

#### Week 2: The Big Split (Days 6-10)

**Day 6 — Split analysis.py: Gap Routes**
- [ ] Create `gap_routes.py` with `APIRouter()`
- [ ] Move `GapBatch`, `GapAnalysisRequest`, `GapResolutionItemRequest`, `GapResolutionRefreshRequest`
- [ ] Move all `_build_gap_*`, `_fetch_*_for_gap_*`, `_derive_*`, `_run_gap_analysis` helpers
- [ ] Move `analyze_gaps_on_demand`, `resolve_gaps_and_refresh`, `analyze_gaps_streaming`
- [ ] Register in `main.py`
- [ ] Delete moved functions from `analysis.py`
- [ ] **Checkpoint:** Safety net gap tests pass. `curl /api/analysis/analyze-gaps` works.
- [ ] **Commit:** "refactor: extract gap analysis routes from analysis.py"

**Day 7 — Split analysis.py: Letter Routes**
- [ ] Create `letter_routes.py` with `APIRouter()`
- [ ] Move all letter Pydantic models
- [ ] Move `stream_findings_letter`, `generate_letter`, `generate_recommendation_letter`, `stream_recommendation_letter`, `calculate_demand_amount`
- [ ] Move letter helper functions (`_resolve_letter_identity_context`, `_resolve_client_name_for_letter`, artifact helpers)
- [ ] Register in `main.py`
- [ ] Delete moved functions from `analysis.py`
- [ ] **Checkpoint:** Safety net letter tests pass. Letter streaming works.
- [ ] **Commit:** "refactor: extract letter generation routes from analysis.py"

**Day 8 — Split analysis.py: Chat + Document Status**
- [ ] Create `chat_routes.py` — move `stream_chat_response`, `case_chat`
- [ ] Create `document_status_routes.py` — move status/retry/skip models and handlers
- [ ] Register in `main.py`
- [ ] Delete moved functions from `analysis.py`
- [ ] **Checkpoint:** Safety net tests pass for chat and document status.
- [ ] **Commit:** "refactor: extract chat and document status routes"

**Day 9 — Finalize analysis.py → analysis_core.py**
- [ ] Rename remaining `analysis.py` to `analysis_core.py`
- [ ] Verify all imports across codebase updated
- [ ] Run full test suite
- [ ] Run `python -c "from legal_portal.api.main import app; print([r.path for r in app.routes])"` and verify all 21 endpoints present
- [ ] **Checkpoint:** All safety net tests pass. Full test suite passes.
- [ ] **Commit:** "refactor: rename analysis.py to analysis_core.py — split complete"

**Day 10 — Service Layer Reorganization**
- [ ] Create subdirectory structure: `services/analysis/`, `services/documents/`, `services/letters/`, `services/integrations/`, `services/shared/`, `services/grouping/`
- [ ] Move files into subdirectories
- [ ] Add `__init__.py` with re-exports for backward compatibility
- [ ] Update imports in route handlers
- [ ] **Checkpoint:** Full test suite passes. `python -c "from legal_portal.services.main_processor import process_case_documents"` works.
- [ ] **Commit:** "refactor: reorganize services into domain subdirectories"

**Milestone: analysis.py split complete. Service layer organized. All endpoints unchanged.**

---

#### Week 3: Polish (Days 11-15)

**Day 11 — Split data_models.py**
- [ ] Create `core/models/` directory
- [ ] Create `document_models.py` — move document-related Pydantic models
- [ ] Create `analysis_models.py` — move analysis-related models
- [ ] Create `letter_models.py` — move letter-related models
- [ ] Create `enums.py` — consolidate all enums
- [ ] Keep `data_models.py` as re-export shim: `from .models.document_models import *` etc.
- [ ] **Checkpoint:** `mypy src/legal_portal/core/` passes. Full tests pass.
- [ ] **Commit:** "refactor: split data_models.py into domain-specific modules"

**Day 12-13 — Frontend Component Extraction**
- [ ] Extract `LettersTab.svelte` from `results/+page.svelte` (lines 2061-2472)
  - State: all findings/demand letter state
  - Props: `results`, `documents`, `analysisId`, `caseId`
  - Events: letter generation callbacks
- [ ] Extract `ChatTab.svelte` from `results/+page.svelte` (lines 2473-2539)
  - State: `chatMessages`, `chatInput`, `sendingMessage`
  - Props: `analysisId`, `caseId`
- [ ] Extract `GapAnalysisTab.svelte` from `results/+page.svelte` (lines 1892-1981)
  - State: gap analysis state
  - Props: `gapAnalysis`, `documents`
- [ ] Extract `DocumentViewerModal.svelte` (shared between both pages)
  - State: `viewingDocument`, `pdfBlobUrl`, `documentViewerTab`
  - Props: document data
- [ ] Extract `DocumentUploadManager.svelte` from `[id]/+page.svelte` (lines 2028-2497)
  - State: upload-related state
  - Props: `caseId`, `documents`
- [ ] **Checkpoint:** Manual test all pages: upload, verify, analyze, results, letters, chat
- [ ] **Commit:** "refactor: extract tab components from monolithic page files"

**Day 14 — Singleton Migration**
- [ ] Add `get_cache_manager`, `get_pii_sanitizer`, `get_vision_client` to `dependencies.py`
- [ ] Add `MetricsCollector` and `ProgressManager` to `app.state` via lifespan
- [ ] Update route handlers to use `Depends()` instead of `.get_instance()`
- [ ] Remove `_instance`, `__new__`, and `_global_*` patterns from original classes
- [ ] Update test fixtures to provide dependencies explicitly
- [ ] **Checkpoint:** Full test suite passes. `pytest tests/safety_net/` passes.
- [ ] **Commit:** "refactor: migrate singletons to dependency injection"

**Day 15 — Remaining Exception Conversion + Final Validation**
- [ ] Convert remaining high-value `except Exception` blocks (target: reduce from 428 to <200)
- [ ] Focus on: `ai_analyzer.py`, `main_processor.py`, `gap_analysis_service.py`, `json_processing_service.py`
- [ ] Run full test suite
- [ ] Run Playwright E2E tests if available
- [ ] Manual smoke test: full case lifecycle (create → upload → analyze → results → letter → export)
- [ ] Document any remaining exceptions that are intentionally broad (e.g., metrics logging)
- [ ] **Final commit:** "refactor: convert broad exception catches to specific types"

**Milestone: Refactor sprint complete. Codebase ready for async job queue architecture.**

---

### Milestone Summary

| Milestone | Day | Validation |
|-----------|-----|------------|
| Foundation complete | Day 5 | Dead code removed, docs cleaned, safety tests pass, shared utils extracted |
| analysis.py split complete | Day 9 | 7,614 LOC → 6 modules, all 21 endpoints unchanged, all tests pass |
| Service layer organized | Day 10 | 40+ flat files → 6 subdirectories, backward-compatible imports |
| data_models.py split | Day 11 | 88 models → 4 domain files + re-export shim |
| Frontend decomposed | Day 13 | 3,326 + 2,873 LOC pages → extracted tab components |
| Singletons removed | Day 14 | 6 singletons → FastAPI Depends() |
| Exception handling normalized | Day 15 | 428 → <200 broad catches, exception hierarchy in place |

### Post-Sprint: Ongoing Work

These items continue after the sprint but are not blockers:

- Continue converting remaining `except Exception` blocks (target: <50)
- Add P0 test coverage for `gap_analysis_service.py` and `json_processing_service.py`
- Add Playwright E2E tests for full case lifecycle
- Set up `mypy --strict` in CI
- Audit remaining `any` types in frontend TypeScript
