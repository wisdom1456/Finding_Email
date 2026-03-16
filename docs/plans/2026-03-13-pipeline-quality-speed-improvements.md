# Pipeline Quality & Speed Improvements — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the analysis and letter generation pipeline faster, smarter about document ordering, and better at producing high-quality findings emails — while cleaning up AI-generated technical debt.

**Architecture:** Replace flat per-document token caps with importance-weighted allocation driven by the existing DocumentRegistryService authority scores. Reduce sequential AI passes in letter generation from 5-6 to 2-3. Extract the 7,600-line analysis.py god file into focused service modules. Consolidate duplicated helpers and dead code.

**Tech Stack:** Python 3.11+, FastAPI, OpenAI API (gpt-5.4/gpt-5-mini), Supabase (PostgreSQL), SSE streaming, tiktoken

---

## Executive Recommendation

**Implementation order rationale:** Start with zero-risk cleanup (dead code, config fixes) to reduce cognitive load. Then implement the highest-value quality improvement (registry-driven context building) while the codebase is cleaner. Then reduce letter generation latency. Finally, tackle the structural refactors that make everything maintainable long-term.

**Why this order:**
1. Phase 1 cleanup removes ~800 lines of noise — makes Phase 2 changes easier to reason about
2. Phase 2 (registry-driven context) is the single highest-leverage quality improvement — it touches only `multi_stage_analyzer.py` and has minimal blast radius
3. Phase 3 (reduce AI passes) directly cuts letter generation time by 40-60%
4. Phase 4 (structural refactors) is important but doesn't change user-visible behavior — defer until the quality/speed wins are shipped

---

## Phase 1: Quick Wins & Cleanup (1-3 Days)

**Objective:** Remove dead code, fix config contradictions, consolidate obvious duplicates. Zero behavior change, reduced maintenance surface.

### Task 1.1: Delete Dead File-Based OCR Functions

**Files:**
- Modify: `src/legal_portal/services/file_processors/pdf_processor.py`

**Context:** The PDF processor contains both file-path-based and bytes-based versions of every OCR function. The file-path versions are never called (confirmed: zero callers outside their own definitions). The bytes-based versions are the active code path (Vercel serverless requires bytes).

**Do Not Break:**
- All bytes-based extraction functions must remain untouched
- The `process_pdf()` entry point and its behavior must not change
- Signature detection logic must remain intact

- [ ] **Step 1: Run existing tests to establish baseline**

Run: `pytest tests/unit/test_pdf_processor.py -v`
Expected: All tests pass (baseline)

- [ ] **Step 2: Verify zero callers of file-based functions**

Run these greps to confirm no callers exist:
```bash
# Each should return ONLY the function definition line, no callers
grep -rn "_extract_text_with_fitz[^_]" src/ --include="*.py"
grep -rn "_extract_text_with_pypdf[^_]" src/ --include="*.py"
grep -rn "_extract_text_via_google_ocr[^_]" src/ --include="*.py"
grep -rn "_extract_text_via_vision[^_]" src/ --include="*.py"
```
Expected: Each returns only its `def` line (no call sites)

- [ ] **Step 3: Delete dead file-based functions**

Delete these functions from `pdf_processor.py`:
- `_extract_text_with_fitz(file_path: str)` (around line 660-667)
- `_extract_text_with_pypdf(file_path: str)` (around line 669-690)
- `_extract_text_via_google_ocr(file_path, ...)` (around line 799-990) — the file-path version
- `_extract_text_via_vision(file_path, ...)` (around line 1214-1410) — the file-path version

Keep all `*_bytes()` variants and `_extract_text_via_google_ocr_bytes()` / `_extract_text_via_vision_bytes()`.

- [ ] **Step 4: Run tests to confirm no regression**

Run: `pytest tests/unit/test_pdf_processor.py tests/unit/test_ocr_compression_chunking.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/services/file_processors/pdf_processor.py
git commit -m "cleanup: remove dead file-based OCR functions from pdf_processor

The bytes-based variants are the only active code path (Vercel serverless).
File-based versions had zero callers confirmed via grep."
```

---

### Task 1.2: Delete Deprecated prompt_and_api_service.py

**Files:**
- Delete: `src/legal_portal/services/prompt_and_api_service.py`

**Context:** This file has a deprecation header and zero imports anywhere in the codebase (confirmed via grep). It was replaced by JsonProcessingService.

- [ ] **Step 1: Confirm zero imports**

```bash
grep -rn "prompt_and_api_service" src/ tests/ --include="*.py"
```
Expected: Only the file's own `__init__.py` entry (if any) or nothing

- [ ] **Step 2: Delete the file**

```bash
rm src/legal_portal/services/prompt_and_api_service.py
```

- [ ] **Step 3: Remove from __init__.py if listed**

Check `src/legal_portal/services/__init__.py` — if it imports or references `prompt_and_api_service`, remove that line.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: No import errors, all tests pass

- [ ] **Step 5: Commit**

```bash
git add -A src/legal_portal/services/
git commit -m "cleanup: remove deprecated prompt_and_api_service.py (zero callers)"
```

---

### Task 1.3: Remove Deprecated Helper Functions

**Files:**
- Modify: `src/legal_portal/utils/helpers.py`
- Modify: `src/legal_portal/services/main_processor.py` (unused import)

- [ ] **Step 1: Confirm `parse_client_name_from_intake` has no callers**

```bash
grep -rn "parse_client_name_from_intake" src/ tests/ --include="*.py"
```
Expected: Only the definition line in helpers.py

- [ ] **Step 2: Delete `parse_client_name_from_intake()` from helpers.py**

Remove the function at lines ~790-810 (marked DEPRECATED in its docstring).

- [ ] **Step 3: Remove unused `SequenceMatcher` import from main_processor.py**

In `src/legal_portal/services/main_processor.py` line 9, delete:
```python
from difflib import SequenceMatcher
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/utils/helpers.py src/legal_portal/services/main_processor.py
git commit -m "cleanup: remove deprecated parse_client_name_from_intake, unused SequenceMatcher import"
```

---

### Task 1.4: Fix Config Contradictions

**Files:**
- Modify: `src/legal_portal/config/default.py`

**Context:** `ocr_remote_enabled: bool = False` (line ~332) contradicts `ocr_remote_required: bool = True` (line ~341). The `openai_timeout` config value (30s) is never used — the client hardcodes 120s.

- [ ] **Step 1: Read current config**

Read `src/legal_portal/config/default.py` to find exact line numbers for:
- `ocr_remote_enabled`
- `ocr_remote_required`
- `openai_timeout`

- [ ] **Step 2: Fix OCR config contradiction**

Change `ocr_remote_required` default to `False` to match `ocr_remote_enabled = False`. Add a comment explaining the relationship:
```python
ocr_remote_enabled: bool = False    # Whether remote OCR service is available
ocr_remote_required: bool = False   # Whether to require remote OCR (only meaningful when enabled)
```

- [ ] **Step 3: Add deprecation comment to openai_timeout**

```python
openai_timeout: float = 30.0  # DEPRECATED: not used — OpenAIClient uses hardcoded httpx timeouts
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/config/default.py
git commit -m "fix: resolve contradictory OCR config defaults, mark unused openai_timeout"
```

---

### Task 1.5: Fix O(n^2) Word Count in Letter Streaming

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py`

**Context:** At line ~2662, every 200 tokens the code runs `re.findall(r"\b[\w'-]+\b", draft_markdown)` over the *entire* accumulated draft. For a 2,000-token letter, this scans the full string ~10 times. Fix: count words incrementally.

**Do Not Break:** SSE word count progress events must still emit at the same frequency with approximately the same values.

- [ ] **Step 1: Read the current implementation**

Read `analysis.py` lines 2620-2670 to see current word count logic.

- [ ] **Step 2: Add incremental word counter**

Before the token loop (around line 2624), add:
```python
_draft_token_count = 0
_last_wc_emit_token = 0
_incremental_wc = 0
```

Then inside the `if msg_type == "token":` block, replace the word count regex scan:
```python
# OLD (around line 2662):
# _wc = len(re.findall(r"\b[\w'-]+\b", draft_markdown))

# NEW: count words in new token only
_incremental_wc += len(re.findall(r"\b[\w'-]+\b", token))
```

And use `_incremental_wc` instead of `_wc` in the progress emission.

- [ ] **Step 3: Update the final word count after the loop**

The `draft_word_count` on line ~2684 can remain as-is (single scan at end is fine):
```python
draft_word_count = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/api/test_letter_stream_integration.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py
git commit -m "perf: replace O(n^2) word count scan with incremental counting in letter stream"
```

---

### Task 1.6: Delete ContentGenerationService Deprecated Stubs

**Files:**
- Modify: `src/legal_portal/services/content_generation_service.py`

- [ ] **Step 1: Read the file and identify deprecated stubs**

Look for methods that return `"[Legacy method - use new architecture]"` or have DEPRECATED docstrings.

- [ ] **Step 2: Confirm zero callers of deprecated methods**

```bash
grep -rn "generate_factual_summary_content" src/ tests/ --include="*.py"
```

- [ ] **Step 3: Delete deprecated method stubs**

Remove any method body that returns a hardcoded deprecation string. If the entire class is deprecated with no live methods, delete the file and remove imports.

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -x -q`

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/services/content_generation_service.py
git commit -m "cleanup: remove deprecated ContentGenerationService stubs"
```

---

**Phase 1 Expected Impact:**
- ~600-800 lines of dead code removed
- Config contradictions resolved
- O(n^2) performance bug fixed in letter streaming
- Zero behavior change for users
- Cleaner codebase for Phase 2 work

**Phase 1 Regression Risk:** Minimal. All changes are deletions of confirmed-unused code or config comment changes. The word count fix changes internal tracking but not visible output.

---

## Phase 2: Registry-Driven Context Building (1-2 Weeks)

**Objective:** Replace flat 1,000-token-per-document caps with importance-weighted allocation using DocumentRegistryService authority scores. This is the single highest-leverage quality improvement.

### Deep Dive: Registry-Driven Context Building Sub-Plan

#### Where Authority Scores Are Produced

`DocumentRegistryService._score_authority()` at `document_registry_service.py:1030-1057`:

| authority_level | Base Score |
|---|---|
| `controlling_signed_instrument` | 95 |
| `controlling_instrument` | 82 |
| `official_record` | 74 |
| `financial_record` | 68 |
| `party_communication` | 64 |
| `offering_material` | 60 |
| `supporting_evidence` | 50 |
| `client_background` | 40 |
| default | 45 |

Modifiers: `+3` for signed, `+4` for key_doc, `+2` for legal_significance, `+1` for important_details. Range: 1-100.

The registry is built in `main_processor.py`:
- Line 927: `build_initial_registry()` per document
- Line 933: `enrich_cross_document()` across all documents
- Line 950: `enrich_with_ai()` with AI summaries

The registry data flows into `multi_stage_result["document_registry"]` and is available during context building.

#### Where Document Ordering Currently Happens

`multi_stage_analyzer.py:104-119` — `_get_doc_priority()`:
```python
# Current: keyword substring matching on doc_type
doc_type = (summary.document_type or "").lower()
for key, pri in _DOC_TYPE_PRIORITY.items():
    if key in doc_type:
        return pri
return 5  # default
```

This is used in `_build_condensed_context()` at line 136 to sort documents before applying the flat 1K token cap.

#### How to Replace Flat Caps with Weighted Allocation

**New approach:**

1. Accept `document_registry` as input to `_build_condensed_context()`
2. Build a lookup from `document_name → authority_score` from registry
3. Compute per-document token allocation proportional to authority score
4. Replace `_MAX_ENTRY_TOKENS = 1000` with dynamic allocation

**Suggested token allocation tiers:**

| Authority Score Range | Tier | Token Budget | Rationale |
|---|---|---|---|
| 80-100 | Controlling | 4,000 tokens | Signed contracts, controlling instruments — need full clause text |
| 65-79 | Primary | 2,000 tokens | Official records, financial records — need key details |
| 50-64 | Supporting | 1,000 tokens | Communications, supporting evidence — summary sufficient |
| 1-49 | Background | 400 tokens | Client background, low-relevance — metadata + brief summary |

**Total budget remains 50K tokens** — allocation just shifts to where it matters.

**Low-priority document handling:**
- Tier "Background" documents (score < 50): Include as metadata-only entry if budget tight:
  `"[15] Cover Letter (correspondence) — present in case file, authority_score=38"`
- Documents that don't fit at all: Listed in `omitted_doc_names` (existing behavior)

#### Shadow Mode / Rollout Strategy

1. First: implement the new allocation alongside the old one, log both results
2. Compare: for 5-10 real cases, log which documents got more/less tokens under each approach
3. Switch: once satisfied that controlling instruments consistently get more budget, make it the default
4. The `ContextBuildResult` dataclass already returns `docs_in_scope`, `docs_omitted`, `omitted_doc_names` — use these for comparison logging

---

### Task 2.1: Add Authority-Score Lookup to Context Builder

**Files:**
- Modify: `src/legal_portal/services/multi_stage_analyzer.py`
- Create: `tests/unit/test_weighted_context_builder.py`

**Do Not Break:**
- Existing `_build_condensed_context()` behavior when no registry is provided (backward compat)
- `ContextBuildResult` dataclass shape
- `analyze_streaming()` return type and behavior

- [ ] **Step 1: Write failing test for authority-score-based token allocation**

Create `tests/unit/test_weighted_context_builder.py`:
```python
"""Tests for importance-weighted document context building."""
import pytest
from unittest.mock import MagicMock
from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer
from legal_portal.core.data_models import DocumentSummaryStructured


def _make_summary(name: str, doc_type: str, content: str) -> DocumentSummaryStructured:
    """Create a minimal DocumentSummaryStructured for testing."""
    return DocumentSummaryStructured(
        document_name=name,
        document_type=doc_type,
        key_content=content,
        executive_summary=content[:200],
    )


def _make_registry_entry(name: str, authority_score: int, authority_level: str = "supporting_evidence") -> dict:
    return {
        "document_name": name,
        "authority_score": authority_score,
        "authority_level": authority_level,
        "is_key_document": authority_score >= 80,
    }


class TestWeightedContextBuilding:
    """Test that authority scores drive token allocation."""

    def setup_method(self):
        mock_client = MagicMock()
        self.analyzer = MultiStageAnalyzer(openai_client=mock_client)

    def test_high_authority_doc_gets_more_tokens_than_low(self):
        """A controlling instrument (score 95) should get more token budget
        than a correspondence document (score 40)."""
        # Create two docs with same-length content
        long_content = "Important contract clause. " * 200  # ~1000 words
        summaries = [
            _make_summary("Cover Letter", "correspondence", long_content),
            _make_summary("Signed Contract", "controlling_instrument", long_content),
        ]
        registry = [
            _make_registry_entry("Cover Letter", 40, "client_background"),
            _make_registry_entry("Signed Contract", 95, "controlling_signed_instrument"),
        ]

        result = self.analyzer._build_condensed_context(
            summaries,
            max_tokens=10_000,
            document_registry=registry,
        )

        # The signed contract should appear before the cover letter
        lines = result.context_text.split("\n")
        contract_idx = next(i for i, l in enumerate(lines) if "Signed Contract" in l)
        cover_idx = next(i for i, l in enumerate(lines) if "Cover Letter" in l)
        assert contract_idx < cover_idx, "High-authority doc should appear first"

        # The signed contract entry should be longer (more tokens allocated)
        contract_block = []
        cover_block = []
        current = None
        for line in lines:
            if "Signed Contract" in line:
                current = "contract"
            elif "Cover Letter" in line:
                current = "cover"
            elif line.strip() == "":
                current = None
            if current == "contract":
                contract_block.append(line)
            elif current == "cover":
                cover_block.append(line)

        contract_text = "\n".join(contract_block)
        cover_text = "\n".join(cover_block)
        assert len(contract_text) > len(cover_text), (
            f"High-authority doc should get more text. "
            f"Contract: {len(contract_text)} chars, Cover: {len(cover_text)} chars"
        )

    def test_backward_compat_no_registry(self):
        """When no registry is provided, behavior matches original flat-cap logic."""
        content = "Some document content. " * 100
        summaries = [
            _make_summary("Doc A", "contract", content),
            _make_summary("Doc B", "correspondence", content),
        ]

        result_old = self.analyzer._build_condensed_context(summaries, max_tokens=10_000)
        result_new = self.analyzer._build_condensed_context(
            summaries, max_tokens=10_000, document_registry=None,
        )

        assert result_old.docs_in_scope == result_new.docs_in_scope
        assert result_old.context_text == result_new.context_text

    def test_metadata_only_for_low_authority_when_budget_tight(self):
        """When budget is tight, low-authority docs should appear as metadata-only."""
        long_content = "Detailed legal analysis. " * 500
        short_content = "Brief note."
        summaries = [
            _make_summary("Main Contract", "controlling_instrument", long_content),
            _make_summary("FYI Email", "correspondence", short_content),
        ]
        registry = [
            _make_registry_entry("Main Contract", 95),
            _make_registry_entry("FYI Email", 35),
        ]

        # Very tight budget — only room for one full doc
        result = self.analyzer._build_condensed_context(
            summaries,
            max_tokens=2_000,
            document_registry=registry,
        )

        assert result.docs_in_scope >= 1
        # Main Contract should be included with content
        assert "Main Contract" in result.context_text
        assert "Detailed legal analysis" in result.context_text

    def test_total_budget_respected(self):
        """Total tokens should not exceed max_tokens regardless of weighting."""
        content = "Word " * 2000
        summaries = [
            _make_summary(f"Doc {i}", "contract", content) for i in range(20)
        ]
        registry = [
            _make_registry_entry(f"Doc {i}", 90) for i in range(20)
        ]

        result = self.analyzer._build_condensed_context(
            summaries,
            max_tokens=10_000,
            document_registry=registry,
        )

        assert result.total_tokens <= 10_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_weighted_context_builder.py -v`
Expected: FAIL — `_build_condensed_context` doesn't accept `document_registry` parameter yet

- [ ] **Step 3: Implement weighted token allocation**

Modify `multi_stage_analyzer.py`:

**A) Add token tier constants** (after line 59):
```python
# --- Importance-weighted token allocation tiers ---
_TOKEN_TIERS = {
    # (min_authority_score, max_tokens_per_doc)
    "controlling": (80, 4_000),   # Signed instruments, controlling docs
    "primary":     (65, 2_000),   # Official/financial records
    "supporting":  (50, 1_000),   # Communications, evidence
    "background":  (0,    400),   # Low-relevance, metadata-heavy
}

def _get_token_budget_for_authority(authority_score: int) -> int:
    """Return per-document token budget based on authority score."""
    for _tier_name, (min_score, budget) in _TOKEN_TIERS.items():
        if authority_score >= min_score:
            return budget
    return 400  # absolute floor
```

**B) Add registry lookup helper** (as a static method):
```python
@staticmethod
def _build_authority_lookup(
    document_registry: Optional[List[Dict[str, Any]]],
) -> Dict[str, int]:
    """Build document_name -> authority_score lookup from registry."""
    if not document_registry:
        return {}
    lookup = {}
    for entry in document_registry:
        name = (entry.get("document_name") or "").strip()
        score = int(entry.get("authority_score") or 45)
        if name:
            lookup[name] = score
    return lookup
```

**C) Modify `_build_condensed_context` signature and logic:**

Change the method signature to accept optional `document_registry`:
```python
def _build_condensed_context(
    self,
    document_summaries: List[DocumentSummaryStructured],
    max_tokens: int = _DEFAULT_BUDGET_TOKENS,
    document_registry: Optional[List[Dict[str, Any]]] = None,
) -> ContextBuildResult:
```

Replace the sorting and per-doc cap logic:
```python
    from legal_portal.utils.token_manager import TokenManager
    tm = TokenManager()

    authority_lookup = self._build_authority_lookup(document_registry)
    use_weighted = bool(authority_lookup)

    # Sort by authority score (desc) if registry available, else by type priority
    if use_weighted:
        indexed = [
            (authority_lookup.get((s.document_name or "").strip(), 45), idx, s)
            for idx, s in enumerate(document_summaries)
        ]
        # Higher authority = processed first (sort descending by score)
        indexed.sort(key=lambda x: (-x[0], x[1]))
    else:
        indexed = [
            (self._get_doc_priority(s), idx, s)
            for idx, s in enumerate(document_summaries)
        ]
        indexed.sort(key=lambda x: (x[0], x[1]))

    lines: list[str] = []
    total_tokens = 0
    included = 0
    omitted_names: list[str] = []

    for score_or_pri, _orig_idx, summary in indexed:
        doc_name = summary.document_name or "unknown"
        doc_type = summary.document_type or "document"

        # Determine per-doc token cap
        if use_weighted:
            doc_token_cap = _get_token_budget_for_authority(score_or_pri)
        else:
            doc_token_cap = _MAX_ENTRY_TOKENS  # legacy flat cap

        content = (summary.key_content or summary.executive_summary or "")[:doc_token_cap * 4]

        entry = f"[{included + 1}] {doc_name} ({doc_type})\n    {content}\n"

        entry_tokens = tm.estimate_tokens_detailed(entry)
        if entry_tokens > doc_token_cap:
            ratio = doc_token_cap / entry_tokens
            truncated_len = int(len(content) * ratio)
            content = content[:truncated_len]
            entry = f"[{included + 1}] {doc_name} ({doc_type})\n    {content}\n"
            entry_tokens = tm.estimate_tokens_detailed(entry)

        if total_tokens + entry_tokens > max_tokens:
            # Budget exhausted — add metadata-only entry for low-authority docs
            if use_weighted and score_or_pri < 50:
                meta_entry = f"[—] {doc_name} ({doc_type}) — present in case file, not analyzed in detail\n"
                meta_tokens = tm.estimate_tokens_detailed(meta_entry)
                if total_tokens + meta_tokens <= max_tokens:
                    lines.append(meta_entry)
                    total_tokens += meta_tokens
            omitted_names.append(doc_name)
            continue

        lines.append(entry)
        total_tokens += entry_tokens
        included += 1

    docs_omitted = len(document_summaries) - included
    omission_reason = ""
    if docs_omitted > 0:
        omission_reason = (
            f"Token budget ({max_tokens:,} tokens) reached after {included} docs. "
            f"{docs_omitted} lower-priority documents excluded."
        )
        if use_weighted:
            omission_reason += " (importance-weighted allocation active)"
        logger.warning(f"[ANALYSIS:BUDGET] {omission_reason}")

    logger.info(
        f"[ANALYSIS:CONTEXT] Included {included}/{len(document_summaries)} docs | "
        f"{total_tokens:,} tokens | weighted={use_weighted}"
    )

    return ContextBuildResult(
        context_text="\n".join(lines),
        docs_in_scope=included,
        docs_omitted=docs_omitted,
        total_tokens=total_tokens,
        omitted_doc_names=omitted_names,
        omission_reason=omission_reason,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_weighted_context_builder.py -v`
Expected: All 4 tests pass

- [ ] **Step 5: Run existing context builder tests for backward compat**

Run: `pytest tests/test_context_builder.py -v`
Expected: All existing tests still pass (no registry provided = old behavior)

- [ ] **Step 6: Commit**

```bash
git add src/legal_portal/services/multi_stage_analyzer.py tests/unit/test_weighted_context_builder.py
git commit -m "feat: importance-weighted token allocation in context builder

Documents with higher authority scores (controlling instruments, signed
contracts) now get up to 4x more token budget than low-priority documents.
Backward compatible — no registry = original flat-cap behavior."
```

---

### Task 2.2: Wire Registry Data into Context Building Call Site

**Files:**
- Modify: `src/legal_portal/services/multi_stage_analyzer.py` (the `analyze_streaming` method)
- Modify: `src/legal_portal/services/main_processor.py` (pass registry to analyzer)

**Context:** The registry is already built in `main_processor.py` at line ~933 and stored in `multi_stage_result["document_registry"]`. We need to pass it through to `_build_condensed_context()`.

**Do Not Break:**
- `analyze_streaming()` return type `Tuple[AsyncGenerator, ContextBuildResult]`
- `process_case_documents()` return type and behavior
- SSE streaming behavior

- [ ] **Step 1: Write test for registry data flowing through analyze_streaming**

Add to `tests/unit/test_weighted_context_builder.py`:
```python
class TestRegistryWiring:
    """Test that registry data flows from analyze_streaming to context builder."""

    def setup_method(self):
        mock_client = MagicMock()
        self.analyzer = MultiStageAnalyzer(openai_client=mock_client)

    def test_analyze_streaming_accepts_document_registry(self):
        """analyze_streaming should accept and use document_registry parameter."""
        import inspect
        sig = inspect.signature(self.analyzer.analyze_streaming)
        assert "document_registry" in sig.parameters, (
            "analyze_streaming must accept document_registry parameter"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_weighted_context_builder.py::TestRegistryWiring -v`
Expected: FAIL

- [ ] **Step 3: Add document_registry parameter to analyze_streaming**

In `multi_stage_analyzer.py`, modify `analyze_streaming()` (line ~370):
```python
async def analyze_streaming(
    self,
    intake_content: str,
    document_summaries: List[DocumentSummaryStructured],
    jurisdiction: str = "Florida",
    document_registry: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[AsyncGenerator[str, None], ContextBuildResult]:
```

And pass it to `_build_condensed_context()` (line ~396):
```python
ctx = self._build_condensed_context(
    document_summaries,
    document_registry=document_registry,
)
```

- [ ] **Step 4: Update main_processor.py to pass registry**

In `main_processor.py`, find where `analyze_streaming()` is called and add the registry:
```python
# Where analyze_streaming is called, add document_registry parameter:
generator, ctx = await analyzer.analyze_streaming(
    intake_content=intake_content,
    document_summaries=document_summaries,
    jurisdiction=jurisdiction,
    document_registry=document_registry,  # NEW: pass registry for weighted allocation
)
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/unit/test_weighted_context_builder.py tests/unit/test_multi_stage_analyzer.py tests/unit/test_main_processor.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/legal_portal/services/multi_stage_analyzer.py src/legal_portal/services/main_processor.py tests/unit/test_weighted_context_builder.py
git commit -m "feat: wire document registry into analyze_streaming for weighted context

Registry authority scores now flow from main_processor through to context
building, enabling importance-weighted token allocation for all analyses."
```

---

### Task 2.3: Add Comparison Logging (Shadow Mode)

**Files:**
- Modify: `src/legal_portal/services/multi_stage_analyzer.py`

**Context:** Before fully switching to weighted allocation as the default, log both old and new results for comparison. This lets us validate the improvement on real cases before committing.

- [ ] **Step 1: Add comparison logging to _build_condensed_context**

When `document_registry` is provided, also compute what the old (flat-cap) approach would have produced, and log the difference:

```python
if use_weighted:
    # Shadow comparison: what would flat-cap have produced?
    old_result = self._build_condensed_context(
        document_summaries, max_tokens=max_tokens, document_registry=None,
    )
    if old_result.docs_in_scope != included:
        logger.info(
            f"[ANALYSIS:WEIGHTED_COMPARE] "
            f"Flat: {old_result.docs_in_scope} docs, {old_result.total_tokens:,} tokens | "
            f"Weighted: {included} docs, {total_tokens:,} tokens | "
            f"Omitted changed: {old_result.omitted_doc_names[:5]} -> {omitted_names[:5]}"
        )
```

**Important:** Add a guard to prevent infinite recursion — the shadow call passes `document_registry=None` so it won't recurse.

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_weighted_context_builder.py -v`
Expected: All pass (shadow logging is additive, doesn't change behavior)

- [ ] **Step 3: Commit**

```bash
git add src/legal_portal/services/multi_stage_analyzer.py
git commit -m "feat: add shadow comparison logging for weighted vs flat context building

Logs both approaches when registry is available, enabling validation
on real cases before removing the flat-cap fallback."
```

---

### Task 2.4: Update Letter Generation Context to Use Registry

**Files:**
- Modify: `src/legal_portal/services/json_processing_service.py`

**Context:** The letter generation prompt in `_build_adaptive_findings_prompt()` (line ~930) already receives `document_registry` but uses it only for display context, not for controlling how much text from each document goes into the prompt. Apply the same weighted logic when selecting `document_summaries_for_context`.

**Do Not Break:**
- `stream_findings_letter_adaptive()` return type (AsyncGenerator)
- `generate_findings_letter_adaptive()` return type (str)
- Prompt must remain under model context limits

- [ ] **Step 1: Read _build_adaptive_findings_prompt to understand current doc inclusion**

Read `json_processing_service.py` lines 930-1020 to see how `document_summaries_for_context` is currently used.

- [ ] **Step 2: Add document sorting by authority score**

In `_build_adaptive_findings_prompt`, before including document summaries in the prompt, sort them by authority score (descending) using the registry:

```python
# Sort document summaries by authority for prompt inclusion
if document_registry and document_summaries_for_context:
    authority_lookup = {
        (entry.get("document_name") or "").strip(): int(entry.get("authority_score") or 45)
        for entry in document_registry
        if isinstance(entry, dict)
    }
    document_summaries_for_context = sorted(
        document_summaries_for_context,
        key=lambda d: -authority_lookup.get((d.get("document_name") or "").strip(), 45),
    )
```

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/unit/test_json_processing_repair.py tests/api/test_letter_stream_integration.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/legal_portal/services/json_processing_service.py
git commit -m "feat: sort document summaries by authority score in letter prompt

Higher-authority documents now appear first in the letter generation
prompt, reducing the chance that critical legal instruments are truncated."
```

---

**Phase 2 Expected Impact:**
- **Quality:** Controlling instruments get 4x more token budget → better factual grounding in letters
- **Speed:** No change (same total token budget, just better allocated)
- **Maintainability:** Clear token allocation policy replaces ad-hoc keyword matching

**Phase 2 Regression Risk:** Medium. Mitigated by:
- Backward compatibility when no registry provided
- Shadow comparison logging for real-case validation
- Existing test suites remain passing

**Phase 2 Verification Plan:**
1. Run full test suite after each task
2. Process 3-5 real cases and compare letter quality (manual review)
3. Check shadow comparison logs for expected behavior (controlling instruments getting more tokens)
4. Verify SSE streaming still works end-to-end

---

## Phase 3: Reduce Letter Generation AI Passes (1-2 Weeks)

**Objective:** Cut letter generation time by 40-60% by reducing sequential model calls from 5-6 to 2-3.

**Current pipeline (5-6 calls):**
1. Strategy (gpt-5-mini) — builds letter strategy object
2. Draft (gpt-5.4) — generates letter markdown
3. Lint (deterministic) — checks quality rules
4. Critic (gpt-5-mini) — AI review of lint violations
5. Repair (gpt-5-mini) — AI fix of violations
6. Polish (gpt-5.2) — prose formatting pass

**Target pipeline (2-3 calls):**
1. Strategy (gpt-5-mini) — keep as-is (fast, useful)
2. Draft (gpt-5.4) — merge polish instructions into draft prompt
3. Conditional repair (gpt-5-mini) — only if lint finds severity=error violations; merge critic into repair prompt

### Task 3.1: Merge Polish Instructions into Draft Prompt

**Files:**
- Modify: `src/legal_portal/services/json_processing_service.py` (`_findings_writer_instructions` at line ~1257)
- Modify: `src/legal_portal/api/routes/analysis.py` (skip polish pass)
- Read: `src/legal_portal/utils/letter_polish.py` (extract key instructions)

**Do Not Break:**
- Letter must still pass all lint checks
- Formatting quality must remain at least equal
- `letter_polish_enabled` config flag must still be respected (set to False to disable)

- [ ] **Step 1: Read the polish prompt to extract key instructions**

Read `src/legal_portal/utils/letter_polish.py` to find the formatting instructions currently sent as a separate AI call.

- [ ] **Step 2: Append key polish instructions to `_findings_writer_instructions()`**

In `json_processing_service.py` at line ~1257, append to the system instructions the formatting rules currently in the polish prompt. Example additions:
- "Use 'I recommend' not 'we recommend'"
- "Replace 'you state' with 'you have indicated'"
- Section formatting rules
- Do NOT include tone-softening rules that weaken legal precision (e.g., "you claim" → "based on what you've shared" — this loses legal meaning)

- [ ] **Step 3: Add config-gated skip for polish pass in analysis.py**

In `analysis.py` around line 2792, change the polish pass to be skipped by default when the draft prompt already includes polish instructions:

```python
# Polish pass: skip when draft prompt already includes formatting instructions
_polish_already_in_draft = True  # Set to False to re-enable separate polish
if getattr(settings, "letter_polish_enabled", True) and not _polish_already_in_draft:
    # ... existing polish logic ...
```

- [ ] **Step 4: Write test comparing output with/without separate polish**

Create a test that verifies the letter still passes lint without the polish pass.

- [ ] **Step 5: Run tests**

Run: `pytest tests/api/test_letter_stream_integration.py tests/unit/test_letter_polish.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/legal_portal/services/json_processing_service.py src/legal_portal/api/routes/analysis.py
git commit -m "perf: merge polish instructions into draft prompt, skip separate polish pass

Eliminates one AI model call (~15-30s) from letter generation.
Polish formatting rules are now part of the primary draft prompt."
```

---

### Task 3.2: Merge Critic into Repair Pass

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (lines ~2720-2790)
- Modify: `src/legal_portal/services/json_processing_service.py` (`repair_letter_constraints`)

**Do Not Break:**
- Lint violations must still be detected and repaired when they exist
- Quality report must still be persisted with generation metrics
- Repair must still only trigger when lint fails

- [ ] **Step 1: Read current critic + repair flow**

Read `analysis.py` lines 2718-2790 to understand the current two-step flow.

- [ ] **Step 2: Modify repair to include critic reasoning**

In `json_processing_service.py`, modify `repair_letter_constraints()` (line ~53) to include critic-style reasoning in its prompt. Instead of two calls (critic identifies issues → repair fixes them), make one call that both diagnoses and fixes:

Add to the repair prompt:
```
First, identify which violations are genuine quality issues vs. false positives.
Then, fix only the genuine issues while preserving all facts, dates, amounts, and party names.
```

- [ ] **Step 3: Remove separate critic call from analysis.py**

In `analysis.py`, remove the critic block (lines ~2720-2746) and pass lint violations directly to repair:

```python
# OLD: critic → repair (two calls)
# NEW: repair with integrated diagnosis (one call)
if (
    settings.letter_conditional_repair_enabled
    and not quality_report.get("lint_passed", True)
    and settings.letter_quality_lint_enabled
):
    remaining_after_lint = _remaining_seconds(internal_deadline)
    if remaining_after_lint >= (repair_budget + finalize_budget):
        phase_msg = _emit("phase", phase="repair", message="Repairing quality issues")
        if phase_msg:
            yield phase_msg
        metrics["repair_attempted"] = True
        metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
        repaired = await json_service.repair_letter_constraints(
            draft_markdown,
            quality_report.get("violations", []),
            mode=mode,
            model="gpt-5-mini",
        )
        # ... rest of repair logic unchanged ...
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/api/test_letter_stream_integration.py tests/unit/test_json_processing_repair.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py src/legal_portal/services/json_processing_service.py
git commit -m "perf: merge critic into repair pass, eliminating one AI call

Letter quality repair now diagnoses and fixes violations in a single
model call instead of two sequential calls (critic + repair)."
```

---

### Task 3.3: Gate Repair on Error-Severity Violations Only

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py`

**Context:** Currently repair triggers on ANY lint failure. Most warnings don't meaningfully affect letter quality. Only trigger repair when there are `severity=error` violations.

- [ ] **Step 1: Modify repair gate condition**

In `analysis.py`, change the repair trigger (around line 2748):

```python
# Only repair for error-severity violations, not warnings
error_violations = [
    v for v in quality_report.get("violations", [])
    if v.get("severity") == "error"
]
if (
    settings.letter_conditional_repair_enabled
    and error_violations  # Changed: only on errors, not all failures
    and settings.letter_quality_lint_enabled
):
    # ... pass error_violations instead of all violations ...
    repaired = await json_service.repair_letter_constraints(
        draft_markdown,
        error_violations,  # Only errors
        mode=mode,
        model="gpt-5-mini",
    )
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/api/test_letter_stream_integration.py -v`

- [ ] **Step 3: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py
git commit -m "perf: only trigger repair pass for error-severity lint violations

Warning-level violations no longer trigger a repair model call,
reducing unnecessary latency for letters that are substantively correct."
```

---

**Phase 3 Expected Impact:**
- **Speed:** ~40-60% reduction in letter generation time (eliminate 2-3 model calls × 10-30s each)
- **Quality:** Equal or better — polish instructions baked into draft prompt produce more consistent output
- **Hallucination risk:** Reduced — fewer rewrite passes = fewer opportunities for fact drift

**Phase 3 Regression Risk:** Medium-High. Mitigated by:
- Lint checks are deterministic and still run
- Repair still triggers for genuine errors
- `letter_polish_enabled` config flag preserved as escape hatch

---

## Phase 4: Structural Refactors (2-4 Weeks)

**Objective:** Break up analysis.py, consolidate duplicated helpers and validation services. Improves maintainability and testability without changing user-visible behavior.

### Task 4.1: Extract Analysis Orchestrator from analysis.py

**Files:**
- Create: `src/legal_portal/services/analysis_orchestrator.py`
- Modify: `src/legal_portal/api/routes/analysis.py`

**What to extract:** `process_case_background()` and its helper functions (~700 lines):
- `_extract_deferred_documents()`
- `_dedup_email_threads()`
- `_dedup_content_hashes()`
- `_download_and_extract_documents()`
- All signature detection helpers

**What stays in analysis.py:** Route handlers only — thin wrappers that validate input and delegate to services.

**Do Not Break:**
- Background task must still be registered correctly with FastAPI BackgroundTasks
- SSE progress events must still emit at the same points
- Error handling and cancellation detection must work identically

- [ ] **Step 1: Create analysis_orchestrator.py with process_case_background**

Move `process_case_background()` and all its helper functions to the new file. Update imports.

- [ ] **Step 2: Update analysis.py to import from orchestrator**

Replace the function definitions with imports:
```python
from legal_portal.services.analysis_orchestrator import process_case_background
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -x -q`

- [ ] **Step 4: Commit**

```bash
git add src/legal_portal/services/analysis_orchestrator.py src/legal_portal/api/routes/analysis.py
git commit -m "refactor: extract analysis orchestrator from analysis.py route file

Moves process_case_background and helpers (~700 lines) to a dedicated
service module. analysis.py now contains only route handlers."
```

---

### Task 4.2: Extract Letter Stream Service from analysis.py

**Files:**
- Create: `src/legal_portal/services/letter_stream_service.py`
- Modify: `src/legal_portal/api/routes/analysis.py`

**What to extract:** The `generate()` inner function from `stream_findings_letter` endpoint (~400 lines):
- Context building for letter
- Strategy computation
- Draft streaming
- Lint/repair/polish pipeline
- Final HTML conversion and persistence

- [ ] Steps follow the same pattern as Task 4.1.

---

### Task 4.3: Consolidate _run_with_heartbeat Duplication

**Files:**
- Create: `src/legal_portal/utils/heartbeat.py`
- Modify: `src/legal_portal/services/main_processor.py` (remove duplicate, import shared)
- Modify: `src/legal_portal/services/multi_stage_analyzer.py` (remove duplicate, import shared)

**Context:** Two implementations exist:
- `main_processor.py:40-84` — module-level async function
- `multi_stage_analyzer.py:459-508` — instance method

Consolidate into a single utility that supports both use patterns.

- [ ] **Step 1: Create shared heartbeat utility**

```python
# src/legal_portal/utils/heartbeat.py
"""Shared heartbeat wrapper for long-running async operations."""

import asyncio
from typing import Any, Callable, Optional

async def run_with_heartbeat(
    coro_or_callable,
    progress_callback: Optional[Callable],
    phase: str,
    percent: int,
    heartbeat_interval: float = 10.0,
    *args,
    **kwargs,
) -> Any:
    """Run a coroutine while sending periodic heartbeat progress updates."""
    # ... unified implementation ...
```

- [ ] **Step 2: Replace both implementations with imports**
- [ ] **Step 3: Run tests**
- [ ] **Step 4: Commit**

---

### Task 4.4: Consolidate Validation Services

**Files:**
- Modify: `src/legal_portal/services/letter_validation_service.py`
- Potentially deprecate: `src/legal_portal/services/letter_review_service.py`

**Context:** Three services overlap:
- `LetterQualityLintService.lint_letter()` — deterministic regex checks (KEEP)
- `LetterValidationService.lint_client_letter()` — delegates to lint service (KEEP as facade)
- `LetterValidationService.validate_letter()` — source-truth validation (KEEP)
- `LetterReviewService.review_and_improve_letter()` — 523-line AI rewrite (REMOVE — folded into draft prompt in Phase 3)

- [ ] **Step 1: Verify LetterReviewService has no active callers after Phase 3**

```bash
grep -rn "LetterReviewService\|review_and_improve_letter\|letter_review_service" src/ --include="*.py"
```

- [ ] **Step 2: If no callers, mark as deprecated or delete**
- [ ] **Step 3: Run tests**
- [ ] **Step 4: Commit**

---

### Task 4.5: Cache Gap Analysis by Input Hash

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (`_ensure_fresh_gap_analysis_for_letter_generation`)

**Context:** This function re-runs gap analysis before every letter stream. Add input hash comparison to skip re-computation when inputs haven't changed.

- [ ] **Step 1: Compute hash of gap analysis inputs**

```python
import hashlib, json

def _gap_analysis_input_hash(analysis_record: dict) -> str:
    """Hash the inputs that would change gap analysis results."""
    result = analysis_record.get("result") or {}
    msr = result.get("multi_stage_result") or {}
    key_data = json.dumps({
        "fact_matrix": msr.get("fact_matrix"),
        "deep_analysis": msr.get("deep_analysis"),
        "document_summaries": result.get("document_summaries"),
    }, sort_keys=True, default=str)
    return hashlib.sha256(key_data.encode()).hexdigest()[:16]
```

- [ ] **Step 2: Compare hash before re-running gap analysis**

In `_ensure_fresh_gap_analysis_for_letter_generation`, check if the stored gap analysis was computed from the same inputs:
```python
current_hash = _gap_analysis_input_hash(analysis_record)
stored_hash = (analysis_record.get("result") or {}).get("gap_analysis_input_hash")
if stored_hash == current_hash:
    logger.info("[GAP] Skipping re-computation — inputs unchanged")
    return
```

- [ ] **Step 3: Store hash after computing gap analysis**
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**

---

**Phase 4 Expected Impact:**
- **Maintainability:** analysis.py drops from ~7,600 lines to ~2,000 lines (route handlers only)
- **Speed:** Gap analysis caching saves 15-30s per letter generation
- **Testability:** Each service module is independently testable
- **No user-visible behavior change**

---

## "Do Not Break" Guidance Summary

| Change | Must Preserve |
|---|---|
| Registry-driven context building | Backward compat when no registry provided; total token budget ≤50K |
| Reducing AI passes | Lint checks still run; repair still triggers for errors; `letter_polish_enabled` flag honored |
| Breaking up analysis.py | Background task registration; SSE event shapes; progress callback signatures |
| Deleting dead OCR paths | All bytes-based extraction functions; process_pdf() entry point |
| Consolidating validation | lint_client_letter() facade; validate_letter() source-truth checks; check_polish_fact_integrity() |
| Caching gap analysis | Fresh gap analysis when documents change; force_generation override |
| Config fixes | Runtime behavior unchanged (only defaults/comments change) |

---

## Recommended Next 3 Tasks

1. **Task 1.1: Delete dead file-based OCR functions** — 30 minutes, zero risk, ~600 lines removed
2. **Task 1.5: Fix O(n^2) word count** — 15 minutes, direct perf improvement
3. **Task 2.1: Implement weighted token allocation** — 2-3 hours, highest-value quality improvement

## Recommended Next Major Project

**Phase 2: Registry-driven context building** (Tasks 2.1-2.4). This is the single highest-leverage improvement because it fixes the root cause of the biggest quality problem (important documents truncated to same size as trivial ones) with minimal blast radius (only changes multi_stage_analyzer.py and its callers).

## What I Would Not Change Yet

1. **ChunkService bin packing algorithm** — works correctly for its use case; changing it alongside context building would create too many moving parts
2. **FallbackGenerationService** — dead code but harmless; not worth the risk of discovering hidden callers right now
3. **LetterStrategyService model+fallback merge pattern** — it's defensive but not hurting performance meaningfully (gpt-5-mini is fast); optimize later if strategy becomes a bottleneck
4. **Citation tracking service** — complex but functioning; save for a dedicated citation quality project
5. **Cost tracking accuracy** — nice-to-have but doesn't affect user-visible quality or speed
6. **Data model schema versioning** — important for long-term but requires migration strategy; plan separately
7. **Legacy multi-stage analysis path** — keep until streaming path has run on 20+ real cases without issues; then delete with confidence
