# Pipeline Quality & Speed Improvements — Implementation Plan v2 (Corrected)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the analysis and letter-generation pipeline faster, smarter about document ordering, and more reliable — while cleaning up AI-generated technical debt. Corrections from engineering review incorporated.

**Architecture:** Replace flat 1K-per-document token caps with importance-weighted allocation driven by DocumentRegistryService authority scores, with proportional scaling when demand exceeds budget. Reduce letter-generation latency by making polish and critic passes conditional rather than eliminating them. Extract the letter-stream service from the 7,600-line analysis.py. Clean up confirmed dead code.

**Tech Stack:** Python 3.11+, FastAPI, OpenAI API (gpt-5.4 / gpt-5-mini / gpt-5.2), Supabase (PostgreSQL), SSE streaming, tiktoken

---

## Executive Summary

**Implementation order rationale:**

1. **Phase 1 (cleanup)** removes ~600 lines of confirmed dead code with zero behavior change. This reduces cognitive load for subsequent phases.
2. **Phase 2 (weighted context building)** is the single highest-leverage quality improvement. It changes only `multi_stage_analyzer.py` and one call site in `analysis.py`, with a narrow blast radius.
3. **Phase 3 (conditional AI passes)** reduces latency by skipping unnecessary polish/critic/repair cycles, without removing safety nets.
4. **Phase 4 (structural)** extracts the letter-stream service — the cleanest extraction boundary in analysis.py — and adds instrumentation.

**What changed from v1:**

| v1 Issue | v2 Fix |
|---|---|
| Task 1.3 would delete live `SequenceMatcher` import | Removed from plan — `SequenceMatcher` is used at `main_processor.py:1321` |
| Task 2.2 wired registry through wrong file (`main_processor.py`) | Corrected to wire through `analysis.py:4171` (actual call site) |
| Document name matching used naive `.strip()` | Now uses `_normalize_name()` from `DocumentRegistryService` |
| Flat token tiers exhaust budget with many high-authority docs | Added proportional scaling when weighted demand exceeds budget |
| Phase 3 merged polish into draft prompt, losing safety net | Polish kept as separate conditional pass with `check_polish_fact_integrity` preserved |
| Phase 3 merged critic into repair | Critic kept separate, made conditional on lint score threshold |
| Phase 3 gated repair on `severity="error"` only | Gated on specific fixable rules instead of severity level |
| Task 4.5 (gap analysis caching) was already implemented | Removed from plan — confirmed existing at `analysis.py:6373-6381` |
| Task 2.3 shadow comparison doubled context-building work | Replaced with structured allocation logging (no re-computation) |
| Phase 4 underestimated analysis.py coupling | Reduced scope: extract letter-stream service only; defer orchestrator |

---

## Chunk 1: Phase 1 — Safe Cleanup

**Objective:** Remove confirmed dead code, fix config contradictions. Zero behavior change.

### Task 1.1: Delete Dead File-Based OCR Functions

**Files:**
- Modify: `src/legal_portal/services/file_processors/pdf_processor.py`
- Test: `tests/unit/test_pdf_processor.py`

**Context:** pdf_processor.py contains file-path-based OCR functions alongside bytes-based equivalents. The file-path versions have zero callers (confirmed via grep). The bytes-based versions are the production code path (Vercel serverless requires bytes).

**Do Not Break:** All `*_bytes()` extraction functions. The `process_pdf()` entry point. Signature detection.

- [ ] **Step 1: Establish test baseline**

Run: `pytest tests/unit/test_pdf_processor.py tests/unit/test_ocr_compression_chunking.py -v`
Expected: All pass

- [ ] **Step 2: Verify zero callers of each file-based function**

```bash
# Each command should return ONLY the def line, no call sites
grep -rn "_extract_text_with_fitz[^_]" src/ --include="*.py"
grep -rn "_extract_text_with_pypdf[^_]" src/ --include="*.py"
grep -rn "def _extract_text_via_google_ocr[^_]" src/ --include="*.py"
grep -rn "def _extract_text_via_vision[^_]" src/ --include="*.py"
```

If ANY grep returns a call site (not just the `def` line), do NOT delete that function.

- [ ] **Step 3: Delete dead file-based functions from pdf_processor.py**

Delete these functions (approximate locations):
- `_extract_text_with_fitz(file_path: str)` (~line 660)
- `_extract_text_with_pypdf(file_path: str)` (~line 669)
- `_extract_text_via_google_ocr(file_path, ...)` (~line 799) — the file-path version only
- `_extract_text_via_vision(file_path, ...)` (~line 1214) — the file-path version only

**Keep all `*_bytes()` variants intact.**

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_pdf_processor.py tests/unit/test_ocr_compression_chunking.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/services/file_processors/pdf_processor.py
git commit -m "cleanup: remove dead file-based OCR functions from pdf_processor

Bytes-based variants are the only active code path (Vercel serverless).
File-based versions had zero callers confirmed via grep."
```

---

### Task 1.2: Delete Deprecated prompt_and_api_service.py

**Files:**
- Delete: `src/legal_portal/services/prompt_and_api_service.py`
- Possibly modify: `src/legal_portal/services/__init__.py`

- [ ] **Step 1: Confirm zero imports**

```bash
grep -rn "prompt_and_api_service" src/ tests/ --include="*.py"
```
Expected: Only the file itself (no imports from other modules)

- [ ] **Step 2: Delete the file**

```bash
rm src/legal_portal/services/prompt_and_api_service.py
```

- [ ] **Step 3: Remove from __init__.py if listed**

Check `src/legal_portal/services/__init__.py`. If it imports or re-exports `prompt_and_api_service`, remove that line.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All pass, no import errors

- [ ] **Step 5: Commit**

```bash
git add -A src/legal_portal/services/
git commit -m "cleanup: remove deprecated prompt_and_api_service.py (zero callers)"
```

---

### Task 1.3: Remove Deprecated parse_client_name_from_intake

**Files:**
- Modify: `src/legal_portal/utils/helpers.py`

**IMPORTANT:** Do NOT delete the `SequenceMatcher` import from `main_processor.py`. It is actively used at `main_processor.py:1321` for near-duplicate filename detection.

- [ ] **Step 1: Confirm `parse_client_name_from_intake` has no callers**

```bash
grep -rn "parse_client_name_from_intake" src/ tests/ --include="*.py"
```
Expected: Only the definition in helpers.py

- [ ] **Step 2: Delete `parse_client_name_from_intake()` from helpers.py**

Remove the function (marked DEPRECATED in its docstring, ~lines 790-810).

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/legal_portal/utils/helpers.py
git commit -m "cleanup: remove deprecated parse_client_name_from_intake from helpers.py"
```

---

### Task 1.4: Fix Config Contradictions

**Files:**
- Modify: `src/legal_portal/config/default.py`

- [ ] **Step 1: Read config to find exact line numbers**

```bash
grep -n "ocr_remote_enabled\|ocr_remote_required\|openai_timeout" src/legal_portal/config/default.py
```

- [ ] **Step 2: Fix OCR config contradiction**

`ocr_remote_enabled = False` + `ocr_remote_required = True` is contradictory. Change:
```python
ocr_remote_enabled: bool = False    # Whether remote OCR service is available
ocr_remote_required: bool = False   # Whether to require remote OCR (only meaningful when enabled)
```

- [ ] **Step 3: Annotate unused openai_timeout**

```python
openai_timeout: float = 30.0  # UNUSED: OpenAIClient hardcodes httpx timeouts (120s read)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/config/default.py
git commit -m "fix: resolve contradictory OCR config defaults, annotate unused openai_timeout"
```

---

### Task 1.5: Delete ContentGenerationService Deprecated Stubs

**Files:**
- Modify: `src/legal_portal/services/content_generation_service.py`

- [ ] **Step 1: Read the file, identify deprecated stubs**

Look for methods returning `"[Legacy method - use new architecture]"` or with DEPRECATED docstrings.

- [ ] **Step 2: Confirm zero callers**

```bash
grep -rn "generate_factual_summary_content" src/ tests/ --include="*.py"
```

- [ ] **Step 3: Delete deprecated stubs**

Remove methods that return hardcoded deprecation strings. If the entire class is unused, delete the file.

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/services/content_generation_service.py
git commit -m "cleanup: remove deprecated ContentGenerationService stubs"
```

---

**Phase 1 expected impact:**
- ~600 lines of dead code removed
- Config contradictions resolved
- Zero behavior change
- Cleaner codebase for Phase 2

**Phase 1 regression risk:** Minimal. Every deletion is preceded by a caller-verification grep.

---

## Chunk 2: Phase 2 — Registry-Driven Context Building (Corrected)

**Objective:** Replace the flat 1,000-token-per-document cap in `_build_condensed_context()` with importance-weighted allocation using authority scores from `DocumentRegistryService`. Add proportional scaling to handle corpora with many high-authority documents.

### How the system works today

**Where authority scores originate:**
- `DocumentRegistryService._score_authority()` at `document_registry_service.py:1030-1057`
- Base score by `authority_level`: `controlling_signed_instrument` = 95, `controlling_instrument` = 82, `official_record` = 74, `financial_record` = 68, `party_communication` = 64, `offering_material` = 60, `supporting_evidence` = 50, `client_background` = 40
- Modifiers: `+3` signed, `+4` key_doc, `+2` legal_significance, `+1` important_details
- Range: 1–100

**Where the registry is built:**
- `main_processor.py:927` → `build_initial_registry()` per document
- `main_processor.py:933` → `enrich_cross_document()` across all docs
- `main_processor.py:950` → `enrich_with_ai()` with AI summaries
- Result stored in `multi_stage_result["document_registry"]`

**Where document ordering currently happens:**
- `multi_stage_analyzer.py:104-119` — `_get_doc_priority()` does keyword substring matching on `doc_type`
- `multi_stage_analyzer.py:121-191` — `_build_condensed_context()` sorts by priority bucket, caps every doc at 1,000 tokens flat

**Where `analyze_streaming()` is called:**
- `analysis.py:4171` — inside the `stream_case_analysis` endpoint (NOT in `main_processor.py`)
- This is the ONLY call site

**Document name matching problem:**
- Registry entries use raw `file_name` from DB
- `DocumentSummaryStructured.document_name` may be AI-normalized
- The registry already uses `_normalize_name()` (`document_registry_service.py:811`) for matching — lowercase, strip extension, replace non-alphanumeric with spaces

---

### Task 2.1: Implement Weighted Token Allocation with Proportional Scaling

**Files:**
- Modify: `src/legal_portal/services/multi_stage_analyzer.py`
- Create: `tests/unit/test_weighted_context_builder.py`

**Do Not Break:**
- `_build_condensed_context()` must produce identical output when no registry provided (backward compat)
- `ContextBuildResult` dataclass shape unchanged
- Total token budget respected regardless of authority distribution

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_weighted_context_builder.py`:

```python
"""Tests for importance-weighted document context building."""
import pytest
from unittest.mock import MagicMock
from legal_portal.services.multi_stage_analyzer import (
    MultiStageAnalyzer,
    _get_token_budget_for_authority,
    _compute_scaled_budgets,
)
from legal_portal.core.data_models import DocumentSummaryStructured


def _make_summary(name: str, doc_type: str, content: str) -> DocumentSummaryStructured:
    """Create a minimal DocumentSummaryStructured for testing."""
    return DocumentSummaryStructured(
        document_name=name,
        document_type=doc_type,
        key_content=content,
        executive_summary=content[:200],
    )


def _make_registry_entry(
    name: str,
    authority_score: int,
    authority_level: str = "supporting_evidence",
) -> dict:
    return {
        "document_name": name,
        "authority_score": authority_score,
        "authority_level": authority_level,
        "is_key_document": authority_score >= 80,
    }


class TestTokenBudgetTiers:
    """Test per-document token budget calculation."""

    def test_controlling_gets_4000(self):
        assert _get_token_budget_for_authority(95) == 4_000

    def test_primary_gets_2000(self):
        assert _get_token_budget_for_authority(70) == 2_000

    def test_supporting_gets_1000(self):
        assert _get_token_budget_for_authority(55) == 1_000

    def test_background_gets_400(self):
        assert _get_token_budget_for_authority(35) == 400

    def test_zero_score_gets_floor(self):
        assert _get_token_budget_for_authority(0) == 400


class TestProportionalScaling:
    """Test that budgets scale down proportionally when demand > total budget."""

    def test_no_scaling_when_under_budget(self):
        """When total demand fits within budget, no scaling occurs."""
        raw_budgets = {"doc_a": 4000, "doc_b": 1000}
        scaled = _compute_scaled_budgets(raw_budgets, max_tokens=50_000)
        assert scaled == raw_budgets

    def test_proportional_scaling_when_over_budget(self):
        """When total demand exceeds budget, all budgets scale proportionally."""
        # 10 docs each wanting 4000 = 40000 demand, budget = 20000
        raw_budgets = {f"doc_{i}": 4000 for i in range(10)}
        scaled = _compute_scaled_budgets(raw_budgets, max_tokens=20_000)

        # Each should get 2000 (half of 4000)
        for name, budget in scaled.items():
            assert budget == 2000, f"{name} got {budget}, expected 2000"

        assert sum(scaled.values()) == 20_000

    def test_scaling_preserves_relative_ordering(self):
        """Higher-authority docs still get more tokens than lower after scaling."""
        raw_budgets = {"contract": 4000, "email": 400}
        scaled = _compute_scaled_budgets(raw_budgets, max_tokens=2_200)

        assert scaled["contract"] > scaled["email"]
        assert sum(scaled.values()) == 2_200

    def test_minimum_floor_per_document(self):
        """Each document gets at least 100 tokens even after scaling."""
        raw_budgets = {f"doc_{i}": 4000 for i in range(100)}
        scaled = _compute_scaled_budgets(raw_budgets, max_tokens=5_000)

        for name, budget in scaled.items():
            assert budget >= 100, f"{name} got {budget}, expected >= 100"


class TestWeightedContextBuilding:
    """Test full context building with registry data."""

    def setup_method(self):
        mock_client = MagicMock()
        self.analyzer = MultiStageAnalyzer(openai_client=mock_client)

    def test_high_authority_doc_gets_more_tokens(self):
        """A controlling instrument should get more token budget than correspondence."""
        long_content = "Important contract clause about obligations. " * 200
        summaries = [
            _make_summary("Cover Letter.pdf", "correspondence", long_content),
            _make_summary("Signed Contract.pdf", "controlling_instrument", long_content),
        ]
        registry = [
            _make_registry_entry("Cover Letter.pdf", 40, "client_background"),
            _make_registry_entry("Signed Contract.pdf", 95, "controlling_signed_instrument"),
        ]

        result = self.analyzer._build_condensed_context(
            summaries,
            max_tokens=10_000,
            document_registry=registry,
        )

        # Signed contract should appear first (higher authority)
        assert result.context_text.index("Signed Contract") < result.context_text.index("Cover Letter")

    def test_backward_compat_no_registry(self):
        """When no registry provided, behavior is identical to original."""
        content = "Some content. " * 100
        summaries = [
            _make_summary("Doc A", "contract", content),
            _make_summary("Doc B", "correspondence", content),
        ]

        result_no_reg = self.analyzer._build_condensed_context(
            summaries, max_tokens=10_000,
        )
        result_none = self.analyzer._build_condensed_context(
            summaries, max_tokens=10_000, document_registry=None,
        )

        assert result_no_reg.docs_in_scope == result_none.docs_in_scope
        assert result_no_reg.context_text == result_none.context_text

    def test_total_budget_respected_with_many_high_authority(self):
        """With 15 controlling docs, total tokens must not exceed budget."""
        content = "Detailed clause. " * 500
        summaries = [
            _make_summary(f"Contract_{i}.pdf", "controlling_instrument", content)
            for i in range(15)
        ]
        registry = [
            _make_registry_entry(f"Contract_{i}.pdf", 95) for i in range(15)
        ]

        result = self.analyzer._build_condensed_context(
            summaries,
            max_tokens=20_000,
            document_registry=registry,
        )

        assert result.total_tokens <= 20_000
        assert result.docs_in_scope >= 1

    def test_name_normalization_matches_across_formats(self):
        """Registry file_name and AI-generated document_name should match
        even when they differ in case/extension/formatting."""
        content = "Important content. " * 100
        summaries = [
            # AI might normalize the name
            _make_summary("Subscription Agreement Final", "contract", content),
        ]
        registry = [
            # Registry uses raw file name
            _make_registry_entry("subscription_agreement_final_v2.pdf", 90),
        ]

        result = self.analyzer._build_condensed_context(
            summaries,
            max_tokens=10_000,
            document_registry=registry,
        )

        # The doc should get the elevated budget (not the default 45 fallback)
        # Verify by checking it was included with substantial content
        assert "Important content" in result.context_text
        assert result.docs_in_scope == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_weighted_context_builder.py -v`
Expected: FAIL — functions don't exist yet

- [ ] **Step 3: Implement weighted allocation with proportional scaling**

Modify `src/legal_portal/services/multi_stage_analyzer.py`:

**A) Add imports and constants** after line 59:

```python
import re as _re
from typing import Dict as _Dict

# --- Importance-weighted token allocation ---
_TOKEN_TIERS = [
    # (min_authority_score, base_tokens_per_doc)
    (80, 4_000),   # Controlling instruments, signed docs
    (65, 2_000),   # Official/financial records
    (50, 1_000),   # Communications, evidence
    (0,    400),   # Background, low-relevance
]
_MIN_TOKENS_PER_DOC = 100  # Absolute floor after scaling


def _get_token_budget_for_authority(authority_score: int) -> int:
    """Return base per-document token budget from authority score."""
    for min_score, budget in _TOKEN_TIERS:
        if authority_score >= min_score:
            return budget
    return 400


def _normalize_name_for_lookup(value: str) -> str:
    """Normalize a document name for cross-system matching.

    Mirrors DocumentRegistryService._normalize_name logic:
    lowercase, strip extension, replace non-alphanumeric with spaces.
    """
    text = (value or "").lower().strip()
    text = _re.sub(r"\.[a-z0-9]{1,8}$", "", text)   # strip extension
    text = _re.sub(r"[^a-z0-9]+", " ", text)          # non-alnum → space
    return _re.sub(r"\s+", " ", text).strip()


def _compute_scaled_budgets(
    raw_budgets: dict[str, int],
    max_tokens: int,
) -> dict[str, int]:
    """Scale all budgets proportionally if total demand exceeds max_tokens.

    Guarantees: sum(result.values()) <= max_tokens and each value >= _MIN_TOKENS_PER_DOC.
    """
    if not raw_budgets:
        return {}

    total_demand = sum(raw_budgets.values())
    if total_demand <= max_tokens:
        return dict(raw_budgets)

    scale = max_tokens / total_demand
    scaled = {}
    for name, budget in raw_budgets.items():
        scaled[name] = max(_MIN_TOKENS_PER_DOC, int(budget * scale))

    # If floors pushed us over budget, do a second pass
    total_scaled = sum(scaled.values())
    if total_scaled > max_tokens:
        excess = total_scaled - max_tokens
        # Trim from largest allocations first
        sorted_names = sorted(scaled, key=lambda n: -scaled[n])
        for name in sorted_names:
            if excess <= 0:
                break
            trim = min(excess, scaled[name] - _MIN_TOKENS_PER_DOC)
            scaled[name] -= trim
            excess -= trim

    return scaled
```

**B) Modify `_build_condensed_context` to accept and use registry:**

Replace the method body (lines ~121-191):

```python
    def _build_condensed_context(
        self,
        document_summaries: List[DocumentSummaryStructured],
        max_tokens: int = _DEFAULT_BUDGET_TOKENS,
        document_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> ContextBuildResult:
        """Build token-budgeted context from document summaries.

        When document_registry is provided, uses authority scores for:
        1. Sort order (highest authority first)
        2. Per-document token allocation (controlling instruments get more)
        3. Proportional scaling when total demand exceeds budget

        When document_registry is None, falls back to original keyword-based
        priority with flat 1K-per-doc caps (backward compatible).
        """
        from legal_portal.utils.token_manager import TokenManager
        tm = TokenManager()

        # Build normalized authority lookup from registry
        authority_lookup: dict[str, int] = {}
        if document_registry:
            for entry in document_registry:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("document_name") or ""
                score = int(entry.get("authority_score") or 45)
                normalized = _normalize_name_for_lookup(raw_name)
                if normalized:
                    authority_lookup[normalized] = score

        use_weighted = bool(authority_lookup)

        # --- Sort documents ---
        if use_weighted:
            indexed = []
            for idx, s in enumerate(document_summaries):
                norm = _normalize_name_for_lookup(s.document_name or "")
                score = authority_lookup.get(norm, 45)  # default if no match
                indexed.append((score, idx, s))
            # Higher authority first (descending score)
            indexed.sort(key=lambda x: (-x[0], x[1]))
        else:
            indexed = [
                (self._get_doc_priority(s), idx, s)
                for idx, s in enumerate(document_summaries)
            ]
            indexed.sort(key=lambda x: (x[0], x[1]))

        # --- Compute per-document token budgets ---
        if use_weighted:
            raw_budgets = {}
            score_by_key = {}
            for score, idx, s in indexed:
                key = f"{idx}_{s.document_name or 'unknown'}"
                raw_budgets[key] = _get_token_budget_for_authority(score)
                score_by_key[key] = score

            scaled_budgets = _compute_scaled_budgets(raw_budgets, max_tokens)
        else:
            scaled_budgets = None

        # --- Build context entries ---
        lines: list[str] = []
        total_tokens = 0
        included = 0
        omitted_names: list[str] = []
        allocation_log: list[str] = []

        for pos, (score_or_pri, orig_idx, summary) in enumerate(indexed):
            doc_name = summary.document_name or "unknown"
            doc_type = summary.document_type or "document"

            # Determine per-doc token cap
            if use_weighted and scaled_budgets is not None:
                key = f"{orig_idx}_{doc_name}"
                doc_token_cap = scaled_budgets.get(key, _MAX_ENTRY_TOKENS)
            else:
                doc_token_cap = _MAX_ENTRY_TOKENS

            # Truncate content to roughly match token cap (chars ≈ tokens * 4)
            max_chars = doc_token_cap * 4
            content = (summary.key_content or summary.executive_summary or "")[:max_chars]

            entry = f"[{included + 1}] {doc_name} ({doc_type})\n    {content}\n"

            entry_tokens = tm.estimate_tokens_detailed(entry)
            if entry_tokens > doc_token_cap:
                ratio = doc_token_cap / entry_tokens
                truncated_len = int(len(content) * ratio)
                content = content[:truncated_len]
                entry = f"[{included + 1}] {doc_name} ({doc_type})\n    {content}\n"
                entry_tokens = tm.estimate_tokens_detailed(entry)

            if total_tokens + entry_tokens > max_tokens:
                omitted_names.append(doc_name)
                continue

            lines.append(entry)
            total_tokens += entry_tokens
            included += 1

            if use_weighted:
                allocation_log.append(
                    f"  {doc_name}: authority={score_or_pri} "
                    f"budget={doc_token_cap} used={entry_tokens}"
                )

        docs_omitted = len(document_summaries) - included
        omission_reason = ""
        if docs_omitted > 0:
            omission_reason = (
                f"Token budget ({max_tokens:,}) reached after {included} docs. "
                f"{docs_omitted} lower-priority documents excluded."
            )
            logger.warning(f"[ANALYSIS:BUDGET] {omission_reason}")

        if allocation_log:
            logger.info(
                f"[ANALYSIS:ALLOCATION] Weighted token allocation "
                f"({included}/{len(document_summaries)} docs, "
                f"{total_tokens:,} tokens):\n" + "\n".join(allocation_log)
            )
        else:
            logger.info(
                f"[ANALYSIS:CONTEXT] Flat-cap allocation: "
                f"{included}/{len(document_summaries)} docs, "
                f"{total_tokens:,} tokens"
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

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_weighted_context_builder.py -v`
Expected: All pass

- [ ] **Step 5: Run existing context builder tests for backward compat**

Run: `pytest tests/test_context_builder.py -v`
Expected: All existing tests pass unchanged

- [ ] **Step 6: Commit**

```bash
git add src/legal_portal/services/multi_stage_analyzer.py tests/unit/test_weighted_context_builder.py
git commit -m "feat: importance-weighted token allocation with proportional scaling

Documents with higher authority scores get proportionally more token
budget (up to 4K for controlling instruments, 400 for background).
When total demand exceeds budget, all allocations scale down proportionally.
Uses normalized name matching (mirrors DocumentRegistryService._normalize_name).
Backward compatible: no registry = original flat-cap behavior."
```

---

### Task 2.2: Wire Registry into analyze_streaming Call Site

**Files:**
- Modify: `src/legal_portal/services/multi_stage_analyzer.py` (`analyze_streaming` method)
- Modify: `src/legal_portal/api/routes/analysis.py` (line ~4171, the ACTUAL call site)

**Context:** `analyze_streaming()` is called at `analysis.py:4171` inside `stream_case_analysis`. It currently does NOT receive registry data. The registry is available in the analysis result as `multi_stage_result["document_registry"]`.

**Do Not Break:** `analyze_streaming()` return type `Tuple[AsyncGenerator, ContextBuildResult]`. SSE streaming behavior.

- [ ] **Step 1: Add document_registry parameter to analyze_streaming**

In `multi_stage_analyzer.py`, modify the signature at line ~370:

```python
async def analyze_streaming(
    self,
    intake_content: str,
    document_summaries: List[DocumentSummaryStructured],
    jurisdiction: str = "Florida",
    document_registry: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[AsyncGenerator[str, None], ContextBuildResult]:
```

Pass it through at line ~396:
```python
ctx = self._build_condensed_context(
    document_summaries,
    document_registry=document_registry,
)
```

- [ ] **Step 2: Wire registry at the call site in analysis.py**

At `analysis.py:4171`, the call currently reads:
```python
token_generator, ctx_result = await analyzer.analyze_streaming(
    intake_content=intake_content,
    document_summaries=doc_summaries,
    jurisdiction=jurisdiction,
)
```

Find where `document_registry` is available in the surrounding scope. Look for it in `multi_stage_result` or the analysis record. Add it:

```python
# Get registry from analysis result if available
document_registry = None
if multi_stage_result:
    document_registry = multi_stage_result.get("document_registry")

token_generator, ctx_result = await analyzer.analyze_streaming(
    intake_content=intake_content,
    document_summaries=doc_summaries,
    jurisdiction=jurisdiction,
    document_registry=document_registry,
)
```

If `multi_stage_result` is not in scope at line 4171, trace the variable back to find where the analysis result is loaded and extract the registry from there.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_weighted_context_builder.py tests/unit/test_multi_stage_analyzer.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/legal_portal/services/multi_stage_analyzer.py src/legal_portal/api/routes/analysis.py
git commit -m "feat: wire document registry into analyze_streaming for weighted context

Registry authority scores now flow from analysis.py stream endpoint
through to context building. Enables importance-weighted allocation."
```

---

### Task 2.3: Sort Document Summaries by Authority in Letter Prompt

**Files:**
- Modify: `src/legal_portal/services/json_processing_service.py` (`_build_adaptive_findings_prompt`)

**Context:** The letter generation prompt assembles document summaries through `_build_adaptive_findings_prompt()` at line ~930. It receives `document_registry` and `document_summaries_for_context` but doesn't use registry scores for ordering. Higher-authority documents should appear first in the prompt so they survive any truncation.

**Do Not Break:** `stream_findings_letter_adaptive()` and `generate_findings_letter_adaptive()` return types. Prompt structure.

- [ ] **Step 1: Add authority-score sorting before document inclusion**

In `_build_adaptive_findings_prompt()`, before the document summaries are formatted into the prompt, sort them:

```python
# Sort document summaries by authority score (highest first)
if document_registry and document_summaries_for_context:
    _authority_lookup = {}
    for entry in document_registry:
        if isinstance(entry, dict):
            _norm = _normalize_name_for_lookup(entry.get("document_name") or "")
            _authority_lookup[_norm] = int(entry.get("authority_score") or 45)

    def _doc_sort_key(d):
        _norm = _normalize_name_for_lookup(d.get("document_name") or "")
        return -_authority_lookup.get(_norm, 45)

    document_summaries_for_context = sorted(
        document_summaries_for_context,
        key=_doc_sort_key,
    )
```

Import the normalization function at the top of the file:
```python
from legal_portal.services.multi_stage_analyzer import _normalize_name_for_lookup
```

- [ ] **Step 2: Run existing tests**

Run: `pytest tests/unit/test_json_processing_repair.py -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add src/legal_portal/services/json_processing_service.py
git commit -m "feat: sort document summaries by authority score in letter prompt

Higher-authority documents now appear first in letter generation prompt,
reducing risk of critical instruments being truncated."
```

---

### Task 2.4: Add Prompt-Size Monitoring

**Files:**
- Modify: `src/legal_portal/services/json_processing_service.py`
- Modify: `src/legal_portal/services/multi_stage_analyzer.py`

**Context:** The review identified missing instrumentation — no structured logging of actual prompt sizes hitting the model. This is necessary to validate that weighted allocation is producing prompts within expected bounds.

- [ ] **Step 1: Add prompt-size logging to analyze_streaming**

After the prompt is built at `multi_stage_analyzer.py` (inside `analyze_streaming`, after `_build_streaming_prompt`), add:

```python
from legal_portal.utils.token_manager import TokenManager
_tm = TokenManager()
_prompt_tokens = _tm.estimate_tokens_detailed(prompt)
_system_tokens = _tm.estimate_tokens_detailed(system_prompt)
logger.info(
    f"[PROMPT:SIZE] analyze_streaming: "
    f"system={_system_tokens:,} prompt={_prompt_tokens:,} "
    f"total={_system_tokens + _prompt_tokens:,} "
    f"context_docs={ctx.docs_in_scope} context_tokens={ctx.total_tokens:,}"
)
```

- [ ] **Step 2: Add prompt-size logging to letter generation**

In `json_processing_service.py`, after `_build_adaptive_findings_prompt` returns (around line 1475), add:

```python
from legal_portal.utils.token_manager import TokenManager
_tm = TokenManager()
_prompt_tokens = _tm.estimate_tokens_detailed(prompt)
logger.info(
    f"[PROMPT:SIZE] findings_letter: "
    f"prompt_tokens={_prompt_tokens:,} prompt_chars={len(prompt):,} "
    f"includes_raw_docs={prompt_includes_raw_docs}"
)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/legal_portal/services/multi_stage_analyzer.py src/legal_portal/services/json_processing_service.py
git commit -m "feat: add prompt-size monitoring for analysis and letter generation

Logs token counts for every prompt sent to the model, enabling
validation of weighted allocation impact and prompt budget tracking."
```

---

**Phase 2 expected impact:**
- **Quality:** Controlling instruments get up to 4x more token budget, with proportional scaling preventing budget starvation
- **Observability:** Structured logging of token allocation decisions and prompt sizes
- **Speed:** No change (same total budget, better allocated)
- **Backward compat:** Identical behavior when no registry provided

**Phase 2 regression risks and mitigations:**
- **Name mismatch risk:** `_normalize_name_for_lookup` mirrors the registry's own normalization. Documents that don't match fall back to score 45 (mid-range), not catastrophic.
- **Budget exhaustion with many high-authority docs:** Proportional scaling prevents any single tier from consuming the entire budget.
- **Changed document ordering:** Different documents may get more/less representation. Allocation log enables before/after comparison on real cases.

**Phase 2 testing strategy:**
1. Unit tests (Task 2.1) verify allocation math and backward compat
2. Run 3-5 real cases after deployment; compare allocation logs to previous letter quality
3. If quality degrades, the `document_registry=None` fallback path is always available

---

## Chunk 3: Phase 3 — Targeted Latency Reduction (Revised)

**Objective:** Reduce letter-generation time by making polish and critic passes conditional, without removing safety nets. Target: 25-40% latency reduction.

**Key design decisions (from review corrections):**
- Polish is a **substantive rewrite pass** (artifact removal, jargon translation, tone adjustment), not just formatting. It MUST remain a separate AI call.
- The `check_polish_fact_integrity` safety net MUST be preserved.
- Critic provides **structured, section-level repair instructions** with explicit `do_not_change` guards. It MUST remain separate from repair.
- Lint severity is **mode-dependent** — most violations are `warning` in `default` mode. Gating on severity alone would skip real issues.

### Task 3.1: Make Polish Pass Conditional on Artifact Detection

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (lines ~2791-2838, polish section)
- Create: `tests/unit/test_conditional_polish.py`

**Do Not Break:** `check_polish_fact_integrity` must still run when polish executes. `letter_polish_enabled` config flag must still work. Letter formatting quality must not degrade.

**How this works:** Before calling the polish AI, scan the draft for pipeline artifacts that polish is designed to fix. If none found, skip the pass entirely. When polish runs, the existing fact-integrity check remains in place.

- [ ] **Step 1: Write test for artifact detection**

Create `tests/unit/test_conditional_polish.py`:

```python
"""Tests for conditional polish pass — skip when no artifacts detected."""
import re

# These patterns match what the polish prompt is designed to fix.
# Extracted from letter_polish.py formatting rules.
_POLISH_ARTIFACT_PATTERNS = [
    r"\(intake\s+packet\b",           # pipeline source labels
    r"\(photos?,\s*file\)",           # file reference artifacts
    r"\bclient-reported\b",           # internal pipeline language
    r"\bper\s+intake\b",             # internal pipeline language
    r"\bflagged\s+in\s+analysis\b",  # internal pipeline language
    r"\b[a-z]+_[a-z]+_[a-z]+\b",    # snake_case tokens (3+ segments)
    r"\.[a-z]{2,4}\b",               # raw file extensions in prose
]


def _draft_needs_polish(draft: str) -> bool:
    """Check if draft contains artifacts that the polish pass fixes."""
    text = draft.lower()
    for pattern in _POLISH_ARTIFACT_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def test_clean_draft_skips_polish():
    clean = (
        "Good afternoon, I wanted to share my preliminary findings "
        "after reviewing the documents in your case. Based on the "
        "subscription agreement dated January 15, 2024, there appear "
        "to be several potential claims."
    )
    assert not _draft_needs_polish(clean)


def test_draft_with_source_labels_needs_polish():
    dirty = (
        "You invested $50,000 (intake packet 01-11-2026) into "
        "the development project."
    )
    assert _draft_needs_polish(dirty)


def test_draft_with_pipeline_language_needs_polish():
    dirty = "The client-reported timeline indicates delays."
    assert _draft_needs_polish(dirty)


def test_draft_with_snake_case_needs_polish():
    dirty = "This constitutes a breach_of_contract under Florida law."
    assert _draft_needs_polish(dirty)


def test_draft_with_raw_filename_needs_polish():
    dirty = "As documented in subscription_agreement_v2.pdf, the terms state..."
    assert _draft_needs_polish(dirty)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/unit/test_conditional_polish.py -v`
Expected: All pass (these test pure functions, no system dependencies)

- [ ] **Step 3: Extract artifact detection into a utility**

Create the `_draft_needs_polish()` function in `src/legal_portal/utils/letter_polish.py` (add near the top, after imports):

```python
import re as _re

_POLISH_ARTIFACT_PATTERNS = [
    _re.compile(r"\(intake\s+packet\b", _re.IGNORECASE),
    _re.compile(r"\(photos?,\s*file\)", _re.IGNORECASE),
    _re.compile(r"\bclient-reported\b", _re.IGNORECASE),
    _re.compile(r"\bper\s+intake\b", _re.IGNORECASE),
    _re.compile(r"\bflagged\s+in\s+analysis\b", _re.IGNORECASE),
    _re.compile(r"\b[a-z]+_[a-z]+_[a-z]+\b"),  # snake_case (3+ segments)
    _re.compile(r"\w+\.[a-z]{2,4}\b"),          # raw extensions in prose
]


def draft_needs_polish(draft: str) -> bool:
    """Return True if draft contains artifacts the polish pass is designed to fix."""
    for pattern in _POLISH_ARTIFACT_PATTERNS:
        if pattern.search(draft):
            return True
    return False
```

- [ ] **Step 4: Make polish conditional in analysis.py**

At `analysis.py` ~line 2792, change:

```python
# BEFORE:
if getattr(settings, "letter_polish_enabled", True):
    # ... polish logic ...

# AFTER:
from legal_portal.utils.letter_polish import draft_needs_polish

_polish_enabled = getattr(settings, "letter_polish_enabled", True)
_artifacts_detected = draft_needs_polish(final_markdown)

if _polish_enabled and _artifacts_detected:
    polish_msg = _emit("phase", phase="polishing", message="Polishing letter...")
    if polish_msg:
        yield polish_msg
    # ... existing polish logic unchanged ...
elif _polish_enabled and not _artifacts_detected:
    logger.info("[LETTER] Polish skipped — no pipeline artifacts detected in draft")
    metrics["polish_skipped_reason"] = "no_artifacts_detected"
```

The existing `check_polish_fact_integrity` safety net inside the polish block remains **unchanged**.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_conditional_polish.py tests/api/test_letter_stream_integration.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/legal_portal/utils/letter_polish.py src/legal_portal/api/routes/analysis.py tests/unit/test_conditional_polish.py
git commit -m "perf: make polish pass conditional on artifact detection

Polish only runs when draft contains pipeline artifacts (source labels,
snake_case tokens, internal language, raw filenames). Clean drafts skip
the pass entirely, saving ~15-30s. check_polish_fact_integrity safety
net preserved when polish runs."
```

---

### Task 3.2: Make Critic Pass Conditional on Lint Score

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (lines ~2720-2746, critic section)

**Context:** The critic pass calls gpt-5-mini to produce structured section-level diagnosis. Currently runs whenever lint fails. Make it conditional: skip critic (and therefore repair) when the lint score is above a threshold, indicating minor issues only.

**Do Not Break:** When critic DOES run, its structured `failed_sections` output (with `do_not_change` guards) must still flow to repair unchanged. Repair logic unchanged.

- [ ] **Step 1: Add lint-score threshold for critic**

At `analysis.py` ~line 2720, the current condition is:
```python
if (
    settings.letter_quality_critic_enabled
    and not quality_report.get("lint_passed", True)
    and settings.letter_quality_lint_enabled
):
```

Add a score threshold — skip critic for high-scoring letters with only minor issues:
```python
_lint_score = quality_report.get("score", 100)
_has_error_violations = any(
    v.get("severity") == "error"
    for v in quality_report.get("violations", [])
)

if (
    settings.letter_quality_critic_enabled
    and not quality_report.get("lint_passed", True)
    and settings.letter_quality_lint_enabled
    and (_lint_score < 85 or _has_error_violations)  # NEW: skip critic for high-scoring letters
):
    # ... existing critic logic unchanged ...
else:
    if not quality_report.get("lint_passed", True):
        metrics["critic_skipped_reason"] = f"lint_score_above_threshold:{_lint_score}"
        logger.info(
            "[LETTER] Critic skipped — lint score %s >= 85 with no error-severity violations",
            _lint_score,
        )
```

- [ ] **Step 2: Gate repair on critic-or-error-violations**

The repair block (~line 2748) currently triggers when lint fails. Add the same gating — repair should only trigger when critic provided instructions OR when there are error-severity or fixable violations:

```python
_fixable_rules = {
    "raw_filename_exposure",
    "generic_snake_case_token",
    "unsupported_assertions",
    "parenthetical_citation_artifacts",
    "meta_language_patterns",
    "gap_analysis_flagged",
}
_fixable_violations = [
    v for v in quality_report.get("violations", [])
    if v.get("rule") in _fixable_rules or v.get("severity") == "error"
]

if (
    settings.letter_conditional_repair_enabled
    and settings.letter_quality_lint_enabled
    and (critic_feedback.get("failed_sections") or _fixable_violations)
):
    # ... existing repair logic, but pass _fixable_violations + critic_feedback ...
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/api/test_letter_stream_integration.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py
git commit -m "perf: make critic conditional on lint score, gate repair on fixable violations

Critic skipped when lint score >= 85 with no error violations.
Repair only triggers for fixable rule violations or when critic
provides section-level instructions. Saves 10-25s per letter
for high-quality drafts."
```

---

### Task 3.3: Add Integration Tests for Letter Quality Pipeline

**Files:**
- Create: `tests/unit/test_letter_quality_pipeline.py`

**Context:** The review identified missing integration tests for the lint → critic → repair → polish pipeline. Before changing repair gating, we need tests that verify known-bad letters get caught.

- [ ] **Step 1: Write integration tests**

```python
"""Integration tests for the letter quality pipeline.

Verifies that known-bad patterns are caught by lint and that
the conditional logic correctly skips or triggers each pass.
"""
from legal_portal.services.letter_quality_lint_service import LetterQualityLintService
from legal_portal.services.letter_validation_service import LetterValidationService
from legal_portal.utils.letter_polish import draft_needs_polish


class TestLintCatchesKnownBadPatterns:
    """Verify that lint detects patterns that should trigger repair."""

    def setup_method(self):
        self.lint = LetterQualityLintService()

    def test_snake_case_in_letter_detected(self):
        letter = """## Background & Issue

        Your case involves a potential breach_of_contract claim
        against the developer for failure_to_deliver the project.
        """
        result = self.lint.lint_letter(letter, mode="default", letter_type="findings")
        rules = [v.rule for v in result.get("violations", []) if hasattr(v, 'rule')]
        assert not result.get("lint_passed", True) or "generic_snake_case_token" in rules

    def test_raw_filename_in_letter_detected(self):
        letter = """## Background & Issue

        As documented in subscription_agreement_final_v2.pdf, the investment
        terms required quarterly distributions.
        """
        result = self.lint.lint_letter(letter, mode="default", letter_type="findings")
        violations = result.get("violations", [])
        has_filename_violation = any(
            getattr(v, 'rule', v.get('rule', '')) == "raw_filename_exposure"
            for v in violations
            if isinstance(v, dict) or hasattr(v, 'rule')
        )
        assert has_filename_violation

    def test_unsupported_assertion_detected(self):
        letter = """## Analysis

        The developer committed fraud by stealing your investment funds
        and converting them to personal use.
        """ * 20  # pad to meet word count
        result = self.lint.lint_letter(letter, mode="default", letter_type="findings")
        violations = result.get("violations", [])
        rules = [
            getattr(v, 'rule', v.get('rule', ''))
            for v in violations
            if isinstance(v, dict) or hasattr(v, 'rule')
        ]
        # Should flag unsupported assertions about fraud/theft
        assert "unsupported_assertions" in rules or not result.get("lint_passed", True)


class TestConditionalPolishDetection:
    """Verify artifact detection correctly identifies drafts that need polish."""

    def test_clean_professional_letter_skips_polish(self):
        letter = (
            "Good afternoon,\n\n"
            "I wanted to share my preliminary findings after reviewing the "
            "documents in your case. Based on the subscription agreement "
            "dated January 15, 2024, there appear to be several potential "
            "claims worth pursuing.\n\n"
            "## Background & Issue\n\n"
            "You invested $50,000 into a real estate development project "
            "managed by ABC Development LLC.\n\n"
        )
        assert not draft_needs_polish(letter)

    def test_letter_with_pipeline_artifacts_triggers_polish(self):
        letter = (
            "Good afternoon,\n\n"
            "You invested $50,000 (intake packet 01-11-2026) into "
            "the development project. The client-reported timeline "
            "indicates delays per intake documentation.\n\n"
        )
        assert draft_needs_polish(letter)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_letter_quality_pipeline.py -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_letter_quality_pipeline.py
git commit -m "test: add integration tests for letter quality pipeline

Verifies lint catches snake_case tokens, raw filenames, and unsupported
assertions. Verifies conditional polish detection logic."
```

---

**Phase 3 expected impact:**
- **Speed:** ~25-40% latency reduction on letters that don't need polish or critic. Clean drafts skip 2 AI calls (~25-50s).
- **Quality:** No degradation. All safety nets preserved. Polish still runs when artifacts detected. Critic still runs for low-scoring letters.
- **Observability:** Metrics track why each pass was skipped.

**Phase 3 regression risks:**
- **Artifact detection false negatives:** If the regex patterns miss an artifact type, polish won't run. Mitigated: the patterns match the specific things polish is designed to fix (per `letter_polish.py:29-69`). New artifact types would require adding patterns.
- **Lint score threshold too high/low:** If set at 85, some letters with moderate issues might skip critic. Mitigated: error-severity violations always trigger critic regardless of score.

---

## Chunk 4: Phase 4 — Structural Improvements (Reduced Scope)

**Objective:** Extract the letter-stream service from analysis.py (cleanest extraction boundary). Add instrumentation. Consolidate one duplicated helper. Defer the full orchestrator extraction.

### Task 4.1: Extract Letter-Stream Service

**Files:**
- Create: `src/legal_portal/services/letter_stream_service.py`
- Modify: `src/legal_portal/api/routes/analysis.py`

**Context:** The `stream_findings_letter` endpoint at `analysis.py:2355` contains a ~400-line `generate()` closure that handles the entire letter-generation pipeline. This is the cleanest extraction boundary because the closure's captured variables can be converted to explicit parameters.

**Do Not Break:** SSE event shapes (`token`, `phase`, `done`, `error`, `quality`, `final`, `heartbeat`). Schema v1/v2 compatibility. Quality report persistence. `letter_polish_enabled` / `letter_quality_lint_enabled` config flags.

- [ ] **Step 1: Identify all variables captured by the generate() closure**

Read `analysis.py` lines 2355-2900 and list every variable from the enclosing scope that `generate()` references:
- `analysis_id`, `supabase`, `mode`, `settings`, `processing_result`, `msr`, `artifacts`, `resolved_identity`, `ai_preferences`
- `_event_payload`, `_to_sse` helper functions
- Various config values extracted from `settings`

- [ ] **Step 2: Create letter_stream_service.py with explicit parameters**

```python
"""Letter-stream service — extracted from analysis.py stream_findings_letter."""

import asyncio
import json
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

from legal_portal.config.default import get_settings
from legal_portal.core.data_models import (
    DeepAnalysis,
    FactMatrix,
    GapAnalysisResult,
    LetterStructure,
    ProcessingResult,
)
from legal_portal.services.document_formatter import DocumentFormatterService
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.letter_validation_service import LetterValidationService
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


async def stream_letter_generation(
    *,
    analysis_id: str,
    processing_result: ProcessingResult,
    multi_stage_result: Dict[str, Any],
    artifacts: Dict[str, Any],
    resolved_identity: Dict[str, str],
    ai_preferences: Optional[Dict[str, Any]],
    mode: Literal["default", "strict_quality"],
    effective_schema_version: int,
    supabase,
) -> AsyncGenerator[str, None]:
    """Stream letter generation with lint/critic/repair/polish pipeline.

    Yields SSE-formatted events. Extracted from analysis.py to enable
    independent testing and reduce the route file size.
    """
    # ... move the body of generate() here, converting captured
    # variables to the explicit parameters above ...
```

- [ ] **Step 3: Update analysis.py to delegate to the service**

Replace the `generate()` closure in `stream_findings_letter` with a call to the extracted service:

```python
from legal_portal.services.letter_stream_service import stream_letter_generation

async def generate():
    async for event in stream_letter_generation(
        analysis_id=analysis_id,
        processing_result=processing_result,
        multi_stage_result=msr,
        artifacts=artifacts,
        resolved_identity=resolved_identity,
        ai_preferences=ai_preferences,
        mode=mode,
        effective_schema_version=effective_schema_version,
        supabase=supabase,
    ):
        yield event
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/api/test_letter_stream_integration.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/services/letter_stream_service.py src/legal_portal/api/routes/analysis.py
git commit -m "refactor: extract letter-stream service from analysis.py

Moves ~400 lines of letter generation pipeline (strategy, draft,
lint, critic, repair, polish, finalization) to a dedicated service.
analysis.py route handler now delegates to the service."
```

---

### Task 4.2: Consolidate _run_with_heartbeat Duplication

**Files:**
- Create: `src/legal_portal/utils/heartbeat.py`
- Modify: `src/legal_portal/services/main_processor.py` (lines 40-84)
- Modify: `src/legal_portal/services/multi_stage_analyzer.py` (lines 459-508)

**Context:** Two implementations exist with different signatures but the same purpose — sending SSE heartbeats during long operations. The `main_processor.py` version (module-level function) is more general. The `multi_stage_analyzer.py` version (instance method) uses a nested coroutine pattern.

- [ ] **Step 1: Create shared heartbeat utility**

```python
"""Shared heartbeat wrapper for long-running async operations.

Sends periodic progress callbacks to prevent SSE timeout during
expensive AI calls or document processing.
"""

import asyncio
import time
from typing import Any, Callable, Optional

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


async def run_with_heartbeat(
    coro_or_callable,
    progress_callback: Optional[Callable],
    phase: str,
    percent: int,
    heartbeat_interval: float = 10.0,
    *args,
    **kwargs,
) -> Any:
    """Run a coroutine or callable while sending heartbeat progress.

    Args:
        coro_or_callable: Async coroutine function or sync callable
        progress_callback: Optional callback for progress updates
        phase: Current phase name for progress reporting
        percent: Current percent for progress reporting
        heartbeat_interval: Seconds between heartbeat emissions
        *args, **kwargs: Passed to the coroutine/callable

    Returns:
        Result of the coroutine/callable
    """
    start = time.time()

    if asyncio.iscoroutinefunction(coro_or_callable):
        task = asyncio.create_task(coro_or_callable(*args, **kwargs))
    elif callable(coro_or_callable):
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(
            loop.run_in_executor(None, lambda: coro_or_callable(*args, **kwargs))
        )
    else:
        task = asyncio.ensure_future(coro_or_callable)

    while not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=heartbeat_interval)
        except asyncio.TimeoutError:
            elapsed = time.time() - start
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(
                            message=f"Still processing ({elapsed:.0f}s)...",
                            phase=phase,
                            percent=percent,
                        )
                    else:
                        progress_callback(
                            message=f"Still processing ({elapsed:.0f}s)...",
                            phase=phase,
                            percent=percent,
                        )
                except Exception as cb_err:
                    logger.debug("Heartbeat callback error: %s", cb_err)

    return task.result()
```

- [ ] **Step 2: Replace main_processor.py implementation with import**

At `main_processor.py:40`, replace the `_run_with_heartbeat` function definition with:
```python
from legal_portal.utils.heartbeat import run_with_heartbeat as _run_with_heartbeat
```

Verify the call site at line ~719 still works with the same signature.

- [ ] **Step 3: Replace multi_stage_analyzer.py implementation**

At `multi_stage_analyzer.py:459`, replace the `_run_with_heartbeat` instance method. The call sites at lines ~565, 620, 675 use a different signature (`api_call, progress_callback, stage_id, stage_name, base_progress`). Create a thin adapter method that translates:

```python
async def _run_with_heartbeat(self, api_call, progress_callback, stage_id, stage_name, base_progress, heartbeat_interval=10.0):
    """Adapter for shared heartbeat utility."""
    from legal_portal.utils.heartbeat import run_with_heartbeat
    return await run_with_heartbeat(
        api_call,
        progress_callback,
        phase=stage_name,
        percent=base_progress,
        heartbeat_interval=heartbeat_interval,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_main_processor.py tests/unit/test_multi_stage_analyzer.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/utils/heartbeat.py src/legal_portal/services/main_processor.py src/legal_portal/services/multi_stage_analyzer.py
git commit -m "refactor: consolidate duplicated _run_with_heartbeat into shared utility

Two implementations (main_processor.py and multi_stage_analyzer.py)
replaced with one shared utility. Adapter method preserves legacy
call signature in multi_stage_analyzer."
```

---

### Task 4.3: Plan Import-Time Document Classification (Design Only)

**Files:**
- Create: `docs/plans/2026-03-XX-import-time-classification.md`

**Context:** The review identified that moving document classification to import time (instead of analysis time) would let the entire pipeline make importance-aware decisions from upload. Currently, `DocumentRegistryService.build_initial_registry()` is called at both upload time (`documents.py:75`) and processing time (`main_processor.py:927`). The upload-time call already produces authority scores — but they're not stored or used by the analysis pipeline.

This is a larger architectural change. This task produces a design document, not implementation.

- [ ] **Step 1: Write design document**

Document:
- Current state: registry built at upload and at analysis time (duplicate work)
- Proposed: store initial registry scores in `documents` table at upload, enrich during analysis
- Benefits: skip full extraction for low-authority docs, pre-sorted document sets
- Risks: scores may change after cross-document enrichment, upgrade path for existing docs
- Dependencies: database schema change (add `authority_score` column to documents table)

- [ ] **Step 2: Commit**

```bash
git add docs/plans/
git commit -m "docs: design document for import-time document classification"
```

---

**Phase 4 expected impact:**
- **Maintainability:** Letter stream logic isolated in own module (~400 lines out of analysis.py)
- **Testability:** Letter stream service independently testable
- **Code clarity:** Single heartbeat implementation

**What is deferred and why:**
- **Full analysis.py orchestrator extraction:** `process_case_background()` depends on ~1,500 lines of helpers, many shared with other endpoints. Extracting it requires a full dependency analysis to determine which helpers are exclusive vs. shared, and where shared helpers should live. This is a 1-2 week project that deserves its own plan.
- **Import-time classification:** Requires a database schema change. Design document produced in this phase; implementation planned separately.

---

## Top 5 Improvements to Implement First

| Priority | Task | Time | Impact |
|---|---|---|---|
| 1 | **Task 1.1**: Delete dead file-based OCR functions | 30 min | ~600 lines of noise removed, zero risk |
| 2 | **Task 2.1**: Weighted token allocation with proportional scaling | 2-3 hrs | Highest-value quality improvement for letters |
| 3 | **Task 2.2**: Wire registry through analysis.py:4171 | 30 min | Makes Task 2.1 effective in production |
| 4 | **Task 3.1**: Conditional polish pass | 1-2 hrs | ~15-30s saved on clean drafts, safety net preserved |
| 5 | **Task 2.3**: Sort doc summaries by authority in letter prompt | 30 min | Better document ordering in letter generation |

## Biggest Remaining Architectural Bottleneck

**Document classification happens too late in the pipeline.** The registry is built during `process_case_documents()`, after all documents have already been fully extracted. This means every document — including cover letters, duplicate forwards, and metadata stubs — consumes the same OCR and extraction budget as controlling instruments. Moving classification to upload time would let the pipeline defer extraction for low-value documents and prioritize expensive processing for the documents that actually matter. (Designed in Task 4.3, implemented separately.)

## One Improvement That Would Most Increase Both Speed AND Letter Quality

**Importance-weighted token allocation (Phase 2).** It is the only change that simultaneously:
- Improves speed: higher-authority documents occupy more of the budget, so the model does less work reasoning about irrelevant content
- Improves quality: controlling instruments get 4x more token budget, meaning the model sees actual contract terms, obligation clauses, and signature details instead of truncated stubs
- Reduces hallucination: the model has more source material from authoritative documents to ground its claims in

No other single change in this plan achieves all three.
