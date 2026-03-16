# Full Codebase Audit & Refactor Plan

**Date:** 2026-03-15
**Author:** Technical Audit (Claude)
**Status:** Draft - Awaiting Review
**Scope:** Complete technical audit of the Finding_Emails / Legal Portal repository

---

## Executive Summary

This repository is a legal document analysis platform with a FastAPI backend, SvelteKit frontend, and Supabase database. It processes legal documents (PDFs, images, emails), runs AI-powered analysis through a multi-stage pipeline, and generates findings/demand letters.

The system works but has accumulated significant technical debt from rapid iteration. The most critical issues are:

1. **34 stub shim files** from an incomplete refactor migration
2. **Route files containing 1,400-2,900 lines of business logic** that belongs in services
3. **Duplicate constants and config** (jurisdiction maps, pricing, model names) scattered across files
4. **Security bugs**: pickle deserialization in cache, missing authorization on chat streaming, broken `get_optional_user`
5. **Runtime bugs**: field name mismatch in ProcessingResult, discarded return values, log message lies
6. **~280 obsolete documentation files** inflating the repository
7. **6 overlapping CI/CD workflows** with stale Python version matrices
8. **3 Dockerfiles with conflicting configurations**

The codebase is approximately **58,000 lines of Python** (source only) and **~15,000 lines of Svelte/TypeScript** in the frontend.

---

## Step 1 — System Architecture Overview

### Pipeline Flow

```
Client (SvelteKit)
  |
  v
FastAPI API Layer (src/legal_portal/api/)
  |
  ├─ Document Upload (/api/documents/upload)
  │    → File processors (PDF, DOCX, EML, image, CSV, TXT)
  │    → OCR fallback (Google Vision / batch vision)
  │    → Text extraction + quality validation
  │    → Supabase storage + document registry
  │
  ├─ Analysis Pipeline (/api/analysis/run)
  │    → main_processor.process_case_documents()
  │    │
  │    ├─ Stage 1: Input Validation & Deduplication (0-15%)
  │    ├─ Stage 2: Quality Validation (15-20%)
  │    ├─ Stage 3: Group Detection & Summarization (20%)
  │    ├─ Stage 4: Per-Document AI Summarization (15-20%)
  │    ├─ Stage 5: Synthesis Gate (ChunkStateManager)
  │    ├─ Stage 6: Case Synthesis via OpenAI (25-35%)
  │    ├─ Stage 7: Coverage & Deadline Extraction (40-55%)
  │    └─ Stage 8: Multi-Stage Deep Analysis (55-75%)
  │         ├─ Pass 1: Fact Matrix
  │         ├─ Pass 2: Issue Mapping
  │         ├─ Pass 3: Deep Analysis
  │         └─ Pass 4: Letter Structure
  │
  ├─ Letter Generation (/api/analysis/generate-letter)
  │    → JsonProcessingService (misnamed — this IS the letter engine)
  │    → Three modes: JSON-based, adaptive, streaming
  │    → Letter strategy → content generation → formatting → validation → lint
  │    → HTML/Markdown output
  │
  ├─ Gap Analysis (/api/analysis/gap-*)
  │    → GapAnalysisService (map-reduce across document chunks)
  │    → Resolution tracking per gap
  │
  ├─ Clio Integration (/api/clio/*)
  │    → OAuth flow + matter search + document import
  │    → Rate-limited sync with Clio API
  │
  └─ Chat (/api/analysis/chat)
       → CaseChatService (context-aware Q&A over case data)

Supabase (PostgreSQL + Storage + Auth + RLS)
  ├─ cases, documents, analysis_results, letters
  ├─ document_registry, document_groups
  ├─ gap_analysis, gap_resolutions
  └─ File storage buckets
```

### Major Components

| Component | Location | Lines | Purpose |
|-----------|----------|-------|---------|
| API Routes | `api/routes/` | 15,280 | HTTP endpoints (too much business logic here) |
| Analysis Pipeline | `services/analysis/` | ~8,500 | Document processing, multi-stage analysis |
| Letter Services | `services/letters/` | ~5,500 | Letter generation, review, validation |
| Document Services | `services/documents/` | ~6,000 | File processing, chunking, extraction |
| Shared Services | `services/shared/` | ~6,000 | JSON processing, formatting, citations |
| Core Models | `core/` | ~4,800 | Data models, AI analyzer, document processor |
| Utilities | `utils/` | ~8,500 | Logging, cost tracking, security, helpers |
| Frontend | `frontend/src/` | ~15,000 | SvelteKit UI with Supabase auth |

---

## Step 2 — Codebase Inventory

```
Finding_Emails/
├── src/legal_portal/           # Main Python package (58K lines)
│   ├── api/                    # FastAPI application
│   │   ├── main.py             # App factory, middleware, lifespan
│   │   ├── dependencies.py     # Auth, Supabase client injection
│   │   ├── rate_limiter.py     # Token bucket rate limiter
│   │   ├── middleware/         # Error handler, retry middleware
│   │   ├── routes/            # 16 route modules (15K lines total)
│   │   ├── services/          # Clio auth + client (API-layer services)
│   │   └── utils/             # Content extractor (API-layer util)
│   ├── config/                # Settings (Pydantic) + legacy ConfigManager
│   ├── core/                  # Domain models, AI analyzer, doc processor
│   │   └── models/            # Pydantic models (analysis, document, letter, party, enums)
│   ├── services/              # Business logic (organized into subdomain dirs)
│   │   ├── analysis/          # Main processor, multi-stage analyzer, gap analysis
│   │   ├── documents/         # File processors, chunking, compression, extraction
│   │   ├── letters/           # Generation, review, validation, formatting
│   │   ├── shared/            # Cross-cutting: citations, formatting, progress, QA
│   │   ├── grouping/          # Document group detection and summarization
│   │   ├── integrations/      # Clio context builder + data transformer
│   │   └── [34 stub files]    # importlib shims pointing to subdirectory files
│   ├── utils/                 # 30 utility modules (8.5K lines)
│   ├── prompts/               # AI prompt templates + jurisdiction guidance
│   └── assets/templates/      # Jinja2 letter templates
├── frontend/                  # SvelteKit application
│   ├── src/lib/              # Shared library
│   │   ├── api/              # Supabase client, cases API
│   │   ├── components/       # UI components + domain components
│   │   ├── stores/           # Svelte stores (clio, loading, progress, toast)
│   │   ├── utils/            # Frontend utilities
│   │   └── styles/           # CSS
│   ├── src/routes/           # SvelteKit pages
│   └── tests/                # Vitest + Playwright config
├── tests/                    # Python tests (16 API + 37 unit + 6 integration + misc)
├── scripts/                  # Dev scripts, deployment, testing utilities
├── schemas/                  # JSON schemas for pipeline validation
├── services/ocr/             # Standalone OCR microservice
├── supabase/                 # Migration files
├── docs/                     # Documentation (active + 221 archived files)
├── memory-bank/              # Roo/Cline memory system (43 files)
├── api/index.py              # Vercel serverless entry point
├── .archive/                 # Old phase1 code
└── [root config files]       # Dockerfiles, requirements, pyproject.toml, etc.
```

---

## Step 3 — Bugs and Risky Code

### Critical Bugs

| # | Location | Bug | Impact |
|---|----------|-----|--------|
| B1 | `main_processor.py:798` | `processing_time=` passed but model field is `processing_time_seconds` | Pydantic ValidationError on error-recovery path |
| B2 | `dependencies.py` | `get_optional_user` uses `HTTPBearer()` which rejects unauthenticated requests with 403 before function body runs | All "optional auth" endpoints are effectively mandatory auth |
| B3 | `chat_routes.py` | `stream_chat_response` authenticates user but does NOT verify case ownership | Any authenticated user can stream chat data for any case |
| B4 | `cache_manager.py` | `pickle.load()` for cache deserialization | Arbitrary code execution if cache dir is writable by attacker (CWE-502) |
| B5 | `tracing.py` | Writes to `logs/traces.json` unconditionally | Crashes on Vercel/Lambda read-only filesystem |
| B6 | `main_processor.py:859` | `_convert_to_case_analysis_result()` return value discarded | Either dead code or missing assignment |
| B7 | `document_processor.py` | Custom `ValidationError` shadows Pydantic's `ValidationError` | Pydantic errors silently uncaught in downstream code |

### Medium Bugs

| # | Location | Bug | Impact |
|---|----------|-----|--------|
| B8 | `json_processing_service.py:1099` | Log says "using gpt-5.2" but code uses "gpt-5.4" | Misleading diagnostics |
| B9 | `main_processor.py:1423` | `get_settings()` called O(N^2) times in duplicate detection loop | Performance degradation with many documents |
| B10 | `json_processing_service.py:1558` | `from src.legal_portal...` import attempt before correct import | Unnecessary ImportError logged in some environments |
| B11 | `json_processing_service.py:1191` | Hard-coded phone `"(505) 555-0199"` uses fictitious 555 exchange | Invalid phone number in generated letters for NM |
| B12 | `documents.py:390-499` | Three near-identical `do_google_ocr()` closures copy-pasted | Divergence risk — updating one misses the others |
| B13 | `frontend: new/+page.svelte:62` | Uses `localStorage.getItem('supabase_access_token')` instead of `getSecureSession()` | Auth will fail silently; inconsistent with all other API calls |
| B14 | `analysis_core.py:249` | `if 'processed' in dir()` to check local variable existence | Fragile, non-standard pattern |
| B15 | `main.py:121` | Two overlapping exception handlers registered | `AppError` handling order depends on registration sequence |
| B16 | `progress_manager.py:139,146` | JSON parsed twice identically | Wasteful; first parse result unused |

### Security Issues

| # | Location | Issue | Severity |
|---|----------|-------|----------|
| S1 | `cache_manager.py` | Pickle deserialization (CWE-502) | HIGH |
| S2 | `chat_routes.py` | Missing case ownership check on streaming endpoint | MEDIUM |
| S3 | `health.py` | Exposes missing env var names to unauthenticated callers | LOW |
| S4 | `corpus.py` | No authentication on legal corpus endpoints | LOW |
| S5 | `profile.py` | Logs PII-adjacent data (blacklist contents) at INFO level | LOW |

---

## Step 4 — Technical Debt

### 4.1 Dead Code / Stub Files

**34 importlib stub files** in `src/legal_portal/services/` (flat level). Every one follows this pattern:

```python
"""Stub — real code moved to services/<subdir>/<file>.py."""
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("legal_portal.services.<subdir>.<file>")
_sys.modules[__name__] = _real
```

These exist for backward compatibility from the refactor. They add import indirection and confuse new developers.

**Files to remove (34 stubs):**
- `services/chunk_service.py`, `services/chunk_state_manager.py`, `services/content_extraction_service.py`
- `services/content_formatting_service.py`, `services/content_generation_service.py`, `services/corpus_coverage_service.py`
- `services/demand_letter_service.py`, `services/document_formatter.py`, `services/document_quality_validator.py`
- `services/document_registry_service.py`, `services/fallback_generation_service.py`, `services/file_compression_service.py`
- `services/gap_analysis_service.py`, `services/group_quality_metrics.py`, `services/group_summarizer.py`
- `services/json_processing_service.py`, `services/letter_quality_lint_service.py`, `services/letter_review_service.py`
- `services/letter_strategy_service.py`, `services/letter_validation_service.py`, `services/main_processor.py`
- `services/multi_stage_analyzer.py`, `services/progress_manager.py`, `services/qa_service.py`
- `services/recommendation_letter_service.py`, `services/statute_recommendation_service.py`, `services/statute_validation_service.py`
- `services/template_rendering_service.py`, `services/text_processing_service.py`, `services/case_chat_service.py`
- `services/citation_tracking_service.py`, `services/clio_context_builder.py`, `services/clio_data_transformer.py`
- `services/deadline_extraction_service.py`

**Other dead code:**
- `utils/helpers.py: ProgressTracker` — Streamlit-specific code; app is FastAPI/SvelteKit
- `check_gap_analysis.py` — Root-level debug script
- `debug_signature_evidence.py` — Root-level debug script
- `=2.0.0` — Garbage file from a bad pip install
- `core/data_models.py` vs `core/models/__init__.py` — Overlapping re-exports
- `api/routes/analysis.py` — Pure wildcard re-export shim (31 lines)

### 4.2 Duplicate Logic

| Duplication | File A | File B | Resolution |
|-------------|--------|--------|------------|
| Jurisdiction config maps | `main_processor.py:268` (`JURISDICTION_CITATION_MAP`) | `json_processing_service.py:281` (`JURISDICTION_CONFIG`) | Consolidate to `config/jurisdictions.py` |
| Document instrument patterns | `main_processor.py` (`_SIGNATURE_INSTRUMENT_HINT_PATTERNS`) | `json_processing_service.py` (`_DOCUMENT_INSTRUMENT_HINT_PATTERNS`) | Consolidate to shared constants |
| Pricing rates | `cost_calculator.py` | `cost_estimator.py` | Single source of truth |
| Cost session logic | `cost_session_manager.py` | `cost_exporter.py` | Merge overlapping functions |
| Clio rate limiting | `api/utils/content_extractor.py` | `api/services/clio_client.py` | Single rate limiter |
| OCR fallback chain | `documents.py:390-499` | Copy-pasted 3 times in same file | Extract to single function |
| Boolean-to-string defense | `json_processing_service.py` | Repeated in adaptive + streaming methods | Extract to decorator |

### 4.3 Overly Complex Files

| File | Lines | Problem |
|------|-------|---------|
| `api/routes/analysis_core.py` | 2,940 | Business logic in route layer |
| `api/routes/documents.py` | 2,857 | OCR orchestration, extraction pipeline in routes |
| `services/analysis/main_processor.py` | 2,358 | `process_case_documents()` is 800+ lines |
| `services/analysis/gap_analysis_service.py` | 2,355 | Map-reduce + dedup + batch merge in one file |
| `services/shared/json_processing_service.py` | 2,267 | Misnamed; actually the letter generation engine |
| `api/routes/cases.py` | 2,070 | Case CRUD + Clio import + document management |
| `services/documents/file_processors/pdf_processor.py` | 2,026 | PDF extraction with multiple fallback chains |
| `api/routes/letter_routes.py` | 1,863 | Letter generation orchestration in routes |
| `api/routes/gap_routes.py` | 1,576 | Gap analysis logic in routes |
| `core/ai_analyzer.py` | 1,781 | AI prompt construction + analysis |
| `api/routes/clio.py` | 1,414 | Full Clio integration in one route file |
| `api/routes/_analysis_helpers.py` | 1,072 | Models + helpers + DB wrappers mixed |
| `utils/helpers.py` | 1,091 | Grab-bag of unrelated utilities |

### 4.4 Experimental / Abandoned Code

- `services/ocr/` — Standalone OCR microservice; unclear if deployed
- `scripts/ai_letter_improvement_loop.py` — Experimental AI improvement loop
- `scripts/backfill_*.py` — One-time migration scripts
- `scripts/diagnose_document_registry.py` — One-time diagnostic
- `presentation/` — Slide deck (not application code)
- `notebooklm_sources/` — Marketing content
- `florida_legal_corpus/`, `new_mexico_legal_corpus/` — Static corpus data (should be external)
- `.archive/phase1/` — Old application code

---

## Step 5 — Architecture Problems

### 5.1 Business Logic in Routes

The most severe architectural issue. Route files total **15,280 lines** and contain:
- Document download, extraction, and OCR orchestration (`documents.py`)
- Full analysis pipeline orchestration (`analysis_core.py`)
- Letter generation and streaming (`letter_routes.py`)
- Gap analysis computation (`gap_routes.py`)
- Clio OAuth + import flow (`clio.py`)
- Email deduplication, artifact generation, identity resolution (`_analysis_helpers.py`)

**Fix:** Extract service-layer classes for each domain. Routes should only handle HTTP concerns (request parsing, response formatting, auth).

### 5.2 Misnamed Core Service

`JsonProcessingService` (2,267 lines) is the primary **letter generation engine**. It:
- Constructs prompts with case context
- Calls OpenAI for letter generation
- Converts markdown to HTML
- Handles gap analysis integration in letters
- Supports streaming and non-streaming modes

It should be renamed `LetterGenerationService` or split into focused services.

### 5.3 Synchronous HTTP in Async Context

`clio_client.py` uses the synchronous `requests` library with `time.sleep()` for rate limiting. In a FastAPI async context, this blocks the event loop and degrades throughput for all concurrent requests. Should use `httpx.AsyncClient`.

### 5.4 No Async Job Queue

The analysis pipeline (`process_case_documents`) runs synchronously within a Vercel serverless function, constrained by Vercel's timeout limits. The progress system works around this with SSE heartbeats and stall detection. This is the #1 scaling bottleneck and the reason you need async job queues.

### 5.5 Unclear Service Boundaries

```
Current (tangled):                  Target (clean):
main_processor ─────┐              analysis_orchestrator
  ├── imports from   │                ├── document_pipeline
  │   routes layer! ◄┘                ├── synthesis_service
  ├── json_proc_svc                   ├── letter_service
  ├── gap_analysis                    └── gap_service
  └── multi_stage
                                    document_pipeline
json_processing_svc                   ├── extraction
  ├── letter gen                      ├── validation
  ├── markdown/HTML                   ├── grouping
  └── gap integration                 └── registry
```

### 5.6 Dual Config Systems

- `config/default.py` — Pydantic `Settings` class (correct approach)
- `config/config_manager.py` — JSON-based `ConfigManager` (legacy)
- Env vars also read via raw `os.getenv()` in 10+ files, bypassing Settings

### 5.7 Port/Path Inconsistencies

| Source | Port | Module Path |
|--------|------|-------------|
| `run_app.py` | 8000 | `src.legal_portal.api.main:app` |
| `Makefile` | 8000 | `api.index:app` |
| `Dockerfile` | 8080 | `legal_portal.api.main:app` |
| `Dockerfile.backend` | 8080 | `src.legal_portal.api.main:app` |
| `default.py Settings` | 8501 | N/A |

---

## Step 6 — Documentation Audit

### Current State: ~280+ markdown files

### Proposed Actions

**KEEP (18 files):**
- `docs/README.md`, `docs/SETUP.md`, `docs/API.md`, `docs/TESTING.md`
- `docs/AUTHENTICATION.md`, `docs/HALLUCINATION_PREVENTION.md`
- `docs/FULL_DOCUMENT_CONTENT_ARCHITECTURE.md`
- `docs/developer/ARCHITECTURE.md`, `docs/developer/SECURITY.md`
- `docs/developer/DEBUG_GUIDE.md`, `docs/developer/PERFORMANCE.md`
- `docs/features/CLIO_INTEGRATION.md`, `docs/features/LETTER_GENERATION.md`
- `docs/user/AUTO_FILL_LEGAL_ISSUE_USER_GUIDE.md`, `docs/user/README.md`
- `docs/deployment/` files
- `README.md` (root)
- `REFACTOR_README.md` (root — update or merge into README)

**UPDATE (3 files):**
- `docs/API.md` — Verify endpoints match current routes
- `docs/PLAYWRIGHT.md` — No actual E2E tests exist yet
- `release-notes.md` — Update or archive

**ARCHIVE (compress to tarball):**
- `docs/archive/` — 221 files → `docs/archive.tar.gz`
- `docs/plans/` — 18 completed plan files → `docs/archive/plans.tar.gz`
- `memory-bank/archive/` — 39 files → compress or delete

**DELETE:**
- `memory-bank/archive/` — Superseded 2025-08-11 snapshots
- `notebooklm_sources/` — Marketing content, not dev artifacts
- `docs/superpowers/` — Untracked, evaluate before commit
- `docs/plans/baselines/` — Evaluate if still needed

### Target Structure

```
docs/
├── README.md                    # Documentation hub
├── SETUP.md                     # Getting started
├── API.md                       # API reference
├── TESTING.md                   # Test guide
├── AUTHENTICATION.md            # Auth flow
├── developer/
│   ├── ARCHITECTURE.md          # System architecture
│   ├── SECURITY.md              # Security practices
│   ├── DEBUG_GUIDE.md           # Debugging guide
│   └── PERFORMANCE.md           # Performance guide
├── features/
│   ├── CLIO_INTEGRATION.md      # Clio integration
│   ├── LETTER_GENERATION.md     # Letter pipeline
│   ├── HALLUCINATION_PREVENTION.md
│   └── FULL_DOCUMENT_CONTENT_ARCHITECTURE.md
├── deployment/
│   └── [deployment docs]
├── user/
│   └── [user-facing docs]
└── archive.tar.gz               # Compressed historical docs
```

---

## Step 7 — Naming and Consistency

### Inconsistent Naming Patterns

| Issue | Examples | Proposed Standard |
|-------|----------|-------------------|
| Service suffix inconsistency | `JsonProcessingService` does letter gen; `document_formatter` has no Service suffix | All service classes: `XxxService` |
| File naming | `_analysis_helpers.py` (underscore prefix), `chat_routes.py` vs `letter_routes.py` vs `gap_routes.py` | Consistent `xxx_routes.py` for routes |
| Model location | Models in `core/models/`, `core/data_models.py`, AND `_analysis_helpers.py` | All models in `core/models/` |
| Processor vs Service | `document_processor.py` in core, `main_processor.py` in services | Reserve "processor" for data transformation, "service" for business logic |
| Module vs class naming | `gap_analysis_service.py` → `GapAnalysisService` (match), but `json_processing_service.py` → `JsonProcessingService` (semantic mismatch) | File name should match primary class purpose |
| camelCase vs snake_case | Python code is consistently snake_case. Frontend mixes. | Python: snake_case. TS: camelCase for vars, PascalCase for types |

### Terminology Inconsistencies

| Concept | Used As | Standardize To |
|---------|---------|----------------|
| Letter output | "findings letter", "demand letter", "recommendation letter", "client letter" | "findings letter" (primary), "demand letter" (specific type) |
| Document text | "content", "extracted_text", "text", "raw_text" | "extracted_text" for raw, "content" for processed |
| Analysis result | "case_analysis", "analysis_result", "processing_result", "structured_summary" | "analysis_result" for final, "structured_summary" for intermediate |

---

## Step 8 — Folder Structure Problems

### Current Problems

1. **34 stub files** in `services/` alongside the actual subdirectory structure
2. **Business logic in `api/routes/`** — routes are 15K lines total
3. **`utils/helpers.py`** is a 1,091-line grab-bag
4. **Prompts stored in `src/legal_portal/prompts/`** — fine, but no clear ownership
5. **Root-level debris**: `check_gap_analysis.py`, `debug_signature_evidence.py`, `=2.0.0`, `logo_Bernhardt Riley-05.png`, `PageSpeed Insights.pdf`
6. **Multiple test data dirs**: `test_data/`, `test_data_old/`, `test_data_v2/`, `tests/data/`, `tests/docs/test_data/`
7. **Legal corpus at root**: `florida_legal_corpus/`, `new_mexico_legal_corpus/`

### Proposed Target Structure

```
src/legal_portal/
├── api/
│   ├── main.py                 # App factory only
│   ├── dependencies.py         # DI container
│   ├── middleware/              # Error handling, retry
│   └── routes/                 # Thin HTTP handlers only
│       ├── analysis.py         # ~200 lines max
│       ├── cases.py            # ~200 lines max
│       ├── documents.py        # ~200 lines max
│       ├── letters.py          # ~200 lines max
│       ├── gaps.py             # ~200 lines max
│       ├── clio.py             # ~200 lines max
│       ├── chat.py
│       ├── health.py
│       └── [other thin routes]
├── config/
│   ├── settings.py             # Single Pydantic Settings (rename from default.py)
│   ├── jurisdictions.py        # NEW: consolidated jurisdiction config
│   └── constants.py            # NEW: token limits, thresholds, model names
├── core/
│   ├── models/                 # All Pydantic models
│   ├── exceptions.py
│   └── interfaces.py           # NEW: service interfaces/protocols
├── services/
│   ├── analysis/               # KEEP: main processor, multi-stage, gap, corpus
│   ├── documents/              # KEEP: file processors, chunking, extraction
│   ├── letters/                # KEEP: generation, review, validation, formatting
│   ├── shared/                 # KEEP: citations, progress, QA, statutes
│   ├── grouping/               # KEEP: document grouping
│   ├── integrations/           # KEEP: Clio integration
│   └── [NO MORE FLAT STUBS]
├── utils/
│   ├── logging.py              # Consolidate 6 logging modules
│   ├── cost_tracking.py        # Consolidate 4 cost modules
│   ├── security.py
│   ├── openai_client.py
│   ├── validators.py
│   └── [focused utility modules]
├── prompts/                    # AI prompt templates
└── assets/                     # Jinja2 templates

scripts/
├── dev/                        # Local development
│   ├── start.sh
│   └── stop.sh
├── deploy/                     # Deployment
│   ├── deploy.sh
│   └── vercel_build.sh
├── testing/                    # Test utilities
└── maintenance/                # One-time scripts (archive candidates)

tests/
├── api/                        # Route-level tests
├── unit/                       # Service + model tests
├── integration/                # DB + workflow tests
├── regression/                 # Baseline comparison tests
├── fixtures/                   # Shared test data
└── conftest.py

docs/                           # Clean documentation (see Step 6)
```

---

## Step 9 — Dependency and Configuration Cleanup

### Unused / Redundant Dependencies

Review these for removal (need to verify with actual import analysis):
- `streamlit` — Referenced only in dead code (`helpers.py ProgressTracker`)
- Multiple Dockerfile configurations installing different package sets
- `setup.py` declares minimal deps that differ from `requirements.txt`

### Configuration Duplication

| Issue | Fix |
|-------|-----|
| `setup.py` + `pyproject.toml` both define package metadata | Remove `setup.py`; use `pyproject.toml` only |
| `python_requires=">=3.8"` in both; code uses 3.10+ syntax | Update to `>=3.11` |
| 3 Dockerfiles | Keep `Dockerfile.backend` (multi-stage) + `Dockerfile.frontend`. Remove generic `Dockerfile` |
| `Makefile SRC=app` | Fix to `SRC=src/legal_portal` |
| 4 different default ports | Standardize to 8080 everywhere |
| Env vars in `os.getenv()` bypassing Settings | Migrate all to Pydantic Settings |

### Environment Variable Sprawl

These env vars are read via raw `os.getenv()` and should be added to the Settings class:
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (in `dependencies.py`)
- `SUPABASE_ARTIFACT_BUCKET`, `ANALYSIS_ARTIFACT_PREFIX`, `ANALYSIS_ARTIFACT_URL_TTL` (in `analysis_core.py`)
- `CORS_ORIGINS`, `VERCEL_URL` (in `main.py`)
- `VERCEL`, `AWS_LAMBDA_FUNCTION_NAME` (in `metrics.py`, `audit_logger.py`)

### CI/CD Cleanup

| Workflow | Action |
|----------|--------|
| `ci.yml` | DELETE — stale Python 3.9 matrix, overlaps with `test.yml` |
| `test.yml` | KEEP — comprehensive, modern |
| `ci-cd.yml` | EVALUATE — may overlap with `test.yml` |
| `lint.yml` | DELETE if `test.yml` includes lint |
| `startup-tests.yml` | DELETE if `test.yml` includes startup |
| `gcp-deploy.yml` | UPDATE — fix `/_stcore/health` endpoint (Streamlit artifact) |

---

## Step 10 — Testing Coverage

### What Is Covered (Good)

- Document processor (unit + extended)
- Letter services (strategy, validation, quality lint, polish)
- Document grouping (models, grouping, context, quality, summarizer)
- Gap analysis (normalize, map-reduce, signature reconciliation)
- Multi-stage analyzer
- Citation tracking
- Frontend: SSE/polling clients, verification handlers, analysis stream utils, document sorting, blacklist

### Coverage Gaps (Critical)

| Area | Status | Priority |
|------|--------|----------|
| Analysis pipeline end-to-end | No integration test | HIGH |
| Letter generation end-to-end | Only baseline regression test | HIGH |
| Clio import flow | No tests | HIGH |
| Chat functionality | 1 backend test, 0 frontend tests | MEDIUM |
| Document upload → extraction pipeline | Partial | MEDIUM |
| Frontend: Case detail page (1,678 lines) | No tests | MEDIUM |
| Frontend: Results workspace (1,361 lines) | No tests | MEDIUM |
| E2E/Playwright | CI defines job but no test files exist | LOW (foundational) |
| Gap resolution refresh | No frontend tests | LOW |

### Fragile Tests

- **`tests/api/test_cases.py`**: Assertions accept status codes `200, 201, 404, 500` — too permissive, masks failures
- **`tests/api/test_analysis.py`**: Same pattern with `200, 201, 202, 404`
- **`conftest.py`**: Deep MagicMock chains (`mock_table.select.return_value = mock_table`) silently return wrong results
- **Root-level test files** (`test_citation_removal.py`, `test_gap_normalize.py`, etc.) are orphaned outside standard directories

### Recommendations

1. Tighten API test assertions to expect specific status codes
2. Move orphaned root-level test files into `tests/unit/`
3. Add integration test for analysis pipeline (mock OpenAI, real Supabase)
4. Add integration test for Clio import flow
5. Write Playwright E2E tests for the critical user path: upload → analyze → view results → generate letter

---

## Step 11 — Refactoring Roadmap

### Phase 1 — Critical Bug Fixes (1-2 days)

**Risk: LOW | Complexity: LOW**

| Task | File | Change |
|------|------|--------|
| Fix `processing_time` → `processing_time_seconds` | `main_processor.py:798` | Rename kwarg |
| Fix `get_optional_user` HTTPBearer | `dependencies.py` | Add `auto_error=False` |
| Add case ownership check to `stream_chat_response` | `chat_routes.py` | Add ownership verification |
| Replace `pickle.load` with JSON | `cache_manager.py` | Use `json.load` or `msgpack` |
| Add serverless guard to tracing | `tracing.py` | Check `VERCEL` env var |
| Fix localStorage auth in new case page | `frontend/.../new/+page.svelte:62` | Use `getSecureSession()` |

**Validation:** Run full test suite. Manual test of chat streaming and new case creation.

### Phase 2 — Remove Dead Code & Stubs (1-2 days)

**Risk: MEDIUM | Complexity: LOW**

| Task | Files | Change |
|------|-------|--------|
| Remove 34 stub shim files | `services/*.py` (flat level) | Delete files |
| Update all imports to use subdirectory paths | Grep for old import paths | Find and replace |
| Remove root-level debug scripts | `check_gap_analysis.py`, `debug_signature_evidence.py` | Delete or move to `scripts/` |
| Remove `=2.0.0` garbage file | Root | Delete |
| Remove Streamlit `ProgressTracker` from helpers.py | `utils/helpers.py` | Delete class |
| Archive one-time scripts | `scripts/backfill_*.py`, `scripts/diagnose_*.py` | Move to `scripts/maintenance/archive/` |
| Remove or fix discarded `_convert_to_case_analysis_result` call | `main_processor.py:859` | Use return value or remove |

**Validation:** `scripts/check_import_rules.py` + full test suite + `scripts/validate_refactor.sh`

### Phase 3 — Documentation Cleanup (1 day)

**Risk: LOW | Complexity: LOW**

| Task | Change |
|------|--------|
| Compress `docs/archive/` to tarball | `tar czf docs/archive.tar.gz docs/archive/ && rm -rf docs/archive/` |
| Move completed plans to archive | `docs/plans/*.md` → compressed |
| Delete `memory-bank/archive/` | 39 superseded files |
| Delete `notebooklm_sources/` | Marketing content |
| Update `docs/API.md` | Verify against current routes |
| Update `docs/PLAYWRIGHT.md` | Note: no tests yet, or remove |
| Merge `REFACTOR_README.md` into `README.md` | Consolidate |

**Validation:** Links in `docs/README.md` resolve correctly.

### Phase 4 — Configuration Consolidation (1-2 days)

**Risk: MEDIUM | Complexity: MEDIUM**

| Task | Change |
|------|--------|
| Migrate all `os.getenv()` to Pydantic Settings | Add fields to `default.py` |
| Remove `setup.py` | Use `pyproject.toml` only |
| Fix Python version requirement | `>=3.11` |
| Consolidate Dockerfiles | Keep `Dockerfile.backend` + `Dockerfile.frontend`, delete `Dockerfile` |
| Fix `Makefile SRC` variable | `SRC=src/legal_portal` |
| Standardize port to 8080 | Update `run_app.py`, `Makefile` |
| Remove `config/config_manager.py` if unused | Check for references first |
| Create `config/jurisdictions.py` | Consolidate `JURISDICTION_CITATION_MAP` + `JURISDICTION_CONFIG` |
| Create `config/constants.py` | Centralize token limits, model names, thresholds |

**Validation:** `make run` works. Docker build succeeds. All tests pass.

### Phase 5 — CI/CD Cleanup (0.5 days)

**Risk: LOW | Complexity: LOW**

| Task | Change |
|------|--------|
| Delete `ci.yml` | Overlaps with `test.yml` |
| Evaluate/delete `lint.yml`, `startup-tests.yml`, `ci-cd.yml` | If `test.yml` covers them |
| Fix `gcp-deploy.yml` health check URL | Replace `/_stcore/health` with `/api/health` |
| Update Python version matrix | 3.11 + 3.13 |

**Validation:** CI/CD runs green on a test PR.

### Phase 6 — Extract Business Logic from Routes (3-5 days)

**Risk: HIGH | Complexity: HIGH**

This is the largest and most important refactoring phase.

| Route File | Lines | Extract To |
|------------|-------|------------|
| `analysis_core.py` (2,940) | Document download, dedup, artifact gen | `services/analysis/analysis_orchestrator.py` |
| `documents.py` (2,857) | OCR orchestration, extraction | `services/documents/upload_service.py` |
| `cases.py` (2,070) | Clio import, document management | `services/integrations/clio_import_service.py` |
| `letter_routes.py` (1,863) | Letter generation orchestration | Already in services — extract remaining logic |
| `gap_routes.py` (1,576) | Gap computation | Already in services — extract remaining logic |
| `clio.py` (1,414) | OAuth, matter search | `services/integrations/clio_oauth_service.py` |
| `_analysis_helpers.py` (1,072) | Models, DB helpers | Split: models → `core/models/`, helpers → `services/` |

**Target:** Each route file should be <300 lines. Routes handle only:
- Request parsing/validation
- Auth/permission checks
- Delegation to service
- Response formatting

**Validation:** Full test suite. Manual smoke test of all user-facing flows.

### Phase 7 — Service Consolidation & Renaming (2-3 days)

**Risk: MEDIUM | Complexity: MEDIUM**

| Task | Change |
|------|--------|
| Rename `JsonProcessingService` → `LetterGenerationService` | Update all references |
| Consolidate `document_formatter.py` + `content_formatting_service.py` | Merge into `content_formatting_service.py` |
| Consolidate cost utils | Merge `cost_calculator.py` + `cost_estimator.py` + `cost_session_manager.py` + `cost_exporter.py` → `cost_tracking.py` |
| Consolidate logging | Merge 6 logging modules → 2 (structured + audit) |
| Convert `clio_client.py` to async | Replace `requests` with `httpx.AsyncClient` |
| Remove duplicate instrument hint patterns | Single source in shared constants |

**Validation:** Full test suite. Performance benchmark before/after for cost tracking.

### Phase 8 — File Splitting & Modularization (2 days)

**Risk: MEDIUM | Complexity: MEDIUM**

| File | Lines | Split Into |
|------|-------|------------|
| `main_processor.py` (2,358) | Decompose `process_case_documents()` into stage functions | Same file, better structure |
| `gap_analysis_service.py` (2,355) | Map-reduce core + dedup + batch merge | 2-3 focused modules |
| `json_processing_service.py` (2,267) | Prompt building + OpenAI interaction + markdown conversion | 3 modules |
| `pdf_processor.py` (2,026) | Text extraction + OCR fallback + page analysis | 2-3 modules |
| `utils/helpers.py` (1,091) | Split by responsibility | Multiple focused utils |

**Validation:** Full test suite.

### Phase 9 — Testing Improvements (2-3 days)

**Risk: LOW | Complexity: MEDIUM**

| Task | Priority |
|------|----------|
| Tighten API test assertions (remove multi-status-code accepts) | HIGH |
| Move orphaned root-level test files to `tests/unit/` | HIGH |
| Add analysis pipeline integration test | HIGH |
| Add Clio import integration test | MEDIUM |
| Write first Playwright E2E test (upload → analyze → letter) | MEDIUM |
| Add frontend tests for case detail page | LOW |
| Consolidate test data dirs (`test_data/`, `test_data_old/`, `test_data_v2/`) | LOW |

**Validation:** Coverage report. CI green.

---

## Step 12 — Bad Design Decisions

### 12.1 Synchronous Long-Running Requests

**Problem:** The analysis pipeline (`process_case_documents`) runs synchronously in a Vercel serverless function. Vercel has a ~800s timeout for pro plans. The system works around this with SSE heartbeats, stall detection, and chunk-based progress — but this is a fragile architecture.

**Risk:** Large cases with many documents can exceed the timeout. The workaround (heartbeats keeping the connection alive) is fragile and breaks on network interruptions.

**Fix:** Implement an async job queue (e.g., Celery + Redis, or Supabase Edge Functions + pg_cron, or a dedicated Cloud Run worker). The API should return a job ID immediately, and the client polls or subscribes via SSE for updates.

### 12.2 Tightly Coupled Pipeline

**Problem:** `main_processor.py` orchestrates the entire analysis pipeline in a single function with sequential stages. Each stage is coupled to the previous stage's output format. Adding a new stage requires modifying the 800-line orchestrator.

**Risk:** Any change to one stage risks breaking downstream stages. Testing individual stages in isolation is difficult.

**Fix:** Define a `PipelineStage` protocol with `input_type`, `output_type`, and `execute()`. Compose stages declaratively. Each stage becomes independently testable.

### 12.3 Hidden Global State

**Problem:** Module-level singletons (`get_compression_service()`, `@lru_cache` on service factories), OpenAI client instances, and `get_settings()` caching create implicit global state that is invisible to callers and difficult to test.

**Risk:** State leaks between tests. Stale configuration if settings change. Difficult to run parallel tests.

**Fix:** Use explicit dependency injection. FastAPI's `Depends()` system is already available. Create service factories in `dependencies.py` that inject configuration.

### 12.4 Brittle Document Parsing

**Problem:** PDF processing (`pdf_processor.py`, 2,026 lines) has multiple nested fallback chains: PyMuPDF → PyPDF2 → OCR → Google Vision. Each fallback path has slightly different error handling and output formatting.

**Risk:** Silent data loss if a fallback path extracts partial content. Difficult to diagnose which extraction method was used.

**Fix:** Implement a strategy pattern with explicit `ExtractionResult` that includes: method used, confidence score, warnings, and extracted text. Log the chosen strategy for every document.

### 12.5 Architecture Blocking Scaling

**Problem:** The system is designed as a monolithic FastAPI app deployed to Vercel. There's no separation between the lightweight API layer (case CRUD, auth) and the compute-heavy analysis pipeline. Both share the same deployment, the same memory, and the same timeout constraints.

**Risk:** A heavy analysis job starves lightweight API requests. Cannot scale analysis workers independently from the API.

**Fix:** Split into:
1. **API service** (Vercel/Cloud Run) — Case CRUD, auth, file upload, job submission
2. **Analysis worker** (Cloud Run Jobs / dedicated compute) — Pipeline execution
3. **Shared state** (Supabase) — Job status, results, progress

---

## Step 13 — Summary

### Priority Matrix

| Phase | Risk | Effort | Impact | Priority |
|-------|------|--------|--------|----------|
| 1. Critical Bug Fixes | LOW | 1-2d | HIGH | **P0** |
| 2. Remove Dead Code & Stubs | MEDIUM | 1-2d | MEDIUM | **P1** |
| 3. Documentation Cleanup | LOW | 1d | LOW | **P1** |
| 4. Configuration Consolidation | MEDIUM | 1-2d | MEDIUM | **P1** |
| 5. CI/CD Cleanup | LOW | 0.5d | LOW | **P2** |
| 6. Extract Logic from Routes | HIGH | 3-5d | HIGH | **P2** |
| 7. Service Consolidation | MEDIUM | 2-3d | MEDIUM | **P3** |
| 8. File Splitting | MEDIUM | 2d | MEDIUM | **P3** |
| 9. Testing Improvements | LOW | 2-3d | HIGH | **P3** |

**Total estimated effort: 14-21 days**

### Pre-requisites for Async Job Queue Work

Before implementing async job queues / worker pipelines, complete at minimum:
- Phase 1 (bug fixes)
- Phase 2 (dead code removal)
- Phase 4 (config consolidation)
- Phase 6 (extract business logic from routes) — this is critical because the route-embedded logic needs to be callable from a worker context

### Key Metrics to Track

- Route file line counts (target: <300 each)
- Number of stub files (target: 0)
- Test assertion specificity (no multi-status-code accepts)
- `os.getenv()` calls outside Settings (target: 0)
- Documentation file count (target: <30 active files)
