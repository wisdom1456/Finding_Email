# Documents Workflow Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make document extraction automatic and invisible, add AI intake-document selection, show a complete per-document Clio import log, and demote manual extract buttons to recovery-only.

**Architecture:** Four independent features sharing one theme (automate, then surface outcomes). Backend is FastAPI (`src/legal_portal/`), frontend SvelteKit 5 with runes (`frontend/src/`). All behavior changes are flag-gated (`ENABLE_AI_INTAKE_SELECTION` backend; `PUBLIC_ENABLE_AUTO_EXTRACT` frontend). Extraction guard and doc-log are additive/backward-compatible and need no flag.

**Tech Stack:** FastAPI, Supabase (PostgREST), OpenAI via `legal_portal.utils.openai_client.OpenAIClient`, Svelte 5 runes, vitest + @testing-library/svelte, pytest.

## Global Constraints

- **Baselines (pre-existing, NOT regressions):** pytest 23 failures (test_synthesis_gate, letter_generation_baseline, letter_stream_integration); vitest 4 failures (progressStore ×3, tabSwitchBehavior ×1); svelte-check 10 errors. Verify every task against these counts, never against zero.
- Python runner: `venv/bin/pytest` from repo root. Frontend: `npx vitest run` from `frontend/`.
- One commit per task, message prefix `feat(...)`/`fix(...)`/`test(...)` as appropriate. Never mix features in one commit.
- Feature flags default **off**: `ENABLE_AI_INTAKE_SELECTION=false`, `PUBLIC_ENABLE_AUTO_EXTRACT` unset/false. Flag-off behavior must be byte-identical to today.
- Svelte 5 runes style (`$state`, `$derived`, `$effect`, `$props`) — match existing component idiom.

---

## Feature A: Extract-endpoint guard (E2)

### Task A1: Skip re-extraction of healthy documents unless forced

**Files:**
- Modify: `src/legal_portal/api/routes/documents.py:1578-1610` (the `POST /{document_id}/extract` route)
- Test: `tests/api/test_extract_guard.py` (create)

**Interfaces:**
- Produces: route gains `force: bool = False` query param. Response for skipped docs: `{"success": true, "skipped": true, "reason": "already_extracted"}`. Guard rule: skip iff `force is False and force_method is None` and the document has non-empty `extracted_text` and status `ready`.
- Consumes: existing `trigger_extraction(document_id, force_method=...)` service call (unchanged).

- [ ] **Step 1: Read the current route** (`documents.py:1578-1610`) to capture its exact dependency signature (`user`, supabase client dep) before writing the test.

- [ ] **Step 2: Write the failing test**

```python
"""Guard: POST /documents/{id}/extract must not re-extract healthy docs."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_doc(extracted: bool):
    return {
        "id": "doc-1",
        "case_id": "case-1",
        "status": "ready" if extracted else "pending",
        "extracted_text": "existing text" if extracted else None,
        "extracted_at": "2026-01-01T00:00:00Z" if extracted else None,
        "storage_path": "u/c/f.pdf",
    }


def _client_with_doc(doc):
    """Build a TestClient with auth + supabase deps overridden."""
    from legal_portal.api.main import app
    from legal_portal.api.routes import documents as documents_module

    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [doc]

    app.dependency_overrides[documents_module.get_current_user] = lambda: {"id": "user-1"}
    app.dependency_overrides[documents_module.get_user_supabase_client] = lambda: supabase
    return TestClient(app)


def test_extract_skips_already_extracted_doc():
    client = _client_with_doc(_make_doc(extracted=True))
    with patch(
        "legal_portal.api.routes.documents.trigger_extraction"
    ) as mock_extract:
        resp = client.post("/api/documents/doc-1/extract")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("skipped") is True
    mock_extract.assert_not_called()


def test_extract_runs_when_forced():
    client = _client_with_doc(_make_doc(extracted=True))
    with patch(
        "legal_portal.api.routes.documents.trigger_extraction"
    ) as mock_extract:
        mock_extract.return_value = {"success": True}
        resp = client.post("/api/documents/doc-1/extract?force=true")
    assert resp.status_code == 200
    mock_extract.assert_called_once()


def test_extract_runs_with_force_method():
    client = _client_with_doc(_make_doc(extracted=True))
    with patch(
        "legal_portal.api.routes.documents.trigger_extraction"
    ) as mock_extract:
        mock_extract.return_value = {"success": True}
        resp = client.post("/api/documents/doc-1/extract?force_method=vision")
    assert resp.status_code == 200
    mock_extract.assert_called_once()


def test_extract_runs_for_unextracted_doc():
    client = _client_with_doc(_make_doc(extracted=False))
    with patch(
        "legal_portal.api.routes.documents.trigger_extraction"
    ) as mock_extract:
        mock_extract.return_value = {"success": True}
        resp = client.post("/api/documents/doc-1/extract")
    assert resp.status_code == 200
    mock_extract.assert_called_once()
```

**IMPORTANT — adapt the test to reality:** before running, check the route's actual imports (dependency names, the extraction function's import path — grep `trigger_extraction` in `documents.py`). Patch whatever the route actually calls. If the route fetches the document differently (service client vs user client), mirror that in the mock. If an existing tests/api conftest provides an app/client fixture, use it instead of hand-rolling.

- [ ] **Step 3: Run test — expect FAIL** (`skipped` missing / extraction called): `venv/bin/pytest tests/api/test_extract_guard.py -v`

- [ ] **Step 4: Implement the guard** in the route, before triggering extraction:

```python
@router.post("/{document_id}/extract")
async def extract_document_text(
    document_id: str,
    force_method: Optional[str] = None,
    force: bool = False,
    ...existing deps...
):
    ...existing document fetch / ownership check...

    already_extracted = bool(
        (doc.get("extracted_text") or "").strip()
    ) and doc.get("status") == "ready"
    if already_extracted and not force and force_method is None:
        logger.info(
            f"Skipping extraction for {document_id}: already extracted (pass force=true to re-extract)"
        )
        return {"success": True, "skipped": True, "reason": "already_extracted"}

    ...existing extraction call...
```

Fit this into the route's real body — keep every existing behavior (auth, 404s, response shape for the non-skip path) identical.

- [ ] **Step 5: Run test — expect PASS**: `venv/bin/pytest tests/api/test_extract_guard.py -v`

- [ ] **Step 6: Frontend recovery caller passes force.** In `frontend/src/lib/components/CorrectionModal.svelte` (the `triggerReExtraction()` function around line 184-212), change the fetch URL from `/api/documents/${id}/extract` to `/api/documents/${id}/extract?force=true` (it's an explicit user-requested re-extraction of possibly-bad text). The case page `reExtractDocument` (`frontend/src/routes/app/cases/[id]/+page.svelte:570-614`) already sends `force_method`, which bypasses the guard — no change. VerificationHub bulk + `bulk-extract` target docs without text — no change.

- [ ] **Step 7: Full backend check vs baseline**: `venv/bin/pytest tests/ -x -q 2>&1 | tail -5` — confirm failure count is the baseline 23 (or fewer), none new.

- [ ] **Step 8: Commit**

```bash
git add src/legal_portal/api/routes/documents.py tests/api/test_extract_guard.py frontend/src/lib/components/CorrectionModal.svelte
git commit -m "feat(documents): skip re-extraction of healthy docs unless forced"
```

---

## Feature B: Auto-extract on case load (E1, flag-gated)

### Task B1: Pure decision helper + auto-run wiring

**Files:**
- Create: `frontend/src/lib/utils/autoExtract.ts`
- Test: `frontend/src/lib/utils/autoExtract.test.ts`
- Modify: `frontend/src/routes/app/cases/[id]/+page.svelte` (onMount / after documents load)

**Interfaces:**
- Produces: `shouldAutoExtract(docs: DocLike[], opts: {flagEnabled: boolean, analysisInProgress: boolean, importInProgress: boolean, alreadyRanThisLoad: boolean}): boolean` — pure, exported.
- Consumes: the page's existing `runOcrOnMissingDocs()` (`+page.svelte:829-886`) which paginates `POST /api/documents/bulk-extract` (server-side filters to docs missing text — inherently non-redundant).

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect } from 'vitest';
import { shouldAutoExtract } from './autoExtract';

const needing = [{ status: 'pending', extracted_at: null, extracted_text: null }];
const healthy = [{ status: 'ready', extracted_at: '2026-01-01', extracted_text: 'x' }];
const skipped = [{ status: 'skipped_small_image', extracted_at: null, extracted_text: null }];
const base = {
	flagEnabled: true,
	analysisInProgress: false,
	importInProgress: false,
	alreadyRanThisLoad: false,
};

describe('shouldAutoExtract', () => {
	it('runs when flag on and docs need extraction', () => {
		expect(shouldAutoExtract(needing as any, base)).toBe(true);
	});
	it('never runs when flag off', () => {
		expect(shouldAutoExtract(needing as any, { ...base, flagEnabled: false })).toBe(false);
	});
	it('does not run when all docs healthy', () => {
		expect(shouldAutoExtract(healthy as any, base)).toBe(false);
	});
	it('ignores skipped documents', () => {
		expect(shouldAutoExtract(skipped as any, base)).toBe(false);
	});
	it('does not run during analysis', () => {
		expect(shouldAutoExtract(needing as any, { ...base, analysisInProgress: true })).toBe(false);
	});
	it('does not run during an import', () => {
		expect(shouldAutoExtract(needing as any, { ...base, importInProgress: true })).toBe(false);
	});
	it('runs at most once per page load', () => {
		expect(shouldAutoExtract(needing as any, { ...base, alreadyRanThisLoad: true })).toBe(false);
	});
});
```

- [ ] **Step 2: Run — expect FAIL** (module missing): `npx vitest run src/lib/utils/autoExtract.test.ts` (from `frontend/`)

- [ ] **Step 3: Implement**

```typescript
// frontend/src/lib/utils/autoExtract.ts
export interface AutoExtractDoc {
	status?: string | null;
	extracted_at?: string | null;
	extracted_text?: string | null;
}

export interface AutoExtractOpts {
	flagEnabled: boolean;
	analysisInProgress: boolean;
	importInProgress: boolean;
	alreadyRanThisLoad: boolean;
}

const EXCLUDED_STATUSES = new Set([
	'skipped_small_image',
	'skipped',
	'duplicate',
	'corrupted',
	'download_failed',
]);

export function docNeedsExtraction(doc: AutoExtractDoc): boolean {
	if (EXCLUDED_STATUSES.has(doc.status ?? '')) return false;
	const hasText = Boolean((doc.extracted_text ?? '').trim());
	return !doc.extracted_at && !hasText;
}

export function shouldAutoExtract(docs: AutoExtractDoc[], opts: AutoExtractOpts): boolean {
	if (!opts.flagEnabled) return false;
	if (opts.analysisInProgress || opts.importInProgress) return false;
	if (opts.alreadyRanThisLoad) return false;
	return docs.some(docNeedsExtraction);
}
```

- [ ] **Step 4: Run — expect PASS**: `npx vitest run src/lib/utils/autoExtract.test.ts`

- [ ] **Step 5: Wire into the case page.** In `frontend/src/routes/app/cases/[id]/+page.svelte`: import `shouldAutoExtract` and `env` from `'$env/dynamic/public'`. Add module-level `let autoExtractRan = $state(false);`. Where documents finish loading (find the existing post-load point — the function that populates the documents list; grep `documents =` in the page), add:

```typescript
if (
	shouldAutoExtract(documents, {
		flagEnabled: env.PUBLIC_ENABLE_AUTO_EXTRACT === 'true',
		analysisInProgress,
		importInProgress: showImportProgress ?? false,
		alreadyRanThisLoad: autoExtractRan,
	})
) {
	autoExtractRan = true;
	runOcrOnMissingDocs(); // existing function, shows its existing progress UI
}
```

Match the page's real variable names for analysis/import state (grep `analysisInProgress`, `showImportProgress` — adapt to what exists; if the page tracks these under different names, use those). Do not remove the manual button in this task (that's Feature E/E3).

- [ ] **Step 6: Full frontend check vs baseline**: `npx vitest run 2>&1 | tail -4` — 4 pre-existing failures only.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/utils/autoExtract.ts frontend/src/lib/utils/autoExtract.test.ts "frontend/src/routes/app/cases/[id]/+page.svelte"
git commit -m "feat(documents): auto-extract missing text on case load behind PUBLIC_ENABLE_AUTO_EXTRACT"
```

---

## Feature C: AI intake-document selection (flag-gated)

### Task C1: Selection service

**Files:**
- Create: `src/legal_portal/services/analysis/intake_selection_service.py`
- Test: `tests/services/test_intake_selection_service.py`

**Interfaces:**
- Produces:

```python
@dataclass
class IntakeSelection:
    chosen_doc_id: str
    reasoning: str
    scores: list[dict]  # [{"doc_id": ..., "score": 0-100, "note": ...}]

def select_intake_document(
    candidates: list[dict],   # doc dicts with at least id, file_name, file_type
    supabase,                 # client able to read documents.extracted_text
    openai_client,            # legal_portal.utils.openai_client.OpenAIClient
) -> Optional[IntakeSelection]
```

Returns `None` on any failure (LLM error, malformed JSON, chosen id not in candidates, <2 candidates) — callers fall back to mechanical selection. Never raises.
- Consumes: `OpenAIClient.create_chat_completion(...)` and `OpenAIClient.parse_json_response(content)` (`src/legal_portal/utils/openai_client.py:330, 249`) — read both signatures before implementing and match them exactly. Model via `openai_client.get_preferred_model("document_analysis", "gpt-5.4-mini")`.

- [ ] **Step 1: Write the failing tests**

```python
"""AI intake selection: pick the most detailed intake doc among candidates."""
from unittest.mock import MagicMock

from legal_portal.services.analysis.intake_selection_service import (
    IntakeSelection,
    select_intake_document,
)


def _candidates():
    return [
        {"id": "d1", "file_name": "Intake Form - General.pdf", "file_type": "application/pdf"},
        {"id": "d2", "file_name": "intake notes.txt", "file_type": "text/plain"},
    ]


def _supabase_with_text():
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": "d1", "extracted_text": "Full client intake: name, dates, damages..."},
        {"id": "d2", "extracted_text": "brief note"},
    ]
    return sb


def _openai_returning(payload):
    client = MagicMock()
    client.get_preferred_model.return_value = "gpt-5.4-mini"
    client.create_chat_completion.return_value = MagicMock()
    client.parse_json_response.return_value = payload
    return client


def test_returns_choice_with_reasoning():
    payload = {
        "chosen_doc_id": "d1",
        "reasoning": "d1 contains full client details",
        "scores": [{"doc_id": "d1", "score": 90, "note": "complete"},
                   {"doc_id": "d2", "score": 20, "note": "sparse"}],
    }
    result = select_intake_document(_candidates(), _supabase_with_text(), _openai_returning(payload))
    assert isinstance(result, IntakeSelection)
    assert result.chosen_doc_id == "d1"
    assert "full client details" in result.reasoning


def test_none_when_fewer_than_two_candidates():
    result = select_intake_document(_candidates()[:1], _supabase_with_text(), _openai_returning({}))
    assert result is None


def test_none_when_llm_raises():
    client = _openai_returning({})
    client.create_chat_completion.side_effect = RuntimeError("boom")
    assert select_intake_document(_candidates(), _supabase_with_text(), client) is None


def test_none_when_chosen_id_not_a_candidate():
    payload = {"chosen_doc_id": "d999", "reasoning": "?", "scores": []}
    assert select_intake_document(_candidates(), _supabase_with_text(), _openai_returning(payload)) is None
```

- [ ] **Step 2: Run — expect FAIL** (module missing): `venv/bin/pytest tests/services/test_intake_selection_service.py -v`

- [ ] **Step 3: Implement the service**

```python
"""Choose the best intake document among multiple 'intake'-labeled candidates.

One LLM call comparing extracted-text snippets. Any failure returns None and
the caller falls back to the mechanical pick — selection must never block or
break an analysis.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 3500

PROMPT_TEMPLATE = """You are selecting the OFFICIAL CLIENT INTAKE DOCUMENT for a legal case.
Below are {n} candidate documents, each with a snippet of its extracted text.
Judge each on: client identity detail, case narrative, key dates, damages/amounts,
contact information, and overall completeness as an intake record.

{candidate_blocks}

Respond with ONLY a JSON object:
{{"chosen_doc_id": "<id>", "reasoning": "<1-2 sentences>",
  "scores": [{{"doc_id": "<id>", "score": <0-100>, "note": "<short>"}}]}}"""


@dataclass
class IntakeSelection:
    chosen_doc_id: str
    reasoning: str
    scores: list = field(default_factory=list)


def select_intake_document(candidates, supabase, openai_client) -> Optional[IntakeSelection]:
    if not candidates or len(candidates) < 2:
        return None
    try:
        ids = [c["id"] for c in candidates]
        rows = (
            supabase.table("documents")
            .select("id, extracted_text")
            .in_("id", ids)
            .execute()
        )
        text_by_id = {r["id"]: (r.get("extracted_text") or "") for r in (rows.data or [])}

        blocks = []
        for c in candidates:
            snippet = text_by_id.get(c["id"], "").strip()[:SNIPPET_CHARS]
            blocks.append(
                f"--- doc_id: {c['id']}\nfilename: {c.get('file_name', '?')}\n"
                f"type: {c.get('file_type', '?')}\ntext snippet:\n{snippet or '(no extracted text)'}\n"
            )
        prompt = PROMPT_TEMPLATE.format(n=len(candidates), candidate_blocks="\n".join(blocks))

        model = openai_client.get_preferred_model("document_analysis", "gpt-5.4-mini")
        response = openai_client.create_chat_completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        payload = openai_client.parse_json_response(content)

        chosen = payload.get("chosen_doc_id")
        if chosen not in set(ids):
            logger.warning(f"[INTAKE-SELECT] LLM chose unknown doc id {chosen!r}; falling back")
            return None
        return IntakeSelection(
            chosen_doc_id=chosen,
            reasoning=str(payload.get("reasoning", ""))[:500],
            scores=payload.get("scores") or [],
        )
    except Exception as e:
        logger.warning(f"[INTAKE-SELECT] selection failed, falling back to mechanical pick: {e}")
        return None
```

**Adapt to reality:** read `OpenAIClient.create_chat_completion` (`openai_client.py:330`) first — if its signature differs (e.g., takes `operation_type` or returns a dict), match it and adjust the mock in the test accordingly. The seeded-request behavior (`_maybe_add_seed`) applies automatically when `ENABLE_DETERMINISTIC_SEED` is on — do not add seed handling here.

- [ ] **Step 4: Run — expect PASS**: `venv/bin/pytest tests/services/test_intake_selection_service.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/services/analysis/intake_selection_service.py tests/services/test_intake_selection_service.py
git commit -m "feat(analysis): AI intake-document selection service"
```

### Task C2: Config flag + orchestrator integration

**Files:**
- Modify: `src/legal_portal/config/default.py` (~line 228, after `enable_citation_annotations`)
- Modify: `src/legal_portal/services/analysis/analysis_orchestrator.py:571-599` (candidate collection) and the post-loop selection point (~line 612)
- Test: `tests/services/test_intake_candidate_collection.py`

**Interfaces:**
- Consumes: `select_intake_document` from Task C1; `get_settings().enable_ai_intake_selection`.
- Produces: `collect_intake_candidate(doc) -> bool` — pure helper exported from the orchestrator module (or a small `intake_candidates.py` util) returning whether a doc is an intake candidate: `doc.get("metadata", {}).get("is_intake_form", False) or ("intake" in doc.get("file_name", "").lower() and doc.get("file_type", "").lower() in PDF_DOCX_TYPES)` — mirroring the existing conditions at `analysis_orchestrator.py:573-583` exactly.

- [ ] **Step 1: Add the flag** in `config/default.py` following the exact pattern of `enable_citation_annotations` (line 228): field name `enable_ai_intake_selection`, default `False`, env `ENABLE_AI_INTAKE_SELECTION`, description "AI-compare multiple intake candidates and pick the most detailed".

- [ ] **Step 2: Write the failing test** for candidate collection parity:

```python
from legal_portal.services.analysis.analysis_orchestrator import is_intake_candidate


def test_metadata_flag_wins():
    assert is_intake_candidate({"metadata": {"is_intake_form": True}, "file_name": "x.eml", "file_type": "message/rfc822"})


def test_pdf_with_intake_in_name():
    assert is_intake_candidate({"metadata": {}, "file_name": "Client Intake.pdf", "file_type": "application/pdf"})


def test_txt_with_intake_in_name_is_not_candidate():
    # mirrors existing behavior: non-PDF/DOCX name matches don't auto-qualify
    assert not is_intake_candidate({"metadata": {}, "file_name": "intake.txt", "file_type": "text/plain"})


def test_unrelated_doc():
    assert not is_intake_candidate({"metadata": {}, "file_name": "Lease.pdf", "file_type": "application/pdf"})
```

- [ ] **Step 3: Run — expect FAIL**: `venv/bin/pytest tests/services/test_intake_candidate_collection.py -v`

- [ ] **Step 4: Implement.** Extract `is_intake_candidate(doc)` in the orchestrator module encoding exactly the current conditions (metadata flag OR pdf/docx+name). In the file-prep loop (`analysis_orchestrator.py:571-599`), leave the existing mechanical replace logic untouched, and additionally collect `intake_candidates: list[tuple[dict, str]]` (doc, temp_path) for every doc where `is_intake_candidate(doc)`. After the loop (before the "no intake form found" fallback at ~line 612), add:

```python
settings = get_settings()
if settings.enable_ai_intake_selection and len(intake_candidates) > 1:
    from legal_portal.services.analysis.intake_selection_service import select_intake_document

    selection = select_intake_document([c for c, _ in intake_candidates], supabase, openai_client)
    if selection:
        chosen_path = next(
            (path for c, path in intake_candidates if c["id"] == selection.chosen_doc_id), None
        )
        if chosen_path and chosen_path != intake_form_path:
            if intake_form_path and intake_form_path not in file_paths:
                file_paths.append(intake_form_path)
            if chosen_path in file_paths:
                file_paths.remove(chosen_path)
            intake_form_path = chosen_path
        chosen_name = next(
            (c.get("file_name") for c, _ in intake_candidates if c["id"] == selection.chosen_doc_id), "?"
        )
        logger.info(
            f"[INTAKE-SELECT] Chose '{chosen_name}' among {len(intake_candidates)} candidates: {selection.reasoning}"
        )
        if progress_callback:
            await progress_callback(
                f"Selected intake document: {chosen_name} (best of {len(intake_candidates)} candidates)",
                ...match the existing progress_callback call signature used nearby...
            )
```

**Adapt to reality:** check how the orchestrator gets `supabase`, `openai_client`, and the progress callback in this function's scope (read the function signature and nearby usage, e.g. line 1118 `OpenAIClient()`); use what exists — if no client is in scope, construct `OpenAIClient()` locally. Persist the selection for display: update the chosen document's metadata:

```python
supabase.table("documents").update(
    {"metadata": {**(chosen_doc.get("metadata") or {}), "intake_selection": {
        "selected": True,
        "reasoning": selection.reasoning,
        "candidates": len(intake_candidates),
    }}}
).eq("id", selection.chosen_doc_id).execute()
```

- [ ] **Step 5: Run tests — expect PASS**, then full backend vs baseline: `venv/bin/pytest tests/services/test_intake_candidate_collection.py -v && venv/bin/pytest tests/ -q 2>&1 | tail -3`

- [ ] **Step 6: Commit**

```bash
git add src/legal_portal/config/default.py src/legal_portal/services/analysis/analysis_orchestrator.py tests/services/test_intake_candidate_collection.py
git commit -m "feat(analysis): flag-gated AI intake selection in orchestrator (ENABLE_AI_INTAKE_SELECTION)"
```

---

## Feature D: Clio import per-document progress log

Spec: `docs/superpowers/specs/2026-07-02-clio-import-doc-log-design.md` — read it first.

### Task D1: doc-log helpers + import-loop integration (backend)

**Files:**
- Create: `src/legal_portal/services/cases/import_doc_log.py`
- Modify: `src/legal_portal/services/cases/clio_import_service.py` (persist_progress ~line 114-140; document loop ~line 351-…; flush at line 611 + error path)
- Test: `tests/services/test_import_doc_log.py`

**Interfaces:**
- Produces (in `import_doc_log.py`):

```python
MAX_LOG_ENTRIES = 500

def append_entry(doc_log: list, index: int, name: str, size_bytes: int) -> dict:
    """Append a 'downloading' entry, enforce cap, return the entry."""

def set_outcome(entry: dict, outcome: str, reason: str | None = None) -> None:
    """outcome ∈ imported|skipped_small_image|duplicate|blacklisted|failed"""
```

Entry shape: `{"i": int, "name": str(≤80), "size_bytes": int, "outcome": str, "reason": str(≤120, only for failed)}`.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

```python
from legal_portal.services.cases.import_doc_log import MAX_LOG_ENTRIES, append_entry, set_outcome


def test_append_creates_downloading_entry():
    log = []
    e = append_entry(log, 1, "Lease Agreement.pdf", 1048576)
    assert log == [e]
    assert e == {"i": 1, "name": "Lease Agreement.pdf", "size_bytes": 1048576, "outcome": "downloading"}


def test_name_trimmed_to_80_chars():
    e = append_entry([], 1, "x" * 200, 10)
    assert len(e["name"]) == 80


def test_set_outcome_and_failed_reason():
    e = append_entry([], 1, "a.pdf", 1)
    set_outcome(e, "failed", reason="r" * 300)
    assert e["outcome"] == "failed"
    assert len(e["reason"]) == 120


def test_cap_drops_oldest():
    log = []
    for i in range(MAX_LOG_ENTRIES + 10):
        append_entry(log, i + 1, f"doc{i}", 1)
    assert len(log) == MAX_LOG_ENTRIES
    assert log[0]["i"] == 11  # oldest 10 dropped


def test_every_document_gets_exactly_one_entry():
    log = []
    for i in range(69):
        append_entry(log, i + 1, f"doc {i}", i)
    assert [e["i"] for e in log] == list(range(1, 70))
```

- [ ] **Step 2: Run — expect FAIL**: `venv/bin/pytest tests/services/test_import_doc_log.py -v`

- [ ] **Step 3: Implement `import_doc_log.py`**

```python
"""Per-document log for Clio import progress.

Accumulated inside the import progress payload so the throttled DB writer
persists the whole history — throttling delays entries (≤3 s) but never
loses them. See docs/superpowers/specs/2026-07-02-clio-import-doc-log-design.md.
"""
from __future__ import annotations

MAX_LOG_ENTRIES = 500
_NAME_MAX = 80
_REASON_MAX = 120


def append_entry(doc_log: list, index: int, name: str, size_bytes: int) -> dict:
    entry = {
        "i": index,
        "name": (name or "Untitled Document")[:_NAME_MAX],
        "size_bytes": int(size_bytes or 0),
        "outcome": "downloading",
    }
    doc_log.append(entry)
    if len(doc_log) > MAX_LOG_ENTRIES:
        del doc_log[: len(doc_log) - MAX_LOG_ENTRIES]
    return entry


def set_outcome(entry: dict, outcome: str, reason: str | None = None) -> None:
    entry["outcome"] = outcome
    if outcome == "failed" and reason:
        entry["reason"] = reason[:_REASON_MAX]
```

- [ ] **Step 4: Run — expect PASS**: `venv/bin/pytest tests/services/test_import_doc_log.py -v`

- [ ] **Step 5: Integrate into the import loop** (`clio_import_service.py`):
  1. Init `doc_log: list = []` before the documents loop (~line 351).
  2. In `persist_progress` (line 114-140): add `"doc_log": doc_log` to `progress_data` when `doc_log` is non-empty. Also pass through `current_doc` if present in kwargs (it's currently dropped from the DB payload): `progress_data["current_doc"] = kwargs.get("current_doc")` when provided. Note `persist_progress` closes over the outer scope — define `doc_log` before it or attach it via a mutable default; keep it simple with a closure variable defined above `persist_progress`.
  3. At the top of each loop iteration (where `persist_progress("Downloading document …")` is called, ~line 355): `entry = append_entry(doc_log, idx + 1, doc_name, doc.get("size", 0))`.
  4. Set outcomes at each branch: blacklisted `continue` → `set_outcome(entry, "blacklisted")` before continue; small-image filter → `set_outcome(entry, "skipped_small_image")`; duplicate detection → `set_outcome(entry, "duplicate")`; per-doc exception handler → `set_outcome(entry, "failed", reason=str(e))`; successful insert → `set_outcome(entry, "imported")`. Read the whole loop body (lines ~351-560) to find every terminal branch — each `continue`/success path must set exactly one outcome.
  5. Ensure `await _import_db_writer.flush()` also runs on the error path: wrap the function's main body's end so both success (existing line 611) and the `except` path flush (add flush inside the top-level exception handler or a `finally`).
  6. Wrap log mutations in the same "never break the import" spirit: the helpers can't raise on normal input; do NOT wrap in try/except that hides logic errors in tests.

- [ ] **Step 6: Full backend vs baseline**: `venv/bin/pytest tests/ -q 2>&1 | tail -3`

- [ ] **Step 7: Commit**

```bash
git add src/legal_portal/services/cases/import_doc_log.py src/legal_portal/services/cases/clio_import_service.py tests/services/test_import_doc_log.py
git commit -m "feat(clio-import): accumulate per-document log with sizes and outcomes in progress payload"
```

### Task D2: progressStore passthrough + modal rendering (frontend)

**Files:**
- Modify: `frontend/src/lib/stores/progressStore.ts` (interface ~line 56-61, initial state ~line 94-95, event merges at lines ~300, ~631, ~738)
- Modify: `frontend/src/lib/components/ClioImportProgressModal.svelte`
- Test: `frontend/src/lib/components/ClioImportProgressModal.docLog.test.ts`

**Interfaces:**
- Consumes: `doc_log` array from the poll payload (entries `{i, name, size_bytes, outcome, reason?}`).
- Produces: `doc_log: DocLogEntry[] | null` on the progress store state.

- [ ] **Step 1: Write the failing component test**

```typescript
import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import { writable } from 'svelte/store';

const mockState = writable<any>({ status: 'idle' });
vi.mock('$lib/stores/progressStore', () => ({ progressStore: mockState }));

import ClioImportProgressModal from './ClioImportProgressModal.svelte';

function docLog() {
	return [
		{ i: 1, name: 'Lease.pdf', size_bytes: 1048576, outcome: 'imported' },
		{ i: 2, name: 'signature.png', size_bytes: 20480, outcome: 'skipped_small_image' },
		{ i: 3, name: 'Contract.pdf', size_bytes: 2097152, outcome: 'downloading' },
	];
}

describe('ClioImportProgressModal doc log', () => {
	it('renders every doc_log entry with number, name and size', async () => {
		render(ClioImportProgressModal, {
			props: { show: true, onClose: vi.fn() },
		});
		mockState.set({
			status: 'active',
			phase: 'import_documents',
			message: 'Downloading document 3 of 3: Contract.pdf',
			percent: 80,
			current_doc: { index: 3, total: 3, name: 'Contract.pdf' },
			doc_log: docLog(),
		});
		await new Promise((r) => setTimeout(r, 0));
		expect(screen.getByText(/Lease\.pdf/)).toBeTruthy();
		expect(screen.getByText(/1\.0 MB/)).toBeTruthy();
		expect(screen.getByText(/signature\.png/)).toBeTruthy();
		expect(screen.getByText(/Contract\.pdf/)).toBeTruthy();
	});

	it('renders classic message list when doc_log absent', async () => {
		render(ClioImportProgressModal, { props: { show: true, onClose: vi.fn() } });
		mockState.set({
			status: 'active',
			phase: 'import_documents',
			message: 'Downloading document 5 of 9: X',
			percent: 50,
		});
		await new Promise((r) => setTimeout(r, 0));
		expect(screen.getByText(/Downloading document 5 of 9/)).toBeTruthy();
	});
});
```

**Adapt to reality:** the modal's real props (check its `Props` interface — it takes `show`, `caseId?`, `importResult?`, `onClose`) and how `$progressStore` is consumed. If mocking the store module conflicts with how the modal imports it, mirror the approach used by the existing passing modal tests (grep for other tests that mock progressStore).

- [ ] **Step 2: Run — expect FAIL**: `npx vitest run src/lib/components/ClioImportProgressModal.docLog.test.ts`

- [ ] **Step 3: Implement store passthrough.** In `progressStore.ts`: add to the state interface `doc_log: Array<{i: number; name: string; size_bytes: number; outcome: string; reason?: string}> | null;`, initial value `null`, and at each of the three event-merge sites (lines ~300, ~631, ~738) add `doc_log: event.doc_log || state.doc_log,`.

- [ ] **Step 4: Implement modal rendering.** In `ClioImportProgressModal.svelte`:
  - Track `docLog = $state<DocLogEntry[]>([])` — inside the existing `$effect`'s `untrack`, set `docLog = state.doc_log ?? docLog`.
  - Add a `formatSize(bytes: number): string` helper (B/KB/MB, one decimal for MB, `—` for 0/undefined) or import the existing `formatFileSize` from `$lib/utils/formatters` if its output fits (`1.0 MB`) — prefer the existing util.
  - In the PROGRESS section markup: `{#if docLog.length > 0}` render a `max-h-64 overflow-y-auto` list bound to an element ref; `$effect` scrolls it to bottom on growth **unless** the user has scrolled up (track `atBottom` on scroll events: `el.scrollHeight - el.scrollTop - el.clientHeight < 24`). Each row:

```svelte
<div class="flex items-center gap-2 text-sm text-gray-600">
	<span class="text-gray-400 w-10 text-right shrink-0">#{entry.i}</span>
	<span class="truncate flex-1" title={entry.name}>{entry.name}</span>
	<span class="text-gray-400 shrink-0">{formatSize(entry.size_bytes)}</span>
	<span class="shrink-0" title={entry.reason ?? ''}>{outcomeBadge(entry.outcome)}</span>
</div>
```

  with `outcomeBadge`: imported ✓, downloading ⬇, skipped_small_image ⤫, duplicate ≡, blacklisted ⊘, failed ✗ (style failed red, imported green, others gray). `{:else}` keep the existing `steps` message list exactly as-is.

- [ ] **Step 5: Run — expect PASS**, then full suite vs baseline: `npx vitest run src/lib/components/ClioImportProgressModal.docLog.test.ts && npx vitest run 2>&1 | tail -4`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/stores/progressStore.ts frontend/src/lib/components/ClioImportProgressModal.svelte frontend/src/lib/components/ClioImportProgressModal.docLog.test.ts
git commit -m "feat(clio-import): render complete per-document log with sizes and outcomes in progress modal"
```

---

## Feature E: Demote manual extract controls to recovery-only (E3)

### Task E1: Conditional visibility

**Files:**
- Modify: `frontend/src/lib/components/DocumentViewerModal.svelte` (footer re-extract buttons, ~line 516-528)
- Modify: `frontend/src/lib/components/VerificationHub.svelte` (bulk "Run OCR" button, ~line 1006-1019)
- Test: `frontend/src/lib/components/DocumentViewerModal.reextractVisibility.test.ts`

**Interfaces:**
- Consumes: `docNeedsExtraction` / recovery semantics from Feature B; `env.PUBLIC_ENABLE_AUTO_EXTRACT`.
- Produces: re-extract buttons visible only when `document.status === 'extraction_failed' || !document.extracted_at || document.extraction_quality === 'low'`; Hub bulk button hidden when the auto-extract flag is on.

- [ ] **Step 1: Write the failing test** (DocumentViewerModal): render with `showReextract: true` and a **healthy** doc (`status: 'ready'`, `extracted_at` set) → `queryByRole('button', {name: /Re-Extract/})` is null; render with `status: 'extraction_failed'` → both Re-Extract buttons present. Reuse the mock scaffolding from `DocumentViewerModal.test.ts` (config/supabase/toast/classification mocks) verbatim.

- [ ] **Step 2: Run — expect FAIL** (buttons currently always shown when `showReextract`).

- [ ] **Step 3: Implement.** In `DocumentViewerModal.svelte` add `const needsRecovery = $derived(Boolean(document && (document.status === 'extraction_failed' || !document.extracted_at || document.extraction_quality === 'low')));` and change the footer condition from `showReextract` to `showReextract && needsRecovery`. In `VerificationHub.svelte`, wrap the bulk "Run OCR on N Docs" button in `{#if env.PUBLIC_ENABLE_AUTO_EXTRACT !== 'true'}` (import `env` from `$env/dynamic/public`) — the auto path replaces it; while the flag is off, the button remains.

- [ ] **Step 4: Run — expect PASS**, full suite vs baseline: `npx vitest run 2>&1 | tail -4`; also `npx svelte-check 2>&1 | tail -2` — 10 pre-existing errors only.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/DocumentViewerModal.svelte frontend/src/lib/components/DocumentViewerModal.reextractVisibility.test.ts frontend/src/lib/components/VerificationHub.svelte
git commit -m "feat(documents): show re-extract controls only for failed/missing extractions"
```

---

## Final verification (after all tasks)

- [ ] `venv/bin/pytest tests/ -q 2>&1 | tail -3` — 23 baseline failures, none new.
- [ ] `cd frontend && npx vitest run 2>&1 | tail -4` — 4 baseline failures, none new.
- [ ] `cd frontend && npx svelte-check 2>&1 | tail -2` — 10 baseline errors, none new.
- [ ] Confirm flag-off inertness: grep that `ENABLE_AI_INTAKE_SELECTION` and `PUBLIC_ENABLE_AUTO_EXTRACT` gate every new behavior path.

---

## Feature F: Stop gap-analysis failure storm on legacy cases (bug fix)

### Task F1: Gate the auto-run on multi-stage support

**Files:**
- Modify: `frontend/src/routes/app/cases/[id]/results/+page.svelte:379-381` (onMount auto-run)
- Test: `frontend/src/lib/components/gapAutoRun.test.ts` (create; pure-helper test)

**Interfaces:**
- Produces: `shouldAutoRunGapAnalysis(opts: {hasMultiStageSupport: boolean, hasGapAnalysis: boolean, autoRunEnabled: boolean}): boolean` — pure, exported from `frontend/src/lib/utils/gapAutoRun.ts` (create).

Background: today `onMount` auto-runs gap analysis whenever `!gapAnalysis`, but cases without `multi_stage_result` (a) hide the Gaps tab entirely (`+page.svelte:82`) and (b) are rejected by the stream endpoint (`gap_routes.py:466-468`), sending the frontend through a stream failure → sync fallback failure → 10×3s retry loop → error toast. The fix: never auto-run when `hasMultiStageSupport` is false.

- [ ] **Step 1: Write the failing test** — `shouldAutoRunGapAnalysis({hasMultiStageSupport: false, hasGapAnalysis: false, autoRunEnabled: true})` must be `false`; true/false matrix for the other combinations (`true,false,true` → true; `true,true,true` → false; `true,false,false` → false).
- [ ] **Step 2: Run — expect FAIL** (module missing).
- [ ] **Step 3: Implement the util** (trivial boolean AND/NOT composition), then replace the inline condition at `+page.svelte:379-381` with a call to it, passing the page's real variables (`hasMultiStageSupport`, `Boolean(gapAnalysis)`, and the existing `autoRunGapAnalysis` prop).
- [ ] **Step 4: Run — expect PASS**; full vitest vs 4-failure baseline.
- [ ] **Step 5: Commit** `fix(results): don't auto-run gap analysis for cases without multi-stage support`

## Feature G: Attorney info prefill for demand letters

### Task G1: Pass profile fields through and send them on the streaming path

**Files:**
- Modify: `frontend/src/routes/app/cases/[id]/results/+page.svelte:1275-1282` (DemandLetterSection props; profile fields already loaded at `:303-307`)
- Modify: `frontend/src/lib/components/DemandLetterSection.svelte` (props ~`:37-40`, streaming params `:159-170`)
- Test: extend existing DemandLetterSection tests if present, else `frontend/src/lib/components/DemandLetterSection.attorneyPrefill.test.ts`

**Interfaces:**
- Produces: `DemandLetterSection` gains optional props `attorneyName`, `firmName`, `contactPhone`, `contactEmail` (strings, default `''`) used as the INITIAL values of its four attorney fields (user edits still win — props seed `$state`, they do not override later edits).
- The streaming generator's params (`:159-170`) must include the four attorney fields exactly as the sync fallback does (`:353-357`) — same param names the backend expects (read the sync path and reuse its names verbatim).

- [ ] **Step 1: Failing test** — render `DemandLetterSection` with the four props and assert the inputs are prefilled; assert (via a fetch/EventSource mock consistent with existing tests in the file's test suite, if any) that generated streaming request includes the attorney params. If no test harness exists for this component's streaming, cover the param-building by extracting `buildDemandStreamParams(...)` as a pure exported function and unit-testing it directly (preferred — matches the codebase's pure-helper pattern).
- [ ] **Step 2: FAIL run.**
- [ ] **Step 3: Implement** — page passes the already-loaded values; component seeds `$state` from props (`let attorneyName = $state(props.attorneyName ?? '')` per Svelte 5 idiom — do NOT use an `$effect` to sync props into state; if live prop updates matter use `$derived` for display-only values, but here seed-once is correct since the user may edit).
- [ ] **Step 4: PASS run; full vitest vs baseline; svelte-check vs 10-error baseline.**
- [ ] **Step 5: Commit** `feat(results): prefill attorney info from profile and send it on the demand streaming path`

## Feature H: Recommendation-letter progress + draft recovery

### Task H1: Render phase progress and recover drafts on stream error

**Files:**
- Modify: `frontend/src/routes/app/cases/[id]/results/+page.svelte:781-808` (`generateRecommendationLetter`) and the recommendation banner/card area (`:1043-1051`) to show progress text
- Test: `frontend/src/lib/components/recommendationLetterStream.test.ts` (pure helper test)

**Interfaces:**
- Produces: `reduceRecommendationStreamEvent(state, event) -> state` — a pure exported reducer in `frontend/src/lib/utils/recommendationLetterStream.ts` handling event types `phase` (sets `phaseLabel`, `percent`), `token` (appends to `markdownBuffer`), `final` (sets `content`, done), `done`, `error` (if `markdownBuffer` non-empty, salvage it as `content` with `recovered: true`, mirroring `DemandLetterSection.svelte:318-328`; else set `error`).
- Consumes: backend event stream shape from `letter_routes.py:1240-1420` (`phase`, `token`, `final`, `done`, `error` events with `percent`/label fields — read the exact field names before implementing).

- [ ] **Step 1: Failing tests** for the reducer: phase event updates label+percent; token accumulates; error after tokens salvages buffer with `recovered: true`; error with empty buffer sets error; final wins over buffer.
- [ ] **Step 2: FAIL run.**
- [ ] **Step 3: Implement reducer; rewire `generateRecommendationLetter`** to drive it and surface `phaseLabel`/`percent` next to the generating button (simple inline text `Generating — {phaseLabel} {percent}%` is enough; no new component). On `recovered`, show the salvaged letter with the existing letter-display path plus a warning toast.
- [ ] **Step 4: PASS run; full vitest vs baseline.**
- [ ] **Step 5: Commit** `feat(results): phase progress and draft recovery for recommendation letter generation`

## Feature I: Results-page consistency batch (small fixes)

### Task I1: Mechanical consistency fixes

**Files:**
- Modify: `frontend/src/lib/components/FindingsEmailSection.svelte:49-52` — add `'repair'` (and verify `context_build` position) to `FINDINGS_PHASE_ORDER` so `indexOf` never returns -1 mid-generation.
- Modify: `frontend/src/lib/components/DemandLetterSection.svelte:42-53, :396` — add `'loading'` to the `DemandGenerationState` union (and a `DEMAND_PHASE_LABELS` entry "Retrying…") OR change `:396` to an existing union member; pick whichever reads cleaner in context.
- Modify: `frontend/src/routes/app/cases/[id]/results/+page.svelte:1298, 1316` — switch `documents` and `fullAnalysis` panels from `{#if}` to the same `class:hidden` pattern the other five tabs use (comment at `:1018` explains why).
- Modify: `frontend/src/routes/app/cases/[id]/results/+page.svelte:68, :170-174` — delete dead `isStale`; the attorney fields become live via Feature G (do not delete them).
- Modify: remove the duplicate `CaseRecommendationCard` at `+page.svelte:1156-1165` (keep the banner at `:1043` and the Gaps-tab card).
- Test: existing suites must stay at baseline; add one vitest for the phase-order fix (state `'repair'` yields non-negative index → progress bar keeps prior phases lit) if FindingsEmailSection has a test harness; otherwise cover by extracting the phase-index lookup into the component's exported helper.

- [ ] **Step 1:** Implement the five mechanical changes.
- [ ] **Step 2:** `npx vitest run` vs 4-failure baseline; `npx svelte-check` vs 10-error baseline (the union fix may REDUCE the error count — record the new count if so).
- [ ] **Step 3: Commit** `fix(results): phase-order, state-union, tab-mount, and duplicate-CTA consistency batch`

**Svelte 5 practice notes for all frontend tasks (from current svelte.dev docs):** prefer `$derived` for computed values — never sync state with an `$effect`; `$effect` is an escape hatch for DOM/async side effects; an effect must not write state it reads (use `untrack` when a read is intentionally non-reactive); seed-once prop→state is plain `$state(prop)`, not an effect.
