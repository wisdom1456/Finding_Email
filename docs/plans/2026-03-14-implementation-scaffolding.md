# Implementation Scaffolding — Refactor Execution Artifacts

**Date:** 2026-03-14
**Purpose:** Concrete artifacts engineers use during each refactor phase
**Prerequisites:** [Audit](./2026-03-14-codebase-audit-and-refactor-plan.md) · [Execution Plan](./2026-03-14-refactor-execution-plan.md) · [Blueprint](./2026-03-14-engineering-blueprint.md)

---

## 1. Final Architecture

### 1.1 Target Backend Directory Tree

After all 9 refactor phases complete, the backend looks like this:

```
src/legal_portal/
├── __init__.py
│
├── api/                                    # HTTP layer — routing, auth, middleware
│   ├── __init__.py
│   ├── main.py                             # FastAPI app, CORS, lifespan, router registration
│   ├── dependencies.py                     # Auth (JWT), Supabase clients, DI providers
│   ├── rate_limiter.py                     # slowapi rate limiter instance
│   │
│   ├── middleware/                          # NEW — extracted from routes
│   │   ├── __init__.py
│   │   ├── error_handler.py                # Unified exception → HTTP response mapping
│   │   └── retry.py                        # _is_transient_error(), _upsert_with_retry(), retry decorator
│   │
│   ├── routes/                             # Route handlers — thin HTTP wrappers over services
│   │   ├── __init__.py
│   │   ├── _analysis_helpers.py            # Shared helpers: _to_sse(), _ensure_case_access(), constants
│   │   ├── analysis_core.py               # POST /start, /cancel, GET /status, /results, /state
│   │   ├── analysis_streaming.py          # GET /stream/{case_id}, POST /stream/{case_id}/save
│   │   ├── letter_routes.py               # POST /generate-letter, /calculate-demand-amount, GET /letter/stream
│   │   ├── gap_routes.py                  # POST /analyze-gaps, /analyze-gaps/resolve, /analyze-gaps/stream
│   │   ├── chat_routes.py                 # POST /chat, /{analysis_id}/chat/stream
│   │   ├── document_status_routes.py      # GET /{analysis_id}/documents, POST /retry, /skip
│   │   ├── cases.py                        # Case CRUD (unchanged)
│   │   ├── documents.py                    # Document upload/list (unchanged)
│   │   ├── clio.py                         # Clio OAuth + sync (unchanged)
│   │   ├── progress.py                     # SSE progress streams (unchanged)
│   │   ├── intake.py                       # Client intake form (unchanged)
│   │   ├── corpus.py                       # Statute corpus search (unchanged)
│   │   ├── profile.py                      # User profile (unchanged)
│   │   ├── health.py                       # Health check (unchanged)
│   │   └── settings.py                     # App settings (unchanged)
│   │
│   ├── services/                           # API-level service clients (Clio)
│   │   ├── __init__.py
│   │   ├── clio_auth_service.py            # Clio OAuth token management
│   │   └── clio_client.py                  # Clio API HTTP client
│   │
│   └── utils/
│       └── content_extractor.py            # Document text extraction (to be moved to services/)
│
├── core/                                   # Domain models, AI core, exceptions — framework-agnostic
│   ├── __init__.py
│   ├── exceptions.py                       # NEW — unified exception hierarchy
│   ├── ai_analyzer.py                      # OpenAI GPT-4o integration for analysis
│   ├── document_processor.py               # File dispatch orchestrator
│   │
│   └── models/                             # NEW — split from data_models.py (88 models → 5 files)
│       ├── __init__.py                     # Re-exports all models for backward compat
│       ├── enums.py                        # DocumentType, LetterType, AnalysisStatus, CaseType
│       ├── document_models.py              # ProcessedDocument, DocumentMetadata, DocumentGroup
│       ├── analysis_models.py              # AnalysisResult, Finding, Issue, GapAnalysis
│       ├── letter_models.py                # DemandLetter, RecommendationLetter, LetterSection
│       └── party_models.py                 # Party, Client, Attorney, InsuranceCompany
│
├── services/                               # Business logic — the heart of the application
│   ├── __init__.py
│   │
│   ├── analysis/                           # Analysis pipeline
│   │   ├── __init__.py
│   │   ├── main_processor.py               # Pipeline orchestrator (process_case_documents)
│   │   ├── multi_stage_analyzer.py          # 4-stage analysis engine
│   │   ├── gap_analysis_service.py          # Missing evidence + contradiction detection
│   │   └── qa_service.py                    # Quality assurance checks
│   │
│   ├── documents/                          # Document intake and processing
│   │   ├── __init__.py
│   │   ├── document_registry_service.py     # Document type classification
│   │   ├── content_extraction_service.py    # Text extraction orchestration
│   │   ├── chunk_service.py                 # Document chunking for large docs
│   │   ├── chunk_state_manager.py           # Chunk processing state
│   │   ├── document_quality_validator.py    # Upload validation
│   │   ├── file_compression_service.py      # Image/PDF compression
│   │   └── file_processors/                 # Type-specific processors
│   │       ├── __init__.py
│   │       ├── pdf_processor.py             # PDF parsing + OCR chunking
│   │       ├── docx_processor.py            # Word document extraction
│   │       ├── eml_processor.py             # Email (.eml) parsing
│   │       ├── image_processor.py           # Image OCR
│   │       ├── csv_processor.py             # CSV/spreadsheet
│   │       ├── doc_processor.py             # Legacy .doc format
│   │       ├── txt_processor.py             # Plain text
│   │       ├── batch_vision_processor.py    # Batch Google Vision calls
│   │       └── utils.py                     # Shared processor utilities
│   │
│   ├── letters/                            # Letter generation pipeline
│   │   ├── __init__.py
│   │   ├── demand_letter_service.py         # Demand/findings letter generation
│   │   ├── recommendation_letter_service.py # Recommendation letter generation
│   │   ├── letter_strategy_service.py       # Pre-draft strategy planning
│   │   ├── letter_quality_lint_service.py   # Quality lint pass
│   │   ├── letter_review_service.py         # AI-powered final review
│   │   ├── letter_validation_service.py     # Schema + content validation
│   │   ├── template_rendering_service.py    # HTML template rendering
│   │   ├── fallback_generation_service.py   # Fallback when primary generation fails
│   │   └── content_generation_service.py    # Section-level content generation
│   │
│   ├── integrations/                       # External system adapters
│   │   ├── __init__.py
│   │   ├── clio_context_builder.py          # Build analysis context from Clio data
│   │   ├── clio_data_transformer.py         # Transform Clio API responses
│   │   ├── corpus_coverage_service.py       # Statute corpus matching
│   │   ├── statute_recommendation_service.py # Statute recommendations
│   │   └── statute_validation_service.py    # Statute citation validation
│   │
│   ├── shared/                             # Cross-cutting services
│   │   ├── __init__.py
│   │   ├── progress_manager.py              # Analysis progress tracking (DI, not singleton)
│   │   ├── json_processing_service.py       # JSON repair + extraction
│   │   ├── json_architecture_service.py     # JSON structure management
│   │   ├── document_formatter.py            # Document formatting for prompts
│   │   ├── content_formatting_service.py    # HTML/markdown formatting
│   │   ├── text_processing_service.py       # Text normalization
│   │   ├── citation_tracking_service.py     # Citation source tracking
│   │   ├── prompt_and_api_service.py        # Prompt template management
│   │   ├── deadline_extraction_service.py   # Deadline/SOL extraction
│   │   ├── case_chat_service.py             # Case Q&A chat
│   │   ├── group_summarizer.py              # Document group summarization
│   │   └── group_quality_metrics.py         # Group detection quality metrics
│   │
│   └── (no flat files remain — all organized into subdirectories)
│
├── config/                                 # Configuration — lowest layer
│   ├── __init__.py
│   ├── default.py                           # Pydantic Settings (env vars, feature flags)
│   └── prompts_and_settings.json            # AI prompt templates
│
└── utils/                                  # Pure utilities — zero service dependencies
    ├── __init__.py
    │
    ├── clients/                            # External API clients
    │   ├── __init__.py
    │   ├── openai_client.py                 # OpenAI API wrapper (DI, not singleton)
    │   ├── google_vision_client.py          # Google Vision OCR client (DI, not singleton)
    │   └── ocr_service_client.py            # Cloud Run OCR microservice client
    │
    ├── validation/                         # Input validation
    │   ├── __init__.py
    │   ├── enhanced_file_validator.py       # Upload file validation
    │   ├── validators.py                    # Generic validators
    │   └── type_safety.py                   # safe_str, sanitize_nested_dict
    │
    ├── caching/                            # Cache + cost tracking
    │   ├── __init__.py
    │   ├── cache_manager.py                 # File/memory cache (DI, not singleton)
    │   ├── cost_calculator.py               # API call cost calculation
    │   ├── cost_estimator.py                # Pre-call cost estimation
    │   ├── cost_exporter.py                 # Cost report export
    │   └── cost_session_manager.py          # Per-session cost tracking
    │
    ├── logging/                            # Observability
    │   ├── __init__.py
    │   ├── logging_config.py                # Root logger setup
    │   ├── structured_logger.py             # Structured JSON logging
    │   ├── audit_logger.py                  # Audit trail logging
    │   ├── diagnostic_logger.py             # Debug/diagnostic logger
    │   └── tracing.py                       # Request tracing
    │
    ├── metrics.py                           # MetricsCollector (DI, not singleton)
    ├── helpers.py                           # ProgressTracker + misc helpers
    ├── security.py                          # sanitize_text_for_db, XSS prevention
    ├── pii_sanitizer.py                     # PII detection/redaction (DI, not singleton)
    ├── token_manager.py                     # Token counting (single source of truth)
    ├── throttled_db_writer.py               # Batched DB writes
    ├── blacklist.py                         # Term blacklist
    ├── compression_utils.py                 # Generic compression
    ├── shared_utils.py                      # Misc shared utilities
    ├── markdown_utils.py                    # Markdown processing
    ├── timeline_analyzer.py                 # Timeline extraction from documents
    ├── quality_metrics.py                   # Quality scoring
    ├── prompt_builder.py                    # Prompt construction helpers
    ├── letter_formatter.py                  # Letter HTML formatting
    └── letter_polish.py                     # Letter final polish pass
```

### 1.2 Router Registration (main.py after split)

After splitting `analysis.py`, `main.py` registers the new routers. All routes keep the same `/api/analysis` prefix, so no frontend changes are needed:

```python
# main.py — router imports after split
from legal_portal.api.routes import (
    analysis_core,
    analysis_streaming,
    letter_routes,
    gap_routes,
    chat_routes,
    document_status_routes,
    cases,
    clio,
    corpus,
    documents,
    health,
    intake,
    profile,
    progress,
    settings,
)

# Analysis routes (was single analysis.router)
app.include_router(analysis_core.router,          prefix="/api/analysis", tags=["analysis"])
app.include_router(analysis_streaming.router,     prefix="/api/analysis", tags=["analysis-streaming"])
app.include_router(letter_routes.router,          prefix="/api/analysis", tags=["letters"])
app.include_router(gap_routes.router,             prefix="/api/analysis", tags=["gap-analysis"])
app.include_router(chat_routes.router,            prefix="/api/analysis", tags=["chat"])
app.include_router(document_status_routes.router, prefix="/api/analysis", tags=["document-status"])

# Existing routers (unchanged)
app.include_router(health.router,    tags=["health"])
app.include_router(cases.router,     prefix="/api/cases",     tags=["cases"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(progress.router,  prefix="/api",           tags=["progress"])
app.include_router(clio.router,      prefix="/api",           tags=["clio"])
app.include_router(intake.router,    prefix="/api",           tags=["intake"])
app.include_router(profile.router,   prefix="/api",           tags=["profile"])
app.include_router(settings.router,  prefix="/api/settings",  tags=["settings"])
app.include_router(corpus.router,    prefix="/api/corpus",    tags=["corpus"])
```

---

## 2. Migration Map

### 2.1 analysis.py Function-by-Function Migration Checklist

Source: `src/legal_portal/api/routes/analysis.py` (7,614 LOC, 22 endpoints, ~95 functions)

#### Category: Analysis Lifecycle

| Function/Class | Current Lines | Target Module | Dependencies | Tests Covering |
|---|---|---|---|---|
| `AnalysisRequest` | 1262–1267 | `analysis_core.py` | Pydantic BaseModel | `test_analysis.py` (4 tests) |
| `AnalysisResponse` | 1269–1278 | `analysis_core.py` | Pydantic BaseModel | `test_analysis.py` |
| `AnalysisCancelledError` | 530–531 | `analysis_core.py` | Exception | — |
| `_extract_deferred_documents()` | 63–310 | `analysis_core.py` | `_is_transient_error`, `_upsert_with_retry` (from helpers) | `test_deferred_extraction.py` (5 tests) |
| `_dedup_email_threads()` | 312–419 | `analysis_core.py` | None | `test_email_thread_dedup.py` (4 tests) |
| `_analysis_is_cancelled()` | 534–547 | `analysis_core.py` | Supabase query | — |
| `_cancel_analysis()` | 550–578 | `analysis_core.py` | `ProgressManager` | — |
| `_update_analysis_progress()` | 581–597 | `analysis_core.py` | Supabase query | — |
| `_get_user_ai_preferences()` | 599–608 | `analysis_core.py` | Supabase query | — |
| `_download_and_extract_documents()` | 1317–1635 | `analysis_core.py` | `DocumentProcessor`, file processors | — |
| `process_case_background()` | 1636–2354 | `analysis_core.py` | `main_processor`, many helpers | `test_analysis.py` (indirect) |
| **`start_analysis`** | 3014–3201 | `analysis_core.py` | `BackgroundTasks`, deps | `test_analysis.py` (3 tests) |
| **`cancel_analysis`** | 3204–3248 | `analysis_core.py` | — | `test_service_role_resilience.py` (1 test) |
| **`cancel_case_analysis`** | 3250–3300 | `analysis_core.py` | — | **NONE** |
| **`get_analysis_status`** | 3302–3354 | `analysis_core.py` | — | `test_analysis.py` (1 test) |
| **`get_analysis_results`** | 3355–3417 | `analysis_core.py` | — | `test_analysis.py` (2), `test_analysis_results_pending.py` (3) |
| **`get_analysis_state`** | 7524–7577 | `analysis_core.py` | — | **NONE** |

#### Category: Streaming

| Function/Class | Current Lines | Target Module | Dependencies | Tests Covering |
|---|---|---|---|---|
| `StreamingAnalysisSaveRequest` | 3419–3422 | `analysis_streaming.py` | Pydantic BaseModel | `test_save_streaming_analysis.py` |
| `save_streaming_analysis()` | 3425–3939 | `analysis_streaming.py` | `JsonProcessingService` | `test_save_streaming_analysis.py` (11 tests) |
| **`stream_case_analysis`** | 4047–4290 | `analysis_streaming.py` | `MultiStageAnalyzer` | **NONE** |
| **`get_streaming_result`** | 4293–4324 | `analysis_streaming.py` | — | **NONE** |

#### Category: Letter Generation

| Function/Class | Current Lines | Target Module | Dependencies | Tests Covering |
|---|---|---|---|---|
| `LetterGenerationRequest` | 1281–1304 | `letter_routes.py` | Pydantic BaseModel | `test_generate_letter_formatting.py` |
| `LetterGenerationResponse` | 1307–1314 | `letter_routes.py` | Pydantic BaseModel | `test_generate_letter_formatting.py` |
| `RecommendationLetterRequest` | 4875–4887 | `letter_routes.py` | Pydantic BaseModel | — |
| `RecommendationLetterResponse` | 4889–4896 | `letter_routes.py` | Pydantic BaseModel | — |
| `CalculateDemandAmountRequest` | 5475–5479 | `letter_routes.py` | Pydantic BaseModel | — |
| `CalculateDemandAmountResponse` | 5482–5487 | `letter_routes.py` | Pydantic BaseModel | — |
| `_resolve_letter_identity_context()` | 622–752 | `letter_routes.py` | Supabase queries | `test_letter_identity_resolution.py` (2 tests) |
| `_resolve_client_name_for_letter()` | 754–861 | `letter_routes.py` | Supabase queries | `test_letter_identity_resolution.py` |
| `_new_generation_metrics()` | 464–496 | `letter_routes.py` | — | — |
| `_emit_generation_metrics()` | 498–504 | `letter_routes.py` | `DiagnosticLogger` | — |
| `_quality_report_placeholder()` | 511–528 | `letter_routes.py` | — | — |
| `_store_artifact()` | 1173–1193 | `letter_routes.py` | Supabase Storage | — |
| `_generate_and_store_artifacts()` | 1195–1236 | `letter_routes.py` | `_store_artifact` | — |
| `_attach_signed_artifact_urls()` | 1238–1260 | `letter_routes.py` | Supabase Storage | — |
| `_ensure_fresh_gap_analysis_for_letter_generation()` | 6346–6468 | `letter_routes.py` | gap helpers (lazy import) | — |
| `_convert_statute_recommendations_recursive()` | 3941–3976 | `_analysis_helpers.py` | — | — |
| `_parse_currency()` | 3978–3999 | `_analysis_helpers.py` | — | — |
| `_extract_embedded_json()` | 4001–4024 | `_analysis_helpers.py` | — | — |
| `_extract_section()` | 4026–4034 | `_analysis_helpers.py` | — | — |
| `_extract_list_items()` | 4036–4046 | `_analysis_helpers.py` | — | — |
| **`stream_findings_letter`** | 2355–2935 | `letter_routes.py` | `DemandLetterService` + pipeline | `test_letter_stream_integration.py` (4 tests) |
| **`generate_letter`** | 4324–4873 | `letter_routes.py` | All letter services | `test_generate_letter_formatting.py` (1 test) |
| **`generate_recommendation_letter`** | 4899–5087 | `letter_routes.py` | `RecommendationLetterService` | **NONE** |
| **`stream_recommendation_letter`** | 5088–5473 | `letter_routes.py` | `RecommendationLetterService` | **NONE** |
| **`calculate_demand_amount`** | 5490–5589 | `letter_routes.py` | `DemandLetterService` | **NONE** |

#### Category: Gap Analysis

| Function/Class | Current Lines | Target Module | Dependencies | Tests Covering |
|---|---|---|---|---|
| `GapBatch` dataclass | 5891–5901 | `gap_routes.py` | — | — |
| `GapAnalysisRequest` | 5591–5598 | `gap_routes.py` | Pydantic BaseModel | — |
| `GapResolutionItemRequest` | 5601–5620 | `gap_routes.py` | Pydantic BaseModel | — |
| `GapResolutionRefreshRequest` | 5623–5649 | `gap_routes.py` | Pydantic BaseModel | — |
| 18 gap helper functions (signature, hash, batch) | 5652–6684 | `gap_routes.py` | `_hash_jsonable`, sig utils from helpers | `test_gap_resolution_helpers.py` (12 tests) |
| **`analyze_gaps_on_demand`** | 6684–6847 | `gap_routes.py` | `GapAnalysisService` | **NONE** |
| **`resolve_gaps_and_refresh`** | 6848–7043 | `gap_routes.py` | `GapAnalysisService` | **NONE** |
| **`analyze_gaps_streaming`** | 7044–7223 | `gap_routes.py` | `GapAnalysisService` | **NONE** |

#### Category: Chat

| Function/Class | Current Lines | Target Module | Dependencies | Tests Covering |
|---|---|---|---|---|
| **`stream_chat_response`** | 2936–3012 | `chat_routes.py` | `CaseChatService` | **NONE** |
| **`case_chat`** | 7225–7291 | `chat_routes.py` | `CaseChatService` | **NONE** |

#### Category: Document Status

| Function/Class | Current Lines | Target Module | Dependencies | Tests Covering |
|---|---|---|---|---|
| `RetryDocumentsRequest` | 7293–7299 | `document_status_routes.py` | Pydantic BaseModel | — |
| `SkipDocumentsRequest` | 7302–7308 | `document_status_routes.py` | Pydantic BaseModel | — |
| `DocumentStatusResponse` | 7311–7321 | `document_status_routes.py` | Pydantic BaseModel | — |
| `RecoveryActionResponse` | 7324–7330 | `document_status_routes.py` | Pydantic BaseModel | — |
| **`get_document_status`** | 7333–7375 | `document_status_routes.py` | Supabase query | `test_documents.py` (1 test) |
| **`retry_failed_documents`** | 7378–7448 | `document_status_routes.py` | Supabase query | **NONE** |
| **`skip_failed_documents`** | 7450–7522 | `document_status_routes.py` | Supabase query | **NONE** |

#### Category: Shared Helpers → `_analysis_helpers.py`

| Function/Class | Current Lines | Target Module | Dependencies | Tests Covering |
|---|---|---|---|---|
| `_TRANSIENT_CODES`, `_TRANSIENT_MESSAGES` | 60–61 | `_analysis_helpers.py` | constants | `test_service_role_resilience.py` |
| `_DB_COLUMNS_CACHE` | 57 | `_analysis_helpers.py` | convert to `@lru_cache` | — |
| `_SIGNATURE_*` patterns (6 sets) | scattered | `_analysis_helpers.py` | constants | — |
| `_HTML2TEXT_CONVERTER` | mid-file | `_analysis_helpers.py` | `html2text` | — |
| `ARTIFACT_BUCKET`, `ARTIFACT_PREFIX`, `SIGNED_URL_TTL` | mid-file | `_analysis_helpers.py` | constants | — |
| `_is_transient_error()` | 421–428 | `_analysis_helpers.py` | — | `test_service_role_resilience.py` |
| `_upsert_with_retry()` | 430–445 | `_analysis_helpers.py` | — | `test_extract_db_retry.py` (3 tests) |
| `_update_case_with_retry()` | 447–461 | `_analysis_helpers.py` | — | — |
| `_to_sse()` | 506–509 | `_analysis_helpers.py` | — | — |
| `_first_non_empty_text()` | 610–620 | `_analysis_helpers.py` | — | — |
| Signature verification helpers (7 funcs) | 863–1171 | `_analysis_helpers.py` | — | `test_gap_signature_reconciliation.py` |
| `_generate_eml_bytes()` | 1153–1171 | `_analysis_helpers.py` | `email.message` | — |
| `_hash_jsonable()` | 6304–6308 | `_analysis_helpers.py` | `hashlib` | — |
| `_ensure_case_access()` | 7579–7587 | `_analysis_helpers.py` | `get_supabase_client` | — |
| `_fetch_latest_analysis_result()` | 7589–7614 | `_analysis_helpers.py` | `get_supabase_client` | — |

### 2.2 Coverage Summary

| Category | Endpoints | With Tests | Without Tests |
|---|---|---|---|
| Analysis Lifecycle | 7 | 5 | 2 (`cancel_case_analysis`, `get_analysis_state`) |
| Streaming | 2 | 0 | 2 (`stream_case_analysis`, `get_streaming_result`) |
| Letter Generation | 5 | 2 | 3 (`generate_recommendation_letter`, `stream_recommendation_letter`, `calculate_demand_amount`) |
| Gap Analysis | 3 | 0 | 3 |
| Chat | 2 | 0 | 2 |
| Document Status | 3 | 1 | 2 (`retry_failed_documents`, `skip_failed_documents`) |
| **Total** | **22** | **8** | **14** |

**Rule: Write a safety-net test for every untested endpoint before moving it.**

---

## 3. Dependency Rules

### 3.1 Architectural Boundaries

```
ALLOWED DEPENDENCY DIRECTION (top imports from bottom):

    ┌────────────────────────────────┐
    │   api/routes/*                 │  HTTP handlers
    │   api/middleware/*             │  HTTP middleware
    └────────────┬───────────────────┘
                 │ imports
    ┌────────────▼───────────────────┐
    │   api/dependencies.py          │  Auth, DI providers
    └────────────┬───────────────────┘
                 │ imports
    ┌────────────▼───────────────────┐
    │   services/**/*                │  Business logic
    └────────────┬───────────────────┘
                 │ imports
    ┌────────────▼───────────────────┐
    │   core/*                       │  Domain models, exceptions, AI analyzer
    └────────────┬───────────────────┘
                 │ imports
    ┌────────────▼───────────────────┐
    │   utils/*                      │  Pure utilities, clients
    └────────────┬───────────────────┘
                 │ imports
    ┌────────────▼───────────────────┐
    │   config/*                     │  Settings, feature flags
    └────────────────────────────────┘
```

### 3.2 Constraint Rules

| # | Rule | Rationale |
|---|------|-----------|
| R1 | **Routes must not import other route modules** | Prevents cross-route coupling. Shared logic goes in `_analysis_helpers.py` or `services/` |
| R2 | **Services must not import from `api/routes/`** | Services are framework-agnostic; they must not know about HTTP |
| R3 | **Services must not import from `api/dependencies.py`** | No FastAPI `Depends()` in service code; inject clients as constructor args |
| R4 | **Utils must have zero service dependencies** | Utils are pure functions/classes; importing services creates cycles |
| R5 | **Core models must not import from services** | Models are the shared language; services depend on models, not the reverse |
| R6 | **Core must not import from `api/`** | Core is framework-agnostic; currently violated by `document_processor.py:278` |
| R7 | **Config must not import from any layer above it** | Config is the lowest layer; everything else reads from it |
| R8 | **Lateral imports within a layer are allowed** | e.g., `services/letters/demand_letter_service.py` → `services/shared/document_formatter.py` |
| R9 | **`_analysis_helpers.py` may import from `api/dependencies`** | Helpers are route-layer utilities, not services; this is an accepted exception |

### 3.3 Enforcement

Add to CI as a lint step. This script can be run with `python scripts/check_import_rules.py`:

```python
#!/usr/bin/env python3
"""Verify import dependency rules are not violated."""

import ast
import sys
from pathlib import Path

RULES = [
    # (source_pattern, forbidden_import_pattern, rule_name)
    ("api/routes/", "api/routes/", "R1: route→route"),
    ("services/", "api/routes/", "R2: service→route"),
    ("services/", "api/dependencies", "R3: service→dependencies"),
    ("utils/", "services/", "R4: utils→service"),
    ("core/models/", "services/", "R5: model→service"),
    ("core/", "api/", "R6: core→api"),
    ("config/", "api/", "R7: config→api"),
    ("config/", "services/", "R7: config→service"),
    ("config/", "core/", "R7: config→core"),
]

# Exceptions
ALLOWED = {
    ("api/routes/_analysis_helpers.py", "api/dependencies"),  # R9
    ("core/models/__init__.py", "core/data_models"),          # re-export shim
}

def check_file(filepath: Path, src_root: Path) -> list[str]:
    violations = []
    rel = str(filepath.relative_to(src_root))

    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
            else:
                continue

            if not module.startswith("legal_portal."):
                continue

            import_path = module.replace("legal_portal.", "").replace(".", "/")

            for src_pat, forbidden_pat, rule in RULES:
                if src_pat in rel and forbidden_pat in import_path:
                    key = (rel, import_path)
                    if key not in ALLOWED:
                        violations.append(
                            f"  {rel}:{node.lineno} → {module}  [{rule}]"
                        )
    return violations

def main():
    src_root = Path("src/legal_portal")
    all_violations = []

    for py_file in src_root.rglob("*.py"):
        all_violations.extend(check_file(py_file, src_root))

    if all_violations:
        print(f"IMPORT VIOLATIONS ({len(all_violations)}):")
        for v in sorted(all_violations):
            print(v)
        sys.exit(1)
    else:
        print("All import rules pass.")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

---

## 4. Risk Controls

### 4.0 Current Violations (verified by `scripts/check_import_rules.py`)

These 4 violations exist today and must be fixed during the refactor:

| # | File | Line | Violation | Fix Phase |
|---|------|------|-----------|-----------|
| 1 | `api/routes/analysis.py` | 1782 | Imports `api.routes.cases` (R1: route→route) | Phase 4 — eliminated when analysis.py is split |
| 2 | `api/routes/cases.py` | 25 | Imports `api.routes.documents` (R1: route→route) | Phase 5 — extract shared logic to service |
| 3 | `api/utils/content_extractor.py` | 12 | Imports `services.file_compression_service` (R4: utils→service) | Phase 3 — move content_extractor to services/ |
| 4 | `core/document_processor.py` | 278 | Imports `api.utils.content_extractor` (R6: core→api) | Phase 3 — move content_extractor to services/ |

### 4.1 Circular Import Risk Report

| Risk | Modules Involved | How It Happens | Mitigation |
|---|---|---|---|
| **EXISTING** | `core/document_processor.py` ↔ `api/utils/content_extractor.py` | `core/document_processor.py:278` imports `api.utils.content_extractor.DocumentProcessor as ContentExtractor`. If any API module imports `core/document_processor`, a circular chain forms. | **Fix in Phase 3:** Move `ContentExtractor` to `services/documents/content_extraction_service.py`. Update the import in `core/document_processor.py`. |
| **HIGH** | `letter_routes.py` ↔ `gap_routes.py` | `_ensure_fresh_gap_analysis_for_letter_generation()` (in letter_routes) calls gap analysis logic. If gap_routes needs letter helpers, a cycle forms. | Move `_ensure_fresh_gap_analysis_for_letter_generation()` to `_analysis_helpers.py`. Both route modules import it from the shared helper. |
| **MEDIUM** | `analysis_core.py` ↔ `analysis_streaming.py` | `stream_case_analysis` needs `_analysis_is_cancelled()` and `_download_and_extract_documents()`. If analysis_core imports streaming helpers, a cycle forms. | Put shared state-checking helpers in `_analysis_helpers.py`. Each route module imports from helpers, never from each other. |
| **MEDIUM** | `services/analysis/` ↔ `services/letters/` | `letter_strategy_service` calls `gap_analysis_service` to check for gaps before generating. If gap_analysis imports letter models, a cycle forms. | Gap analysis returns plain dicts or core models. Letter services consume these. No letter types in gap service signatures. |
| **LOW** | `services/shared/progress_manager.py` ↔ `services/analysis/main_processor.py` | Both need each other: main_processor sends progress, progress_manager tracks analysis state. | progress_manager accepts a callback protocol (typing.Protocol), not a concrete processor type. No import of main_processor. |
| **LOW** | `_analysis_helpers.py` ↔ `api/dependencies.py` | Helpers import `get_supabase_client` from dependencies. If dependencies imports helpers, a cycle forms. | Dependencies must remain self-contained. It imports only from stdlib, supabase-py, and config. Never from routes. |

### 4.2 Refactor Safety Checklist

Run after **every phase**. Copy this checklist into your PR description:

```markdown
## Post-Phase Validation

### Automated
- [ ] `pytest tests/ -x -q` — all tests pass
- [ ] `python scripts/check_import_rules.py` — no dependency violations
- [ ] `python scripts/validate_endpoints.py` — endpoint count and paths unchanged
- [ ] `python -c "from legal_portal.api.main import app"` — app imports without error

### Manual Smoke Tests
- [ ] Start backend: `uvicorn legal_portal.api.main:app --reload` boots without errors
- [ ] Create a case in the frontend
- [ ] Upload a document → verify it processes
- [ ] Start analysis → verify progress streaming works
- [ ] Generate findings letter → verify output renders
- [ ] Check browser console for new errors
- [ ] Check server logs for new warnings/errors

### Rollback Gate
- [ ] Feature flag (if applicable) can be toggled to revert to old behavior
- [ ] Git revert of this PR's commits produces a working state
- [ ] No database migrations in this phase (if there are, document rollback SQL)

### Code Quality
- [ ] No new `except Exception` blocks without specific handling
- [ ] No new singletons or module-level mutable state
- [ ] No new cross-layer import violations
- [ ] All new files have `__init__.py` in their directory
```

---

## 5. Validation Scripts

### 5.1 Performance Baseline Script

Save as `scripts/collect_performance_baseline.py`. Run before Phase 1 starts:

```python
#!/usr/bin/env python3
"""Collect performance baseline metrics before refactoring.

Run this script before each refactor phase to establish baselines.
Results are saved to docs/plans/baselines/ as timestamped JSON files.

Usage:
    python scripts/collect_performance_baseline.py [--phase PHASE_NAME]
"""

import argparse
import importlib
import json
import os
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def measure_import_time() -> dict:
    """Measure how long it takes to import the main app module."""
    results = {}
    modules = [
        "legal_portal.api.main",
        "legal_portal.core.data_models",
        "legal_portal.services.main_processor",
        "legal_portal.api.routes.analysis",
    ]
    for mod in modules:
        start = time.perf_counter()
        try:
            importlib.import_module(mod)
            elapsed = time.perf_counter() - start
            results[mod] = {"import_time_s": round(elapsed, 4), "status": "ok"}
        except Exception as e:
            elapsed = time.perf_counter() - start
            results[mod] = {"import_time_s": round(elapsed, 4), "status": f"error: {e}"}
    return results


def measure_test_suite_time() -> dict:
    """Measure total test suite runtime."""
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    elapsed = time.perf_counter() - start

    # Parse test counts from pytest output
    lines = result.stdout.strip().split("\n")
    summary_line = lines[-1] if lines else ""

    return {
        "total_time_s": round(elapsed, 2),
        "exit_code": result.returncode,
        "summary": summary_line,
    }


def measure_startup_time() -> dict:
    """Measure FastAPI app startup time."""
    script = (
        "import time; start = time.perf_counter(); "
        "from legal_portal.api.main import app; "
        "elapsed = time.perf_counter() - start; "
        "print(f'{elapsed:.4f}')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    try:
        startup_s = float(result.stdout.strip())
    except ValueError:
        startup_s = -1.0

    return {"startup_time_s": startup_s, "stderr": result.stderr[:500] if result.stderr else ""}


def measure_codebase_stats() -> dict:
    """Measure codebase size metrics."""
    src_root = Path(__file__).parent.parent / "src" / "legal_portal"
    test_root = Path(__file__).parent.parent / "tests"

    py_files = list(src_root.rglob("*.py"))
    test_files = list(test_root.rglob("*.py"))

    total_loc = 0
    for f in py_files:
        try:
            total_loc += len(f.read_text().splitlines())
        except Exception:
            pass

    test_loc = 0
    for f in test_files:
        try:
            test_loc += len(f.read_text().splitlines())
        except Exception:
            pass

    # Check analysis.py specifically
    analysis_py = src_root / "api" / "routes" / "analysis.py"
    analysis_loc = len(analysis_py.read_text().splitlines()) if analysis_py.exists() else 0

    return {
        "source_files": len(py_files),
        "source_loc": total_loc,
        "test_files": len(test_files),
        "test_loc": test_loc,
        "analysis_py_loc": analysis_loc,
        "analysis_py_exists": analysis_py.exists(),
    }


def measure_memory_usage() -> dict:
    """Measure memory after importing the app."""
    script = (
        "import resource, json; "
        "from legal_portal.api.main import app; "
        "usage = resource.getrusage(resource.RUSAGE_SELF); "
        "print(json.dumps({'max_rss_kb': usage.ru_maxrss}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    try:
        return json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return {"max_rss_kb": -1, "stderr": result.stderr[:500]}


def count_endpoints() -> dict:
    """Count registered FastAPI endpoints."""
    script = (
        "from legal_portal.api.main import app; "
        "routes = [r for r in app.routes if hasattr(r, 'methods')]; "
        "print(len(routes)); "
        "[print(f'{list(r.methods)} {r.path}') for r in sorted(routes, key=lambda r: r.path)]"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    lines = result.stdout.strip().split("\n")
    count = int(lines[0]) if lines else 0
    endpoints = lines[1:] if len(lines) > 1 else []

    return {
        "endpoint_count": count,
        "endpoints": endpoints,
    }


def main():
    parser = argparse.ArgumentParser(description="Collect performance baselines")
    parser.add_argument("--phase", default="pre-refactor", help="Phase name (e.g., 'pre-refactor', 'phase-1')")
    args = parser.parse_args()

    print(f"Collecting baseline metrics for phase: {args.phase}")
    print("=" * 60)

    metrics = {
        "phase": args.phase,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
    }

    print("  Measuring codebase stats...")
    metrics["codebase"] = measure_codebase_stats()

    print("  Measuring import times...")
    metrics["imports"] = measure_import_time()

    print("  Measuring app startup...")
    metrics["startup"] = measure_startup_time()

    print("  Counting endpoints...")
    metrics["endpoints"] = count_endpoints()

    print("  Measuring memory...")
    metrics["memory"] = measure_memory_usage()

    print("  Running test suite...")
    metrics["tests"] = measure_test_suite_time()

    # Save results
    baselines_dir = Path(__file__).parent.parent / "docs" / "plans" / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = baselines_dir / f"baseline-{args.phase}-{timestamp}.json"
    output_file.write_text(json.dumps(metrics, indent=2))

    print(f"\nResults saved to: {output_file}")
    print(f"\n{'=' * 60}")
    print(f"SUMMARY — {args.phase}")
    print(f"{'=' * 60}")
    print(f"  Source files:      {metrics['codebase']['source_files']}")
    print(f"  Source LOC:        {metrics['codebase']['source_loc']:,}")
    print(f"  analysis.py LOC:   {metrics['codebase']['analysis_py_loc']:,}")
    print(f"  Test files:        {metrics['codebase']['test_files']}")
    print(f"  Endpoint count:    {metrics['endpoints']['endpoint_count']}")
    print(f"  App startup:       {metrics['startup']['startup_time_s']}s")
    print(f"  Memory (RSS):      {metrics['memory'].get('max_rss_kb', '?')} KB")
    print(f"  Test suite:        {metrics['tests']['total_time_s']}s (exit {metrics['tests']['exit_code']})")


if __name__ == "__main__":
    main()
```

### 5.2 Endpoint Validation Script

Save as `scripts/validate_endpoints.py`. Run after every phase:

```python
#!/usr/bin/env python3
"""Validate that endpoint count and paths are unchanged after refactoring.

Compares the current endpoint list against a saved baseline.
Exits with code 1 if any endpoints are missing or paths changed.

Usage:
    # Save baseline (run once before refactoring)
    python scripts/validate_endpoints.py --save-baseline

    # Validate against baseline (run after each phase)
    python scripts/validate_endpoints.py --check
"""

import argparse
import json
import sys
from pathlib import Path


BASELINE_FILE = Path(__file__).parent.parent / "docs" / "plans" / "baselines" / "endpoint-baseline.json"


def get_current_endpoints() -> list[dict]:
    """Get all registered endpoints from the FastAPI app."""
    # Import inside function to avoid import-time side effects
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from legal_portal.api.main import app

    endpoints = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in sorted(route.methods):
                if method == "HEAD":
                    continue  # Skip implicit HEAD methods
                endpoints.append({
                    "method": method,
                    "path": route.path,
                    "name": getattr(route, "name", ""),
                })

    return sorted(endpoints, key=lambda e: (e["path"], e["method"]))


def save_baseline():
    endpoints = get_current_endpoints()
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps(endpoints, indent=2))
    print(f"Saved {len(endpoints)} endpoints to {BASELINE_FILE}")
    for ep in endpoints:
        print(f"  {ep['method']:6s} {ep['path']}")


def check_against_baseline():
    if not BASELINE_FILE.exists():
        print(f"ERROR: No baseline found at {BASELINE_FILE}")
        print("Run with --save-baseline first.")
        sys.exit(1)

    baseline = json.loads(BASELINE_FILE.read_text())
    current = get_current_endpoints()

    baseline_set = {(e["method"], e["path"]) for e in baseline}
    current_set = {(e["method"], e["path"]) for e in current}

    missing = baseline_set - current_set
    added = current_set - baseline_set

    if not missing and not added:
        print(f"PASS: All {len(baseline)} endpoints match baseline.")
        sys.exit(0)

    if missing:
        print(f"\nMISSING ENDPOINTS ({len(missing)}):")
        for method, path in sorted(missing):
            print(f"  - {method:6s} {path}")

    if added:
        print(f"\nNEW ENDPOINTS ({len(added)}):")
        for method, path in sorted(added):
            print(f"  + {method:6s} {path}")

    if missing:
        print(f"\nFAIL: {len(missing)} endpoint(s) missing from baseline.")
        sys.exit(1)
    else:
        print(f"\nWARN: {len(added)} new endpoint(s) added (not in baseline). No endpoints missing.")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Validate endpoints against baseline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--save-baseline", action="store_true", help="Save current endpoints as baseline")
    group.add_argument("--check", action="store_true", help="Check current endpoints against baseline")
    args = parser.parse_args()

    if args.save_baseline:
        save_baseline()
    else:
        check_against_baseline()


if __name__ == "__main__":
    main()
```

### 5.3 Post-Phase Validation Shell Script

Save as `scripts/validate_refactor.sh`:

```bash
#!/usr/bin/env bash
# Run all validation checks after a refactor phase.
# Usage: ./scripts/validate_refactor.sh [phase-name]

set -euo pipefail

PHASE="${1:-unknown}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check() {
    local label="$1"
    shift
    printf "  %-45s" "$label"
    if "$@" > /tmp/refactor_check_output 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
    else
        echo -e "${RED}FAIL${NC}"
        cat /tmp/refactor_check_output | head -5
        ((FAIL++))
    fi
}

warn_check() {
    local label="$1"
    shift
    printf "  %-45s" "$label"
    if "$@" > /tmp/refactor_check_output 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
    else
        echo -e "${YELLOW}WARN${NC}"
        cat /tmp/refactor_check_output | head -3
        ((WARN++))
    fi
}

echo "=========================================="
echo "  Refactor Validation — Phase: $PHASE"
echo "=========================================="
echo ""

echo "1. Import Checks"
check "App imports cleanly"              python -c "from legal_portal.api.main import app"
check "All route modules import"         python -c "from legal_portal.api.routes import analysis"
warn_check "Import rules pass"           python scripts/check_import_rules.py

echo ""
echo "2. Test Suite"
check "Unit tests pass"                  python -m pytest tests/unit/ -x -q --tb=short
check "API tests pass"                   python -m pytest tests/api/ -x -q --tb=short
warn_check "Integration tests pass"      python -m pytest tests/integration/ -x -q --tb=short

echo ""
echo "3. Endpoint Validation"
check "Endpoint count unchanged"         python scripts/validate_endpoints.py --check

echo ""
echo "4. Syntax & Structure"
check "No syntax errors in src/"         python -m py_compile src/legal_portal/api/main.py
warn_check "No circular imports"         python -c "
import sys
sys.path.insert(0, 'src')
# Import every route module to detect circular imports
from legal_portal.api.routes import analysis
from legal_portal.api.routes import cases
from legal_portal.api.routes import documents
from legal_portal.api.routes import clio
print('All route imports OK')
"

echo ""
echo "=========================================="
echo -e "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${WARN} warnings${NC}"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}VALIDATION FAILED — DO NOT MERGE${NC}"
    exit 1
else
    echo -e "${GREEN}VALIDATION PASSED${NC}"
    exit 0
fi
```

---

## 6. Async Queue Readiness

### 6.1 What Changes After This Refactor

The refactor creates clean service boundaries that make async job processing straightforward. Here is the minimal path from "refactored codebase" to "async job queue":

### 6.2 Architecture

```
CURRENT (after refactor)                    FUTURE (with async queue)
========================                    ========================

Client                                      Client
  │                                           │
  │ POST /api/analysis/start                  │ POST /api/analysis/start
  ▼                                           ▼
┌──────────────────┐                        ┌──────────────────┐
│ analysis_core.py │                        │ analysis_core.py │
│                  │                        │                  │
│  start_analysis()│                        │  start_analysis()│
│  → BackgroundTask│                        │  → enqueue job   │──┐
│  → process_case  │                        │  → return job_id │  │
│    _background() │                        └──────────────────┘  │
└──────────────────┘                                              │
        │                                                         │
        │ runs in-process                         Redis queue     │
        ▼                                              │          │
┌──────────────────┐                        ┌──────────▼─────────┐
│ main_processor   │                        │ Worker Process     │
│  .process_case   │                        │                    │
│  _documents()    │         ════════>      │  main_processor    │
│                  │         same code      │   .process_case    │
│ (services/       │         moved to       │   _documents()     │
│  analysis/)      │         worker         │                    │
└──────────────────┘                        └──────────────────┘
        │                                            │
        │ SSE progress via DB polling                │ progress via Redis pub/sub
        ▼                                            ▼
┌──────────────────┐                        ┌──────────────────┐
│ Frontend         │                        │ Frontend          │
│ (polls /status)  │                        │ (SSE from /status │
└──────────────────┘                        │  backed by Redis) │
                                            └──────────────────┘
```

### 6.3 Steps to Add Async Queue

These steps assume the refactor is complete. None of this should be done until after Phase 4 (analysis.py split) at minimum.

#### Step 1: Add Redis + arq Dependencies

```bash
pip install arq redis
```

```python
# config/default.py — add to Settings class
class Settings(BaseSettings):
    # ... existing fields ...
    redis_url: str = "redis://localhost:6379"
    worker_concurrency: int = 4
    job_timeout_s: int = 900       # 15 minutes
    job_result_ttl_s: int = 3600   # 1 hour
```

#### Step 2: Create Worker Module

```python
# src/legal_portal/worker.py
"""arq worker definition. Run with: arq legal_portal.worker.WorkerSettings"""

from arq import cron
from arq.connections import RedisSettings

from legal_portal.config.default import get_settings
from legal_portal.services.analysis.main_processor import process_case_documents

settings = get_settings()


async def run_analysis(ctx: dict, case_id: str, user_id: str, **kwargs):
    """Execute case analysis as a background job."""
    # The same service function, now called from a worker instead of BackgroundTask
    await process_case_documents(
        case_id=case_id,
        user_id=user_id,
        progress_callback=lambda stage, detail: ctx["redis"].publish(
            f"progress:{case_id}", f"{stage}:{detail}"
        ),
        **kwargs,
    )


class WorkerSettings:
    functions = [run_analysis]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.worker_concurrency
    job_timeout = settings.job_timeout_s
```

#### Step 3: Modify `start_analysis` to Enqueue

```python
# api/routes/analysis_core.py — change from BackgroundTask to arq job

# BEFORE (current)
async def start_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    ...
):
    background_tasks.add_task(process_case_background, case_id, ...)
    return {"analysis_id": analysis_id, "status": "started"}

# AFTER (with queue) — behind feature flag
async def start_analysis(
    request: AnalysisRequest,
    ...
):
    settings = get_settings()
    if settings.use_async_queue:
        redis = await get_arq_pool()
        job = await redis.enqueue_job(
            "run_analysis",
            case_id=str(case_id),
            user_id=current_user["id"],
        )
        return {"analysis_id": analysis_id, "job_id": job.job_id, "status": "queued"}
    else:
        # Fallback to BackgroundTask (existing behavior)
        background_tasks.add_task(process_case_background, case_id, ...)
        return {"analysis_id": analysis_id, "status": "started"}
```

#### Step 4: Add Job Status API

```python
# api/routes/analysis_core.py — new endpoint

@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Check the status of a queued analysis job."""
    redis = await get_arq_pool()
    job = Job(job_id, redis)
    status = await job.status()
    info = await job.info()

    return {
        "job_id": job_id,
        "status": status.value,  # queued, in_progress, complete, not_found
        "start_time": info.start_time.isoformat() if info and info.start_time else None,
        "finish_time": info.finish_time.isoformat() if info and info.finish_time else None,
        "result": info.result if info and status == JobStatus.complete else None,
    }
```

#### Step 5: Progress Streaming via Redis Pub/Sub

```python
# api/routes/progress.py — add Redis-backed SSE

@router.get("/progress/analysis/{case_id}")
async def stream_progress(case_id: str):
    settings = get_settings()
    if settings.use_async_queue:
        return EventSourceResponse(redis_progress_generator(case_id))
    else:
        return EventSourceResponse(db_polling_progress_generator(case_id))


async def redis_progress_generator(case_id: str):
    """Stream progress events from Redis pub/sub."""
    redis = await get_arq_pool()
    channel = f"progress:{case_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                stage, detail = message["data"].decode().split(":", 1)
                yield {"event": "progress", "data": json.dumps({"stage": stage, "detail": detail})}
                if stage == "complete":
                    break
    finally:
        await pubsub.unsubscribe(channel)
```

### 6.4 Deployment Requirements

| Component | Development | Production |
|---|---|---|
| Redis | `docker run -p 6379:6379 redis:7` | Managed Redis (e.g., Upstash, Redis Cloud, Memorystore) |
| Worker | `arq legal_portal.worker.WorkerSettings` | Separate Cloud Run service or VM with `arq` process |
| Feature flag | `USE_ASYNC_QUEUE=false` | `USE_ASYNC_QUEUE=true` (toggle when ready) |
| Monitoring | arq built-in logging | Add worker health check endpoint + alerting |

### 6.5 Why This Works After Refactor

| Refactor Phase | What It Enables for Async |
|---|---|
| Phase 3 (shared utilities) | Retry logic in one place — worker reuses the same retry middleware |
| Phase 4 (analysis.py split) | `start_analysis()` is isolated — can swap BackgroundTask for queue enqueue |
| Phase 5 (service reorg) | `services/analysis/main_processor.py` is a standalone module — can be imported by worker without pulling in FastAPI |
| Phase 8 (singleton removal) | No global state — worker processes can run multiple concurrent jobs safely |

---

## Appendix: File Deletion Checklist (Phase 1)

Files to delete in Phase 1 (dead code removal). Verify each has no live imports before deleting:

```bash
# Dead source files
rm src/legal_portal/core/email_generator_core.py       # 0 bytes
rm src/legal_portal/config/config_manager.py            # legacy wrapper

# Root-level test
rm test_gap_fix.py                                      # covered by unit/test_gap_signature_reconciliation.py

# Empty worktree
rmdir .worktrees/feature/ 2>/dev/null || true

# Verify no imports reference these files
grep -r "email_generator_core" src/ tests/ --include="*.py"
grep -r "config_manager" src/ tests/ --include="*.py"
```
