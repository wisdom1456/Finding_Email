# Phase 4 — Split analysis.py Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 7,586-line `src/legal_portal/api/routes/analysis.py` into focused route modules without changing any endpoint paths, request/response contracts, or frontend behavior.

**Architecture:** Extract routes into domain-specific modules under `api/routes/`, move shared helpers into `_analysis_helpers.py`, and re-export all symbols from the original `analysis.py` to preserve backward compatibility for existing test imports. Each extraction is validated independently before proceeding to the next.

**Tech Stack:** FastAPI, Python 3.13, pytest

---

## 1. Phase Objective

Split `analysis.py` (7,586 lines, 22 endpoints, ~60 helpers) into 6 focused modules. The original `analysis.py` becomes a thin compatibility shim that re-exports all moved symbols so existing test imports AND `monkeypatch.setattr` targets continue working. No endpoint paths change. No request/response contracts change.

---

## 2. Files to Create

| File | Purpose | Endpoints Moved |
|------|---------|----------------|
| `src/legal_portal/api/routes/gap_routes.py` | Gap analysis endpoints | `analyze_gaps_on_demand`, `resolve_gaps_and_refresh`, `analyze_gaps_streaming` |
| `src/legal_portal/api/routes/letter_routes.py` | Letter generation endpoints | `stream_findings_letter`, `generate_letter`, `generate_recommendation_letter`, `stream_recommendation_letter`, `calculate_demand_amount` |
| `src/legal_portal/api/routes/chat_routes.py` | Chat endpoints | `stream_chat_response`, `case_chat` |
| `src/legal_portal/api/routes/document_status_routes.py` | Document status/recovery endpoints | `get_document_status`, `retry_failed_documents`, `skip_failed_documents`, `get_analysis_state` |
| `src/legal_portal/api/routes/analysis_core.py` | Core analysis endpoints + background worker | `start_analysis`, `cancel_analysis`, `cancel_case_analysis`, `get_analysis_status`, `get_analysis_results`, `save_streaming_analysis`, `stream_case_analysis`, `get_streaming_result` |
| `src/legal_portal/api/routes/_analysis_helpers.py` | Shared helpers used across 2+ route modules | Helper functions, Pydantic models, constants |

## 3. Files to Modify

| File | Change |
|------|--------|
| `src/legal_portal/api/routes/analysis.py` | Reduce to compatibility shim: re-exports all moved symbols |
| `src/legal_portal/api/main.py` | Register 5 new routers (same `/api/analysis` prefix + tags) |
| `tests/unit/test_gap_resolution_helpers.py` | Update imports (optional — shim makes this work either way) |
| `tests/unit/test_map_reduce_gap_analysis.py` | Update imports (optional — shim makes this work either way) |

### Critical: `monkeypatch.setattr` Compatibility

Several test files use `monkeypatch.setattr(analysis_routes, "func_name", mock)` where `analysis_routes` is the `analysis` module. After the split, the shim re-exports symbols, but `monkeypatch.setattr` on the shim only patches the shim's copy — NOT the actual function in the new module where it's used.

**Solution:** The shim `analysis.py` must not only re-export via `from X import *` but also serve as the **canonical import location** for patched symbols. Each new route module must import shared helpers FROM the shim (`from legal_portal.api.routes.analysis import ...`) rather than from `_analysis_helpers` directly. This way, `monkeypatch.setattr(analysis_routes, "func", mock)` modifies the binding that the route modules actually reference.

**However, this creates a circular import** (route modules import from shim, shim imports from route modules). The simpler solution:

**Actual solution: Update the 3 affected test files to patch the correct module.** This is the standard Python practice for monkeypatching — patch where the symbol is *used*, not where it's *defined*.

| Test File | Current Patch Target | New Patch Target |
|-----------|---------------------|-----------------|
| `tests/api/test_letter_stream_integration.py` | `analysis_routes.get_settings` etc. | `legal_portal.api.routes.letter_routes.get_settings` etc. |
| `tests/api/test_generate_letter_formatting.py` | `analysis_routes._ensure_case_access` etc. | `legal_portal.api.routes.letter_routes._ensure_case_access` etc. |
| `tests/unit/test_gap_resolution_helpers.py` | `analysis_routes._GAP_ANALYSIS_INPUT_SCHEMA_VERSION` | `legal_portal.api.routes.gap_routes._GAP_ANALYSIS_INPUT_SCHEMA_VERSION` |

**Note:** `tests/unit/test_letter_identity_resolution.py` calls functions directly (e.g., `analysis_routes._resolve_letter_identity_context(...)`) without monkeypatching — the shim re-export handles this correctly.

---

## 4. Exact Function/Class Migration Map

### 4a. `_analysis_helpers.py` — Shared helpers (used by 2+ modules)

**Helper functions:**
| Function | Lines | Used By |
|----------|-------|---------|
| `_ensure_case_access` | 7551-7558 | gap, letter, chat, doc_status, analysis_core |
| `_fetch_latest_analysis_result` | 7561-7586 | gap, letter, chat, analysis_core |
| `_get_user_ai_preferences` | 571-579 | gap, letter, chat |
| `_new_generation_metrics` | 436-467 | letter |
| `_emit_generation_metrics` | 470-475 | letter |
| `_to_sse` | 478-480 | letter |
| `_quality_report_placeholder` | 483-499 | letter |
| `_resolve_letter_identity_context` | 594-723 | letter |
| `_resolve_client_name_for_letter` | 726-760 | letter |
| `_first_non_empty_text` | 582-591 | letter (via _resolve_letter_identity_context) |
| `AnalysisCancelledError` | 502-503 | analysis_core |
| `_analysis_is_cancelled` | 506-519 | analysis_core |
| `_cancel_analysis` | 522-550 | analysis_core |
| `_update_analysis_progress` | 553-568 | analysis_core |
| `_upsert_with_retry` | 418-424 | analysis_core |
| `_update_case_with_retry` | 427-433 | analysis_core |

**Pydantic models (used in route signatures or by tests):**
| Model | Lines | Used By |
|-------|-------|---------|
| `AnalysisRequest` | 1234-1239 | analysis_core |
| `AnalysisResponse` | 1241-1251 | analysis_core |
| `LetterGenerationRequest` | 1253-1277 | letter |
| `LetterGenerationResponse` | 1279-1287 | letter |
| `StreamingAnalysisSaveRequest` | 3391-3395 | analysis_core |
| `RecommendationLetterRequest` | 4847-4859 | letter |
| `RecommendationLetterResponse` | 4861-4869 | letter |
| `CalculateDemandAmountRequest` | 5447-5452 | letter |
| `CalculateDemandAmountResponse` | 5454-5460 | letter |
| `GapAnalysisRequest` | 5563-5571 | gap |
| `GapResolutionItemRequest` | 5573-5593 | gap |
| `GapResolutionRefreshRequest` | 5595-5622 | gap |
| `RetryDocumentsRequest` | 7265-7272 | doc_status |
| `SkipDocumentsRequest` | 7274-7281 | doc_status |
| `DocumentStatusResponse` | 7283-7294 | doc_status |
| `RecoveryActionResponse` | 7296-7303 | doc_status |
| `ChatMessageRequest` | (from data_models) | chat |
| `ChatMessageResponse` | (from data_models) | chat |

**Constants:**
| Constant | Lines | Used By |
|----------|-------|---------|
| `_DB_COLUMNS_CACHE` | 58 | analysis_core |
| `_GAP_ANALYSIS_INPUT_SCHEMA_VERSION` | 59 | gap |

### 4b. `gap_routes.py` — Gap analysis

**Endpoints moved:**
- `analyze_gaps_on_demand` (POST `/analyze-gaps`)
- `resolve_gaps_and_refresh` (POST `/analyze-gaps/resolve`)
- `analyze_gaps_streaming` (POST `/analyze-gaps/stream`)

**Helper functions moved (gap-specific, not shared):**
| Function | Lines |
|----------|-------|
| `GapBatch` (dataclass) | 5863-5873 |
| `_SMALL_GROUP_MERGE_MAP` | 5878-5886 |
| `_GAP_CONTEXT_MAX_DOCS` | 5708 |
| `_GAP_CONTEXT_MAX_CHARS` | 5709 |
| `_build_gap_resolution_hash` | 5624-5643 |
| `_build_supporting_document_hash` | 5646-5706 |
| `_derive_signature_detection_for_gap_doc` | 5674-5706 |
| `_fetch_case_documents_for_gap_context` | 5712-5760 |
| `_build_case_document_state_hash` | 5762-5796 |
| `_fetch_all_case_document_metadata` | 5798-5825 |
| `_build_case_document_state_hash_lightweight` | 5827-5861 |
| `_build_gap_analysis_batches` | 5889-6009 |
| `_run_gap_analysis` | 6011-6067 |
| `_build_signature_evidence` | 6069-6143 |
| `_build_document_registry_for_gap_context` | 6145-6256 |
| `_build_truncation_context` | 6258-6274 |
| `_hash_jsonable` | 6276-6280 |
| `_build_gap_analysis_input_hash` | 6282-6316 |
| `_ensure_fresh_gap_analysis_for_letter_generation` | 6318-6440 |
| `_compute_resolution_document_state_hash` | 6442-6467 |
| `_parse_gap_document_summaries` | 6469-6513 |
| `_stamp_document_ids` | 6515-6557 |
| `_fetch_gap_intake_content` | 6559-6565 |
| `_collect_resolution_documents` | 6567-6606 |
| `_build_resolution_context` | 6608-6654 |

**Signature helpers also needed by gap (move to `_analysis_helpers.py` OR keep in gap since only gap uses them internally):**
| Function | Lines | Decision |
|----------|-------|----------|
| `_normalize_signature_verification_status` | 835-840 | Move to `_analysis_helpers.py` (used by gap + analysis_core via process_case_background) |
| `_extract_signature_verification` | 843-869 | Move to `_analysis_helpers.py` |
| `_apply_signature_verification_override` | 872-930 | Move to `_analysis_helpers.py` |
| `_normalize_text_signing_date` | 931-957 | Move to `_analysis_helpers.py` |
| `_infer_signature_detection_from_text` | 959-1019 | Move to `_analysis_helpers.py` |
| `_is_pdf_like_document` | 1021-1026 | Move to `_analysis_helpers.py` |
| `_is_signature_inference_candidate` | 1028-1063 | Move to `_analysis_helpers.py` |
| `_sample_text_for_state_hash` | 1066-1076 | Move to `_analysis_helpers.py` |
| `_extract_signature_instrument_hints` | 1078-1103 | Move to `_analysis_helpers.py` |
| `_SIGNATURE_TEXT_FALLBACK_PATTERNS` | 763-794 | Move to `_analysis_helpers.py` |
| `_TEXT_SIGNING_DATE_PATTERNS` | 796-803 | Move to `_analysis_helpers.py` |
| `_SIGNER_NAME_PATTERNS` | 805-809 | Move to `_analysis_helpers.py` |
| `_SIGNATURE_INSTRUMENT_HINT_PATTERNS` | 811-821 | Move to `_analysis_helpers.py` |
| `_SIGNATURE_VERIFICATION_STATUS_ALIASES` | 823-832 | Move to `_analysis_helpers.py` |

### 4c. `letter_routes.py` — Letter generation

**Endpoints moved:**
- `stream_findings_letter` (GET `/{analysis_id}/letter/stream`)
- `generate_letter` (POST `/generate-letter`)
- `generate_recommendation_letter` (POST `/generate-recommendation-letter`)
- `stream_recommendation_letter` (GET `/{analysis_id}/recommendation-letter/stream`)
- `calculate_demand_amount` (POST `/calculate-demand-amount`)

**Helper functions moved (letter-specific):**
None — all letter helpers are shared and live in `_analysis_helpers.py`.

**Note:** `_ensure_fresh_gap_analysis_for_letter_generation` lives in `gap_routes.py` and is imported by `letter_routes.py`.

### 4d. `chat_routes.py` — Chat

**Endpoints moved:**
- `stream_chat_response` (POST `/{analysis_id}/chat/stream`)
- `case_chat` (POST `/chat`)

**Helper functions moved:** None — uses only shared helpers from `_analysis_helpers.py`.

### 4e. `document_status_routes.py` — Document status/recovery

**Endpoints moved:**
- `get_document_status` (GET `/{analysis_id}/documents`)
- `retry_failed_documents` (POST `/{analysis_id}/retry`)
- `skip_failed_documents` (POST `/{analysis_id}/skip`)
- `get_analysis_state` (GET `/{analysis_id}/state`)

**Helper functions moved:** None — uses only `_ensure_case_access` from `_analysis_helpers.py`.

### 4f. `analysis_core.py` — Core analysis + background worker

**Endpoints moved:**
- `start_analysis` (POST `/start`)
- `cancel_analysis` (POST `/cancel/{analysis_id}`)
- `cancel_case_analysis` (POST `/cancel-case/{case_id}`)
- `get_analysis_status` (GET `/status/{case_id}`)
- `get_analysis_results` (GET `/results/{case_id}`)
- `save_streaming_analysis` (POST `/stream/{case_id}/save`)
- `stream_case_analysis` (GET `/stream/{case_id}`)
- `get_streaming_result` (GET `/stream/{case_id}/result`)

**Functions moved (core-specific):**
| Function | Lines |
|----------|-------|
| `_extract_deferred_documents` | 61-306 |
| `_dedup_email_threads` | 309-415 |
| `process_case_background` | 1608-2325 |
| `_download_and_extract_documents` | 1289-1607 |
| `_convert_statute_recommendations_recursive` | 3913-3948 |
| `_parse_currency` | 3950-3971 |
| `_extract_embedded_json` | 3973-3996 |
| `_extract_section` | 3998-4006 |
| `_extract_list_items` | 4008-4017 |
| `_html_to_plain_text` | 1114-1122 |
| `_generate_eml_bytes` | 1125-1142 |
| `_store_artifact` | 1145-1164 |
| `_generate_and_store_artifacts` | 1167-1207 |
| `_attach_signed_artifact_urls` | 1210-1231 |
| `ARTIFACT_BUCKET` | 1105 |
| `ARTIFACT_PREFIX` | 1106 |
| `SIGNED_URL_TTL` | 1107 |
| `_HTML2TEXT_CONVERTER` | 1109-1111 |

---

## 5. Import Rewrite Plan

### 5a. `_analysis_helpers.py` imports

```python
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from legal_portal.api.dependencies import get_current_user, get_user_supabase_client
from legal_portal.api.middleware.retry import retry_sync
from legal_portal.config.default import get_settings
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.type_safety import safe_str, safe_str_required, sanitize_nested_dict
```

### 5b. `gap_routes.py` imports

```python
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.routes._analysis_helpers import (
    _ensure_case_access,
    _fetch_latest_analysis_result,
    _get_user_ai_preferences,
    # Signature helpers
    _apply_signature_verification_override,
    _extract_signature_instrument_hints,
    _infer_signature_detection_from_text,
    _is_signature_inference_candidate,
    _sample_text_for_state_hash,
    # Pydantic models
    GapAnalysisRequest,
    GapResolutionItemRequest,
    GapResolutionRefreshRequest,
    # Constants
    _GAP_ANALYSIS_INPUT_SCHEMA_VERSION,
)
from legal_portal.config.default import get_settings
from legal_portal.utils.openai_client import OpenAIClient
```

### 5c. `letter_routes.py` imports

```python
import asyncio
import json
import logging
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.routes._analysis_helpers import (
    _emit_generation_metrics,
    _ensure_case_access,
    _fetch_latest_analysis_result,
    _get_user_ai_preferences,
    _new_generation_metrics,
    _quality_report_placeholder,
    _resolve_client_name_for_letter,
    _resolve_letter_identity_context,
    _to_sse,
    CalculateDemandAmountRequest,
    CalculateDemandAmountResponse,
    LetterGenerationRequest,
    LetterGenerationResponse,
    RecommendationLetterRequest,
    RecommendationLetterResponse,
)
from legal_portal.api.routes.gap_routes import _ensure_fresh_gap_analysis_for_letter_generation
from legal_portal.config.default import get_settings
from legal_portal.services.demand_letter_service import DemandLetterService
from legal_portal.services.document_formatter import DocumentFormatterService
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.letter_validation_service import LetterValidationService
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.openai_client import OpenAIClient
```

### 5d. `chat_routes.py` imports

```python
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from legal_portal.api.dependencies import get_current_user, get_user_supabase_client
from legal_portal.api.routes._analysis_helpers import (
    _ensure_case_access,
    _fetch_latest_analysis_result,
    _get_user_ai_preferences,
)
from legal_portal.services.case_chat_service import CaseChatService
from legal_portal.utils.openai_client import OpenAIClient
```

### 5e. `document_status_routes.py` imports

```python
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from legal_portal.api.dependencies import get_current_user, get_user_supabase_client
from legal_portal.api.routes._analysis_helpers import (
    _ensure_case_access,
    DocumentStatusResponse,
    RecoveryActionResponse,
    RetryDocumentsRequest,
    SkipDocumentsRequest,
)
```

### 5f. `analysis_core.py` imports

```python
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import traceback
import uuid
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, List, Literal, Optional

import html2text
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from starlette.concurrency import run_in_threadpool

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.rate_limiter import limiter
from legal_portal.api.routes._analysis_helpers import (
    AnalysisCancelledError,
    AnalysisRequest,
    AnalysisResponse,
    StreamingAnalysisSaveRequest,
    _analysis_is_cancelled,
    # _attach_signed_artifact_urls is core-specific, defined in analysis_core.py itself
    _cancel_analysis,
    _ensure_case_access,
    _fetch_latest_analysis_result,
    _get_user_ai_preferences,
    _update_analysis_progress,
    _update_case_with_retry,
    _upsert_with_retry,
    # Signature helpers used by process_case_background
    _apply_signature_verification_override,
    _extract_signature_verification,
    _infer_signature_detection_from_text,
    _is_signature_inference_candidate,
    _normalize_signature_verification_status,
    _DB_COLUMNS_CACHE,
)
from legal_portal.config.default import get_settings
from legal_portal.core.data_models import (
    ChatMessageRequest,
    ChatMessageResponse,
    ClioMatterContext,
    DocumentStatus,
    DocumentType,
    LetterType,
    ProcessedDocument,
    ProcessingResult,
    SkippedDocument,
)
from legal_portal.services.document_formatter import DocumentFormatterService
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.main_processor import process_case_documents
from legal_portal.services.progress_manager import ProgressManager
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.security import sanitize_text_for_db
from legal_portal.utils.throttled_db_writer import ThrottledDBWriter
from legal_portal.utils.type_safety import safe_str, safe_str_required, sanitize_nested_dict
```

**Note:** Some imports may need adjustment — the exact set depends on which helpers are used by `process_case_background` vs. the endpoints. The implementor should verify by running the app after creating the file.

### 5g. `analysis.py` becomes compatibility shim

```python
"""Backward-compatibility shim — re-exports all symbols moved during Phase 4.

Existing tests import from legal_portal.api.routes.analysis.
This module re-exports so those imports continue to work.
New code should import from the specific module directly.
"""

# Re-export everything from the new modules
from legal_portal.api.routes._analysis_helpers import *  # noqa: F401,F403
from legal_portal.api.routes.gap_routes import *  # noqa: F401,F403
from legal_portal.api.routes.letter_routes import *  # noqa: F401,F403
from legal_portal.api.routes.chat_routes import *  # noqa: F401,F403
from legal_portal.api.routes.document_status_routes import *  # noqa: F401,F403
from legal_portal.api.routes.analysis_core import *  # noqa: F401,F403
```

Each new module will define `__all__` listing its public symbols to control what `*` exports.

**Important:** The `from X import *` re-export creates new bindings on the `analysis` module. Direct attribute access (e.g., `analysis_routes._resolve_letter_identity_context(...)`) works fine. But `monkeypatch.setattr(analysis_routes, "func", mock)` only patches the shim's copy — the real code in the new modules still uses its own import. That's why Task 7 updates the 3 affected test files to patch the correct module.

---

## 6. Circular Import Avoidance Plan

**Risk:** `letter_routes.py` imports `_ensure_fresh_gap_analysis_for_letter_generation` from `gap_routes.py`. If `gap_routes.py` ever imports from `letter_routes.py`, we get a cycle.

**Mitigation:**
1. **Dependency direction is one-way:** `letter_routes → gap_routes → _analysis_helpers`. No reverse.
2. **`_analysis_helpers.py` imports from NO route module.** It only imports from `services/`, `core/`, `utils/`, `config/`.
3. **`analysis.py` (shim) is terminal.** It imports from all route modules but no route module imports from it.
4. **All lazy/inline imports within endpoint bodies are preserved as-is.** They only import from `services/` and `core/`, never from sibling route modules.

Import dependency graph:
```
analysis.py (shim) ──imports──> analysis_core.py
                    ──imports──> gap_routes.py
                    ──imports──> letter_routes.py ──imports──> gap_routes.py
                    ──imports──> chat_routes.py
                    ──imports──> document_status_routes.py
                    ──imports──> _analysis_helpers.py

All route modules ──imports──> _analysis_helpers.py
_analysis_helpers.py ──imports──> services/, core/, utils/, config/ (ONLY)
```

No cycles possible.

---

## 7. Router Registration Changes in `main.py`

**Current (line 129):**
```python
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
```

**After:**
```python
from legal_portal.api.routes import (
    analysis_core,
    chat_routes,
    document_status_routes,
    gap_routes,
    letter_routes,
)

# ... existing router registrations ...

# Analysis routes (split from monolithic analysis.py)
app.include_router(analysis_core.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(gap_routes.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(letter_routes.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(chat_routes.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(document_status_routes.router, prefix="/api/analysis", tags=["analysis"])
```

Remove the old `analysis` import and `analysis.router` registration line. The shim `analysis.py` no longer defines a `router` — each new module has its own.

---

## 8. Safety-Net Tests Required Before Each Move

Before each extraction step, run:
```bash
# Verify app boots
python3 -c "from legal_portal.api.main import app; print('OK')"

# Verify endpoint count unchanged
python3 scripts/validate_endpoints.py --check

# Run full test suite (non-integration)
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration

# Check no dangling references
grep -rn "from legal_portal.api.routes.analysis import" tests/ | grep -v ".pyc"
```

These must all pass after each extraction step with the same results:
- App imports OK
- 71 endpoints
- ≥ 771 tests passing, ≤ 1 pre-existing failure

---

## 9. Ordered Migration Steps

### Chunk 1: Extract shared helpers into `_analysis_helpers.py`

---

### Task 1: Create `_analysis_helpers.py` with shared helpers

**Files:**
- Create: `src/legal_portal/api/routes/_analysis_helpers.py`

- [ ] **Step 1: Read current analysis.py to capture exact source of each helper**

Read lines: 418-433, 436-499, 502-579, 582-760, 763-832, 835-1103, 1234-1287, 3391-3395, 4847-4869, 5447-5460, 5563-5622, 7265-7303, 7551-7586

- [ ] **Step 2: Create `_analysis_helpers.py`**

Write the file with all shared helpers, Pydantic models, constants, and signature-related helpers listed in section 4a. Include an `__all__` list of every exported symbol.

Required imports for this file (derive from the functions being moved):
- Standard lib: `hashlib`, `json`, `logging`, `os`, `re`, `time`, `datetime`, `typing`
- FastAPI: `HTTPException`, `status`
- Internal: `retry_sync`, `get_settings`, `safe_str`, `safe_str_required`, `sanitize_nested_dict`
- Pydantic: `BaseModel`, `Field`, `validator`

- [ ] **Step 3: Verify the module imports cleanly**

Run: `python3 -c "from legal_portal.api.routes._analysis_helpers import _ensure_case_access, AnalysisRequest; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add src/legal_portal/api/routes/_analysis_helpers.py
git commit -m "refactor(phase4): extract shared helpers into _analysis_helpers.py"
```

---

### Task 2: Extract `document_status_routes.py` (simplest — 4 endpoints, minimal deps)

**Files:**
- Create: `src/legal_portal/api/routes/document_status_routes.py`
- Modify: `src/legal_portal/api/routes/analysis.py` (remove moved code)
- Modify: `src/legal_portal/api/main.py` (add router registration)

- [ ] **Step 1: Create `document_status_routes.py`**

Move these endpoints and their Pydantic models:
- `get_document_status` (lines 7305-7348)
- `retry_failed_documents` (lines 7350-7421)
- `skip_failed_documents` (lines 7422-7495)
- `get_analysis_state` (lines 7496-7548)

Models already in `_analysis_helpers.py`: `RetryDocumentsRequest`, `SkipDocumentsRequest`, `DocumentStatusResponse`, `RecoveryActionResponse`

The file gets its own `router = APIRouter()` and imports shared helpers from `_analysis_helpers`.

- [ ] **Step 2: Remove moved code from `analysis.py`**

Delete the 4 endpoint functions and the 4 Pydantic model definitions from `analysis.py`.
Add import re-exports at the top of `analysis.py`:
```python
from legal_portal.api.routes.document_status_routes import router as _doc_status_router  # noqa: F401
```

- [ ] **Step 3: Register new router in `main.py`**

Add import and `app.include_router(document_status_routes.router, prefix="/api/analysis", tags=["analysis"])`.

- [ ] **Step 4: Validate**

```bash
python3 -c "from legal_portal.api.main import app; print('OK')"
python3 scripts/validate_endpoints.py --check
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration
```

Expected: OK, 71 endpoints, ≥ 771 passing

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(phase4): extract document_status_routes.py (4 endpoints)"
```

---

### Task 3: Extract `chat_routes.py` (2 endpoints, minimal deps)

**Files:**
- Create: `src/legal_portal/api/routes/chat_routes.py`
- Modify: `src/legal_portal/api/routes/analysis.py` (remove moved code)
- Modify: `src/legal_portal/api/main.py` (add router registration)

- [ ] **Step 1: Create `chat_routes.py`**

Move these endpoints:
- `stream_chat_response` (lines 2908-2985)
- `case_chat` (lines 7197-7258)

Imports from `_analysis_helpers`: `_ensure_case_access`, `_fetch_latest_analysis_result`, `_get_user_ai_preferences`
Data model imports: `ChatMessageRequest`, `ChatMessageResponse`, `ProcessingResult` from `legal_portal.core.data_models`
Service imports: `CaseChatService`, `OpenAIClient`

- [ ] **Step 2: Remove moved code from `analysis.py`**

Delete the 2 endpoint functions from `analysis.py`.

- [ ] **Step 3: Register new router in `main.py`**

Add: `app.include_router(chat_routes.router, prefix="/api/analysis", tags=["analysis"])`

- [ ] **Step 4: Validate**

```bash
python3 -c "from legal_portal.api.main import app; print('OK')"
python3 scripts/validate_endpoints.py --check
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(phase4): extract chat_routes.py (2 endpoints)"
```

---

### Chunk 2: Extract gap and letter routes

---

### Task 4: Extract `gap_routes.py` (3 endpoints, ~1400 lines of helpers)

**Files:**
- Create: `src/legal_portal/api/routes/gap_routes.py`
- Modify: `src/legal_portal/api/routes/analysis.py` (remove moved code)
- Modify: `src/legal_portal/api/main.py` (add router registration)

- [ ] **Step 1: Create `gap_routes.py`**

Move these endpoints:
- `analyze_gaps_on_demand` (lines 6656-6818)
- `resolve_gaps_and_refresh` (lines 6820-7014)
- `analyze_gaps_streaming` (lines 7016-7195)

Move ALL gap-specific helpers listed in section 4b (from `GapBatch` through `_build_resolution_context`).
Move `_ensure_fresh_gap_analysis_for_letter_generation` (needed by letter_routes).

Import signature helpers from `_analysis_helpers.py`:
- `_apply_signature_verification_override`
- `_infer_signature_detection_from_text`
- `_sample_text_for_state_hash`

Import shared helpers from `_analysis_helpers.py`:
- `_ensure_case_access`, `_fetch_latest_analysis_result`, `_get_user_ai_preferences`
- `GapAnalysisRequest`, `GapResolutionItemRequest`, `GapResolutionRefreshRequest`
- `_GAP_ANALYSIS_INPUT_SCHEMA_VERSION`

Include `__all__` with all public symbols (especially `_ensure_fresh_gap_analysis_for_letter_generation`, `GapBatch`, `_SMALL_GROUP_MERGE_MAP`, and all other test-imported symbols).

- [ ] **Step 2: Remove moved code from `analysis.py`**

Delete the 3 endpoints plus all gap-specific helper functions, constants, and models from `analysis.py`.
Add re-export:
```python
from legal_portal.api.routes.gap_routes import *  # noqa: F401,F403
```

- [ ] **Step 3: Register new router in `main.py`**

Add: `app.include_router(gap_routes.router, prefix="/api/analysis", tags=["analysis"])`

- [ ] **Step 4: Validate**

```bash
python3 -c "from legal_portal.api.main import app; print('OK')"
python3 scripts/validate_endpoints.py --check
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration
# Specifically test gap-related tests
python3 -m pytest tests/unit/test_gap_resolution_helpers.py tests/unit/test_map_reduce_gap_analysis.py -q --tb=short
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(phase4): extract gap_routes.py (3 endpoints, gap helpers)"
```

---

### Task 5: Extract `letter_routes.py` (5 endpoints)

**Files:**
- Create: `src/legal_portal/api/routes/letter_routes.py`
- Modify: `src/legal_portal/api/routes/analysis.py` (remove moved code)
- Modify: `src/legal_portal/api/main.py` (add router registration)

- [ ] **Step 1: Create `letter_routes.py`**

Move these endpoints:
- `stream_findings_letter` (lines 2327-2906)
- `generate_letter` (lines 4296-4845)
- `generate_recommendation_letter` (lines 4871-5059)
- `stream_recommendation_letter` (lines 5060-5445)
- `calculate_demand_amount` (lines 5462-5561)

Import from `_analysis_helpers.py`: all letter-specific helpers and models listed in section 5c.
Import from `gap_routes.py`: `_ensure_fresh_gap_analysis_for_letter_generation`.

Preserve ALL lazy/inline imports within endpoint bodies (e.g., `from legal_portal.core.data_models import DeepAnalysis, FactMatrix, GapAnalysisResult, LetterStructure` etc.)

- [ ] **Step 2: Remove moved code from `analysis.py`**

Delete the 5 endpoints and their specific Pydantic models from `analysis.py`.

- [ ] **Step 3: Register new router in `main.py`**

Add: `app.include_router(letter_routes.router, prefix="/api/analysis", tags=["analysis"])`

- [ ] **Step 4: Validate**

```bash
python3 -c "from legal_portal.api.main import app; print('OK')"
python3 scripts/validate_endpoints.py --check
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(phase4): extract letter_routes.py (5 endpoints)"
```

---

### Chunk 3: Extract core and finalize shim

---

### Task 6: Extract `analysis_core.py` (remaining 8 endpoints + background worker)

**Files:**
- Create: `src/legal_portal/api/routes/analysis_core.py`
- Modify: `src/legal_portal/api/routes/analysis.py` (reduce to shim)
- Modify: `src/legal_portal/api/main.py` (replace old router with new)

- [ ] **Step 1: Create `analysis_core.py`**

Move ALL remaining code from `analysis.py` into `analysis_core.py`:
- 8 remaining endpoints: `start_analysis`, `cancel_analysis`, `cancel_case_analysis`, `get_analysis_status`, `get_analysis_results`, `save_streaming_analysis`, `stream_case_analysis`, `get_streaming_result`
- Background worker: `process_case_background`
- Core-specific helpers: `_extract_deferred_documents`, `_dedup_email_threads`, `_download_and_extract_documents`, artifact helpers, parsing helpers
- Core-specific constants: `ARTIFACT_BUCKET`, `ARTIFACT_PREFIX`, `SIGNED_URL_TTL`, `_HTML2TEXT_CONVERTER`

Import shared helpers from `_analysis_helpers.py`.

Include `__all__` listing: `router`, `process_case_background`, `_extract_deferred_documents`, `_dedup_email_threads`, `get_analysis_results` (all symbols imported by tests). Note: `_fetch_gap_intake_content` lives in `gap_routes.py`, NOT here.

- [ ] **Step 2: Convert `analysis.py` to compatibility shim**

Replace entire contents with the re-export shim from section 5g.
Do NOT define `router` in the shim — the routers are now in the individual modules.

- [ ] **Step 3: Update `main.py`**

Remove old: `from legal_portal.api.routes import analysis` and `app.include_router(analysis.router, ...)`
Add: `from legal_portal.api.routes import analysis_core` and `app.include_router(analysis_core.router, ...)`
(Other 4 routers were already added in previous tasks.)

- [ ] **Step 4: Validate**

```bash
python3 -c "from legal_portal.api.main import app; print('OK')"
python3 scripts/validate_endpoints.py --check
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration
# Verify backward-compat imports still work
python3 -c "from legal_portal.api.routes.analysis import _extract_deferred_documents, GapBatch, _build_gap_analysis_batches; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(phase4): extract analysis_core.py, convert analysis.py to compat shim"
```

---

### Task 7: Fix monkeypatch test targets

**Files:**
- Modify: `tests/api/test_letter_stream_integration.py`
- Modify: `tests/api/test_generate_letter_formatting.py`
- Modify: `tests/unit/test_gap_resolution_helpers.py`

- [ ] **Step 1: Update `test_letter_stream_integration.py`**

Change all `monkeypatch.setattr(analysis_routes, "X", mock)` calls to target `letter_routes` instead:

```python
# Before (at top of file):
from legal_portal.api.routes import analysis as analysis_routes
# After:
from legal_portal.api.routes import letter_routes

# Before (each setattr):
monkeypatch.setattr(analysis_routes, "get_settings", ...)
# After:
monkeypatch.setattr(letter_routes, "get_settings", ...)
```

Targets to retarget: `get_settings`, `_ensure_fresh_gap_analysis_for_letter_generation`, `_get_user_ai_preferences`, `OpenAIClient`, `JsonProcessingService`, `LetterValidationService`, `_emit_generation_metrics`

- [ ] **Step 2: Update `test_generate_letter_formatting.py`**

Same pattern — retarget from `analysis_routes` to `letter_routes`:
Targets: `get_settings`, `_ensure_case_access`, `_ensure_fresh_gap_analysis_for_letter_generation`, `_get_user_ai_preferences`, `OpenAIClient`, `JsonProcessingService`, `_emit_generation_metrics`

- [ ] **Step 3: Update `test_gap_resolution_helpers.py`**

Retarget from `analysis_routes` to `gap_routes`:
```python
# Before:
monkeypatch.setattr(analysis_routes, "_GAP_ANALYSIS_INPUT_SCHEMA_VERSION", ...)
# After:
from legal_portal.api.routes import gap_routes
monkeypatch.setattr(gap_routes, "_GAP_ANALYSIS_INPUT_SCHEMA_VERSION", ...)
```

- [ ] **Step 4: Validate**

```bash
python3 -m pytest tests/api/test_letter_stream_integration.py tests/api/test_generate_letter_formatting.py tests/unit/test_gap_resolution_helpers.py -q --tb=short
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(phase4): retarget monkeypatch.setattr to new route modules"
```

---

### Task 8: Final validation and cleanup

- [ ] **Step 1: Run full validation suite**

```bash
# App imports
python3 -c "from legal_portal.api.main import app; print('OK')"

# Endpoint count unchanged
python3 scripts/validate_endpoints.py --check

# All tests pass
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration

# Import rules
python3 scripts/check_import_rules.py

# Backward-compat imports work
python3 -c "
from legal_portal.api.routes.analysis import (
    _extract_deferred_documents,
    _dedup_email_threads,
    _build_gap_analysis_batches,
    _build_gap_resolution_hash,
    _build_signature_evidence,
    _derive_signature_detection_for_gap_doc,
    _infer_signature_detection_from_text,
    _ensure_case_access,
    _fetch_latest_analysis_result,
    GapBatch,
    GapResolutionItemRequest,
    GapResolutionRefreshRequest,
    get_analysis_results,
    _fetch_gap_intake_content,
    _SMALL_GROUP_MERGE_MAP,
    _build_case_document_state_hash_lightweight,
    _run_gap_analysis,
    _stamp_document_ids,
    _build_case_document_state_hash,
    _build_gap_analysis_input_hash,
    _build_resolution_context,
    _build_supporting_document_hash,
)
print('All backward-compat imports OK')
"

# No endpoint path changes
python3 -c "
from legal_portal.api.main import app
paths = sorted([r.path for r in app.routes if hasattr(r, 'path')])
for p in paths:
    print(p)
" | head -30
```

- [ ] **Step 2: Verify file sizes**

```bash
wc -l src/legal_portal/api/routes/analysis.py \
      src/legal_portal/api/routes/_analysis_helpers.py \
      src/legal_portal/api/routes/analysis_core.py \
      src/legal_portal/api/routes/gap_routes.py \
      src/legal_portal/api/routes/letter_routes.py \
      src/legal_portal/api/routes/chat_routes.py \
      src/legal_portal/api/routes/document_status_routes.py
```

Expected: `analysis.py` ~20 lines (shim), each new module < 2000 lines.

- [ ] **Step 3: Commit if any cleanup was needed**

```bash
git commit -m "refactor(phase4): final validation and cleanup"
```

---

## 10. Validation Commands After Each Extraction Step

After **every** task commit:

```bash
# 1. App boots
python3 -c "from legal_portal.api.main import app; print('OK')"

# 2. Endpoint count unchanged
python3 scripts/validate_endpoints.py --check
# Expected: PASS: All 71 endpoints match baseline.

# 3. Tests pass
python3 -m pytest tests/ -q --tb=short --ignore=tests/integration
# Expected: ≥ 771 passed, ≤ 1 failed (pre-existing)

# 4. Backward-compat imports (after shim is in place)
python3 -c "from legal_portal.api.routes.analysis import _ensure_case_access; print('OK')"
```

If ANY check fails, do NOT proceed to the next task. Fix the issue first.

---

## 11. Rollback Plan

Each extraction step is a separate commit. Rollback any single step:
```bash
git revert <commit-sha>
```

Rollback the entire phase:
```bash
git revert --no-commit <first-phase4-commit>..HEAD
git commit -m "revert: rollback Phase 4 split"
```

No database migrations, no config changes, no schema changes. Pure code reorganization.

---

## 12. Definition of Done

- [ ] `analysis.py` reduced from 7,586 lines to ~20-line compatibility shim
- [ ] 6 new route modules created, each < 2000 lines
- [ ] `_analysis_helpers.py` contains shared helpers only (no endpoints)
- [ ] All 22 endpoints have identical paths, methods, and response contracts
- [ ] `python3 -c "from legal_portal.api.main import app"` succeeds
- [ ] `python3 scripts/validate_endpoints.py --check` reports PASS (71 endpoints)
- [ ] ≥ 771 tests passing (non-integration), ≤ 1 pre-existing failure
- [ ] All existing test imports from `legal_portal.api.routes.analysis` still work via shim
- [ ] All `monkeypatch.setattr` targets updated to point at correct new modules (3 test files)
- [ ] No circular imports (verified by app boot + import checks)
- [ ] Import direction: `routes → _analysis_helpers → services/core/utils/config` (no reverse)
- [ ] 8 separate revertable commits (1 per task)
