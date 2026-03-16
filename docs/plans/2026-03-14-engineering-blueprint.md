# Engineering Blueprint — Refactor Artifacts

**Date:** 2026-03-14
**Purpose:** Final engineering artifacts for executing the codebase refactor
**Prerequisite:** [Execution Plan](./2026-03-14-refactor-execution-plan.md)

---

## 1. Architecture Diagram

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SVELTEKIT FRONTEND                               │
│                     (Vercel Static + Functions)                         │
│                                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Login    │ │ Cases    │ │ Case [id]│ │ Results  │ │ Help/Settings│ │
│  │ Register │ │ List     │ │ Detail   │ │ Workspace│ │ Design System│ │
│  └──────────┘ └──────────┘ └────┬─────┘ └────┬─────┘ └──────────────┘ │
│                                  │             │                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    lib/                                          │   │
│  │  stores/          api/           utils/         components/      │   │
│  │  progressStore    cases.ts       sseClient      VerificationHub  │   │
│  │  toastStore       (fetch API)    pollingClient   AnalysisStream   │   │
│  │  clioStore                       streamRecovery  GapAnalysisPanel │   │
│  │  loadingStore                    letterCopy      DocumentCard     │   │
│  └─────────────────────────────────┬───────────────────────────────┘   │
└────────────────────────────────────┼───────────────────────────────────┘
                                     │
                          REST + SSE (EventSource)
                                     │
┌────────────────────────────────────┼───────────────────────────────────┐
│                        FASTAPI BACKEND                                  │
│                                                                         │
│  ┌─────────────────────── API Layer ──────────────────────────────┐    │
│  │                                                                 │    │
│  │  main.py ─── CORS, Rate Limiter, Exception Handler, Lifespan  │    │
│  │  dependencies.py ─── Auth (JWT), Supabase clients              │    │
│  │                                                                 │    │
│  │  ┌─── Routes ────────────────────────────────────────────────┐ │    │
│  │  │                                                            │ │    │
│  │  │  CURRENT (analysis.py = 7,614 LOC monolith)               │ │    │
│  │  │                    ↓ REFACTORS TO ↓                        │ │    │
│  │  │                                                            │ │    │
│  │  │  analysis_core.py ──── start, cancel, status, results     │ │    │
│  │  │  letter_routes.py ──── findings, demand, recommendation   │ │    │
│  │  │  gap_routes.py    ──── gap analysis run/resolve/stream    │ │    │
│  │  │  chat_routes.py   ──── case chat with AI                  │ │    │
│  │  │  document_status_routes.py ── doc status/retry/skip       │ │    │
│  │  │  _analysis_helpers.py ─── shared retry, signature utils   │ │    │
│  │  │                                                            │ │    │
│  │  │  cases.py         ──── case CRUD + Clio import            │ │    │
│  │  │  documents.py     ──── upload, extract, verify, delete    │ │    │
│  │  │  clio.py          ──── OAuth flow, matter search, sync    │ │    │
│  │  │  progress.py      ──── SSE streaming + polling fallback   │ │    │
│  │  │  intake.py        ──── intake form processing             │ │    │
│  │  │  corpus.py        ──── legal corpus lookup                │ │    │
│  │  │  profile.py       ──── user profile                       │ │    │
│  │  │  health.py        ──── health checks                      │ │    │
│  │  │  settings.py      ──── system settings                    │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌──────────────────── Service Layer ─────────────────────────────┐    │
│  │                                                                 │    │
│  │  analysis/                   documents/                         │    │
│  │  ├── multi_stage_analyzer    ├── main_processor                 │    │
│  │  ├── gap_analysis_service    ├── document_registry_service      │    │
│  │  ├── corpus_coverage_svc     ├── document_quality_validator     │    │
│  │  ├── statute_validation_svc  ├── content_extraction_service     │    │
│  │  ├── statute_recommend_svc   ├── chunk_service                  │    │
│  │  ├── deadline_extraction_svc ├── chunk_state_manager            │    │
│  │  └── qa_service              └── file_processors/               │    │
│  │                                   ├── pdf_processor             │    │
│  │  letters/                         ├── docx_processor            │    │
│  │  ├── demand_letter_service        ├── eml_processor             │    │
│  │  ├── recommendation_letter_svc    ├── image_processor           │    │
│  │  ├── letter_strategy_service      ├── batch_vision_processor    │    │
│  │  ├── letter_quality_lint_svc      ├── csv/txt/doc_processor     │    │
│  │  ├── letter_validation_service    └── utils                     │    │
│  │  ├── letter_review_service                                      │    │
│  │  ├── fallback_generation_svc  shared/                           │    │
│  │  ├── citation_tracking_svc    ├── json_processing_service       │    │
│  │  └── json_architecture_svc    ├── document_formatter            │    │
│  │                                ├── content_formatting_service   │    │
│  │  integrations/                 ├── content_generation_service   │    │
│  │  ├── clio_context_builder     ├── text_processing_service      │    │
│  │  ├── clio_data_transformer    ├── template_rendering_service   │    │
│  │  └── case_chat_service        ├── file_compression_service     │    │
│  │                                └── progress_manager             │    │
│  │  grouping/                                                      │    │
│  │  ├── group_summarizer                                           │    │
│  │  └── group_quality_metrics                                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌──────────────────── Core Layer ────────────────────────────────┐    │
│  │                                                                 │    │
│  │  exceptions.py ──── Unified exception hierarchy (NEW)          │    │
│  │  ai_analyzer.py ──── OpenAI API interaction + caching          │    │
│  │  document_processor.py ──── File dispatch orchestrator         │    │
│  │  models/                                                        │    │
│  │  ├── document_models.py                                         │    │
│  │  ├── analysis_models.py   (SPLIT from data_models.py)          │    │
│  │  ├── letter_models.py                                           │    │
│  │  ├── party_models.py                                            │    │
│  │  └── enums.py                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌──────────────────── Utils Layer ───────────────────────────────┐    │
│  │  openai_client      google_vision_client    cache_manager       │    │
│  │  token_manager      cost_calculator         pii_sanitizer       │    │
│  │  helpers             validators             security             │    │
│  │  logging_config      structured_logger      metrics              │    │
│  │  tracing             type_safety            throttled_db_writer  │    │
│  │  ocr_service_client  letter_formatter       markdown_utils       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌──────────────────── Config Layer ──────────────────────────────┐    │
│  │  default.py (Pydantic Settings)    prompts_and_settings.json   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐    ┌──────────────────┐    ┌──────────────┐
│  Supabase   │    │   OpenAI API     │    │ Google Cloud  │
│  ─────────  │    │   ──────────     │    │  ──────────── │
│  PostgreSQL │    │   GPT-4o         │    │  Vision API   │
│  Auth (JWT) │    │   GPT-4o-mini    │    │  Cloud Run    │
│  Storage    │    │   Embeddings     │    │  (OCR svc)    │
│  RLS        │    │                  │    │               │
└─────────────┘    └──────────────────┘    └──────────────┘
                            │
                   ┌────────▼────────┐
                   │  Clio API       │
                   │  (Practice Mgmt)│
                   │  OAuth 2.0      │
                   └─────────────────┘
```

### Data Flow: Full Case Lifecycle

```
[1] CREATE CASE
    Client POST /api/cases
    → cases.py validates + inserts into Supabase `cases` table
    → Returns case_id

[2] UPLOAD DOCUMENTS
    Client POST /api/documents/upload (multipart/form-data)
    → documents.py validates file type/size
    → DocumentProcessor dispatches to type-specific processor:
        PDF  → pdf_processor.py  → PyMuPDF text extraction
                                  → GPT-4o Vision (if scanned/OCR needed)
                                  → Google Vision (if remote OCR enabled)
        DOCX → docx_processor.py → python-docx extraction
        EML  → eml_processor.py  → email parsing + attachment extraction
        IMG  → image_processor.py → Vision API OCR
        TXT  → txt_processor.py  → direct read
        CSV  → csv_processor.py  → tabular parsing
    → Stores text in Supabase `documents` table
    → DocumentRegistryService classifies document type

[3] START ANALYSIS
    Client POST /api/analysis/start { case_id }
    → analysis_core.py creates `analysis_results` record (status: processing)
    → On Vercel: runs synchronously within request (SSE streaming)
    → On local: BackgroundTasks.add_task(process_case_background)
    → process_case_background():
        a) _extract_deferred_documents() — extract any deferred docs
        b) _dedup_email_threads() — deduplicate email threads
        c) main_processor.process_case_documents():
            1. ChunkService creates balanced document chunks
            2. Per chunk: ai_analyzer calls OpenAI GPT-4o
            3. MultiStageAnalyzer runs 4-stage pipeline:
               Stage 1: Fact extraction from each document
               Stage 2: Issue mapping to legal elements
               Stage 3: Deep analysis with statute matching
               Stage 4: Letter structure generation
            4. GapAnalysisService identifies missing evidence
            5. CorpusCoverageService checks statute coverage
        d) Results stored in `analysis_results.result` JSONB

[4] STREAM PROGRESS
    Client GET /api/progress/analysis/{id} (EventSource SSE)
    → progress.py polls `analysis_results.progress` JSONB
    → Sends SSE events: { stage, percent, message }
    → Fallback: Client polls GET /api/progress/analysis/{id}/status

[5] VIEW RESULTS
    Client GET /api/analysis/results/{case_id}
    → analysis_core.py fetches from `analysis_results` table
    → Returns: case_analysis, document_summaries, gap_analysis,
               opposing_parties, statute_recommendations, quality_report

[6] GENERATE LETTER
    Client GET /api/analysis/{id}/letter/stream (SSE)
    → letter_routes.py:
        a) _resolve_letter_identity_context() — attorney/firm info
        b) _resolve_client_name_for_letter() — client name
        c) DemandLetterService.stream_demand_letter()
        d) LetterStrategyService.build_findings_strategy()
        e) LetterQualityLintService.lint_letter()
        f) LetterReviewService.review_and_improve_letter()
    → Streams HTML chunks via SSE
    → Stores final letter in `analysis_results.artifacts`

[7] GAP ANALYSIS
    Client POST /api/analysis/analyze-gaps/stream (SSE)
    → gap_routes.py:
        a) _build_gap_analysis_batches() — partition docs
        b) _run_gap_analysis() — per-batch AI inference
        c) Merge batch results, deduplicate
    → Returns: gaps[], critical_count, high_count, statute_coverage

[8] CHAT
    Client POST /api/analysis/{id}/chat/stream (SSE)
    → chat_routes.py → CaseChatService.stream_message()
    → Streams AI response with case context
```

---

## 2. analysis.py Migration Map

### Function-by-Function Checklist

Legend: `→` = moves to, `deps` = import changes needed, `tests` = existing test coverage

#### Module: `_analysis_helpers.py` (shared utilities, no router)

| # | Function | Lines | Deps Change | Test Coverage |
|---|----------|-------|-------------|---------------|
| 1 | `_TRANSIENT_CODES`, `_TRANSIENT_MESSAGES` | 60-61 | None (constants) | `test_service_role_resilience.py` |
| 2 | `_DB_COLUMNS_CACHE` | 57 | Convert to `@lru_cache` | None |
| 3 | `_SIGNATURE_*` patterns (6 sets) | scattered | None (constants) | None |
| 4 | `_HTML2TEXT_CONVERTER` | mid-file | None (constant) | None |
| 5 | `ARTIFACT_BUCKET`, `ARTIFACT_PREFIX`, `SIGNED_URL_TTL` | mid-file | None (constants) | None |
| 6 | `_is_transient_error()` | 421-428 | None | `test_service_role_resilience.py` |
| 7 | `_upsert_with_retry()` | 430-445 | None | `test_extract_db_retry.py` (3 tests) |
| 8 | `_update_case_with_retry()` | 447-461 | None | None |
| 9 | `_to_sse()` | 506-509 | None | None |
| 10 | `_first_non_empty_text()` | 610-620 | None | None |
| 11 | `_normalize_signature_verification_status()` | 863-869 | None | `test_gap_signature_reconciliation.py` |
| 12 | `_extract_signature_verification()` | 871-898 | None | `test_gap_signature_reconciliation.py` |
| 13 | `_apply_signature_verification_override()` | 900-957 | None | None |
| 14 | `_normalize_text_signing_date()` | 959-985 | None | None |
| 15 | `_infer_signature_detection_from_text()` | 987-1047 | None | None |
| 16 | `_is_pdf_like_document()` | 1049-1054 | None | None |
| 17 | `_is_signature_inference_candidate()` | 1056-1092 | None | None |
| 18 | `_sample_text_for_state_hash()` | 1094-1104 | None | None |
| 19 | `_extract_signature_instrument_hints()` | 1106-1140 | None | None |
| 20 | `_html_to_plain_text()` | 1142-1151 | `import html2text` | None |
| 21 | `_generate_eml_bytes()` | 1153-1171 | `from email.message import EmailMessage` | None |
| 22 | `_convert_statute_recommendations_recursive()` | 3941-3976 | None | None |
| 23 | `_parse_currency()` | 3978-3999 | None | None |
| 24 | `_extract_embedded_json()` | 4001-4024 | None | None |
| 25 | `_extract_section()` | 4026-4034 | None | None |
| 26 | `_extract_list_items()` | 4036-4046 | None | None |
| 27 | `_hash_jsonable()` | 6304-6308 | None | None |
| 28 | `_ensure_case_access()` | 7579-7587 | `get_supabase_client` (from deps) | None |
| 29 | `_fetch_latest_analysis_result()` | 7589-7614 | `get_supabase_client` (from deps) | None |

**Import this module needs:**
```python
import hashlib, json, re
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import html2text
from legal_portal.api.dependencies import get_supabase_client
```

---

#### Module: `analysis_core.py`

| # | Function | Lines | Deps Change | Test Coverage |
|---|----------|-------|-------------|---------------|
| 1 | `AnalysisRequest` | 1262-1267 | None | `test_analysis.py` (4 tests) |
| 2 | `AnalysisResponse` | 1269-1278 | None | `test_analysis.py` |
| 3 | `AnalysisCancelledError` | 530-531 | None | None |
| 4 | `StreamingAnalysisSaveRequest` | 3419-3422 | None | `test_save_streaming_analysis.py` (3 tests) |
| 5 | `_extract_deferred_documents()` | 63-310 | Add: `from ._analysis_helpers import _is_transient_error, _upsert_with_retry` | `test_deferred_extraction.py` (5 tests) |
| 6 | `_dedup_email_threads()` | 312-419 | None | `test_email_thread_dedup.py` (6 tests) |
| 7 | `_download_and_extract_documents()` | 1317-1635 | None | None |
| 8 | `_analysis_is_cancelled()` | 534-547 | None | None |
| 9 | `_cancel_analysis()` | 550-578 | Import ProgressManager | None |
| 10 | `_update_analysis_progress()` | 581-597 | None | None |
| 11 | `_get_user_ai_preferences()` | 599-608 | None | None |
| 12 | `process_case_background()` | 1636-2354 | Add: `from ._analysis_helpers import *` (uses many helpers) | `test_analysis.py` (indirect) |
| 13 | `start_analysis()` | 3016-3201 | `BackgroundTasks`, deps unchanged | `test_analysis.py` (4 tests) |
| 14 | `cancel_analysis()` | 3205-3248 | None | None |
| 15 | `cancel_case_analysis()` | 3251-3300 | None | None |
| 16 | `get_analysis_status()` | 3303-3354 | None | `test_analysis.py` (1 test) |
| 17 | `get_analysis_results()` | 3356-3417 | None | `test_analysis.py` (2 tests), `test_analysis_results_pending.py` (2 tests) |
| 18 | `save_streaming_analysis()` | 3426-3939 | Import JsonProcessingService | `test_save_streaming_analysis.py` (3 tests) |
| 19 | `stream_case_analysis()` | 4048-4290 | Import MultiStageAnalyzer | None |
| 20 | `get_streaming_result()` | 4294-4324 | None | None |
| 21 | `get_analysis_state()` | 7525-7577 | None | None |

**Import this module needs:**
```python
from legal_portal.api.routes._analysis_helpers import (
    _is_transient_error, _upsert_with_retry, _update_case_with_retry,
    _to_sse, _ensure_case_access, _fetch_latest_analysis_result,
)
from legal_portal.services.main_processor import process_case_documents
from legal_portal.services.progress_manager import ProgressManager
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer
```

---

#### Module: `letter_routes.py`

| # | Function | Lines | Deps Change | Test Coverage |
|---|----------|-------|-------------|---------------|
| 1 | `LetterGenerationRequest` | 1281-1304 | None | `test_generate_letter_formatting.py` (4 tests) |
| 2 | `LetterGenerationResponse` | 1307-1314 | None | `test_generate_letter_formatting.py` |
| 3 | `RecommendationLetterRequest` | 4875-4887 | None | None |
| 4 | `RecommendationLetterResponse` | 4889-4896 | None | None |
| 5 | `CalculateDemandAmountRequest` | 5475-5479 | None | None |
| 6 | `CalculateDemandAmountResponse` | 5482-5487 | None | None |
| 7 | `_resolve_letter_identity_context()` | 622-752 | None | `test_letter_identity_resolution.py` (6 tests) |
| 8 | `_resolve_client_name_for_letter()` | 754-861 | None | `test_letter_identity_resolution.py` |
| 9 | `_new_generation_metrics()` | 464-496 | None | None |
| 10 | `_emit_generation_metrics()` | 498-504 | None | None |
| 11 | `_quality_report_placeholder()` | 511-528 | None | None |
| 12 | `_store_artifact()` | 1173-1193 | None | None |
| 13 | `_generate_and_store_artifacts()` | 1195-1236 | None | None |
| 14 | `_attach_signed_artifact_urls()` | 1238-1260 | None | None |
| 15 | `_ensure_fresh_gap_analysis_for_letter_generation()` | 6346-6468 | Import gap helpers | None |
| 16 | `stream_findings_letter()` | 2356-2935 | Import DemandLetterService + deps | `test_letter_stream_integration.py` (3 tests) |
| 17 | `generate_letter()` | 4326-4873 | Import all letter services | `test_generate_letter_formatting.py` (4 tests) |
| 18 | `generate_recommendation_letter()` | 4900-5087 | None | None |
| 19 | `stream_recommendation_letter()` | 5089-5473 | None | None |
| 20 | `calculate_demand_amount()` | 5491-5589 | Import DemandLetterService | None |

---

#### Module: `gap_routes.py`

| # | Function | Lines | Deps Change | Test Coverage |
|---|----------|-------|-------------|---------------|
| 1 | `GapBatch` (dataclass) | 5891-5901 | None | None |
| 2 | `GapAnalysisRequest` | 5591-5598 | None | None |
| 3 | `GapResolutionItemRequest` | 5601-5620 | None | None |
| 4 | `GapResolutionRefreshRequest` | 5623-5649 | None | None |
| 5 | 18 gap helper functions | 5652-6684 | From helpers: `_hash_jsonable`, signature utils | None |
| 6 | `analyze_gaps_on_demand()` | 6686-6847 | Import GapAnalysisService | None |
| 7 | `resolve_gaps_and_refresh()` | 6850-7043 | Import GapAnalysisService | None |
| 8 | `analyze_gaps_streaming()` | 7046-7223 | Import GapAnalysisService | None |

---

#### Module: `chat_routes.py`

| # | Function | Lines | Deps Change | Test Coverage |
|---|----------|-------|-------------|---------------|
| 1 | `stream_chat_response()` | 2937-3012 | Import CaseChatService | None |
| 2 | `case_chat()` | 7226-7291 | Import CaseChatService | None |

---

#### Module: `document_status_routes.py`

| # | Function | Lines | Deps Change | Test Coverage |
|---|----------|-------|-------------|---------------|
| 1 | `RetryDocumentsRequest` | 7293-7299 | None | None |
| 2 | `SkipDocumentsRequest` | 7302-7308 | None | None |
| 3 | `DocumentStatusResponse` | 7311-7321 | None | None |
| 4 | `RecoveryActionResponse` | 7324-7330 | None | None |
| 5 | `get_document_status()` | 7334-7375 | None | None |
| 6 | `retry_failed_documents()` | 7379-7448 | None | None |
| 7 | `skip_failed_documents()` | 7451-7522 | None | None |

---

### Endpoint Test Coverage Summary

**7 of 21 endpoint functions have tests. 14 are untested.**

| Risk | Endpoints | Action Before Refactor |
|------|-----------|----------------------|
| **LOW** (3+ tests) | `start_analysis`, `get_analysis_results`, `save_streaming_analysis`, `stream_findings_letter` | Safe to move — tests catch regressions |
| **MEDIUM** (1 test) | `cancel_analysis`, `get_analysis_status`, `get_document_status`, `generate_letter` | Add 1-2 more tests before moving |
| **HIGH** (0 tests) | `cancel_case_analysis`, `get_streaming_result`, `generate_recommendation_letter`, `stream_recommendation_letter`, `calculate_demand_amount`, `stream_chat_response`, `case_chat`, `analyze_gaps_on_demand`, `resolve_gaps_and_refresh`, `analyze_gaps_streaming`, `process_case_background`, `stream_case_analysis`, `retry_failed_documents`, `skip_failed_documents`, `get_analysis_state` | Write safety-net tests before moving |

**Well-tested helper functions:** `_extract_deferred_documents` (5 tests), `_dedup_email_threads` (4 tests), `_resolve_letter_identity_context` (2 tests), gap resolution helpers (12 tests)

---

## 3. Import Dependency Graph

### Dependency Rules

```
ALLOWED DIRECTION (top can import bottom):

    api/routes/*
        ↓
    api/dependencies.py
        ↓
    services/*
        ↓
    core/*
        ↓
    utils/*
        ↓
    config/*

FORBIDDEN:
    services → api/routes     (service must not know about HTTP)
    utils → services          (utils must be self-contained)
    core → api                (core must be framework-agnostic)
    config → anything above   (config is lowest layer)
```

### Current Import Map for analysis.py

```
analysis.py imports:
├── api/dependencies ─── get_current_user, get_supabase_client, get_user_supabase_client
├── api/rate_limiter ─── limiter
├── config/default ───── get_settings
├── core/data_models ─── ChatMessageRequest, DocumentStatus, DocumentType, LetterType, ...
├── services/
│   ├── case_chat_service ──── CaseChatService
│   ├── demand_letter_service ── DemandLetterService
│   ├── document_formatter ──── DocumentFormatterService
│   ├── json_processing_service ── JsonProcessingService
│   ├── letter_validation_service ── LetterValidationService
│   ├── main_processor ─────── process_case_documents
│   └── progress_manager ───── ProgressManager
└── utils/
    ├── diagnostic_logger ──── DiagnosticLogger
    ├── openai_client ──────── OpenAIClient
    ├── security ───────────── sanitize_text_for_db
    ├── throttled_db_writer ── ThrottledDBWriter
    └── type_safety ────────── safe_str, safe_str_required, sanitize_nested_dict
```

### After Split: Import Graph Per Module

```
_analysis_helpers.py:
├── api/dependencies (get_supabase_client only)
├── config/default
└── (stdlib: hashlib, json, re, email)

analysis_core.py:
├── _analysis_helpers ──── shared functions/constants
├── api/dependencies
├── config/default
├── core/data_models
├── services/main_processor
├── services/progress_manager
├── services/json_processing_service
├── services/multi_stage_analyzer (conditional, for streaming)
└── utils/openai_client, security, type_safety, throttled_db_writer

letter_routes.py:
├── _analysis_helpers ──── _to_sse, _ensure_case_access, artifact helpers
├── api/dependencies
├── config/default
├── core/data_models
├── services/demand_letter_service
├── services/document_formatter
├── services/letter_validation_service
├── services/json_processing_service
└── utils/openai_client, security

gap_routes.py:
├── _analysis_helpers ──── signature utils, _hash_jsonable, _to_sse
├── api/dependencies
├── config/default
├── core/data_models
├── services/gap_analysis_service (NEW direct import)
└── utils/openai_client

chat_routes.py:
├── _analysis_helpers ──── _ensure_case_access, _to_sse
├── api/dependencies
├── core/data_models
└── services/case_chat_service

document_status_routes.py:
├── _analysis_helpers ──── _ensure_case_access
├── api/dependencies
└── (no service imports — direct Supabase queries)
```

### Known Violations (from automated analysis)

| Severity | File | Line | Violation | Fix |
|----------|------|------|-----------|-----|
| **HIGH** | `core/document_processor.py` | 278 | Imports `api.utils.content_extractor` — Core → API reverse dependency | Move `ContentExtractor` to `services/` or `utils/`, update import |

All other layers are compliant — services never import from routes, utils never import from services.

### Potential Circular Import Risks

| Risk | Modules | Mitigation |
|------|---------|------------|
| `letter_routes` needs gap helpers from `gap_routes` | `_ensure_fresh_gap_analysis_for_letter_generation()` calls gap functions | Move this function to `_analysis_helpers.py` or have it import from `gap_routes` at call time (lazy import) |
| `_analysis_helpers` imports from `api/dependencies` | Creates a dependency on FastAPI | Accept this — helpers are route-layer utilities, not core business logic |
| `services/main_processor` imports from `services/multi_stage_analyzer` which imports from `services/gap_analysis_service` | Linear chain, no cycle | No action needed |

### Modules That Must Remain Dependency-Free

| Module | Reason | Allowed Imports |
|--------|--------|-----------------|
| `core/exceptions.py` | Used by everything | stdlib only |
| `core/models/*.py` | Used by everything | Pydantic, stdlib only |
| `config/default.py` | Used by everything | Pydantic Settings, stdlib, dotenv |
| `utils/type_safety.py` | Pure utility | stdlib only |
| `utils/validators.py` | Pure utility | stdlib, re only |

---

## 4. Performance Baseline Metrics

### What to Measure

| Metric | Where to Capture | Method |
|--------|-----------------|--------|
| Analysis total runtime | `process_case_background()` | `time.time()` start/end |
| Per-stage duration | `ProgressTracker.complete_phase()` | Already tracked in `helpers.py:112` |
| Gap analysis runtime | `_run_gap_analysis()` | `time.time()` around AI call |
| Letter generation latency | `stream_findings_letter()` | First SSE event to last |
| DB query count per request | All Supabase calls | Counter middleware |
| Peak memory usage | Process level | `tracemalloc` |
| OpenAI API call count/tokens | `OpenAIClient` | Already tracked in `cost_calculator.py` |

### Baseline Collection Script

Create `scripts/collect_performance_baseline.py`:

```python
"""Collect performance baseline metrics before refactoring.

Run against a test case with known documents to establish
repeatable benchmarks. Results are saved to .cache/baselines/.

Usage:
    python scripts/collect_performance_baseline.py --case-id <UUID>
"""

import asyncio
import json
import os
import time
import tracemalloc
from datetime import datetime
from pathlib import Path

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
BASELINE_DIR = Path(".cache/baselines")


async def measure_endpoint(client: httpx.AsyncClient, method: str, path: str,
                           token: str, body: dict | None = None) -> dict:
    """Measure a single endpoint call."""
    headers = {"Authorization": f"Bearer {token}"}
    start = time.perf_counter()

    if method == "GET":
        resp = await client.get(f"{API_URL}{path}", headers=headers, timeout=600)
    else:
        resp = await client.post(f"{API_URL}{path}", headers=headers, json=body, timeout=600)

    duration_ms = (time.perf_counter() - start) * 1000

    return {
        "endpoint": f"{method} {path}",
        "status": resp.status_code,
        "duration_ms": round(duration_ms, 1),
        "response_size_bytes": len(resp.content),
        "timestamp": datetime.utcnow().isoformat(),
    }


async def measure_sse_stream(client: httpx.AsyncClient, path: str,
                              token: str) -> dict:
    """Measure an SSE streaming endpoint."""
    headers = {"Authorization": f"Bearer {token}"}
    start = time.perf_counter()
    event_count = 0
    first_event_ms = None

    async with client.stream("GET", f"{API_URL}{path}", headers=headers, timeout=600) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                event_count += 1
                if first_event_ms is None:
                    first_event_ms = (time.perf_counter() - start) * 1000

    total_ms = (time.perf_counter() - start) * 1000

    return {
        "endpoint": f"SSE {path}",
        "total_duration_ms": round(total_ms, 1),
        "time_to_first_event_ms": round(first_event_ms or 0, 1),
        "event_count": event_count,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def collect_baseline(case_id: str, token: str):
    """Collect full baseline for a case."""
    tracemalloc.start()
    results = {"case_id": case_id, "collected_at": datetime.utcnow().isoformat(), "metrics": []}

    async with httpx.AsyncClient() as client:
        # 1. Analysis status
        results["metrics"].append(
            await measure_endpoint(client, "GET", f"/api/analysis/status/{case_id}", token)
        )

        # 2. Analysis results
        results["metrics"].append(
            await measure_endpoint(client, "GET", f"/api/analysis/results/{case_id}", token)
        )

        # 3. Gap analysis
        results["metrics"].append(
            await measure_endpoint(client, "POST", "/api/analysis/analyze-gaps",
                                   token, {"case_id": case_id})
        )

        # 4. Letter generation
        results["metrics"].append(
            await measure_endpoint(client, "POST", "/api/analysis/generate-letter",
                                   token, {"case_id": case_id, "letter_type": "findings"})
        )

    # Memory snapshot
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["memory"] = {
        "current_mb": round(current / 1024 / 1024, 2),
        "peak_mb": round(peak / 1024 / 1024, 2),
    }

    # Save
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = BASELINE_DIR / f"baseline_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(results, indent=2))
    print(f"Baseline saved to {output_path}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--token", required=True, help="JWT bearer token")
    args = parser.parse_args()
    asyncio.run(collect_baseline(args.case_id, args.token))
```

### Logging-Based Metrics (Add to Existing Code)

Add timing decorators to critical paths:

```python
# utils/timing.py (new, lightweight)
import functools
import logging
import time

logger = logging.getLogger("legal_portal.timing")

def timed(name: str):
    """Decorator to log function execution time."""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = (time.perf_counter() - start) * 1000
                logger.info("timing.%s", name, extra={"duration_ms": round(duration, 1)})
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = (time.perf_counter() - start) * 1000
                logger.info("timing.%s", name, extra={"duration_ms": round(duration, 1)})
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator
```

Apply to critical functions:

```python
# In analysis_core.py
@timed("analysis.process_case_background")
async def process_case_background(...): ...

# In gap_routes.py
@timed("gap_analysis.run")
async def analyze_gaps_on_demand(...): ...

# In letter_routes.py
@timed("letter.generate_findings")
async def generate_letter(...): ...

@timed("letter.stream_findings")
async def stream_findings_letter(...): ...
```

---

## 5. Refactor Validation Checklist

### After Every Phase

Run this checklist. Every item must pass before merging.

```bash
#!/bin/bash
# scripts/validate_refactor.sh
# Run after each refactor phase to verify nothing is broken.

set -e

echo "=== REFACTOR VALIDATION ==="
echo ""

# 1. Python imports resolve
echo "[1/7] Checking imports..."
python -c "from legal_portal.api.main import app; print(f'  App loaded: {len(app.routes)} routes')"

# 2. All tests pass
echo "[2/7] Running test suite..."
python -m pytest tests/ -x -q --tb=short 2>&1 | tail -5

# 3. Safety net tests pass
echo "[3/7] Running safety net tests..."
python -m pytest tests/safety_net/ -x -q --tb=short 2>&1 | tail -3

# 4. OpenAPI route count unchanged
echo "[4/7] Checking OpenAPI route count..."
ROUTE_COUNT=$(python -c "
from legal_portal.api.main import app
paths = list(app.openapi()['paths'].keys())
print(len(paths))
")
echo "  Routes: $ROUTE_COUNT (expected: 32)"
# Update expected count after first run

# 5. No circular imports
echo "[5/7] Checking for circular imports..."
python -c "
import importlib
modules = [
    'legal_portal.api.routes.analysis_core',
    'legal_portal.api.routes.letter_routes',
    'legal_portal.api.routes.gap_routes',
    'legal_portal.api.routes.chat_routes',
    'legal_portal.api.routes.document_status_routes',
    'legal_portal.api.routes._analysis_helpers',
]
for mod in modules:
    try:
        importlib.import_module(mod)
        print(f'  OK: {mod}')
    except ImportError as e:
        print(f'  FAIL: {mod} - {e}')
    except Exception:
        pass  # Module may not exist yet
"

# 6. Lint passes
echo "[6/7] Running linter..."
python -m ruff check src/legal_portal/ --quiet 2>&1 | tail -3

# 7. Type check (informational)
echo "[7/7] Running type check..."
python -m mypy src/legal_portal/core/ --ignore-missing-imports --no-error-summary 2>&1 | tail -3

echo ""
echo "=== VALIDATION COMPLETE ==="
```

### Phase-Specific Checks

| Phase | Additional Checks |
|-------|-------------------|
| Phase 1 (Dead code) | `grep -r "email_generator_core" src/` returns nothing |
| Phase 2 (Docs) | `ls *.md \| wc -l` shows ~15 |
| Phase 3 (Exceptions) | `grep -c "except Exception" src/legal_portal/` decreasing |
| Phase 4 (Split analysis.py) | `wc -l src/legal_portal/api/routes/analysis*.py gap_routes.py letter_routes.py chat_routes.py document_status_routes.py` — total matches original 7,614 |
| Phase 5 (Services reorg) | `python -c "from legal_portal.services.main_processor import process_case_documents"` |
| Phase 6 (data_models split) | `python -c "from legal_portal.core.data_models import DocumentType, LetterType"` (re-export shim works) |
| Phase 7 (Frontend) | Manual: upload doc → start analysis → view results → generate letter → chat |
| Phase 8 (Singletons) | `grep -r "get_instance\|_global_\|__new__" src/legal_portal/` shows 0 matches |

---

## 6. Async Job Queue Readiness

### Current State

The system uses two mechanisms for long-running work:
1. **Vercel:** Synchronous execution within the HTTP request (SSE streaming, 800s timeout)
2. **Local/Cloud Run:** `FastAPI.BackgroundTasks` (in-process, no persistence)

Both are fragile: if the process dies, the analysis is lost.

### Target State: Redis + Worker Queue

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  API Server │────→│  Redis       │────→│  Worker      │
│  (FastAPI)  │     │  (Queue +    │     │  (Celery/    │
│             │←────│   Pub/Sub)   │←────│   arq/SAQ)   │
└─────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Frontend   │     │  Progress    │     │  Supabase    │
│  (SSE)      │     │  Channel     │     │  (Results)   │
└─────────────┘     └──────────────┘     └──────────────┘
```

### Exact Changes Required Post-Refactor

#### 1. Add Redis dependency

```bash
pip install redis arq  # arq = async Redis queue (lighter than Celery)
```

Add to `requirements.txt`:
```
redis>=5.0.0
arq>=0.26.0
```

#### 2. Create job definitions

```python
# src/legal_portal/workers/analysis_worker.py
"""Analysis worker — processes cases in background via Redis queue."""

from arq import create_pool
from arq.connections import RedisSettings

from legal_portal.services.main_processor import process_case_documents


async def run_analysis_job(ctx: dict, case_id: str, analysis_id: str,
                            user_id: str, documents: list[dict]):
    """Process a case analysis as a background job."""
    redis = ctx["redis"]

    async def publish_progress(stage: str, percent: int, message: str):
        await redis.publish(
            f"progress:{analysis_id}",
            json.dumps({"stage": stage, "percent": percent, "message": message}),
        )

    try:
        result = await process_case_documents(
            case_id=case_id,
            documents=documents,
            progress_callback=publish_progress,
        )
        # Store result in Supabase
        # ... (same logic currently in process_case_background)

        await publish_progress("complete", 100, "Analysis complete")
    except Exception as e:
        await publish_progress("error", 0, str(e))
        raise


class WorkerSettings:
    functions = [run_analysis_job]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))
    max_jobs = 3  # concurrent analyses per worker
    job_timeout = 900  # 15 minutes max
```

#### 3. Modify analysis_core.py to enqueue instead of BackgroundTasks

```python
# In analysis_core.py — start_analysis()

# BEFORE:
background_tasks.add_task(process_case_background, ...)

# AFTER:
from arq import create_pool
from legal_portal.workers.analysis_worker import WorkerSettings

redis_pool = await create_pool(WorkerSettings.redis_settings)
job = await redis_pool.enqueue_job(
    "run_analysis_job",
    case_id=case_id,
    analysis_id=analysis_id,
    user_id=user_id,
    documents=docs,
)
return {"analysis_id": analysis_id, "job_id": job.job_id, "status": "queued"}
```

#### 4. Replace ProgressManager with Redis Pub/Sub

```python
# src/legal_portal/services/progress_manager.py — REFACTORED

class RedisProgressManager:
    """Progress manager backed by Redis Pub/Sub for multi-instance support."""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    async def publish(self, channel_id: str, data: dict):
        await self.redis.publish(f"progress:{channel_id}", json.dumps(data))

    async def subscribe(self, channel_id: str):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"progress:{channel_id}")
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield json.loads(message["data"])
```

#### 5. Update progress.py to use Redis Pub/Sub

```python
# In progress.py — stream_analysis_progress()

# BEFORE: Poll database every 2 seconds
# AFTER: Subscribe to Redis channel

progress_mgr = get_progress_manager(request)  # Now returns RedisProgressManager

async def event_generator():
    async for event in progress_mgr.subscribe(analysis_id):
        yield f"data: {json.dumps(event)}\n\n"
        if event.get("stage") in ("complete", "error"):
            break

return StreamingResponse(event_generator(), media_type="text/event-stream")
```

#### 6. Worker deployment

```yaml
# docker-compose.yml (new)
services:
  api:
    build: .
    command: uvicorn legal_portal.api.main:app --host 0.0.0.0
    environment:
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis

  worker:
    build: .
    command: arq legal_portal.workers.analysis_worker.WorkerSettings
    environment:
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
    deploy:
      replicas: 2  # Scale workers independently

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### Why the Refactor Enables This

| Refactor Change | How It Enables Queues |
|-----------------|----------------------|
| Split `analysis.py` | `analysis_core.py` has a clean `start_analysis()` that can enqueue vs inline |
| Singleton removal | `ProgressManager` can be swapped to `RedisProgressManager` via DI |
| Exception hierarchy | Worker can catch `AnalysisCancelledError` and clean up properly |
| Service layer reorg | `process_case_documents()` is a clean function with no HTTP dependencies — runs in worker as-is |
| Shared retry logic | Worker uses same `TransientDatabaseError` retry for DB writes |

---

## 7. Final Target Architecture

### Complete Directory Structure

```
Finding_Emails/
│
├── src/
│   └── legal_portal/
│       ├── __init__.py
│       │
│       ├── api/                                    # HTTP Layer
│       │   ├── __init__.py
│       │   ├── main.py                             # FastAPI app, CORS, lifespan, exception handlers
│       │   ├── dependencies.py                     # Auth + DI providers (Supabase, cache, sanitizer, etc.)
│       │   ├── rate_limiter.py                     # slowapi config
│       │   │
│       │   └── routes/
│       │       ├── __init__.py
│       │       ├── _analysis_helpers.py            # Shared: retry logic, signature utils, SSE helpers
│       │       ├── analysis_core.py                # Start, cancel, status, results, streaming
│       │       ├── letter_routes.py                # Findings, demand, recommendation letters
│       │       ├── gap_routes.py                   # Gap analysis run/resolve/stream
│       │       ├── chat_routes.py                  # Case chat
│       │       ├── document_status_routes.py       # Document status/retry/skip
│       │       ├── cases.py                        # Case CRUD + Clio import
│       │       ├── documents.py                    # Upload, extract, verify, delete
│       │       ├── clio.py                         # OAuth, matter search, sync
│       │       ├── progress.py                     # SSE streaming + polling fallback
│       │       ├── intake.py                       # Intake form processing
│       │       ├── corpus.py                       # Legal corpus lookup
│       │       ├── profile.py                      # User profile
│       │       ├── health.py                       # Health checks
│       │       └── settings.py                     # System settings
│       │
│       ├── core/                                   # Domain Layer (framework-agnostic)
│       │   ├── __init__.py
│       │   ├── exceptions.py                       # Unified exception hierarchy
│       │   ├── ai_analyzer.py                      # OpenAI interaction + caching
│       │   ├── document_processor.py               # File type dispatch
│       │   ├── data_models.py                      # Re-export shim (backward compat)
│       │   └── models/
│       │       ├── __init__.py                     # Re-exports all models
│       │       ├── document_models.py              # ProcessedDocument, DocumentType, etc.
│       │       ├── analysis_models.py              # AnalyzedDocument, LegalAssessment, etc.
│       │       ├── letter_models.py                # LetterType, DemandLetterEvaluation, etc.
│       │       ├── party_models.py                 # Party, PersonOrEntity, etc.
│       │       └── enums.py                        # All enums consolidated
│       │
│       ├── services/                               # Business Logic Layer
│       │   ├── __init__.py
│       │   │
│       │   ├── analysis/
│       │   │   ├── __init__.py
│       │   │   ├── multi_stage_analyzer.py
│       │   │   ├── gap_analysis_service.py
│       │   │   ├── corpus_coverage_service.py
│       │   │   ├── statute_validation_service.py
│       │   │   ├── statute_recommendation_service.py
│       │   │   ├── deadline_extraction_service.py
│       │   │   └── qa_service.py
│       │   │
│       │   ├── documents/
│       │   │   ├── __init__.py
│       │   │   ├── main_processor.py
│       │   │   ├── document_registry_service.py
│       │   │   ├── document_quality_validator.py
│       │   │   ├── content_extraction_service.py
│       │   │   ├── chunk_service.py
│       │   │   ├── chunk_state_manager.py
│       │   │   └── file_processors/
│       │   │       ├── __init__.py
│       │   │       ├── pdf_processor.py
│       │   │       ├── docx_processor.py
│       │   │       ├── eml_processor.py
│       │   │       ├── image_processor.py
│       │   │       ├── batch_vision_processor.py
│       │   │       ├── csv_processor.py
│       │   │       ├── txt_processor.py
│       │   │       ├── doc_processor.py
│       │   │       └── utils.py
│       │   │
│       │   ├── letters/
│       │   │   ├── __init__.py
│       │   │   ├── demand_letter_service.py
│       │   │   ├── recommendation_letter_service.py
│       │   │   ├── letter_strategy_service.py
│       │   │   ├── letter_quality_lint_service.py
│       │   │   ├── letter_validation_service.py
│       │   │   ├── letter_review_service.py
│       │   │   ├── fallback_generation_service.py
│       │   │   ├── citation_tracking_service.py
│       │   │   └── json_architecture_service.py
│       │   │
│       │   ├── integrations/
│       │   │   ├── __init__.py
│       │   │   ├── clio_context_builder.py
│       │   │   ├── clio_data_transformer.py
│       │   │   └── case_chat_service.py
│       │   │
│       │   ├── shared/
│       │   │   ├── __init__.py
│       │   │   ├── json_processing_service.py
│       │   │   ├── document_formatter.py
│       │   │   ├── content_formatting_service.py
│       │   │   ├── content_generation_service.py
│       │   │   ├── text_processing_service.py
│       │   │   ├── template_rendering_service.py
│       │   │   ├── prompt_and_api_service.py
│       │   │   ├── file_compression_service.py
│       │   │   └── progress_manager.py
│       │   │
│       │   └── grouping/
│       │       ├── __init__.py
│       │       ├── group_summarizer.py
│       │       └── group_quality_metrics.py
│       │
│       ├── workers/                                # Async Workers (NEW, post-refactor)
│       │   ├── __init__.py
│       │   └── analysis_worker.py                  # arq job definitions
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   ├── default.py                          # Pydantic Settings
│       │   └── prompts_and_settings.json           # AI prompts
│       │
│       └── utils/
│           ├── __init__.py
│           ├── timing.py                           # NEW: @timed decorator
│           ├── openai_client.py
│           ├── google_vision_client.py
│           ├── ocr_service_client.py
│           ├── cache_manager.py
│           ├── token_manager.py
│           ├── cost_calculator.py
│           ├── cost_estimator.py
│           ├── cost_exporter.py
│           ├── cost_session_manager.py
│           ├── pii_sanitizer.py
│           ├── helpers.py
│           ├── validators.py
│           ├── enhanced_file_validator.py
│           ├── security.py
│           ├── type_safety.py
│           ├── blacklist.py
│           ├── compression_utils.py
│           ├── diagnostic_logger.py
│           ├── logging_config.py
│           ├── structured_logger.py
│           ├── metrics.py
│           ├── tracing.py
│           ├── audit_logger.py
│           ├── letter_formatter.py
│           ├── letter_polish.py
│           ├── markdown_utils.py
│           ├── prompt_builder.py
│           ├── quality_metrics.py
│           ├── shared_utils.py
│           ├── throttled_db_writer.py
│           └── timeline_analyzer.py
│
├── frontend/
│   └── src/
│       ├── routes/
│       │   ├── +layout.svelte
│       │   ├── +layout.server.ts
│       │   ├── +page.svelte                        # Landing
│       │   ├── login/+page.svelte
│       │   ├── register/+page.svelte
│       │   ├── account-pending/+page.svelte
│       │   └── app/
│       │       ├── +layout.svelte
│       │       ├── +page.svelte                    # Dashboard
│       │       ├── cases/
│       │       │   ├── +page.svelte                # Case list
│       │       │   ├── new/+page.svelte            # New case
│       │       │   └── [id]/
│       │       │       ├── +page.svelte            # Case detail (reduced from 3,326 LOC)
│       │       │       ├── review/+page.svelte
│       │       │       └── results/
│       │       │           ├── +page.svelte        # Results (reduced from 2,873 LOC)
│       │       │           └── +page.server.ts
│       │       ├── help/+page.svelte
│       │       ├── settings/+page.svelte
│       │       └── design-system/+page.svelte
│       │
│       ├── lib/
│       │   ├── components/
│       │   │   ├── case/                           # EXTRACTED from [id]/+page.svelte
│       │   │   │   ├── DocumentUploadManager.svelte
│       │   │   │   ├── CaseDetailHeader.svelte
│       │   │   │   └── AnalysisControls.svelte
│       │   │   │
│       │   │   ├── results/                        # EXTRACTED from results/+page.svelte
│       │   │   │   ├── LettersTab.svelte
│       │   │   │   ├── ChatTab.svelte
│       │   │   │   ├── GapAnalysisTab.svelte
│       │   │   │   ├── DocumentReviewTab.svelte
│       │   │   │   ├── QualityReportTab.svelte
│       │   │   │   └── DocumentViewerModal.svelte
│       │   │   │
│       │   │   ├── ui/                             # Shared UI primitives (existing)
│       │   │   │   ├── AsyncButton.svelte
│       │   │   │   ├── Badge.svelte
│       │   │   │   ├── Button.svelte
│       │   │   │   ├── Card.svelte
│       │   │   │   ├── ConfirmDialog.svelte
│       │   │   │   ├── Modal.svelte
│       │   │   │   ├── PageHeader.svelte
│       │   │   │   ├── Spinner.svelte
│       │   │   │   ├── Tabs.svelte
│       │   │   │   ├── Toast.svelte
│       │   │   │   └── (other UI components)
│       │   │   │
│       │   │   ├── AnalysisStreamPanel.svelte      # (existing)
│       │   │   ├── DocumentCard.svelte
│       │   │   ├── DocumentCoverageSection.svelte
│       │   │   ├── DocumentPreviewPane.svelte
│       │   │   ├── DocumentSummaryCard.svelte
│       │   │   ├── FullAnalysisDisplay.svelte
│       │   │   ├── GapAnalysisPanel.svelte
│       │   │   ├── VerificationHub.svelte
│       │   │   ├── verificationHandlers.ts
│       │   │   └── (other existing components)
│       │   │
│       │   ├── stores/
│       │   │   ├── progressStore.ts
│       │   │   ├── toastStore.ts
│       │   │   ├── clioStore.ts
│       │   │   └── loadingStore.ts
│       │   │
│       │   ├── api/
│       │   │   └── cases.ts
│       │   │
│       │   ├── utils/
│       │   │   ├── sseClient.ts
│       │   │   ├── pollingClient.ts
│       │   │   ├── streamRecovery.ts
│       │   │   ├── letterCopy.ts
│       │   │   ├── markdown.ts
│       │   │   ├── documentSorting.ts
│       │   │   ├── blacklist.ts
│       │   │   ├── triageGrouping.ts
│       │   │   ├── redirectSanitizer.ts
│       │   │   └── supabaseRetry.ts
│       │   │
│       │   ├── config.ts
│       │   ├── supabase.ts
│       │   ├── types.ts
│       │   └── database.types.ts
│       │
│       └── tests/                                  # Frontend test mocks
│
├── tests/                                          # Backend tests
│   ├── conftest.py                                 # Shared fixtures (625 LOC)
│   ├── safety_net/                                 # PRE-REFACTOR safety tests
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_analysis_lifecycle.py
│   │   ├── test_letter_generation.py
│   │   ├── test_gap_analysis.py
│   │   ├── test_streaming_endpoints.py
│   │   ├── test_document_operations.py
│   │   ├── test_chat.py
│   │   └── test_document_status.py
│   ├── unit/                                       # Unit tests (41+ files)
│   ├── api/                                        # API tests (16+ files)
│   ├── integration/                                # Integration tests (7+ files)
│   │   └── conftest.py
│   └── e2e/                                        # Playwright E2E (NEW)
│       ├── auth.spec.ts
│       ├── case-workflow.spec.ts
│       └── results-display.spec.ts
│
├── scripts/
│   ├── start_backend.sh
│   ├── start_frontend.sh
│   ├── stop_local_dev.sh
│   ├── restart_servers.sh
│   ├── setup_and_deploy.sh
│   ├── setup_frontend_env.py
│   ├── validate_refactor.sh                        # NEW: post-phase validation
│   ├── collect_performance_baseline.py             # NEW: baseline metrics
│   ├── vercel_build.sh
│   ├── deploy.sh
│   ├── maintenance/
│   │   └── purge_old_artifacts.py
│   └── testing/
│       ├── run_analysis.py
│       ├── pull_case.py
│       └── verify_deployment.py
│
├── services/ocr/                                   # Cloud Run OCR microservice
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── deploy.sh
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── models.py
│       ├── vision_client.py
│       └── pdf_renderer.py
│
├── florida_legal_corpus/                           # FL statute corpus
├── new_mexico_legal_corpus/                        # NM statute corpus
│
├── docs/
│   ├── README.md                                   # Index
│   ├── API.md                                      # API reference
│   ├── AUTHENTICATION.md                           # Auth documentation
│   ├── ARCHITECTURE.md                             # System architecture (NEW)
│   ├── CLIO_INTEGRATION.md                         # Clio setup
│   ├── LETTER_GENERATION.md                        # Consolidated letter docs
│   ├── DEPLOYMENT.md                               # Consolidated deployment
│   ├── TESTING.md                                  # Consolidated testing
│   ├── HALLUCINATION_PREVENTION.md                 # Quality controls
│   ├── CITATION_ENHANCEMENT.md                     # Citation system
│   ├── plans/                                      # Design & implementation plans
│   │   ├── 2026-03-14-codebase-audit-and-refactor-plan.md
│   │   ├── 2026-03-14-refactor-execution-plan.md
│   │   ├── 2026-03-14-engineering-blueprint.md
│   │   └── (other plan files)
│   └── archive/                                    # Historical documentation
│
├── api/index.py                                    # Vercel entry point
├── run_app.py                                      # Local entry point
├── Dockerfile
├── cloudbuild.yaml
├── vercel.json
├── pyproject.toml
├── requirements.txt
├── pytest.ini
├── setup.py
│
├── README.md
├── START_HERE.md
├── FUNCTIONALITY.md
├── LAUNCH_APP.md
├── SETUP_INSTRUCTIONS.md
├── TESTING_GUIDE.md
├── DEPLOYMENT_GUIDE.md
├── DEPLOYMENT_CONFIG.md
├── REFACTOR_README.md
├── HOW_TO_GUIDE.md
├── GITHUB_AUTH_SETUP.md
├── ACCESSIBILITY_AUDIT.md
└── release-notes.md
```

### File Counts: Before vs After

| Category | Before | After | Change |
|----------|--------|-------|--------|
| Root .md files | 48 | 13 | -35 |
| Backend route files | 10 | 15 | +5 (split) |
| Backend service dirs | 1 flat | 6 subdirs | organized |
| Core model files | 1 (1,280 LOC) | 5 + shim | split |
| Frontend components | 40 (flat) | 40 + 9 extracted | +9 |
| Test directories | 4 | 5 + e2e | +2 |
| Scripts | 38 | 18 | -20 |
| Total Python source | 110 | ~125 | +15 (splits) |
| Largest backend file | 7,614 LOC | ~2,200 LOC | -72% |
| Largest frontend file | 3,326 LOC | ~1,500 LOC | -55% |
