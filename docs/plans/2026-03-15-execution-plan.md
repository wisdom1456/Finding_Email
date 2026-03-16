# Execution Plan: Codebase Cleanup & Stabilization

**Date:** 2026-03-15
**Status:** Ready for Review
**Scope:** All findings validated against actual code

---

## Executive Summary

Every finding from the original audit has been re-validated against the live codebase. All critical bugs are confirmed. The stub count is 33 (not 34 — one fewer than originally reported). The route files contain 13,792 lines of embedded business logic across 7 files. Model name strings are scattered across 23 files. 55 `os.getenv` calls bypass the centralized Settings class.

This plan converts those findings into **12 PR-sized work units** that can be implemented sequentially. Each PR is designed to be independently mergeable, behavior-preserving, and testable.

---

## Validated Findings

### 1. Critical Bugs — ALL 8 CONFIRMED

| ID | Location | Issue | Severity |
|----|----------|-------|----------|
| B1 | `main_processor.py:797` | `processing_time=` should be `processing_time_seconds=` | Medium (silent data loss, not crash — Pydantic v2 ignores extra fields) |
| B2 | `dependencies.py:20,146` | `get_optional_user` depends on `HTTPBearer()` with `auto_error=True`; unauthenticated requests always 403 | High |
| B3 | `chat_routes.py:40-114` | `stream_chat_response` does not verify case ownership; non-streaming version does | High (authz bypass) |
| B4 | `cache_manager.py:81,96` | `pickle.loads()` and `pickle.load()` for cache deserialization | Medium (CWE-502) |
| B5 | `tracing.py:72-78` | Writes to `logs/traces.json` without checking for serverless environment | Medium |
| B6 | `main_processor.py:859` | `_convert_to_case_analysis_result()` return value discarded | Low (wasted computation) |
| B7 | `document_processor.py:50` | Custom `ValidationError` shadows Pydantic's `ValidationError` | Low-Medium |
| B8 | `frontend/new/+page.svelte:62` | `localStorage.getItem('supabase_access_token')` instead of `getSecureSession()` | Medium-High |

### 2. Dead Code / Stubs — CONFIRMED

- **33 importlib stub files** in `services/` (flat level), not 34
- **91 imports** currently route through stub paths (48 in src, 43 in tests)
- **8 imports** already use direct subdirectory paths
- **5 root-level debris files**: `check_gap_analysis.py`, `debug_signature_evidence.py`, `=2.0.0`, `logo_Bernhardt Riley-05.png`, `PageSpeed Insights.pdf`
- **`ProgressTracker`** in `helpers.py` — Streamlit code, zero importers
- **`analysis.py`** route shim — 6 wildcard re-exports

### 3. Route File Business Logic — CONFIRMED

| File | Lines | Largest Embedded Logic Block |
|------|-------|------------------------------|
| `analysis_core.py` | 2,940 | `process_case_background()` — 720 lines of pipeline orchestration |
| `documents.py` | 2,857 | `upload_document()` — 520 lines, `_trigger_extraction_inner()` — 690 lines |
| `cases.py` | 2,070 | `import_clio_documents_helper()` — 680 lines |
| `letter_routes.py` | 1,863 | `stream_findings_letter()` — 580 lines, `generate_letter()` — 550 lines |
| `gap_routes.py` | 1,576 | `_run_gap_analysis()` + batch construction — 400 lines |
| `clio.py` | 1,414 | `import_clio_data()` — 480 lines, `sync_clio_matter()` — 330 lines |
| `_analysis_helpers.py` | 1,072 | `_resolve_letter_identity_context()` — 130 lines + 200 lines of models |

### 4. Duplicate Configuration — CONFIRMED

| Duplication | Locations | Status |
|-------------|-----------|--------|
| Jurisdiction config maps | `main_processor.py:268` + `json_processing_service.py:281` | Verbatim duplicate |
| Instrument hint patterns | `main_processor.py:103` + `_analysis_helpers.py:165` + `json_processing_service.py:300` | 3 copies, 2 identical + 1 variant |
| Pricing rates | `cost_calculator.py:28` + `cost_estimator.py:23` | 6 shared keys identical; calculator has extra GPT-5.2 entry |
| Model name strings | 23 files, ~100+ occurrences | `config/default.py` defines `openai_model` setting but almost no code reads it |
| `os.getenv` bypassing Settings | 55 calls across 15 files | 26+ env vars not in Settings class |

### 5. CI/CD Workflows — CONFIRMED

| Capability | Duplicated Across |
|------------|-------------------|
| Ruff linting | ci.yml, ci-cd.yml, test.yml, lint.yml (4x) |
| Bandit security scan | ci.yml, ci-cd.yml, lint.yml (3x) |
| pytest execution | ci.yml, ci-cd.yml, test.yml, lint.yml (4x) |
| pip-audit / Safety | ci.yml, ci-cd.yml, lint.yml (3x) |

ci.yml tests Python 3.9-3.11 matrix. Code requires 3.10+ minimum (12 files use `str | None` without `from __future__ import annotations`).

### 6. Dockerfiles — CONFIRMED

| Conflict | `Dockerfile` | `Dockerfile.backend` |
|----------|-------------|---------------------|
| App module | `legal_portal.api.main:app` | `src.legal_portal.api.main:app` |
| PYTHONPATH | `/app:/app/src:/app/app` | `/app:/app/src` |
| Build stages | 1 (monolithic) | 2 (builder + production) |
| Dev headers in prod | Yes (gcc, g++) | No (correctly separated) |
| gunicorn installed | No | Yes (but never used in CMD) |

### 7. Oversized Files — CONFIRMED

17 files exceed 1,000 lines. 7 files exceed 2,000 lines. Total: 30,947 lines in oversized files.

### 8. Documentation — CONFIRMED

- `docs/archive/`: 221 files
- `docs/plans/`: 19 files
- `memory-bank/archive/`: 39 files
- `notebooklm_sources/`: 6 files
- Total `.md` files in repo: 1,624

---

## Priority Classification

### P0 — Security / Correctness (Must fix before any feature work)

| ID | Issue | Rationale |
|----|-------|-----------|
| B2 | `get_optional_user` always 403s | Any endpoint using optional auth is broken |
| B3 | Chat streaming missing authorization | Horizontal privilege escalation |
| B4 | Pickle deserialization in cache | CWE-502, arbitrary code execution risk |
| B8 | Frontend localStorage auth bypass | Auth failures for new case creation |

### P1 — Structural Blockers (Block safe development)

| ID | Issue | Rationale |
|----|-------|-----------|
| B1 | ProcessingResult field name | Silent data loss on error-recovery path |
| B5 | Tracing crashes on serverless | Production crashes if tracing decorator is used |
| Stubs | 33 stub files + 91 legacy imports | Import indirection confuses developers, slows onboarding |
| Root debris | 5 misplaced root files | Clutters repo root |
| Config duplication | 55 `os.getenv` calls bypassing Settings | Config drift, untestable |
| Dockerfile conflicts | 2 backend Dockerfiles with conflicting module paths | Deployment confusion |

### P2 — Maintainability (Enable safe future development)

| ID | Issue | Rationale |
|----|-------|-----------|
| Route logic | 13,792 lines of business logic in routes | Blocks route-layer testing, prevents async worker extraction |
| Oversized files | 7 files >2,000 lines | Hard to review, understand, and modify |
| Model name scatter | 23 files with hard-coded model strings | Model upgrade requires touching 23 files |
| CI/CD overlap | 6 workflows with 4x duplication of lint/test | Slow CI, maintenance burden |
| Pricing duplication | 2 files with divergent rate tables | Cost tracking inaccurate for newer models |

### P3 — Cleanup (Nice-to-have improvements)

| ID | Issue | Rationale |
|----|-------|-----------|
| B6 | Discarded return value | Wasted CPU, confusing code |
| B7 | ValidationError naming | Maintenance hazard |
| Documentation | 280+ obsolete markdown files | Repo bloat, search noise |
| Dead code | ProgressTracker, analysis.py shim | Minor clutter |
| Port inconsistency | 4 different default ports | Confusion for new developers |
| Python version claim | `>=3.8` but requires 3.10+ | Misleading metadata |

---

## PR-Based Implementation Plan

### PR-1: Security & Correctness Fixes

**Objective:** Fix all P0 security and correctness bugs.

**Files to modify:**
- `src/legal_portal/api/dependencies.py`
- `src/legal_portal/api/routes/chat_routes.py`
- `src/legal_portal/utils/cache_manager.py`
- `frontend/src/routes/app/cases/new/+page.svelte`
- `src/legal_portal/services/analysis/main_processor.py` (line 797)
- `src/legal_portal/utils/tracing.py`

**Steps:**
1. In `dependencies.py` line 20: create a second HTTPBearer instance `optional_security = HTTPBearer(auto_error=False)`. Update `get_optional_user` signature (line 146) to depend on `optional_security` instead of `security`.
2. In `chat_routes.py`: add `_ensure_case_access(supabase, case_id, user["id"])` at the start of `stream_chat_response`, matching the pattern in `case_chat` (line 126). This requires looking up the `case_id` from the `analysis_id` first — follow the pattern used in the non-streaming version.
3. In `cache_manager.py`: replace `pickle.loads` (line 81) with `json.loads` and `pickle.load` (line 96) with `json.load`. Update the corresponding write paths (`pickle.dumps` → `json.dumps`, `pickle.dump` → `json.dump`). Change file extension from `.pkl` to `.json`. Add a migration: if a `.pkl` file exists, delete it (stale cache is acceptable).
4. In `frontend/.../new/+page.svelte` line 62: replace `localStorage.getItem('supabase_access_token')` with `const { session } = await getSecureSession()` and use `session.access_token`. Add the import if not present.
5. In `main_processor.py` line 797: change `processing_time=` to `processing_time_seconds=`.
6. In `tracing.py`: wrap the file-write block (lines 72-78) in `if not os.getenv("VERCEL"):`.

**Tests to add:**
- Unit test: `get_optional_user` returns `None` when no Bearer token provided
- Unit test: `stream_chat_response` returns 403 when user doesn't own the case
- Unit test: `cache_manager` round-trips data through JSON serialization

**Risk:** LOW. Each fix is isolated. No behavioral changes to happy paths.

**Verification:**
```bash
pytest tests/ -x
# Manual: test chat streaming with a non-owner user
# Manual: test new case creation page without cached token
```

---

### PR-2: Remove Root-Level Debris & Dead Code

**Objective:** Clean up misplaced files and confirmed dead code.

**Files to delete:**
- `check_gap_analysis.py` (root)
- `debug_signature_evidence.py` (root)
- `=2.0.0` (root — garbage file)

**Files to move:**
- `logo_Bernhardt Riley-05.png` → `frontend/static/` or `src/legal_portal/assets/`
- `PageSpeed Insights.pdf` → `docs/archive/` or delete

**Files to edit:**
- `src/legal_portal/utils/helpers.py`: remove `ProgressTracker` class (confirmed zero importers)
- `src/legal_portal/services/analysis/main_processor.py` line 859: remove the discarded `_convert_to_case_analysis_result()` call, or assign its return value if it should be used

**Steps:**
1. Delete the 3 root-level files.
2. Move logo to `frontend/static/`. Delete or archive the PDF.
3. Remove `ProgressTracker` from `helpers.py`.
4. Remove or fix the discarded call at line 859 of `main_processor.py`.

**Risk:** LOW. No behavioral changes. Dead code removal only.

**Verification:**
```bash
pytest tests/ -x
python -c "from legal_portal.utils.helpers import *"  # confirms no import breakage
```

---

### PR-3: Remove Migration Stub Files

**Objective:** Delete 33 importlib stub files and update all 91 import sites to use direct subdirectory paths.

**Files to delete (33 stubs):**
```
src/legal_portal/services/case_chat_service.py
src/legal_portal/services/chunk_service.py
src/legal_portal/services/chunk_state_manager.py
src/legal_portal/services/citation_tracking_service.py
src/legal_portal/services/clio_context_builder.py
src/legal_portal/services/clio_data_transformer.py
src/legal_portal/services/content_extraction_service.py
src/legal_portal/services/content_formatting_service.py
src/legal_portal/services/content_generation_service.py
src/legal_portal/services/corpus_coverage_service.py
src/legal_portal/services/deadline_extraction_service.py
src/legal_portal/services/demand_letter_service.py
src/legal_portal/services/document_formatter.py
src/legal_portal/services/document_quality_validator.py
src/legal_portal/services/document_registry_service.py
src/legal_portal/services/fallback_generation_service.py
src/legal_portal/services/file_compression_service.py
src/legal_portal/services/gap_analysis_service.py
src/legal_portal/services/group_quality_metrics.py
src/legal_portal/services/group_summarizer.py
src/legal_portal/services/json_processing_service.py
src/legal_portal/services/letter_quality_lint_service.py
src/legal_portal/services/letter_review_service.py
src/legal_portal/services/letter_strategy_service.py
src/legal_portal/services/letter_validation_service.py
src/legal_portal/services/main_processor.py
src/legal_portal/services/multi_stage_analyzer.py
src/legal_portal/services/progress_manager.py
src/legal_portal/services/qa_service.py
src/legal_portal/services/recommendation_letter_service.py
src/legal_portal/services/statute_recommendation_service.py
src/legal_portal/services/statute_validation_service.py
src/legal_portal/services/template_rendering_service.py
src/legal_portal/services/text_processing_service.py
```

**Files to edit (~91 import sites):**
Every import of the form:
```python
from legal_portal.services.<module> import X
```
must become:
```python
from legal_portal.services.<subdomain>.<module> import X
```

Mapping (each stub's docstring tells you the target):
- `services.chunk_service` → `services.documents.chunk_service`
- `services.main_processor` → `services.analysis.main_processor`
- `services.json_processing_service` → `services.shared.json_processing_service`
- `services.demand_letter_service` → `services.letters.demand_letter_service`
- `services.gap_analysis_service` → `services.analysis.gap_analysis_service`
- `services.citation_tracking_service` → `services.shared.citation_tracking_service`
- (etc. — each stub file contains the correct target path in its docstring)

**Steps:**
1. Build a mapping dict from each stub's docstring.
2. For each stub path, grep `src/` and `tests/` for imports.
3. Replace each import with the direct path.
4. Run the full test suite after each batch of replacements to catch breakage.
5. Delete all 33 stub files.
6. Run the import validation script: `python scripts/check_import_rules.py`.

**Risk:** MEDIUM. 91 import sites across production and test code. A single missed rename breaks imports. Mitigation: run `python -c "import legal_portal.api.main"` to verify all transitive imports resolve.

**Verification:**
```bash
python -c "from legal_portal.api.main import app"  # transitive import check
pytest tests/ -x
python scripts/check_import_rules.py
python scripts/validate_refactor.sh
```

---

### PR-4: Configuration Consolidation

**Objective:** Establish a single source of truth for all configuration.

**New files to create:**
- `src/legal_portal/config/constants.py` — model names, token limits, thresholds
- `src/legal_portal/config/jurisdictions.py` — consolidated jurisdiction config

**Files to edit:**
- `src/legal_portal/config/default.py` — add 26 missing env vars to Settings class
- `src/legal_portal/services/analysis/main_processor.py` — remove `JURISDICTION_CITATION_MAP`, import from `config.jurisdictions`
- `src/legal_portal/services/shared/json_processing_service.py` — remove `JURISDICTION_CONFIG`, import from `config.jurisdictions`
- `src/legal_portal/api/routes/_analysis_helpers.py` — remove `_SIGNATURE_INSTRUMENT_HINT_PATTERNS`, import from `config.constants`
- All 15 files with `os.getenv` calls — replace with `get_settings().field_name`

**Step 1 — Create `config/constants.py`:**
```python
# Model names
DEFAULT_MODEL = "gpt-5.4"
FAST_MODEL = "gpt-5-mini"
NANO_MODEL = "gpt-5-nano"
LEGACY_MODEL = "gpt-5.2"

# Token limits
PROMPT_MAX_DOC_CHARS = 24_000
MAX_FINDINGS_PROMPT_CHARS = 220_000
MAX_RAW_DOC_TOTAL_CHARS = 50_000

# Instrument hint patterns (consolidated from 3 copies)
INSTRUMENT_HINT_PATTERNS = [...]
```

**Step 2 — Create `config/jurisdictions.py`:**
Merge `JURISDICTION_CITATION_MAP` and `JURISDICTION_CONFIG` into one dict keyed by jurisdiction name.

**Step 3 — Add missing env vars to Settings:**
Add all 26 env vars currently accessed via `os.getenv` to the Pydantic Settings class with appropriate defaults.

**Step 4 — Replace `os.getenv` calls:**
In each of the 15 files, replace raw `os.getenv("X")` with `get_settings().x`.

**Step 5 — Replace hard-coded model strings:**
In each of the 23 files, replace `"gpt-5.4"` with `constants.DEFAULT_MODEL` (or read from Settings where the model is user-configurable).

**Risk:** MEDIUM. Many files touched, but each change is mechanical. Incorrect defaults could change behavior.

**Verification:**
```bash
pytest tests/ -x
# Grep for remaining os.getenv calls (should only be in config/default.py itself):
grep -r "os.getenv" src/legal_portal/ --include="*.py" | grep -v config/default.py | grep -v __pycache__
# Grep for remaining hard-coded model names:
grep -rn '"gpt-5' src/legal_portal/ --include="*.py" | grep -v config/constants.py | grep -v __pycache__
```

---

### PR-5: Dockerfile & Port Standardization

**Objective:** One canonical backend Dockerfile. Consistent ports.

**Files to delete:**
- `Dockerfile` (the single-stage version with stale PYTHONPATH)

**Files to edit:**
- `Dockerfile.backend` — fix app module path, remove unused gunicorn install
- `run_app.py` — change port from 8000 to 8080
- `Makefile` — change port from 8000 to 8080, fix `SRC=app` to `SRC=src/legal_portal`
- `src/legal_portal/config/default.py` — change Settings.port default from 8501 to 8080
- `pyproject.toml` — update `requires-python` from `>=3.8` to `>=3.10`
- `setup.py` — delete (pyproject.toml is sufficient)

**Steps:**
1. Delete `Dockerfile`. Rename or keep `Dockerfile.backend` as the canonical Dockerfile.
2. In `Dockerfile.backend`: remove `gunicorn` from pip install (it's installed but never used). Verify the app module path is correct for the PYTHONPATH (`/app:/app/src` means `legal_portal.api.main:app` is the correct path, not `src.legal_portal...`). Fix if needed.
3. Standardize port to 8080 across `run_app.py`, `Makefile`, and `default.py`.
4. Fix `Makefile` `SRC` variable from `app` to `src/legal_portal`.
5. Delete `setup.py`. Update `pyproject.toml` `requires-python` to `>=3.10`.

**Risk:** LOW. Port change only affects local dev (Docker already uses 8080). Dockerfile deletion is safe since `Dockerfile.backend` is the better version.

**Verification:**
```bash
docker build -f Dockerfile.backend -t test-build .
docker run -p 8080:8080 test-build  # verify app starts
make run  # verify local dev works
pytest tests/ -x
```

---

### PR-6: CI/CD Workflow Consolidation

**Objective:** Reduce 6 workflows to 2 (CI + Deploy).

**Files to delete:**
- `.github/workflows/ci.yml` — fully superseded by test.yml (stale Python 3.9 matrix)
- `.github/workflows/lint.yml` — duplicates test.yml lint + ci-cd.yml security
- `.github/workflows/startup-tests.yml` — import smoke tests can be a job in test.yml

**Files to edit:**
- `.github/workflows/test.yml` — add startup smoke test job, add Bandit security scan job
- `.github/workflows/ci-cd.yml` — evaluate: if it duplicates test.yml, delete. If it adds deployment triggers, merge those into gcp-deploy.yml.
- `.github/workflows/gcp-deploy.yml` — change health check URL from `/_stcore/health` to `/api/health`

**Target state:**
- `test.yml` — all CI: lint, security scan, backend tests, frontend tests, e2e tests, integration tests, smoke tests
- `gcp-deploy.yml` — deployment only

**Risk:** LOW. CI workflow changes don't affect application code.

**Verification:**
Push to a feature branch and verify all checks pass in GitHub Actions.

---

### PR-7: Extract Business Logic from Routes — Batch 1 (Analysis + Documents)

**Objective:** Extract `analysis_core.py` and `documents.py` to <500 lines each.

**New files to create:**
- `src/legal_portal/services/analysis/analysis_orchestrator.py` — receives `process_case_background()` and `_download_and_extract_documents()` and `_extract_deferred_documents()`
- `src/legal_portal/services/documents/upload_service.py` — receives document upload orchestration, OCR fallback chain, extraction pipeline

**Files to edit:**
- `src/legal_portal/api/routes/analysis_core.py` — reduce to thin HTTP handlers that call `AnalysisOrchestrator`
- `src/legal_portal/api/routes/documents.py` — reduce to thin HTTP handlers that call `UploadService`

**Extraction strategy for `analysis_core.py`:**
1. Move `process_case_background()` (lines ~910-1630) to `analysis_orchestrator.py` as `AnalysisOrchestrator.run()`.
2. Move `_download_and_extract_documents()` (lines ~590-910) to `analysis_orchestrator.py` as a private method.
3. Move `_extract_deferred_documents()` (lines ~107-354) to `analysis_orchestrator.py`.
4. Move `_dedup_email_threads()` (lines ~354-470) to `analysis_orchestrator.py`.
5. Move `_generate_and_store_artifacts()` (lines ~524-567) to `analysis_orchestrator.py`.
6. Route file keeps: endpoint definitions, request parsing, auth checks, response formatting, SSE/streaming wrappers.

**Extraction strategy for `documents.py`:**
1. Move `upload_document()` content extraction logic (lines ~171-690, the business logic inside the route handler) to `UploadService.process_upload()`.
2. Move `_trigger_extraction_inner()` (lines ~1940-2630) to `UploadService.trigger_extraction()`.
3. Consolidate the 3 near-identical `do_google_ocr()` closures into a single `UploadService._run_google_ocr()` method.
4. Move `enrich_cross_document_for_case()` (lines ~741-920) to `UploadService.enrich_cross_document()`.
5. Route file keeps: endpoint definitions, auth checks, multipart file handling, response formatting.

**Risk:** HIGH. These are the most complex route files. Careful interface design needed to avoid breaking the pipeline.

**Verification:**
```bash
pytest tests/api/ -x
pytest tests/unit/ -x
# Manual: upload a document, run an analysis end-to-end
```

---

### PR-8: Extract Business Logic from Routes — Batch 2 (Letters + Gaps + Clio)

**Objective:** Extract `letter_routes.py`, `gap_routes.py`, `clio.py`, and `cases.py` to <500 lines each.

**New files to create:**
- `src/legal_portal/services/letters/letter_orchestrator.py` — streaming/non-streaming letter generation pipeline
- `src/legal_portal/services/analysis/gap_orchestrator.py` — gap analysis orchestration
- `src/legal_portal/services/integrations/clio_import_service.py` — Clio document import pipeline
- `src/legal_portal/services/integrations/clio_oauth_service.py` — OAuth flow

**Files to edit:**
- `src/legal_portal/api/routes/letter_routes.py` — thin out to endpoint definitions
- `src/legal_portal/api/routes/gap_routes.py` — thin out
- `src/legal_portal/api/routes/clio.py` — thin out
- `src/legal_portal/api/routes/cases.py` — thin out (move `import_clio_documents_helper` to `clio_import_service.py`)

**Extraction strategy for `letter_routes.py`:**
1. `stream_findings_letter()` orchestration (580 lines) → `LetterOrchestrator.stream_findings()`.
2. `generate_letter()` orchestration (550 lines) → `LetterOrchestrator.generate_findings()`.
3. Both share a common pipeline (strategy → draft → lint → repair → critic → polish). This pipeline logic becomes a single method with a `streaming: bool` parameter.

**Extraction strategy for `cases.py`:**
1. `import_clio_documents_helper()` (680 lines) → `ClioImportService.import_documents()`.
2. `process_clio_import_background()` → `ClioImportService.process_background()`.
3. `run_content_hash_dedup()` → `DocumentDedupService.dedup_by_hash()` or add to existing document service.

**Files to also edit:**
- `src/legal_portal/api/routes/_analysis_helpers.py` — move the ~200 lines of Pydantic models to `src/legal_portal/core/models/api_models.py`. Move DB helpers to a service. Keep only utility functions that genuinely help route handlers.

**Risk:** HIGH. Same concerns as PR-7.

**Verification:**
```bash
pytest tests/ -x
# Manual: generate a letter, run gap analysis, import from Clio
```

---

### PR-9: Split Oversized Service Files

**Objective:** Break down the 7 service files exceeding 2,000 lines.

**Files to split:**

| Original | Lines | Split Into |
|----------|-------|------------|
| `main_processor.py` | 2,358 | Decompose `process_case_documents()` into stage methods within the same file. Extract `_convert_to_case_analysis_result`, `_detect_near_duplicates`, jurisdiction constants to dedicated files. Target: <1,500 lines. |
| `gap_analysis_service.py` | 2,355 | Extract `GapDeduplicator` (batch merge + dedup logic) to `gap_dedup.py`. Keep map-reduce core. Target: <1,500 lines. |
| `json_processing_service.py` | 2,267 | Rename to `letter_generation_service.py`. Extract prompt building to `letter_prompts.py`. Extract markdown/HTML conversion to `letter_formatting.py`. Target: <1,200 lines. |
| `pdf_processor.py` | 2,026 | Extract OCR fallback chain to `ocr_pipeline.py`. Keep PDF-specific extraction. Target: <1,200 lines. |
| `ai_analyzer.py` | 1,781 | Review: if it's a single coherent AI analysis class, deep nesting may be acceptable. Otherwise extract prompt templates to separate files. |

**Risk:** MEDIUM. Internal refactoring within the service layer. Interfaces remain unchanged.

**Verification:**
```bash
pytest tests/ -x
python scripts/check_import_rules.py
```

---

### PR-10: Documentation Consolidation

**Objective:** Reduce ~280 obsolete docs to a clean, navigable structure.

**Steps:**
1. Archive `docs/archive/` (221 files) — compress to `docs/archive-2026-03.tar.gz`, then delete the directory.
2. Archive `docs/plans/` (19 files) — these are completed implementation plans. Compress to `docs/plans-archive-2026-03.tar.gz`, keep directory for future plans.
3. Delete `memory-bank/archive/` (39 files) — superseded 2025-08-11 snapshots.
4. Delete `notebooklm_sources/` (6 files) — marketing content, not dev artifacts.
5. Update `docs/README.md` to reflect the cleaned structure.
6. Merge `REFACTOR_README.md` into `README.md` or delete if content is outdated.

**Target structure:**
```
docs/
├── README.md
├── SETUP.md
├── API.md
├── TESTING.md
├── AUTHENTICATION.md
├── developer/
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── DEBUG_GUIDE.md
│   └── PERFORMANCE.md
├── features/
│   ├── CLIO_INTEGRATION.md
│   ├── LETTER_GENERATION.md
│   ├── HALLUCINATION_PREVENTION.md
│   └── FULL_DOCUMENT_CONTENT_ARCHITECTURE.md
├── deployment/
│   └── [deployment docs]
├── user/
│   └── [user guides]
├── archive-2026-03.tar.gz
└── plans-archive-2026-03.tar.gz
```

**Risk:** LOW. No code changes.

**Verification:**
All links in `docs/README.md` resolve. No broken internal references.

---

### PR-11: Consolidate Cost & Logging Utilities

**Objective:** Reduce utility module count by merging overlapping modules.

**Cost tracking (merge 4 → 2):**
- Merge `cost_calculator.py` + `cost_estimator.py` → `cost_tracking.py` (single pricing rates dict)
- Keep `cost_session_manager.py` (orchestration) and `cost_exporter.py` (output formatting) or merge if they overlap sufficiently

**Logging (consolidate 6 → 2):**
- Keep `structured_logger.py` as the primary logger. Merge `logging_config.py` setup into it.
- Keep `audit_logger.py` for compliance/integrity logging (separate concern).
- `diagnostic_logger.py` — add serverless guard and consider merging into structured_logger as a debug mode.
- `metrics.py` — keep separate (different concern: in-memory metrics vs. log output).
- `tracing.py` — keep separate (distributed tracing).

**Other utils to clean up:**
- `helpers.py` — after removing `ProgressTracker` (PR-2), evaluate remaining functions. Move AI-calling functions to a service. Move HTML generation to a template or formatter.

**Risk:** MEDIUM. Merging modules requires updating all import sites.

**Verification:**
```bash
pytest tests/ -x
grep -r "from legal_portal.utils.cost_calculator import" src/ tests/
grep -r "from legal_portal.utils.cost_estimator import" src/ tests/
# Both should return 0 results after migration
```

---

### PR-12: Testing Improvements

**Objective:** Fix fragile tests, add missing coverage for critical paths.

**Fix fragile tests:**
- `tests/api/test_cases.py` — replace multi-status-code assertions (`assert status in [200, 201, 404, 500]`) with specific expected status codes. If the test can't predict the status code, the mock setup is wrong.
- `tests/api/test_analysis.py` — same treatment.
- `tests/conftest.py` — review deep MagicMock chains. Consider using a more realistic Supabase mock or a fixture that returns structured data.

**Move orphaned tests:**
- Move `tests/test_citation_removal.py`, `tests/test_gap_normalize.py`, `tests/test_citation_enhancement.py`, `tests/test_citation_integration.py`, `tests/test_citation_tracking.py`, `tests/test_context_builder.py`, `tests/test_multi_stage_analysis.py`, `tests/test_simplified_workflow.py`, `tests/test_appendix_fix.py`, `tests/test_pdf_fixtures.py` into `tests/unit/`.

**Add missing tests:**
- Integration test: analysis pipeline end-to-end (mock OpenAI, real or semi-real Supabase)
- Unit test: `LetterOrchestrator` pipeline (strategy → draft → lint → repair → polish)
- Unit test: `get_optional_user` returns None for unauthenticated requests (from PR-1)
- Unit test: `stream_chat_response` rejects non-owners (from PR-1)

**Risk:** LOW. Test changes don't affect production code.

**Verification:**
```bash
pytest tests/ -x --tb=short
pytest tests/ --co -q | wc -l  # count total test cases
```

---

## Bug Fix Plan (Detailed)

### B2: `get_optional_user` — HTTPBearer `auto_error`

**Root cause:** The function was defined using the same `security` dependency as `get_current_user`. `HTTPBearer()` defaults to `auto_error=True`, which raises 403 before the function body executes.

**Location:** `src/legal_portal/api/dependencies.py` lines 20, 146-148

**Fix:**
```python
# Line 20 area — add:
optional_security = HTTPBearer(auto_error=False)

# Line 146 — change:
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    # Also need a separate supabase client that doesn't depend on auth:
```

**Side effects:** Endpoints using `get_optional_user` will now actually receive unauthenticated requests. Verify that all such endpoints handle `None` user correctly.

**Test:** Create a request to an endpoint using `get_optional_user` with no Authorization header. Assert 200 (not 403) and that `user` is `None`.

---

### B3: `stream_chat_response` — Missing Authorization

**Root cause:** The streaming version was likely copy-pasted from a simpler implementation and the ownership check was missed.

**Location:** `src/legal_portal/api/routes/chat_routes.py` lines 40-114

**Fix:** After authenticating the user (line ~45), look up the case_id from the analysis_id, then call `_ensure_case_access(supabase, case_id, user["id"])`. Follow the exact pattern used in `case_chat` (line 126).

**Side effects:** Users who somehow accessed other users' analyses via streaming will now get 403. This is the correct behavior.

**Test:** Mock a Supabase client that returns an analysis belonging to user A. Call `stream_chat_response` authenticated as user B. Assert 403.

---

### B4: Pickle Deserialization

**Root cause:** The cache was implemented using Python's `pickle` module for serialization, which is a known arbitrary code execution vector.

**Location:** `src/legal_portal/utils/cache_manager.py` lines 81, 96

**Fix:** Replace with `json.dumps`/`json.loads`. This means cached objects must be JSON-serializable. If any cached values are complex objects (Pydantic models, etc.), call `.model_dump()` before caching and reconstruct after retrieval.

**Side effects:** Existing pickle cache files become unreadable. Add a one-time cleanup: if a `.pkl` file is found, delete it. The cache will repopulate naturally.

**Test:** Unit test that caches a dict, retrieves it, and verifies equality. Unit test that verifies `.pkl` files are deleted on startup.

---

### B8: Frontend localStorage Auth

**Root cause:** This page was likely written before `getSecureSession()` was introduced, and was missed during the security hardening pass.

**Location:** `frontend/src/routes/app/cases/new/+page.svelte` line 62

**Fix:**
```typescript
// Replace:
const token = localStorage.getItem('supabase_access_token');

// With:
const { session } = await getSecureSession();
if (!session) { /* redirect to login */ return; }
const token = session.access_token;
```

**Side effects:** Users with an expired localStorage token who previously got silent failures will now get properly redirected to login.

**Test:** Frontend unit test that mocks `getSecureSession` returning null and verifies redirect behavior.

---

## Route Refactor Strategy

### Current State

```
api/routes/         (13,792 lines of business logic)
    analysis_core.py    → pipeline orchestration, document download, artifact storage
    documents.py        → upload, OCR, extraction, classification, enrichment
    cases.py            → Clio import, document management, dedup
    letter_routes.py    → letter generation pipeline (strategy→draft→lint→repair→polish)
    gap_routes.py       → gap analysis, batch construction, streaming
    clio.py             → OAuth, matter search, import, sync
    _analysis_helpers.py → models, identity resolution, signature detection, DB helpers
```

### Target State

```
api/routes/                    (< 300 lines each — HTTP concerns only)
    analysis.py                → delegates to AnalysisOrchestrator
    documents.py               → delegates to UploadService
    cases.py                   → delegates to CaseService + ClioImportService
    letters.py                 → delegates to LetterOrchestrator
    gaps.py                    → delegates to GapOrchestrator
    clio.py                    → delegates to ClioOAuthService
    chat.py                    → delegates to CaseChatService
    health.py                  → (already thin)
    progress.py                → (already thin)
    settings.py                → (already thin)

services/
    analysis/
        analysis_orchestrator.py   ← NEW (from analysis_core.py)
        main_processor.py          (existing — called by orchestrator)
        multi_stage_analyzer.py    (existing)
        gap_analysis_service.py    (existing)
        gap_orchestrator.py        ← NEW (from gap_routes.py)
        corpus_coverage_service.py (existing)
    documents/
        upload_service.py          ← NEW (from documents.py)
        (existing file processors, chunking, etc.)
    letters/
        letter_orchestrator.py     ← NEW (from letter_routes.py)
        (existing letter services)
    integrations/
        clio_import_service.py     ← NEW (from cases.py + clio.py)
        clio_oauth_service.py      ← NEW (from clio.py)
        (existing clio_context_builder, clio_data_transformer)

core/models/
    api_models.py                  ← NEW (from _analysis_helpers.py Pydantic models)
```

### Extraction Rules

Each route handler follows this pattern after refactoring:

```python
@router.post("/analyze")
async def run_analysis(
    request: AnalysisRequest,
    user: dict = Depends(get_current_user),
    supabase = Depends(get_user_supabase_client),
):
    """Thin handler — parse, auth, delegate, respond."""
    orchestrator = AnalysisOrchestrator(supabase, user)
    result = await orchestrator.run(request.case_id, request.options)
    return AnalysisResponse(status=result.status, analysis_id=result.id)
```

No business logic. No data transformation. No AI calls. No Supabase queries beyond auth verification.

### Staged Extraction (Within PR-7 and PR-8)

For each route file, the extraction follows 4 steps:

1. **Create the service file** with the extracted functions as methods on a service class.
2. **Update the route handler** to instantiate the service and delegate.
3. **Run tests** to verify behavior is unchanged.
4. **Commit** before moving to the next file.

This means PR-7 and PR-8 each contain 2-3 atomic commits, one per route file extraction.

---

## Configuration Consolidation Plan

### Current State

| Source | What It Holds | Problem |
|--------|---------------|---------|
| `config/default.py` Settings | ~20 env vars | Missing 26+ env vars that are accessed via raw `os.getenv` |
| `config/config_manager.py` | Legacy JSON config | Parallel config system |
| `main_processor.py:268` | `JURISDICTION_CITATION_MAP` | Duplicated in `json_processing_service.py:281` |
| `_analysis_helpers.py:165` | `_SIGNATURE_INSTRUMENT_HINT_PATTERNS` | Duplicated in `main_processor.py:103` |
| `json_processing_service.py:300` | `_DOCUMENT_INSTRUMENT_HINT_PATTERNS` | Overlapping variant of the above |
| `cost_calculator.py:28` | `PRICING_RATES` (7 keys) | Divergent copy in `cost_estimator.py:23` (6 keys) |
| 23 files | Hard-coded `"gpt-5.4"`, `"gpt-5-mini"`, etc. | `Settings.openai_model` exists but is ignored |

### Target State

```
config/
├── default.py         # Pydantic Settings — ALL env vars, no os.getenv elsewhere
├── constants.py       # Static constants: model names, token limits, thresholds, patterns
├── jurisdictions.py   # Jurisdiction-specific config (one source of truth)
```

**`config/constants.py` contents:**
```python
# Model identifiers
DEFAULT_MODEL = "gpt-5.4"
FAST_MODEL = "gpt-5-mini"
NANO_MODEL = "gpt-5-nano"
LEGACY_MODEL = "gpt-5.2"

# Token/character limits
PROMPT_MAX_DOC_CHARS = 24_000
MAX_FINDINGS_PROMPT_CHARS = 220_000
MAX_RAW_DOC_TOTAL_CHARS = 50_000

# Pricing rates (single source)
PRICING_RATES = { ... }  # merged from cost_calculator + cost_estimator

# Instrument hint patterns (merged from 3 copies)
INSTRUMENT_HINT_PATTERNS = [ ... ]

# Thresholds
COMMUNICATION_GAP_DAYS = 30
PARTY_CLASSIFICATION_THRESHOLD = 10
```

**`config/jurisdictions.py` contents:**
Single `JURISDICTIONS` dict merging `JURISDICTION_CITATION_MAP` and `JURISDICTION_CONFIG`.

**Migration:**
- `os.getenv("SUPABASE_URL")` → `get_settings().supabase_url`
- `"gpt-5.4"` → `constants.DEFAULT_MODEL`
- `JURISDICTION_CITATION_MAP[jurisdiction]` → `jurisdictions.JURISDICTIONS[jurisdiction]`
- `PRICING_RATES` → `constants.PRICING_RATES`

---

## Docker & Deployment Cleanup

### Decision

**Keep `Dockerfile.backend`** (multi-stage, correct dependency separation). **Delete `Dockerfile`** (single-stage, stale PYTHONPATH, dev headers in prod image).

### Fixes to `Dockerfile.backend`

1. **Remove unused gunicorn**: `pip install gunicorn uvloop` → `pip install uvloop`
2. **Verify app module path**: With PYTHONPATH `/app:/app/src`, the correct module is `legal_portal.api.main:app` (not `src.legal_portal.api.main:app`). Fix the CMD.
3. **Rename** to `Dockerfile` (since the old one is deleted).

### CI Target State

| Workflow | Purpose | Trigger |
|----------|---------|---------|
| `test.yml` | All CI: lint, security, backend tests, frontend tests, e2e, integration, smoke tests | push(main, develop), PR |
| `gcp-deploy.yml` | Deployment to GCP | push(main), workflow_dispatch |

Delete: `ci.yml`, `lint.yml`, `startup-tests.yml`, `ci-cd.yml` (merge any unique jobs into `test.yml`).

Fix in `gcp-deploy.yml`: `/_stcore/health` → `/api/health`.

---

## File Size Refactor Plan

| File | Lines | Strategy | Target |
|------|-------|----------|--------|
| `analysis_core.py` | 2,940 | **PR-7** — extract to `analysis_orchestrator.py` | <500 (route) |
| `documents.py` | 2,857 | **PR-7** — extract to `upload_service.py` | <500 (route) |
| `main_processor.py` | 2,358 | **PR-9** — decompose `process_case_documents()` into stage methods | <1,500 |
| `gap_analysis_service.py` | 2,355 | **PR-9** — extract dedup/merge logic to `gap_dedup.py` | <1,500 |
| `json_processing_service.py` | 2,267 | **PR-9** — rename to `letter_generation_service.py`, extract prompts and HTML conversion | <1,200 |
| `cases.py` | 2,070 | **PR-8** — extract Clio import to `clio_import_service.py` | <500 (route) |
| `pdf_processor.py` | 2,026 | **PR-9** — extract OCR pipeline to `ocr_pipeline.py` | <1,200 |

---

## Testing Improvements

### Fix Fragile Tests (PR-12)

| File | Problem | Fix |
|------|---------|-----|
| `tests/api/test_cases.py` | `assert status in [200, 201, 404, 500]` | Assert exact expected status per test case |
| `tests/api/test_analysis.py` | Same multi-status pattern | Same fix |
| `tests/conftest.py` | Deep MagicMock chains silently succeed | Add `spec=True` to mocks or use a structured fake |

### Move Orphaned Tests (PR-12)

Move 10 root-level test files to `tests/unit/`.

### Add Missing Tests (PR-12)

| Test | Priority | What It Covers |
|------|----------|----------------|
| `tests/unit/test_optional_auth.py` | P0 | `get_optional_user` returns None without token |
| `tests/unit/test_chat_ownership.py` | P0 | `stream_chat_response` rejects non-owners |
| `tests/integration/test_analysis_pipeline.py` | P2 | End-to-end analysis with mocked OpenAI |
| `tests/integration/test_clio_import.py` | P2 | Clio import flow with mocked Clio API |

---

## Execution Timeline

### Week 1: Critical Fixes & Cleanup

| Day | PR | Description | Est. Effort |
|-----|-----|-------------|-------------|
| Mon | PR-1 | Security & correctness fixes (8 bugs) | 4-6 hours |
| Tue | PR-2 | Remove root debris + dead code | 1-2 hours |
| Tue-Wed | PR-3 | Remove 33 stubs, update 91 imports | 4-6 hours |
| Thu | PR-4 | Configuration consolidation | 4-6 hours |
| Fri | PR-5 | Dockerfile & port standardization | 2-3 hours |

### Week 2: Structural Refactoring

| Day | PR | Description | Est. Effort |
|-----|-----|-------------|-------------|
| Mon | PR-6 | CI/CD workflow consolidation | 2-3 hours |
| Mon-Wed | PR-7 | Extract routes batch 1 (analysis_core + documents) | 8-12 hours |
| Thu-Fri | PR-8 | Extract routes batch 2 (letters + gaps + clio + cases) | 8-12 hours |

### Week 3: Polish & Testing

| Day | PR | Description | Est. Effort |
|-----|-----|-------------|-------------|
| Mon-Tue | PR-9 | Split oversized service files | 6-8 hours |
| Wed | PR-10 | Documentation consolidation | 2-3 hours |
| Thu | PR-11 | Consolidate cost & logging utilities | 4-6 hours |
| Fri | PR-12 | Testing improvements | 4-6 hours |

**Total: ~50-70 hours across 3 weeks**

---

## Safeguards

### Before Each PR

1. **Branch from main.** Never stack PRs on top of unmerged PRs.
2. **Run the full test suite locally** before pushing: `pytest tests/ -x && cd frontend && npm run test`
3. **Run import validation**: `python -c "from legal_portal.api.main import app"` — verifies all transitive imports resolve.
4. **Run the refactor validator**: `python scripts/validate_refactor.sh` (if it exists and works).

### During Each PR

1. **One commit per logical change.** Don't mix bug fixes with refactoring.
2. **No behavior changes.** Every PR must be a pure refactor or targeted fix. No new features, no changed logic.
3. **Run affected tests after each commit**, not just at the end.

### After Each PR Merges

1. **Deploy to staging** and run a manual smoke test: upload a document, run analysis, generate a letter.
2. **Monitor error logs** for 24 hours before starting the next PR.
3. **If anything breaks**, revert the PR immediately. Every PR is designed to be independently revertible.

### Feature Flags

Not needed for this refactoring. All changes are:
- Pure renames (stub removal)
- Code movement (route extraction)
- Bug fixes (security patches)
- File deletion (dead code, obsolete docs)

None introduce new behavior that requires gradual rollout.

### Rollback Strategy

Every PR is a single merge commit on `main`. Rollback is:
```bash
git revert <merge-commit-sha>
```

The PR ordering is designed so that reverting any single PR does not break subsequent PRs. Exception: PR-3 (stub removal) should not be reverted after PR-4+ builds on the new import paths. If PR-3 needs reverting, also revert PR-4.

### Test Coverage Requirements

- PR-1 must add at least 3 new tests (optional auth, chat ownership, cache serialization).
- PR-7 and PR-8 must maintain existing test pass rate. No test deletions.
- PR-12 must improve assertion specificity (no more multi-status-code accepts).

### Dependency Chain

```
PR-1 (bugs) ← independent, merge first
PR-2 (debris) ← independent
PR-3 (stubs) ← must merge before PR-4
PR-4 (config) ← depends on PR-3
PR-5 (docker) ← independent
PR-6 (CI) ← independent
PR-7 (routes batch 1) ← depends on PR-3
PR-8 (routes batch 2) ← depends on PR-7
PR-9 (file splits) ← depends on PR-7, PR-8
PR-10 (docs) ← independent
PR-11 (utils) ← depends on PR-4
PR-12 (tests) ← should be last
```

PRs 1, 2, 5, 6, and 10 can be merged in any order. PR-3 must precede PR-4, PR-7, PR-8. PR-7 must precede PR-8 and PR-9.
