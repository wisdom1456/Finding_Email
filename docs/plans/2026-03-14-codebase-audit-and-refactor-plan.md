# Codebase Audit & Refactor Plan

**Date:** 2026-03-14
**Scope:** Full technical audit of the Finding Emails legal document analysis platform
**Purpose:** Stabilize and clean the codebase before introducing async job queues and worker pipelines

---

## Executive Summary

The platform is a production-ready legal document analysis system with a **FastAPI backend** (57,946 LOC across 110 Python files) and a **SvelteKit frontend** (~22,000 LOC across 120+ files), deployed on Vercel with optional Google Cloud Run for OCR.

**Overall Code Health: 6/10**

The system works and delivers value, but is reaching complexity limits. The biggest risks are:

1. **One file (analysis.py) is 7,614 lines** — a monolithic route handler mixing business logic, streaming, caching, and error handling
2. **428 bare `except Exception` blocks** mask specific failures and make debugging hard
3. **48 root-level markdown files** with heavy duplication obscure actual documentation
4. **No E2E frontend tests** and incomplete coverage of v2.0 features
5. **Global singletons** (6 instances) make testing difficult and create implicit dependencies
6. **Dead code** including an empty `email_generator_core.py` and ~15 orphaned debug scripts

The architecture is sound underneath. The refactoring work is primarily about **splitting oversized files**, **removing dead weight**, and **normalizing patterns** — not a rewrite.

---

## Step 1 — System Architecture Overview

### Component Map

```
┌─────────────────────────────────────────────────────────┐
│                    SvelteKit Frontend                    │
│  (Vercel)  routes/ → components/ → stores/ → api/       │
└──────────────────────────┬──────────────────────────────┘
                           │ REST + SSE
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Backend                        │
│  api/routes/  →  services/  →  core/  →  utils/         │
│                                                          │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ Routes   │ │ Services     │ │ Core                 │ │
│  │----------│ │--------------│ │--------------------  │ │
│  │analysis  │→│main_processor│→│ai_analyzer           │ │
│  │documents │→│gap_analysis  │ │document_processor    │ │
│  │cases     │→│demand_letter │ │data_models (88 types)│ │
│  │clio      │→│multi_stage   │ └──────────────────────┘ │
│  │progress  │ │letter_*      │                          │
│  │intake    │ │chunk_service │  ┌─────────────────────┐ │
│  │profile   │ │doc_registry  │  │ File Processors     │ │
│  │corpus    │ │group_*       │  │ PDF, DOCX, EML,     │ │
│  │health    │ │chat_service  │  │ Image, TXT, CSV,DOC │ │
│  │settings  │ └──────────────┘  └─────────────────────┘ │
│  └──────────┘                                           │
└───────────────┬────────────────────┬────────────────────┘
                │                    │
        ┌───────▼───────┐   ┌───────▼───────┐
        │   Supabase    │   │   OpenAI API  │
        │  (DB + Auth   │   │  (GPT-4o)     │
        │   + Storage)  │   │               │
        └───────────────┘   └───────────────┘
                                    │
                            ┌───────▼───────┐
                            │ Google Vision  │
                            │ (OCR, optional)│
                            └───────────────┘
```

### Data Flow: Document Processing → Analysis → Letter Generation

```
1. Upload              Client uploads files via /api/documents/upload
                        ↓
2. Extract              DocumentProcessor dispatches to type-specific processor
                        (PDF→pdf_processor, DOCX→docx_processor, EML→eml_processor, etc.)
                        ↓
3. Classify             DocumentRegistryService classifies document type
                        (medical_record, police_report, correspondence, etc.)
                        ↓
4. Group                GroupSummarizer detects document groups (if enabled)
                        ↓
5. Analyze              POST /api/analysis/start triggers BackgroundTask
                        → main_processor.process_case_documents()
                        → multi_stage_analyzer (4 stages):
                           Stage 1: Fact extraction from each document
                           Stage 2: Issue mapping to legal elements
                           Stage 3: Deep analysis with statute matching
                           Stage 4: Letter structure generation
                        ↓
6. Gap Analysis         gap_analysis_service identifies missing evidence,
                        contradictions, statute coverage gaps
                        ↓
7. Letter Generation    demand_letter_service or recommendation_letter_service
                        → letter_strategy_service (pre-draft strategy)
                        → letter_quality_lint_service (quality validation)
                        → letter_review_service (AI-powered final review)
                        ↓
8. Stream Response      SSE streaming via /progress/analysis/{id}
                        Frontend progressStore manages display
```

---

## Step 2 — Codebase Inventory

### Directory Structure

```
Finding_Emails/
├── src/legal_portal/              # Main application (57,946 LOC, 110 files)
│   ├── api/                       #   API layer
│   │   ├── main.py                #     FastAPI app setup, CORS, middleware
│   │   ├── dependencies.py        #     Auth + Supabase dependency injection
│   │   ├── rate_limiter.py        #     Rate limiting (slowapi)
│   │   ├── routes/                #     Route handlers (10 files)
│   │   │   ├── analysis.py        #       7,614 LOC — MONOLITHIC, needs splitting
│   │   │   ├── documents.py       #       2,884 LOC
│   │   │   ├── cases.py           #       2,070 LOC
│   │   │   ├── clio.py            #       1,413 LOC
│   │   │   ├── progress.py        #       387 LOC
│   │   │   ├── intake.py          #       197 LOC
│   │   │   ├── corpus.py          #       152 LOC
│   │   │   ├── profile.py         #       116 LOC
│   │   │   ├── health.py          #       98 LOC
│   │   │   └── settings.py        #       53 LOC
│   │   ├── services/              #     API-level services (Clio auth/client)
│   │   └── utils/                 #     Content extractor
│   ├── core/                      #   Core domain logic
│   │   ├── data_models.py         #     88 Pydantic models (1,280 LOC)
│   │   ├── ai_analyzer.py         #     OpenAI integration (1,781 LOC)
│   │   ├── document_processor.py  #     File dispatch orchestrator (1,021 LOC)
│   │   └── email_generator_core.py#     EMPTY FILE — dead code
│   ├── services/                  #   Business logic services (40+ files)
│   │   ├── main_processor.py      #     Pipeline orchestrator (2,358 LOC)
│   │   ├── gap_analysis_service.py#     Gap detection (2,355 LOC)
│   │   ├── json_processing_service.py # JSON repair (2,267 LOC)
│   │   ├── multi_stage_analyzer.py#     4-stage analysis (1,471 LOC)
│   │   ├── document_registry_service.py # Classification (1,417 LOC)
│   │   ├── letter_strategy_service.py   # Pre-draft strategy (889 LOC)
│   │   ├── letter_quality_lint_service.py # Quality lint (831 LOC)
│   │   ├── letter_review_service.py     # AI review (759 LOC)
│   │   ├── content_formatting_service.py# Formatting (671 LOC)
│   │   ├── recommendation_letter_service.py # Rec. letters (522 LOC)
│   │   ├── demand_letter_service.py     # Demand letters (447 LOC)
│   │   ├── letter_validation_service.py # Validation (461 LOC)
│   │   ├── file_processors/       #     Type-specific processors
│   │   │   ├── pdf_processor.py   #       2,026 LOC — complex, handles OCR
│   │   │   ├── eml_processor.py   #       Email parsing
│   │   │   ├── docx_processor.py  #       Word docs
│   │   │   ├── image_processor.py #       Images + OCR
│   │   │   └── (csv, doc, txt)    #       Other formats
│   │   └── (20+ other services)   #     Chat, chunks, citations, etc.
│   ├── config/                    #   Configuration
│   │   ├── default.py             #     Pydantic Settings (603 LOC)
│   │   ├── config_manager.py      #     Legacy wrapper
│   │   └── prompts_and_settings.json # AI prompts
│   └── utils/                     #   Utilities (30 files)
│       ├── helpers.py             #     1,091 LOC — mixed utilities
│       ├── openai_client.py       #     855 LOC
│       ├── enhanced_file_validator.py # 784 LOC
│       ├── google_vision_client.py#     Vision API client
│       ├── cache_manager.py       #     File/memory caching
│       ├── token_manager.py       #     Token counting
│       ├── cost_calculator.py     #     API cost tracking
│       ├── pii_sanitizer.py       #     PII detection
│       └── (20+ other utilities)  #     Logging, security, etc.
│
├── frontend/                      # SvelteKit frontend (~22,000 LOC)
│   └── src/
│       ├── routes/app/            #   Page components
│       │   ├── cases/[id]/+page.svelte  # 3,326 LOC — MONOLITHIC
│       │   ├── cases/[id]/results/+page.svelte # 2,873 LOC — MONOLITHIC
│       │   └── help/+page.svelte  #   1,822 LOC
│       ├── lib/components/        #   UI components (40+ files)
│       │   ├── VerificationHub.svelte # 1,518 LOC
│       │   ├── AnalysisStreamPanel.svelte # 922 LOC
│       │   └── (35+ other components)
│       ├── lib/stores/            #   State management
│       ├── lib/api/               #   API client functions
│       └── lib/utils/             #   Frontend utilities
│
├── tests/                         # Test suite (81 files)
│   ├── unit/           (41 files) #   Unit tests
│   ├── api/            (16 files) #   API tests
│   ├── integration/     (7 files) #   Integration tests
│   └── conftest.py                #   Shared fixtures
│
├── scripts/                       # Utility scripts (38 files)
├── services/ocr/                  # Cloud Run OCR microservice
├── florida_legal_corpus/          # FL statute corpus
├── new_mexico_legal_corpus/       # NM statute corpus
├── docs/                          # Documentation (204 .md files)
│   ├── plans/                     #   Design/implementation plans
│   └── archive/                   #   Archived docs (150+ files)
├── .archive/                      # Phase 1 Streamlit code (deprecated)
├── .worktrees/                    # Git worktrees (2 active, 1 empty)
├── notebooklm_sources/            # Product reference docs
│
├── api/index.py                   # Vercel entry point
├── Dockerfile                     # Docker build
├── cloudbuild.yaml                # GCP Cloud Build
├── vercel.json                    # Vercel config
├── pyproject.toml                 # Python project config
├── requirements.txt               # Python deps (24 packages)
└── 48 root-level .md files        # BLOATED — needs cleanup
```

---

## Step 3 — Bug Findings & Risky Code

### CRITICAL

| # | Issue | Location | Risk | Fix |
|---|-------|----------|------|-----|
| B1 | **Empty file imported** — `email_generator_core.py` is 0 bytes but may be referenced | `src/legal_portal/core/email_generator_core.py` | Import errors or confusion | Delete file, remove imports |
| B2 | **Module-level mutable cache** — `_DB_COLUMNS_CACHE = {}` shared across all requests with no locking | `analysis.py:57` | Thread safety: concurrent requests could corrupt cache | Use `functools.lru_cache` or `contextvars` |
| B3 | **428 bare `except Exception` blocks** — masks specific failures, swallows tracebacks | Throughout `src/` | Bugs hidden in production; debugging extremely difficult | Replace with specific exception types |

### HIGH

| # | Issue | Location | Risk | Fix |
|---|-------|----------|------|-----|
| B4 | **SSE polling has no decay** — PollingClient retries up to 400 times at fixed interval with no exponential backoff | `frontend/src/lib/utils/pollingClient.ts` | Could hammer server under high load | Add exponential backoff |
| B5 | **No fetch timeouts** — most frontend API calls have no explicit timeout | Throughout frontend `fetch()` calls | Hung connections with no user feedback | Add AbortController with 60s default |
| B6 | **Session expiration not handled** — 401 responses from API don't trigger re-auth | Frontend API calls | User sees generic errors instead of login redirect | Intercept 401, redirect to login |
| B7 | **Transient error retry code duplicated** — `_is_transient_error()` and retry patterns copied across `analysis.py`, `documents.py`, `cases.py` | API routes | Inconsistent retry behavior; maintenance burden | Extract to shared utility |
| B8 | **Progress callback type unclear** — `Callable[[str, Optional[str]], Awaitable[None]]` used inconsistently | `main_processor.py`, file processors | Hard to test; tight coupling between processing and UI | Use event/signal pattern |

### MEDIUM

| # | Issue | Location | Risk | Fix |
|---|-------|----------|------|-----|
| B9 | **`@ts-ignore` on import** — suppresses type error on VerificationHub import | `frontend/[id]/+page.svelte:14` | Hides real type issues | Fix the import typing |
| B10 | **`any` types throughout frontend** — `doc: any`, `any[]` arrays | Multiple frontend components | No type safety on document objects | Create proper TypeScript interfaces |
| B11 | **CORS `allow_headers=["*"]`** — overly permissive | `api/main.py` | Security: allows any header in cross-origin requests | Whitelist specific headers |
| B12 | **OAuth redirect URI from host header** — falls back to request host if env var missing | `clio.py` | Could be manipulated in preview deployments | Always use configured redirect URI |

---

## Step 4 — Technical Debt Findings

### Dead Code

| Item | Location | Evidence |
|------|----------|----------|
| `email_generator_core.py` | `src/legal_portal/core/` | 0 bytes, empty file |
| `config_manager.py` | `src/legal_portal/config/` | Legacy wrapper, only used by old tests |
| `auth_config.yaml` | `src/legal_portal/config/` | Hardcoded users, not integrated with FastAPI/Supabase auth |
| ~15 debug/one-off scripts | `scripts/` root | `debug_create_case.py`, `create_mock_session.py`, `verify_sse_setup.py`, etc. |
| `test_gap_fix.py` | Root directory | One-off test, covered by `test_gap_signature_reconciliation.py` |
| `.worktrees/feature/` | `.worktrees/` | Empty directory — not a real worktree |
| Unused icon imports | Multiple frontend components | Icons imported but not used in markup |
| `thinkingTime` variable | `AnalysisStreamPanel.svelte` | Set but never read |

### Duplicate Logic

| Duplication | Files Involved | Lines Wasted |
|-------------|----------------|--------------|
| Transient error detection + retry | `analysis.py`, `documents.py`, `cases.py` | ~60 lines × 3 |
| Document formatting | `document_formatter.py` (1,368 LOC), `content_formatting_service.py` (671 LOC) | Overlapping HTML/markdown formatting |
| Letter validation pipeline | 5 separate services: `letter_strategy`, `letter_quality_lint`, `letter_review`, `letter_validation`, `demand_letter` | Unclear boundaries |
| Token counting | `token_manager.py`, `cost_calculator.py`, `openai_client.py`, `multi_stage_analyzer.py` | Same logic in 4 places |
| Modal upload logic | `CorrectionModal`, `RecoveryModal`, `AnalysisRecoveryModal` | ~290 lines each with shared patterns |

### Overly Complex Code

| File | LOC | Problem |
|------|-----|---------|
| `analysis.py` | 7,614 | Route handler doing business logic, streaming, caching, error handling — 82 functions, 18 classes |
| `[id]/+page.svelte` | 3,326 | Case detail page handling uploads, analysis, verification, Clio sync, dedup — 40+ state variables |
| `results/+page.svelte` | 2,873 | Results page handling gap analysis, findings, chat, letters, quality report |
| `data_models.py` | 1,280 | 88 Pydantic models in one file, no domain grouping |
| `helpers.py` | 1,091 | Mixed utilities + ProgressTracker class |
| `pdf_processor.py` | 2,026 | Mixes PDF parsing, OCR chunking, and Vision API calls |

### Large Constant Blocks in Code

| Constant | Location | Lines | Problem |
|----------|----------|-------|---------|
| `IMAGE_HANDLING_INSTRUCTIONS` | `main_processor.py` | ~88 lines | Prompt text embedded in Python code |
| Hard-coded model names | Multiple services | Scattered | Should be in config |
| OCR chunk size constants | `pdf_processor.py` | Scattered | Should be in config |

---

## Step 5 — Architecture Problems

### 1. analysis.py is a God Object

`analysis.py` at 7,614 lines is the single biggest architectural problem. It handles:
- Analysis start/cancel/status/results
- Letter generation (demand + recommendation)
- Gap analysis (start/resolve/stream)
- Chat functionality
- Document status queries
- Streaming (SSE)
- Progress tracking
- Caching (DB column checks)
- Retry logic
- Deferred document extraction

**Proposed split:**

| New Module | Responsibilities | Est. LOC |
|------------|-----------------|----------|
| `routes/analysis_core.py` | Start, cancel, status, results, retry | ~1,500 |
| `routes/analysis_streaming.py` | SSE streaming, progress, save/load stream | ~1,200 |
| `routes/letter_routes.py` | Generate/stream demand + recommendation letters | ~2,000 |
| `routes/gap_routes.py` | Gap analysis start, resolve, stream | ~1,500 |
| `routes/chat_routes.py` | Chat endpoint, case chat service | ~800 |
| Shared: `routes/_analysis_helpers.py` | Column cache, retry, transient errors | ~600 |

### 2. Singletons Blocking Testability

Six global singletons with different implementation patterns:

| Singleton | Pattern | File |
|-----------|---------|------|
| `_global_cache` | Module-level variable | `cache_manager.py` |
| `_global_sanitizer` | Module-level instance | `pii_sanitizer.py` |
| `GoogleVisionClient` | `_instance` class variable | `google_vision_client.py` |
| `MetricsCollector` | `__new__` override | `metrics.py` |
| `ProgressManager` | `__new__` override | `progress_manager.py` |
| Supabase client | `@lru_cache` | `dependencies.py` |

**Fix:** Migrate to FastAPI `Depends()` injection. Create a `ServiceContainer` or use `app.state` for shared instances.

### 3. Services Layer Too Flat

40+ service files in a single `services/` directory with no sub-organization:

**Proposed grouping:**

```
services/
├── analysis/
│   ├── multi_stage_analyzer.py
│   ├── gap_analysis_service.py
│   └── qa_service.py
├── documents/
│   ├── main_processor.py
│   ├── document_registry_service.py
│   ├── content_extraction_service.py
│   ├── chunk_service.py
│   └── file_processors/  (already exists)
├── letters/
│   ├── demand_letter_service.py
│   ├── recommendation_letter_service.py
│   ├── letter_strategy_service.py
│   ├── letter_quality_lint_service.py
│   ├── letter_review_service.py
│   ├── letter_validation_service.py
│   └── template_rendering_service.py
├── integrations/
│   ├── clio_context_builder.py
│   ├── clio_data_transformer.py
│   └── corpus_coverage_service.py
└── shared/
    ├── content_formatting_service.py
    ├── document_formatter.py
    ├── json_processing_service.py
    ├── progress_manager.py
    └── text_processing_service.py
```

### 4. Frontend Monolithic Pages

Two page components exceed 2,800 lines:

**`[id]/+page.svelte` (3,326 LOC) proposed split:**
- `CaseUploadPanel.svelte` — file selection, upload, duplicate detection
- `CaseAnalysisPanel.svelte` — streaming analysis UI, progress
- `CaseClioSync.svelte` — Clio sync operations
- `CaseVerification.svelte` — document triage (already has VerificationHub)
- `[id]/+page.svelte` — reduced to layout + routing between sub-panels

**`results/+page.svelte` (2,873 LOC) proposed split:**
- `ResultsGapPanel.svelte` — gap analysis display + resolution
- `ResultsLetterPanel.svelte` — letter generation + streaming
- `ResultsChatPanel.svelte` — case chat
- `ResultsQualityPanel.svelte` — quality report
- `results/+page.svelte` — reduced to layout + tab routing

### 5. No Unified Error Handling

Custom exceptions defined in multiple places with no hierarchy:
- `DocumentProcessingError` in `document_processor.py`
- `ValidationError` in `enhanced_file_validator.py` AND `document_processor.py`
- `AIAnalysisError` in `data_models.py`
- Various `ClioAPIError`, `ClioAuthError` in Clio services

**Proposed exception hierarchy:**
```python
# src/legal_portal/core/exceptions.py
class LegalPortalError(Exception): ...
class DocumentError(LegalPortalError): ...
class AnalysisError(LegalPortalError): ...
class LetterGenerationError(LegalPortalError): ...
class IntegrationError(LegalPortalError): ...
class ClioError(IntegrationError): ...
class ValidationError(LegalPortalError): ...
class TransientError(LegalPortalError): ...  # auto-retryable
```

---

## Step 6 — Documentation Cleanup Plan

### Current State: 48 root .md files, 204 docs/ .md files

### Root-Level Files

| Action | Files | Count |
|--------|-------|-------|
| **KEEP** | `README.md`, `START_HERE.md`, `FUNCTIONALITY.md`, `LAUNCH_APP.md`, `SETUP_INSTRUCTIONS.md`, `TESTING_GUIDE.md`, `DEPLOYMENT_GUIDE.md`, `DEPLOYMENT_CONFIG.md`, `REFACTOR_README.md`, `HOW_TO_GUIDE.md`, `GITHUB_AUTH_SETUP.md`, `release-notes.md` | 12 |
| **MERGE** | `ENV_SETUP_GUIDE.md` → into `START_HERE.md`; `RESTART_*.md` (2) → into `LAUNCH_APP.md`; `TESTING_VALIDATION_GUIDE.md` → into `TESTING_GUIDE.md`; `ENV_TEMPLATE.md` → update `.env.example` | 5 |
| **ARCHIVE** | `SSE_IMPLEMENTATION_SUMMARY.md`, `GRACEFUL_ERROR_HANDLING.md`, `EXISTING_DATABASE_MIGRATION.md`, `OPTIMIZATION_IMPLEMENTATION_SUMMARY.md`, `PHASE_4_IMPLEMENTATION_SUMMARY.md`, `FINAL_IMPLEMENTATION_SUMMARY.md`, `DEPLOYMENT_READY_SUMMARY.md`, `DISK_IO_DEPLOYMENT_CHECKLIST.md`, `FRONTEND_DESIGN_COMPLETE.md` | 9 |
| **DELETE** | All `VERCEL_*.md` (9), all `*_FIX.md`/`*_FIX_SUMMARY.md` (5), `QUICK_FIX_STEPS.md`, `CHECK_PUBLIC_API_URL.md`, `FORCE_VERCEL_REBUILD.md`, `QUICK_START_OPTIMIZATIONS.md`, `PYTHON_DEPENDENCIES_FIX.md`, `ACCOUNT_APPROVAL_IMPLEMENTATION.md`, `GAP_ANALYSIS_DEBUG_PROMPT.md`, `help-section-redesign.md` | ~22 |
| **UPDATE** | `ACCESSIBILITY_AUDIT.md`, `COLOR_CONTRAST_REPORT.md`, `PROJECT_CLEANUP_2025.md` | 3 |

**Target:** 48 → ~15 root-level .md files

### docs/ Directory Consolidation

| Action | Files | Details |
|--------|-------|---------|
| **Merge letter docs** | 7 `DEMAND_LETTER_*` / `LETTER_FORMAT_*` files | → single `docs/LETTER_GENERATION.md` |
| **Merge deployment docs** | 5 deployment files | → single `docs/DEPLOYMENT.md` |
| **Merge testing docs** | 3 testing files | → single `docs/TESTING.md` |
| **Keep archive** | 150+ files in `docs/archive/` | Already properly organized |
| **Keep plans** | 14 plan files in `docs/plans/` | Active planning artifacts |

### Proposed Clean Structure

```
docs/
├── README.md                      # Index
├── API.md                         # API reference
├── AUTHENTICATION.md              # Auth documentation
├── CLIO_INTEGRATION.md            # Clio setup
├── LETTER_GENERATION.md           # Consolidated letter docs
├── DEPLOYMENT.md                  # Consolidated deployment docs
├── TESTING.md                     # Consolidated testing docs
├── HALLUCINATION_PREVENTION.md    # Quality controls
├── CITATION_ENHANCEMENT.md        # Citation system
├── ARCHITECTURE.md                # System architecture
├── plans/                         # Design & implementation plans
└── archive/                       # Historical documentation
```

---

## Step 7 — Naming & Consistency

### Inconsistent Patterns Found

| Pattern | Examples | Proposed Standard |
|---------|----------|-------------------|
| Service naming | `*_service.py` vs `*_processor.py` vs `*_manager.py` | Use `*_service.py` for business logic, `*_processor.py` for data transformation, `*_client.py` for external APIs |
| Document terminology | `doc`, `document`, `file`, `processed_document` | Standardize: `document` for domain objects, `file` for raw uploads |
| Class name collision | `DocumentProcessor` in both `core/document_processor.py` and `api/utils/content_extractor.py` | Rename to `DocumentDispatcher` (core) and `ContentExtractor` (api) |
| Frontend prop patterns | Some use typed `$props()`, others use `any` | Always use typed interfaces |
| Error message style | Some with emojis (`AI ANALYZER: 🔍`), some plain | Remove emojis from logs; use structured logging |
| Config access | `settings.X` vs `os.environ["X"]` vs constants | Always use `settings.X` from Pydantic Settings |

### Naming Conventions to Adopt

```
Python:
  Files:      snake_case.py
  Classes:    PascalCase
  Functions:  snake_case
  Constants:  UPPER_SNAKE_CASE
  Private:    _leading_underscore

Frontend:
  Components: PascalCase.svelte
  Utilities:  camelCase.ts
  Stores:     camelCaseStore.ts
  Types:      PascalCase (in types.ts)
```

---

## Step 8 — Folder Structure Refactor Proposal

### Backend Target Structure

```
src/legal_portal/
├── api/
│   ├── main.py
│   ├── dependencies.py
│   ├── rate_limiter.py
│   ├── middleware/               # NEW: extract from routes
│   │   ├── error_handler.py
│   │   └── retry.py
│   └── routes/
│       ├── analysis_core.py     # SPLIT from analysis.py
│       ├── analysis_streaming.py# SPLIT from analysis.py
│       ├── letter_routes.py     # SPLIT from analysis.py
│       ├── gap_routes.py        # SPLIT from analysis.py
│       ├── chat_routes.py       # SPLIT from analysis.py
│       ├── cases.py
│       ├── documents.py
│       ├── clio.py
│       ├── progress.py
│       ├── intake.py
│       ├── corpus.py
│       ├── profile.py
│       ├── health.py
│       └── settings.py
├── core/
│   ├── exceptions.py            # NEW: unified exception hierarchy
│   ├── ai_analyzer.py
│   ├── document_processor.py
│   └── models/                  # SPLIT from data_models.py
│       ├── document_models.py
│       ├── analysis_models.py
│       ├── letter_models.py
│       ├── party_models.py
│       └── enums.py
├── services/
│   ├── analysis/                # NEW subdirectory
│   ├── documents/               # NEW subdirectory
│   ├── letters/                 # NEW subdirectory
│   ├── integrations/            # NEW subdirectory
│   ├── shared/                  # NEW subdirectory
│   └── file_processors/         # Already exists
├── config/
│   ├── default.py
│   └── prompts_and_settings.json
└── utils/
    ├── clients/                 # NEW: openai_client, google_vision_client, ocr_client
    ├── validation/              # NEW: validators, enhanced_file_validator
    ├── caching/                 # NEW: cache_manager, cost_session_manager
    └── (remaining utilities)
```

### Frontend Target Structure (component extraction)

```
frontend/src/lib/components/
├── case/                        # NEW: extracted from [id]/+page.svelte
│   ├── CaseUploadPanel.svelte
│   ├── CaseAnalysisPanel.svelte
│   └── CaseClioSync.svelte
├── results/                     # NEW: extracted from results/+page.svelte
│   ├── ResultsGapPanel.svelte
│   ├── ResultsLetterPanel.svelte
│   ├── ResultsChatPanel.svelte
│   └── ResultsQualityPanel.svelte
├── shared/                      # NEW: shared modal/upload base
│   └── BaseUploadModal.svelte
└── (existing components)
```

---

## Step 9 — Dependency & Configuration Cleanup

### Unused/Questionable Dependencies

Review these in `requirements.txt`:
- `streamlit` — if still present, remove (Phase 1 code is archived)
- `altair` — likely only needed for Streamlit, remove if unused
- `plotly` — same as above

### Configuration Cleanup

| Action | Item | Details |
|--------|------|---------|
| **DELETE** | `config/auth_config.yaml` | Not used; auth handled by Supabase |
| **DELETE** | `config/config_manager.py` | Legacy wrapper; modern code uses `settings` |
| **CONSOLIDATE** | Feature flags | Currently scattered across `default.py` and route handlers; create `FeatureFlags` section |
| **VALIDATE** | Feature flag dependencies | Phase C requires Phase B; add validation |
| **UPDATE** | `.env.example` | Out of sync with actual required variables |

### Environment Variable Cleanup

Current env vars are reasonable but need documentation. Create a table in `.env.example`:

```bash
# Required
SUPABASE_URL=         # Supabase instance URL
SUPABASE_SERVICE_KEY= # Backend service role key
SUPABASE_ANON_KEY=    # Frontend anonymous key
OPENAI_API_KEY=       # OpenAI API key

# Clio Integration (optional)
CLIO_CLIENT_ID=       # Clio OAuth client ID
CLIO_CLIENT_SECRET=   # Clio OAuth client secret
CLIO_PRODUCTION_URL=  # Production callback URL

# Deployment
CORS_ORIGINS=         # Comma-separated allowed origins
FRONTEND_URL=         # Frontend URL for redirects
ENVIRONMENT=          # prod/dev

# Feature Flags
ENABLE_GROUP_DETECTION=false
ENABLE_GROUP_SUMMARIZATION=false
ENABLE_GROUP_CONTEXT=false
```

---

## Step 10 — Testing Improvements

### Current Coverage

| Area | Files | Coverage | Gap |
|------|-------|----------|-----|
| Unit tests | 41 | Good for core services | Missing: VerificationHub, group features |
| API tests | 16 | Basic endpoint coverage | Missing: error cases, auth edge cases |
| Integration tests | 7 | DB write paths, RLS | Missing: full workflow tests |
| Frontend unit tests | ~34 | Basic component tests | Missing: key components |
| E2E tests | 0 | **None** | **Critical gap** |
| Security tests | 0 | **None** | Should validate XSS, CSRF, RLS |

### Recommended Test Additions

**Priority 1 — Must Have:**
- E2E tests for auth flow (login → case creation → upload → analysis → results)
- Tests for `analysis.py` route handler (largest untested surface area)
- Tests for VerificationHub component (1,518 LOC, no tests)
- Security tests for RLS policies and auth bypass

**Priority 2 — Should Have:**
- Tests for v2.0 features: group detection, map-reduce gap analysis, letter critic
- Frontend tests for `[id]/+page.svelte` and `results/+page.svelte`
- Performance tests for large case handling (50+ documents)
- Tests for streaming recovery and SSE reconnection

**Priority 3 — Nice to Have:**
- Mutation testing for critical paths
- Load testing for concurrent analysis requests
- Visual regression tests for letter formatting

---

## Step 11 — Refactoring Roadmap

### Phase 1: Remove Dead Code & Abandoned Experiments
**Estimated effort:** 1 day | **Risk:** Low | **Validation:** Run full test suite

| Task | Files | Complexity |
|------|-------|------------|
| Delete `email_generator_core.py` | 1 file | Trivial |
| Delete `test_gap_fix.py` from root | 1 file | Trivial |
| Delete `config_manager.py` + `auth_config.yaml` | 2 files | Low — verify no imports |
| Clean `.worktrees/feature/` empty dir | 1 dir | Trivial |
| Remove unused frontend icon imports | ~5 files | Low |
| Remove `thinkingTime` dead variable | 1 file | Trivial |
| Delete ~15 orphaned debug scripts | 15 files | Low — verify none are in CI |

### Phase 2: Documentation Cleanup
**Estimated effort:** 1 day | **Risk:** Low | **Validation:** Manual review

| Task | Files | Complexity |
|------|-------|------------|
| Delete ~22 one-off fix/Vercel .md files from root | 22 files | Trivial |
| Merge ENV/restart/testing duplicates | 5 files | Low |
| Archive 9 implementation summary files | 9 files | Low |
| Consolidate 7 letter docs into 1 | 7 → 1 file | Medium |
| Consolidate deployment docs | 5 → 1 file | Medium |
| Update `.env.example` | 1 file | Low |

### Phase 3: Extract Shared Utilities
**Estimated effort:** 2 days | **Risk:** Medium | **Validation:** Run full test suite

| Task | Files | Complexity |
|------|-------|------------|
| Create `core/exceptions.py` — unified exception hierarchy | New file + update imports | Medium |
| Extract transient error retry to `api/middleware/retry.py` | 3 route files | Medium |
| Centralize token counting in `token_manager.py` | 4 files | Medium |
| Move `IMAGE_HANDLING_INSTRUCTIONS` to config | 1 file | Low |

### Phase 4: Split analysis.py (The Big One)
**Estimated effort:** 3-5 days | **Risk:** High | **Validation:** Full test suite + manual API testing

| Task | New File | Est. LOC |
|------|----------|----------|
| Extract letter generation routes | `routes/letter_routes.py` | ~2,000 |
| Extract gap analysis routes | `routes/gap_routes.py` | ~1,500 |
| Extract chat routes | `routes/chat_routes.py` | ~800 |
| Extract streaming logic | `routes/analysis_streaming.py` | ~1,200 |
| Extract shared helpers | `routes/_analysis_helpers.py` | ~600 |
| Slim down `analysis.py` to core CRUD | `routes/analysis_core.py` | ~1,500 |

**Feature flag approach:** Add `USE_SPLIT_ROUTES` flag, register both old and new routers, switch gradually.

### Phase 5: Service Layer Reorganization
**Estimated effort:** 2-3 days | **Risk:** Medium | **Validation:** Full test suite

| Task | Details | Complexity |
|------|---------|------------|
| Create `services/analysis/` subdirectory | Move 3 files | Medium |
| Create `services/documents/` subdirectory | Move 5 files | Medium |
| Create `services/letters/` subdirectory | Move 6 files | Medium |
| Create `services/integrations/` subdirectory | Move 3 files | Low |
| Update all imports | Across codebase | Tedious but low risk |

### Phase 6: Split data_models.py
**Estimated effort:** 1-2 days | **Risk:** Medium | **Validation:** mypy + full test suite

| Task | Details | Complexity |
|------|---------|------------|
| Create `core/models/` directory | New directory | Trivial |
| Split 88 models into 4-5 domain files | 1 → 5 files | Medium |
| Create `core/models/enums.py` | Consolidate enums | Medium |
| Update all imports across codebase | ~100 imports | Tedious |
| Keep `data_models.py` as re-export shim temporarily | Backward compat | Low |

### Phase 7: Frontend Component Extraction
**Estimated effort:** 3-5 days | **Risk:** Medium | **Validation:** Manual UI testing + frontend tests

| Task | Details | Complexity |
|------|---------|------------|
| Extract upload logic from `[id]/+page.svelte` | New `CaseUploadPanel.svelte` | High |
| Extract analysis UI from `[id]/+page.svelte` | New `CaseAnalysisPanel.svelte` | High |
| Extract gap panel from `results/+page.svelte` | New `ResultsGapPanel.svelte` | Medium |
| Extract letter panel from `results/+page.svelte` | New `ResultsLetterPanel.svelte` | Medium |
| Create shared `BaseUploadModal.svelte` | Deduplicate 3 modals | Medium |
| Add TypeScript interfaces for document types | Replace `any` types | Medium |

### Phase 8: Singleton Migration
**Estimated effort:** 2 days | **Risk:** Medium | **Validation:** Full test suite

| Task | Details | Complexity |
|------|---------|------------|
| Convert `GoogleVisionClient` to DI | Use `Depends()` | Medium |
| Convert `MetricsCollector` to DI | Use `app.state` | Medium |
| Convert `ProgressManager` to DI | Use `Depends()` | Medium |
| Convert `_global_cache` to DI | Use `Depends()` | Medium |
| Convert `_global_sanitizer` to DI | Use `Depends()` | Low |

### Phase 9: Testing Improvements
**Estimated effort:** Ongoing | **Risk:** Low | **Validation:** Coverage reports

| Task | Details | Priority |
|------|---------|----------|
| Add Playwright E2E tests | Auth, case workflow, upload | High |
| Add VerificationHub tests | Component testing | High |
| Add analysis.py route tests | After Phase 4 split | High |
| Add security tests | RLS, XSS, auth bypass | Medium |
| Replace broad `except Exception` | 428 instances | Ongoing |
| Add frontend TypeScript strict mode | `tsconfig.json` | Medium |

---

## Step 12 — Bad Design Decisions to Address

### 1. Synchronous Long-Running Analysis in Serverless

**Problem:** Analysis can take 5-15 minutes. On Vercel, this runs inside a single serverless function invocation with an 800s timeout. If the function cold-starts or the connection drops, the analysis is lost.

**Current mitigation:** Database polling for progress, SSE with reconnection.

**Long-term fix:** Move analysis to an async job queue (Redis/Celery or Cloud Tasks) with a worker pool. The API should return a job ID immediately and the frontend polls for status. This is the architectural work this audit is preparing for.

### 2. All Business Logic Funneled Through One Route File

**Problem:** `analysis.py` is a 7,614-line route handler that has become a God Object. Every new feature (chat, gaps, letters, streaming) gets added here because it needs access to analysis state.

**Risk:** Any bug in this file could take down all analysis functionality. Changes are high-risk because the file is too large to reason about.

**Fix:** Phase 4 of the roadmap — split into 5-6 focused route modules.

### 3. Pickle-Based Caching

**Problem:** `cache_manager.py` and `cost_session_manager.py` use pickle for serialization.

**Risk:** Pickle is not human-readable, has Python version incompatibilities, and is a security vector if loading untrusted data.

**Fix:** Switch to JSON serialization with explicit schemas.

### 4. Hidden Global State via Singletons

**Problem:** 6 different singleton implementations create invisible dependencies between components. Tests can't easily mock these.

**Risk:** State pollution between tests, thread safety issues in production, impossible to run multiple instances.

**Fix:** Phase 8 — migrate to FastAPI dependency injection.

### 5. Brittle Document Parsing

**Problem:** `pdf_processor.py` (2,026 LOC) handles PDF parsing, OCR chunking, and Vision API calls in one file. OCR failures are caught with broad `except Exception` and silently degraded.

**Risk:** Silent data loss — if OCR fails on page 3 of a 10-page medical record, the analysis proceeds without that evidence and the user is not clearly informed.

**Fix:** Split OCR logic into dedicated service; make failure modes explicit; show per-page extraction status to user.

### 6. Frontend Monoliths Block Testing

**Problem:** Two page components (3,326 and 2,873 lines) are too large to unit test. They contain interleaved state, effects, and API calls that can't be tested in isolation.

**Risk:** Regressions go undetected. Currently 0 meaningful tests for these critical pages.

**Fix:** Phase 7 — extract into testable sub-components.

---

## Step 13 — Final Summary

### Key Metrics

| Metric | Value |
|--------|-------|
| Backend LOC | 57,946 |
| Frontend LOC | ~22,000 |
| Total source files | 230+ |
| Test files | 81 |
| Documentation files | 252 (many duplicate) |
| Largest file | `analysis.py` — 7,614 LOC |
| Broad exception handlers | 428 |
| Global singletons | 6 |
| Dead files | ~20 |
| Orphaned scripts | ~15 |
| Root .md files to delete/archive | ~31 |

### Priority Order

1. **Phase 1 — Dead code removal** (1 day, low risk) — immediate cleanup
2. **Phase 2 — Documentation cleanup** (1 day, low risk) — reduce noise
3. **Phase 3 — Shared utilities extraction** (2 days, medium risk) — foundation for Phase 4
4. **Phase 4 — Split analysis.py** (3-5 days, high risk) — biggest single improvement
5. **Phase 5 — Service reorganization** (2-3 days, medium risk) — clarity
6. **Phase 6 — Split data_models.py** (1-2 days, medium risk) — maintainability
7. **Phase 7 — Frontend extraction** (3-5 days, medium risk) — testability
8. **Phase 8 — Singleton migration** (2 days, medium risk) — testability
9. **Phase 9 — Testing improvements** (ongoing) — confidence

**Total estimated effort: 15-22 working days across all phases**

### What This Enables

After this cleanup, the codebase will be ready for:
- **Async job queues** — clean service boundaries make it straightforward to wrap services in Celery/Cloud Tasks workers
- **Worker pipelines** — the split analysis routes become natural queue producers; services become queue consumers
- **Horizontal scaling** — removing singletons and global state enables multi-instance deployment
- **Confident iteration** — better test coverage and smaller files mean changes can be made safely
