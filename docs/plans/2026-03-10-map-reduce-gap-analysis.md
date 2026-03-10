# Map-Reduce Gap Analysis for Large Cases (150-250 docs)

## Context

Gap analysis currently caps document context at 50 docs (`_GAP_CONTEXT_MAX_DOCS = 50`), but cases regularly have 150-250 documents. This causes:
- **Missing gaps**: Evidence gaps not identified because the AI never saw excluded docs
- **Wrong gaps**: AI flags things as missing that exist in unseen documents

Document summaries (`DocumentSummaryStructured`) are already generated for ALL documents during Stage 2 and stored in `result_payload["document_summaries_json"]`. The 50-doc cap only applies to the gap analysis fetch path.

## Approach: Two-Stage Map-Reduce

**Map phase**: Partition all docs into 4-7 intelligent batches by role/type, run each through gpt-5-mini (`reasoning_effort="low"`) in parallel, producing a structured `BatchGapReport`.

**Reduce phase**: Merge all batch reports + full case context into a single gpt-5.4 call (`reasoning_effort="medium"`) producing the final `GapAnalysisResult`.

Cases with <=50 docs continue using the existing single-pass path (no regression risk).

## Model Selection

**Why the existing single-pass uses gpt-4.1 and the new map-reduce path does not:**

The existing single-pass `analyze_gaps()` deliberately chose gpt-4.1 with the comment: *"GPT-5.2 with reasoning_effort spends tokens on internal reasoning, not output."* This was the correct call for the single-pass path — it processes at most 50 pre-summarized documents, doing straightforward structured extraction where gpt-4.1's speed and JSON reliability outweigh reasoning capability.

The map-reduce path has a fundamentally different task profile:
- **Map batches must detect cross-document contradictions and infer missing evidence** from partial views of the case. This requires reasoning capability that gpt-4.x models lack — they extract what's stated but don't infer what's absent or contradictory across documents.
- **The reduce phase must merge conflicting signals across batches**, resolve `cross_batch_uncertain` flags, and recalibrate severity with full-case context. This is a synthesis task, not an extraction task.

The existing single-pass path remains on gpt-4.1 via `get_preferred_model("gap_analysis", "gpt-4.1")`. This is unchanged.

**Map phase — gpt-5-mini with reasoning_effort="low":**
- The map phase is the only chance to detect signals — if it misses a gap or contradiction, the reduce phase cannot recover it.
- Contradiction detection and cross-document inference require reasoning capability, which GPT-4.x models lack.
- `reasoning_effort="low"` provides reasoning without excessive token overhead.
- Configurable via `get_preferred_model("gap_analysis_map", "gpt-5-mini")` for tuning.
- Risk: gpt-5-mini structured JSON reliability is unverified at this schema complexity. Mitigation: see Step 5b for tiered retry strategy and Step 9 for parse failure rate monitoring.

**Reduce phase — gpt-5.4 with reasoning_effort="medium":**
- gpt-5.4 is the current top-tier model and should be the default reducer unless testing reveals a specific regression vs gpt-5.2.
- Cross-batch merge, deduplication, and severity recalibration are complex reasoning tasks that benefit from the strongest available model.
- Configurable via `get_preferred_model("gap_analysis_reduce", "gpt-5.4")`.
- Note: gpt-5.4 is not currently in the codebase's pricing table or model routing. Step 0 adds it with explicit "unverified" pricing handling.

**Latency & cost**: Estimates below are approximate and must be validated empirically during integration testing. No official latency benchmarks are available for gpt-5.4 or gpt-5-mini at these prompt sizes. Cost estimates use the codebase's 2025 pricing table which may be outdated.

---

## Step 0: Add gpt-5.4 to Model Routing

**File:** `src/legal_portal/utils/openai_client.py`

- Add gpt-5.4 to the pricing table (lines 237-249) with **`pricing_verified: False`**. Do NOT use placeholder gpt-5.2 pricing. Instead:
  - Set `input_per_1k` and `output_per_1k` to `None`.
  - Guard cost-calculation code: if pricing is `None`, skip cost tracking and log `[COST:SKIP] gpt-5.4 pricing unverified — cost not tracked for this call`.
  - This ensures the model is routable but cost reports don't contain fabricated numbers.
- Verify `_is_gpt5_model()` matches gpt-5.4 (it should — checks for "gpt-5" prefix).
- No other changes needed — `create_response()` routes all gpt-5.* models through the same parameter path (`max_completion_tokens`, `reasoning_effort`).

---

## Step 1: Add document_id to DocumentSummaryStructured

**File:** `src/legal_portal/core/data_models.py`

**Problem:** `DocumentSummaryStructured` identifies documents by `document_name` (a display string). Signature evidence and document registry both carry `document_id` (database UUID). The current system joins these by fuzzy name matching, which is fragile.

**Fix:** Add `document_id: Optional[str] = None` to `DocumentSummaryStructured`. This is backward-compatible — existing summaries without IDs still parse.

**Populate it:** In `_parse_gap_document_summaries()` (`analysis.py:6098`), after parsing summaries, build an ID map from metadata rows using a normalized key `file_name.lower().strip()` -> `document_id`. For collisions (multiple docs with the same display name), prefer the most recently updated match (`updated_at DESC`) and log a warning:
```
[GAP:ID_STAMP] Collision on normalized name "{name}" — {n} docs match, using most recent (id={id})
```
Stamp `document_id` on each summary via this map. Summaries that fail to match get `document_id=None` and are logged:
```
[GAP:ID_STAMP] No metadata match for summary "{document_name}" — will use name-based fallback
```

All new batch/map/reduce code uses `document_id` for joins. Name-based matching is eliminated from the new code paths. Summaries without `document_id` are included in an "unmatched" batch to avoid silent data loss.

**Follow-up (non-blocking):** Stage 2 should be updated to emit `document_id` directly during summarization, eliminating this parse-time join entirely.

---

## Step 2: Simplified Intermediate Models

**File:** `src/legal_portal/core/data_models.py`

The previous `BatchGapReport` schema had 7 list fields, 4 sub-models, and a boolean flag (`may_exist_in_other_batches`). This is too complex for reliable structured JSON output from gpt-5-mini.

Simplified schema — 3 core sections instead of 7:

```python
class BatchEvidence(BaseModel):
    """Evidence category detected in a batch."""
    category: str                     # e.g., "executed_contracts"
    document_ids: List[str]           # database UUIDs
    status: str                       # "present" | "missing" | "incomplete"
    severity: Optional[str] = None    # only for missing/incomplete: "critical"/"high"/"medium"/"low"
    detail: str                       # 1-2 sentence explanation

class BatchFinding(BaseModel):
    """A gap, contradiction, or concern found in a batch."""
    category: str                     # maps to GapCategory values
    severity: str                     # "critical" / "high" / "medium" / "low"
    title: str
    description: str
    document_ids: List[str]           # database UUIDs of related docs
    affected_issue: Optional[str] = None
    cross_batch_uncertain: bool = False  # may be resolved by another batch

class BatchGapReport(BaseModel):
    """Structured output from a single map-phase batch."""
    batch_id: str
    batch_label: str
    document_count: int
    evidence: List[BatchEvidence]     # what's present, missing, or incomplete
    findings: List[BatchFinding]      # gaps, contradictions, concerns
    cross_batch_flags: List[str]      # structured flags, max 5, format: "CHECK_BATCH:{label} FOR:{category}"
```

**`cross_batch_flags` format:** Short, structured strings the reduce phase can parse programmatically. Examples:
- `"CHECK_BATCH:correspondence FOR:executed_subscription_agreement"`
- `"CHECK_BATCH:financial_evidence FOR:payment_receipts"`
- `"CHECK_BATCH:official_records FOR:corporate_registration"`

The map prompt constrains output to this format and limits to 5 flags. This replaces the previous free-form notes field which would produce unpredictable content.

**Why this is better:**
- 2 list fields + 1 structured flags field vs. 7 separate lists
- `BatchEvidence` merges "present" and "missing" into one list with a status discriminator — simpler for the model to produce
- `BatchFinding` merges gaps, contradictions, and execution issues into one list — the `category` field discriminates
- Fewer nested types = more reliable JSON from smaller models
- `cross_batch_uncertain` replaces `may_exist_in_other_batches` (same semantics, clearer name)

**Add to `GapAnalysisResult`:**
```python
map_reduce_metadata: Optional[Dict[str, Any]] = None
analysis_quality: Optional[str] = None  # "full" | "degraded_partial" | "degraded_merge" | "fallback_single_pass"
```

**`analysis_quality` values:**
- `"full"` — map-reduce completed successfully with all batches
- `"degraded_partial"` — some map batches failed, reduce ran on partial data
- `"degraded_merge"` — reduce phase failed, mechanical merge used instead
- `"fallback_single_pass"` — all map batches failed, fell back to existing 50-doc single-pass
- `None` — analysis ran via existing single-pass path (<=50 docs, backward compatible)

The frontend should display a warning banner for any non-`"full"` / non-`None` value. Letter generation should check this field and log a warning if generating from degraded results.

---

## Step 3: Document Fetch — Remove Cap for Metadata

**File:** `src/legal_portal/api/routes/analysis.py`

### 3a: New function `_fetch_all_case_document_metadata()`

Fetches ALL document rows WITHOUT full text columns:
```python
def _fetch_all_case_document_metadata(supabase, case_id: str) -> List[Dict[str, Any]]:
    """Fetch lightweight metadata for ALL case documents (no full text).

    Includes extracted_at and text_hash for cache invalidation without
    transferring full extracted_text/manual_text payloads.
    """
    resp = supabase.table("documents") \
        .select("id, file_name, file_type, status, updated_at, extracted_at, metadata") \
        .eq("case_id", case_id) \
        .order("updated_at", desc=True) \
        .execute()
    rows = resp.data or []
    logger.info(f"[GAP:FETCH_META] case_id={case_id} total_docs={len(rows)}")
    return rows
```

~500 bytes/row = ~125KB for 250 docs (no payload concern).

**State hash for >50-doc cases (C1 fix):**

The existing `_build_case_document_state_hash()` computes a `text_fingerprint` from `manual_text`/`extracted_text`. The metadata-only fetch deliberately excludes those columns to avoid 40MB+ payloads. For the >50-doc path, state hashing uses a different strategy:

```python
def _build_case_document_state_hash_lightweight(metadata_rows: List[Dict[str, Any]]) -> str:
    """State hash for large cases using metadata-only rows.

    Trade-off (documented): This hash is sensitive to document additions,
    deletions, status changes, and re-extractions (via extracted_at timestamp),
    but NOT to manual text edits that don't update extracted_at or updated_at.

    This is acceptable for v1 because:
    1. Manual text edits always update updated_at (verified in verify_document endpoint)
    2. The gap analysis input hash also includes document_summaries_hash,
       which changes when summaries are regenerated after text edits
    3. The only blind spot is: user edits manual_text, updated_at changes,
       but summaries are NOT regenerated. This already causes stale gap analysis
       in the single-pass path too — it's a pre-existing limitation, not a regression.
    """
    if not metadata_rows:
        return "no_case_documents"

    canonical_rows = sorted(
        [
            {
                "id": doc.get("id"),
                "updated_at": doc.get("updated_at"),
                "status": str(doc.get("status") or ""),
                "file_name": doc.get("file_name"),
                "extracted_at": doc.get("extracted_at"),
            }
            for doc in metadata_rows
        ],
        key=lambda r: r["id"] or "",
    )
    return _hash_jsonable(canonical_rows)
```

The routing logic selects the appropriate hash function:
- <=50 docs: existing `_build_case_document_state_hash()` with full text fingerprints (no change)
- &gt;50 docs: `_build_case_document_state_hash_lightweight()` with metadata-only fields

### 3b: Keep `_fetch_case_documents_for_gap_context()` as-is

Still used by the single-pass path for <=50 doc cases.

---

## Step 4: Intelligent Batching

**File:** `src/legal_portal/api/routes/analysis.py`

**New function:** `_build_gap_analysis_batches()`

All joins use `document_id` — summaries, registry entries, and signature evidence are matched by database UUID, not by name.

**Grouping strategy (priority-ordered):**
1. **Primary axis — `role_in_case`** from document registry (already has `document_id`):
   - `"controlling_instrument"` — contracts, agreements, operating docs
   - `"financial_evidence"` — invoices, receipts, financial statements
   - `"correspondence"` — emails, letters, messages
   - `"official_record"` — government filings, certificates
   - `"supporting_evidence"` — photos, media, miscellaneous
   - `"intake"` — intake forms
   - Unmapped docs -> `"other"`
2. **Overflow splitting** — if any group >40 docs, split by `document_type` within that group. If still >40, split by date bands (chronological thirds of `updated_at`).
3. **Merge small groups** — groups with <3 docs merge into a deterministic target group using this explicit mapping:

```python
# Deterministic small-group merge targets.
# When a role group has <3 docs, merge it into the specified target.
# Order matters: if the target is also small, both merge into the next target.
_SMALL_GROUP_MERGE_MAP = {
    "intake":              "correspondence",
    "official_record":     "controlling_instrument",
    "supporting_evidence": "financial_evidence",
    "other":               "correspondence",
    "correspondence":      "controlling_instrument",
    "financial_evidence":  "controlling_instrument",
    # "controlling_instrument" is the terminal merge target — never merges further.
}
```

Merge algorithm:
1. Identify all groups with <3 docs.
2. For each small group (processed in alphabetical order for determinism), look up merge target in `_SMALL_GROUP_MERGE_MAP`.
3. If the target group exists (regardless of its current size), merge into it.
4. If the target group was already merged into something else, follow the chain (max depth 3, then dump into `"controlling_instrument"`).
5. Unit test: verify that for every role in the enum, the merge chain terminates at `"controlling_instrument"` within 3 hops.

**Input:** `doc_summaries_list` (with `document_id` stamped), `signature_evidence` list, `document_registry` list
**Output:** `List[GapBatch]` — each batch contains subsets of summaries, signature evidence, and registry entries, all linked by `document_id`.

```python
@dataclass
class GapBatch:
    batch_id: str
    batch_label: str
    document_ids: List[str]
    document_summaries: List[DocumentSummaryStructured]
    signature_evidence: List[Dict[str, Any]]
    registry_entries: List[Dict[str, Any]]
```

---

## Step 5: Map Phase — Batch Gap Analysis

**File:** `src/legal_portal/services/gap_analysis_service.py`

### 5a: New method `_build_map_prompt()`

Per-batch prompt includes:
- Batch label and context ("Batch 2 of 6: Controlling Instruments")
- Other batch labels (so AI knows what's analyzed elsewhere)
- Document evidence summary (reuse `_build_document_evidence_summary()`)
- Signature evidence for batch docs (reuse `_build_signature_evidence_summary()`)
- Registry entries for batch docs (reuse `_build_document_registry_summary()`)
- Condensed `fact_matrix.parties` and `fact_matrix.timeline` (shared, small)
- `issue_map.primary_issues` (shared, small)
- Document ID mapping table at the top: `doc_id` -> `file_name` so the AI can reference IDs in output

**NOT included in map prompts** (saved for reduce):
- `deep_analysis`, `intake_content`, prior gap analysis, resolution context

**Model:** gpt-5-mini, `reasoning_effort="low"`, `max_output_tokens=3000`
**Configurable via:** `get_preferred_model("gap_analysis_map", "gpt-5-mini")`

### 5b: New method `_run_map_batch()`

Tiered retry strategy for parse failures:

1. **Attempt 1:** gpt-5-mini with standard map prompt. Parse response JSON into `BatchGapReport`.
2. **Attempt 2 (same model, repair prompt):** If JSON parse fails, retry with the same gpt-5-mini model using a stricter repair prompt that includes:
   - The malformed output from attempt 1
   - Explicit instruction: "The previous output had invalid JSON. Return ONLY the corrected JSON object matching the BatchGapReport schema. No markdown, no explanation."
   - Reduced `max_output_tokens=2000` to constrain output
3. **Attempt 3 (fallback model):** If still fails, retry with gpt-4.1 (no reasoning, but more reliable structured JSON) using the original map prompt.
4. If all 3 attempts fail, raise and treat as batch failure.

Returns `BatchGapReport` on success, raises on failure.

### 5c: New method `analyze_gaps_map_reduce()`

```python
async def analyze_gaps_map_reduce(
    self,
    batches: List[GapBatch],
    fact_matrix, issue_map, deep_analysis,
    intake_content, signature_evidence, document_registry,
    resolution_context=None, prior_gap_analysis=None,
) -> GapAnalysisResult:
    # Map phase — parallel
    map_tasks = [self._run_map_batch(batch, fact_matrix, issue_map) for batch in batches]
    batch_results = await asyncio.gather(*map_tasks, return_exceptions=True)

    successful = [r for r in batch_results if isinstance(r, BatchGapReport)]
    failed = [(batches[i], r) for i, r in enumerate(batch_results) if isinstance(r, Exception)]

    # Reduce phase
    result = await self._run_reduce(successful, failed, fact_matrix, issue_map,
                                     deep_analysis, intake_content, signature_evidence,
                                     document_registry, resolution_context, prior_gap_analysis)

    # Reconciliation (same as current single-pass)
    result = self._reconcile_signature_execution_gaps(result, signature_evidence)
    result.recommendation = self._generate_recommendation(result, deep_analysis=deep_analysis)

    # Attach provenance metadata
    result.map_reduce_metadata = { ... }
    return result
```

---

## Step 6: Reduce Phase — Merge Batch Findings

**File:** `src/legal_portal/services/gap_analysis_service.py`

### 6a: New method `_build_reduce_prompt()`

**Inputs:**
- All `BatchGapReport` objects serialized as JSON
- `fact_matrix` (full), `issue_map` (full), `deep_analysis` (full)
- `intake_content` (up to 2000 chars)
- Full signature evidence summary, full document registry summary
- Prior gap analysis + resolution context (if selective refresh)

**Merge instructions in prompt:**
1. Cross-reference: if Batch A flags "missing contract" but Batch B's evidence shows `status="present"` for that category, REMOVE the gap
2. Items with `cross_batch_uncertain=true` require cross-batch verification before including
3. Identify NEW cross-batch gaps not visible to any single batch
4. Deduplicate overlapping findings across batches
5. Recalibrate severity with full-case context
6. Calculate single `overall_completeness_score`

**Output:** `GapAnalysisResult` JSON (same schema as current — unchanged API contract)
**Model:** gpt-5.4, `reasoning_effort="medium"`, `max_output_tokens=6000`
**Configurable via:** `get_preferred_model("gap_analysis_reduce", "gpt-5.4")`

### 6b: New method `_run_reduce()`

- Calls `asyncio.to_thread(self.client.create_response, ...)` with reduce prompt
- On failure: mechanical merge fallback (see below)

**Mechanical merge fallback (deterministic deduplication):**

When the reduce phase fails, concatenate batch findings and deduplicate using this deterministic algorithm:

```python
def _deduplicate_findings(findings: List[BatchFinding]) -> List[BatchFinding]:
    """Deterministic deduplication for mechanical merge fallback.

    Two findings are considered duplicates if ALL of:
    1. Normalized titles match (lowercase, strip whitespace, remove punctuation)
    2. Same category
    3. Overlapping document_ids (intersection >= 1)

    When duplicates are found:
    - Keep the finding with the higher severity (critical > high > medium > low)
    - On severity tie, keep the one with more document_ids
    - On further tie, keep the first encountered (stable sort)
    - Merge document_ids from both into the kept finding (union)
    """
```

This replaces the previous vague "deduplicate by title similarity" instruction with concrete, testable logic.

---

## Step 7: Route to Map-Reduce in Endpoint

**File:** `src/legal_portal/api/routes/analysis.py`

Four entry points invoke gap analysis. The `_run_gap_analysis` helper covers all of them transitively, but all 4 must be verified during testing:

1. `analyze_gaps_on_demand` (line 6230) — on-demand full analysis
2. `resolve_gaps_and_refresh` (line 6376) — selective refresh with user resolutions
3. `stream_findings_letter` (line 2384) — calls `_ensure_fresh_gap_analysis_for_letter_generation`
4. `generate_letter` (line 4303) — also calls `_ensure_fresh_gap_analysis_for_letter_generation`

The actual routing change is in 3 functions (the `_ensure_fresh_...` helper serves both letter endpoints):
1. `analyze_gaps_on_demand`
2. `resolve_gaps_and_refresh`
3. `_ensure_fresh_gap_analysis_for_letter_generation` (line 5964)

**Extract shared helper:**

```python
async def _run_gap_analysis(
    gap_service, doc_summaries_list, fact_matrix, issue_map, deep_analysis,
    intake_content, signature_evidence, document_registry,
    resolution_context=None, prior_gap_analysis=None,
):
    if len(doc_summaries_list) > _GAP_CONTEXT_MAX_DOCS:
        batches = _build_gap_analysis_batches(
            doc_summaries_list, signature_evidence, document_registry)
        return await gap_service.analyze_gaps_map_reduce(
            batches=batches, ...)
    else:
        return await gap_service.analyze_gaps(...)
```

**Document fetch changes:**
- Use `_fetch_all_case_document_metadata()` (no text, no cap) for state hashing and signature evidence
- Load document registry from `multi_stage_result["document_registry"]` when available (already stored at line 6342), only rebuild if missing
- Stamp `document_id` on summaries in `_parse_gap_document_summaries()` using the metadata rows

---

## Step 8: Cache Invalidation Updates

**File:** `src/legal_portal/api/routes/analysis.py`

- **<=50 docs path**: `_build_case_document_state_hash()` unchanged — uses full text fingerprints from `_fetch_case_documents_for_gap_context()`
- **>50 docs path**: New `_build_case_document_state_hash_lightweight()` operates on ALL doc metadata rows (from `_fetch_all_case_document_metadata`) — uses `(id, updated_at, status, file_name, extracted_at)` tuples instead of text fingerprints (see Step 3a for trade-off documentation)
- Add `"map_reduce_version": "1"` to `_build_gap_analysis_input_hash` canonical payload
- Bump `_GAP_ANALYSIS_INPUT_SCHEMA_VERSION` to force re-analysis of all cached results

---

## Step 9: Logging

**Map phase (per batch):**
```
[GAP:MAP:{batch_id}] Starting | docs={n} label={label} model={model}
[GAP:MAP:{batch_id}] Complete | duration={s} evidence={n} findings={n}
[GAP:MAP:{batch_id}] FAILED | error={e} retry_stage={1|2|3}
```

**Reduce phase:**
```
[GAP:REDUCE] Starting | batches_ok={n} batches_failed={n} total_findings={n} model={model}
[GAP:REDUCE] Complete | duration={s} final_gaps={n} score={score}
```

**Map parse failure rate monitoring (operational watch item):**

gpt-5-mini structured JSON reliability at this schema complexity is the biggest technical risk. Add explicit counters to detect viability problems early:

```
[GAP:MAP:PARSE_STATS] total_batches={n} first_attempt_success={n} repair_success={n} fallback_success={n} total_failures={n} parse_failure_rate={pct}%
```

Log this summary line after all map batches complete (success or failure). Include it in `map_reduce_metadata`:
```python
"parse_stats": {
    "first_attempt_success": 4,
    "repair_prompt_success": 1,
    "fallback_model_success": 0,
    "total_failures": 0,
    "parse_failure_rate_pct": 0.0,
}
```

If `parse_failure_rate_pct` exceeds 40% across a rolling window of 10 analyses, log a `[GAP:MAP:VIABILITY_WARNING]` — this signals gpt-5-mini may not be viable at this schema complexity and the default should be reconsidered.

**Provenance in `map_reduce_metadata`:**
```json
{
    "pipeline": "map_reduce",
    "total_documents_analyzed": 187,
    "map_model": "gpt-5-mini",
    "reduce_model": "gpt-5.4",
    "batches": [
        {"batch_id": "...", "batch_label": "...", "doc_count": 32,
         "evidence_count": 12, "findings_count": 4, "duration_s": 5.1,
         "model_used": "gpt-5-mini", "retry_count": 0},
        ...
    ],
    "failed_batches": [],
    "reduce_duration_s": 12.3,
    "map_total_findings": 18,
    "reduce_final_gaps": 12,
    "parse_stats": {"first_attempt_success": 4, "repair_prompt_success": 1, "fallback_model_success": 0, "total_failures": 0, "parse_failure_rate_pct": 0.0}
}
```

---

## Step 10: Error Handling

| Scenario | Behavior |
|----------|----------|
| Map batch JSON parse failure | Tiered retry: (1) same model + repair prompt, (2) gpt-4.1 fallback. If all 3 attempts fail, treat as batch failure. |
| One map batch fails | Log, continue with other batches. Reduce prompt notes the missing batch. Add `INCOMPLETE_INFO` gap item. Set `analysis_quality="degraded_partial"`. |
| Reduce fails | Mechanical merge: concatenate batch findings, deduplicate deterministically (normalized title + category + overlapping doc IDs). Set `analysis_quality="degraded_merge"`. |
| All map batches fail | Fall back to single-pass `analyze_gaps()` with 50-doc cap. Set `analysis_quality="fallback_single_pass"`. |
| All batches + reduce succeed | Set `analysis_quality="full"`. |
| <=50 docs | Use existing single-pass path. `analysis_quality` remains `None` (backward compatible). |

---

## Files Modified

| File | Changes |
|------|---------|
| `src/legal_portal/utils/openai_client.py` | Add gpt-5.4 to pricing table with `None` pricing and cost-skip guard. |
| `src/legal_portal/core/data_models.py` | Add `document_id` to `DocumentSummaryStructured`. Add `BatchEvidence`, `BatchFinding`, `BatchGapReport` models. Add `map_reduce_metadata` and `analysis_quality` to `GapAnalysisResult`. |
| `src/legal_portal/api/routes/analysis.py` | Add `_fetch_all_case_document_metadata()`, `_build_gap_analysis_batches()`, `_run_gap_analysis()`. Update `_parse_gap_document_summaries()` to stamp `document_id`. Update 3 call sites. Update hash computation. |
| `src/legal_portal/services/gap_analysis_service.py` | Add `analyze_gaps_map_reduce()`, `_run_map_batch()`, `_build_map_prompt()`, `_run_reduce()`, `_build_reduce_prompt()`, `_deduplicate_findings()`. |

## Existing Code to Reuse

- `_build_document_evidence_summary()` (gap_analysis_service.py:205) — reuse for map prompts
- `_build_signature_evidence_summary()` (gap_analysis_service.py:241) — reuse for map prompts
- `_build_document_registry_summary()` (gap_analysis_service.py:280) — reuse for map prompts
- `_truncate_text()` (gap_analysis_service.py:196) — reuse as-is
- `_reconcile_signature_execution_gaps()` (gap_analysis_service.py:615) — runs on final result after reduce
- `_generate_recommendation()` — runs on final result after reduce
- `asyncio.gather(*tasks, return_exceptions=True)` pattern from `document_processor.py`
- `asyncio.to_thread(self.client.create_response, ...)` pattern from existing `analyze_gaps()`

---

## Verification

1. **Unit tests: Batching logic** — mock docs of sizes 10, 50, 100, 250. Verify grouping by role, overflow splitting, small-group merging. Verify all joins use `document_id`.
2. **Unit tests: Small-group merge map** — verify every role terminates at `"controlling_instrument"` within 3 hops. Verify deterministic ordering (alphabetical processing).
3. **Unit tests: Deduplication** — verify exact match (same normalized title + category + overlapping IDs) deduplicates. Verify non-overlapping IDs keeps both. Verify severity ranking.
4. **Unit tests: Map prompt** — verify batch gets only its docs, shared context included, document ID mapping table present.
5. **Unit tests: Reduce prompt** — verify all batch reports included, merge instructions present.
6. **Unit tests: Routing** — <=50 docs uses single-pass, >50 uses map-reduce.
7. **Unit tests: Error handling** — one batch failure, all batch failure, reduce failure, tiered parse retry (repair prompt then gpt-4.1).
8. **Unit tests: Pricing guard** — gpt-5.4 calls log cost-skip warning, don't produce cost entries.
9. **Unit tests: Lightweight state hash** — verify hash changes when `updated_at`, `status`, or `extracted_at` changes. Verify hash does NOT change on field reordering. Verify <=50-doc path still uses full text fingerprint hash.
10. **Unit tests: Parse stats** — verify `parse_stats` in `map_reduce_metadata` accurately counts first-attempt, repair, fallback, and failure outcomes.
11. **Integration test:** Run on real case with 150+ docs. Compare quality to 50-doc single-pass.
12. **Integration test:** Verify gpt-5.4 is reachable and produces valid `GapAnalysisResult` JSON.
13. **Integration test:** Verify gpt-5-mini produces valid `BatchGapReport` JSON at `reasoning_effort="low"`.
14. **Cache test:** Adding a document to a large case invalidates cached gap analysis.
15. **Latency measurement:** Record actual timings for map and reduce phases on 200-doc case.
16. **Entry point test:** Verify all 4 entry points (analyze_gaps_on_demand, resolve_gaps_and_refresh, stream_findings_letter, generate_letter) correctly route to map-reduce for >50-doc cases.

---

## Estimated Latency & Cost (Unverified)

These are rough estimates based on the codebase's 2025 pricing table and observed latencies for similar models. Must be validated empirically during integration testing.

**Latency (200-doc case, ~5 batches):**
- Map phase: 5 parallel gpt-5-mini calls = est. 3-8s wall clock
- Reduce phase: 1 gpt-5.4 call with medium reasoning = est. 10-20s
- Overhead: ~1-2s
- Estimated total: 15-30s

**Cost per run (rough, using codebase pricing which may be outdated):**
- Map: 5 batches x ~3K input + ~2K output tokens each at gpt-5-mini rates
- Reduce: ~15K input + ~5K output tokens at gpt-5.4 rates
- Exact gpt-5.4 costs unknown until pricing is verified (see Step 0)
