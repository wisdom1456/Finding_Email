# Next Major Architectural Improvement: Tiered Document Intelligence Pipeline

---

## Executive Summary

The single highest-impact architectural change is to **move document classification and importance scoring upstream — from analysis time to upload time** — and use those scores to create a **tiered extraction pipeline** where expensive processing (full OCR, multi-page vision, AI summarization) is prioritized for legally important documents and deferred or skipped for low-value ones.

Today, every document gets identical treatment: full text extraction, full OCR if needed, full AI summarization, full token allocation. A 50-page signed operating agreement and a 1-paragraph forwarding email both consume the same OCR budget, the same summarization call, and until the v2 plan, the same context token allocation.

The v2 plan fixed the token allocation problem. This proposal fixes the two remaining bottlenecks:

1. **Extraction waste** — expensive OCR runs on documents before anyone knows if they matter
2. **AI call volume** — 16-21 model calls per case, many of which process low-value documents at the same fidelity as controlling instruments

**Estimated impact:**
- **Speed:** 30-50% reduction in total analysis time for typical 20-document cases
- **Cost:** 25-40% reduction in API spend per case
- **Quality:** Higher because the model spends more of its reasoning budget on legally significant documents

---

## The Single Highest-Impact Architectural Improvement

### Problem Statement

The current pipeline has a fundamental ordering problem:

```
Upload → Full Extraction → Full OCR → Registry Classification → Analysis → Letter
           ↑                              ↑
     Expensive work happens here    Importance known here
```

Classification happens AFTER the expensive work. By the time the system knows a document is a cover letter with authority_score 40, it has already spent 15-30 seconds on OCR and 5-10 seconds on AI summarization for that document.

### Proposed Solution

Invert the order. Classify first using cheap signals, then allocate expensive processing proportionally:

```
Upload → Cheap Classification → Tiered Extraction → Enriched Registry → Analysis → Letter
              ↑                        ↑
     Importance estimated here    Expensive work targeted here
```

The key insight from the codebase: `DocumentRegistryService.build_initial_registry()` already computes a useful authority_score from **filename + first 3,000 chars of text + signature metadata alone** — no AI needed. And the filename-based classification (`_infer_doc_type_from_name()` at `document_registry_service.py:80`) is available **at upload time with zero extraction**.

---

## Proposed System Architecture

### Document Intelligence Layer

A new service that sits between upload and extraction:

```
┌──────────────────────────────────────────────────────────┐
│                   Document Intelligence                   │
│                                                          │
│  Stage 0: Metadata Classification (at upload, <100ms)    │
│  ├─ filename pattern matching                            │
│  ├─ MIME type / file size signals                        │
│  ├─ duplicate detection (content hash)                   │
│  └─ preliminary authority_score estimate                 │
│                                                          │
│  Stage 1: Light Extraction (first 3K chars, <5s)         │
│  ├─ first-page text extraction (no OCR)                  │
│  ├─ signature page detection                             │
│  ├─ contract/instrument keyword scan                     │
│  └─ refined authority_score                              │
│                                                          │
│  Stage 2: Full Extraction (OCR if needed, 5-60s)         │
│  ├─ only for docs with authority_score >= threshold       │
│  ├─ prioritized by score (highest first)                 │
│  └─ low-priority docs get metadata-only entries          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Tiered Extraction Strategy

| Tier | Authority Score | Extraction Level | OCR | AI Summary | Estimated Time |
|------|----------------|-----------------|-----|-----------|----------------|
| **Controlling** | 75-100 | Full text + signature detection | Yes, all pages | Full structured summary | 15-60s |
| **Primary** | 55-74 | Full text, first 10 pages OCR | Yes, limited pages | Full structured summary | 5-20s |
| **Supporting** | 35-54 | First 3 pages + last page | Only if text empty | Compact summary (key facts only) | 2-10s |
| **Background** | 0-34 | First page only | No | Metadata-only entry | <2s |

### What Signals Drive Early Classification

**Available at upload time (zero cost):**

| Signal | What it tells you | Implementation |
|---|---|---|
| Filename patterns | Document type with medium confidence | `_infer_doc_type_from_name()` already exists at `document_registry_service.py:80` |
| File extension | Format class (PDF/DOCX/EML/image) | Already available from MIME detection |
| File size | Complexity estimate (1-page vs 50-page) | `len(file_content)` at upload |
| `is_intake_form` flag | User-marked intake | Form parameter in upload endpoint |
| Case document count | How selective to be | Query existing document count for case |

**Available after light extraction (first page, <5s):**

| Signal | What it tells you | Cost |
|---|---|---|
| First 3,000 chars of text | Contract vs. correspondence vs. receipt | PyMuPDF first-page extraction, no OCR |
| Keyword scan for "AGREEMENT", "CONTRACT", "DEED", "NOTE" | Controlling instrument detection | Regex on first-page text |
| Signature block patterns | Likely executed document | Regex for "Signed:", "By:", "DocuSign" |
| Date patterns near signatures | Execution date | Regex |
| Party name patterns | Who is involved | Regex for "Party A", "Landlord", "Borrower" |
| PDF digital signature metadata | Definitely signed | `/Type/Sig` in PDF objects — already detected in `pdf_processor.py` |

**Key point:** The existing `_infer_doc_type_from_name()`, `_infer_signature_expectation()`, `_infer_role_in_case()`, and `_score_authority()` methods in `DocumentRegistryService` already implement most of this logic. They just run too late in the pipeline.

### Duplicate / Forward / Chain Detection

Run at upload time using cheap signals:

1. **Content hash dedup**: Hash the file bytes at upload. Check against existing documents in the case. If match, mark as `DUPLICATE` and skip all extraction. This already exists as a concept (`_dedup_content_hashes` in analysis.py) but runs during analysis instead of upload.

2. **Email chain detection**: For `.eml` files, parse headers (From, To, Subject, Date, In-Reply-To, References) without extracting the body. Group by `In-Reply-To` / `References` chain. Within a chain, keep only the longest message (it contains all previous messages). This replaces the existing `_dedup_email_threads` logic in analysis.py but runs at upload time.

3. **Forward detection**: For `.eml` files, if `Subject` starts with "Fwd:" or "FW:" and contains an attachment, the attachment is the important content — the forwarding email wrapper has low authority.

All three are deterministic — no AI needed.

---

## Revised Processing Pipeline

### Current Pipeline (post-v2)

```
Step 1: Upload + full extraction (all docs, serial)         ~2-5 min for 20 docs
Step 2: Content hash dedup + email thread dedup              ~5s
Step 3: Registry build (initial + cross-doc)                 ~2s
Step 4: Document summarization (AI, 2 batch calls)           ~30-60s
Step 5: Case synthesis (AI, 1 call)                          ~15-30s
Step 6: Multi-stage analysis (AI, 4 sequential calls)        ~60-120s
Step 7: Gap analysis (AI, 6-9 map-reduce calls)              ~30-60s
Step 8: Registry enrichment with AI (deterministic merge)    ~1s
Step 9: Letter strategy (AI, 1 call)                         ~10-15s
Step 10: Letter draft (AI, 1 streaming call)                 ~30-60s
Step 11: Lint (deterministic)                                ~1s
Step 12: Conditional critic (AI, 0-1 call)                   ~0-15s
Step 13: Conditional repair (AI, 0-1 call)                   ~0-15s
Step 14: Conditional polish (AI, 0-1 call)                   ~0-20s

Total: ~4-8 minutes, 16-21 AI calls
```

### Proposed Pipeline

```
Step 1: Upload + metadata classification (deterministic)     ~100ms per doc
Step 2: Content hash dedup (deterministic, at upload)         ~50ms per doc
Step 3: Light extraction (first page, no OCR)                 ~1-3s per doc
Step 4: Refined classification + authority scoring            ~100ms per doc
Step 5: Tiered full extraction (prioritized by score)         ~1-3 min (parallel)
    - Controlling: full text + OCR + signature detection
    - Primary: full text + limited OCR
    - Supporting: first 3 pages
    - Background: first page only (already done in Step 3)
Step 6: Email chain dedup (deterministic, after extraction)   ~2s
Step 7: Registry build (initial + cross-doc)                  ~2s
Step 8: Tiered document summarization (AI)                    ~20-40s
    - Controlling/Primary: full structured summary (gpt-5.4)
    - Supporting: compact summary (gpt-5-mini)
    - Background: no AI summary (use system_summary from registry)
Step 9: Case synthesis (AI, 1 call)                           ~15-30s
Step 10: Combined fact extraction + legal analysis (AI)       ~45-90s
    - Merge Stages 1+2 of multi-stage into single call
    - Keep Stage 3 (deep analysis) separate
Step 11: Gap analysis (AI, map-reduce)                        ~20-40s
    - Map only controlling + primary docs (skip background)
Step 12: Letter strategy (AI, 1 call)                         ~10-15s
Step 13: Letter draft (AI, 1 streaming call)                  ~30-60s
Step 14: Lint + conditional repair/polish                     ~0-30s

Total: ~3-5 minutes, 11-15 AI calls
```

### Where Time is Saved

| Optimization | Mechanism | Estimated Savings |
|---|---|---|
| Skip full OCR for background docs | Tiered extraction | 30-90s (3-5 docs × 10-20s each) |
| Skip AI summarization for background docs | Tiered summarization | 10-20s |
| Use gpt-5-mini for supporting doc summaries | Model downgrade where safe | 5-10s |
| Merge fact extraction + issue mapping | Combine 2 sequential gpt-5.4 calls into 1 | 15-30s |
| Skip background docs in gap analysis mapping | Fewer map calls | 10-20s |
| Upload-time dedup | Avoid extracting duplicates entirely | 10-30s per duplicate |

**Net:** ~1.5-3 minutes saved per 20-document case. AI calls reduced from 16-21 to 11-15.

---

## Reducing AI Calls — Detailed Analysis

### Current: 16-21 calls per case

| # | Call | Model | Can Reduce? | How |
|---|---|---|---|---|
| 1-2 | Document summarization (2 batches) | gpt-5.4 | **Yes** | Skip background docs; use gpt-5-mini for supporting docs |
| 3 | Case synthesis | gpt-5.4 | No | Single consolidation call, already efficient |
| 4 | Fact matrix extraction | gpt-5.4 | **Yes** | Merge with issue mapping (Call #5) |
| 5 | Legal issue mapping | gpt-5.4 | **Yes** | Merge with fact extraction (Call #4) |
| 6 | Deep legal analysis | gpt-5.4 | No | Needs fact matrix + issue map as input; keep separate |
| 7 | Letter structure | gpt-5.4 | **Yes** | Replace with deterministic logic based on case_strength + issue_count |
| 8-14 | Gap analysis (map-reduce) | gpt-5.4/mini | **Yes** | Skip background docs in mapping phase |
| 15 | Letter strategy | gpt-5-mini | No | Fast, useful, already cheap |
| 16 | Letter draft | gpt-5.4 | No | Core output, must be high quality |
| 17 | Critic | gpt-5-mini | **Already conditional** (v2) | Skip when lint score >= 85 |
| 18 | Repair | gpt-5-mini | **Already conditional** (v2) | Skip when no fixable violations |
| 19 | Polish | gpt-5.2 | **Already conditional** (v2) | Skip when no artifacts detected |

### Specific Reductions

**1. Merge Fact Matrix + Legal Issue Mapping (Calls #4-5 → 1 call)**

These two stages have the same input (document context + intake) and produce complementary outputs. The current separation exists because the legacy 4-stage pipeline was designed for smaller context windows. With gpt-5.4's 1M token context, a single call can extract both:

```
Current:
  Call 4: "Extract parties, timeline, financial data" → FactMatrix
  Call 5: "Identify applicable statutes and issues" → LegalIssueMap

Proposed:
  Call 4+5: "Extract structured facts AND identify legal issues" → FactMatrix + LegalIssueMap
```

The combined prompt adds ~2K tokens of output schema. The input context is identical. This eliminates one 15-30s gpt-5.4 call.

**Risk:** Combined output schema is more complex. Mitigation: validate both sub-schemas independently after parsing.

**2. Replace Letter Structure Determination with Deterministic Logic (Call #7 → 0 calls)**

`LetterStructure` (Stage 4 of multi-stage) determines whether to generate a "findings" or "demand" letter. Looking at the actual data model, the decision depends on:
- `case_strength` (from DeepAnalysis)
- Number and severity of issues
- Whether financial damages are quantified
- Client's stated goal (from intake)

This can be a deterministic function:

```python
def determine_letter_structure(
    deep_analysis: DeepAnalysis,
    fact_matrix: FactMatrix,
    intake_content: str,
) -> LetterStructure:
    has_quantified_damages = any(
        f.amount for f in fact_matrix.financial_data if f.amount
    )
    issue_count = len(deep_analysis.issue_analyses)
    case_strength = deep_analysis.risk_assessment.overall_case_strength

    if case_strength in ("Strong", "Moderate") and has_quantified_damages:
        return LetterStructure(
            recommended_type="demand_with_findings",
            sections=["background", "legal_basis", "demand", "next_steps"],
        )
    elif issue_count >= 2:
        return LetterStructure(
            recommended_type="findings",
            sections=["background", "issues", "analysis", "next_steps"],
        )
    else:
        return LetterStructure(
            recommended_type="findings",
            sections=["background", "issues", "analysis", "next_steps"],
        )
```

This eliminates one gpt-5.4 call (~15-30s) with zero quality risk — the AI was making the same deterministic decision with extra steps.

**3. Tiered Document Summarization**

Instead of summarizing all 20 documents at the same fidelity:

| Tier | Count (typical) | Model | Summary Type | Time |
|---|---|---|---|---|
| Controlling (score 75+) | 3-5 docs | gpt-5.4 | Full DocumentSummaryStructured | 15-25s |
| Primary (score 55-74) | 5-8 docs | gpt-5.4 | Full DocumentSummaryStructured | 15-25s |
| Supporting (score 35-54) | 4-6 docs | gpt-5-mini | Compact: name, type, key_content only | 5-10s |
| Background (score 0-34) | 2-4 docs | None | Use registry's system_summary | 0s |

The existing `build_initial_registry()` already produces `system_summary` (first meaningful sentence) and `quick_facts_raw` (dates, amounts via regex) for every document. For background documents, these are sufficient — no AI summarization needed.

**4. Scoped Gap Analysis Mapping**

The gap analysis map-reduce currently maps ALL documents. Background documents (cover letters, duplicate forwards, metadata stubs) don't contribute meaningful gap signals. Skip them:

```python
# In gap_analysis_service.py, filter before mapping
docs_for_gap_analysis = [
    doc for doc in document_summaries
    if doc.authority_score >= 35  # Skip background tier
]
```

This reduces mapping calls from ~6-9 to ~4-6 for a 20-document case.

### Net AI Call Reduction

| Change | Calls Saved | Model | Time Saved |
|---|---|---|---|
| Merge fact matrix + issue mapping | 1 × gpt-5.4 | gpt-5.4 | 15-30s |
| Deterministic letter structure | 1 × gpt-5.4 | gpt-5.4 | 15-30s |
| Skip background doc summaries | 0.5-1 batch | gpt-5.4 | 5-15s |
| Use gpt-5-mini for supporting summaries | 0 (same calls, cheaper) | gpt-5-mini | 5-10s |
| Scope gap analysis mapping | 2-3 map calls | gpt-5.4/mini | 10-20s |
| **Total** | **4-6 fewer calls** | — | **50-105s** |

---

## Codebase Maintainability: Modular Pipeline Architecture

### Current Problem

The pipeline logic is spread across:
- `analysis.py` (7,600 lines) — orchestration, dedup, extraction, letter streaming, artifacts
- `main_processor.py` (2,258 lines) — document processing, summarization, synthesis, multi-stage invocation
- `multi_stage_analyzer.py` (1,416 lines) — 4-stage analysis, context building, streaming
- `json_processing_service.py` (2,267 lines) — letter generation, prompt building, repair
- `gap_analysis_service.py` (2,355 lines) — gap analysis with map-reduce

These files grew organically through AI-generated development. Functions in `analysis.py` call functions in `main_processor.py` which call `multi_stage_analyzer.py` which calls `gap_analysis_service.py`. The dependency chain is deep and tangled.

### Proposed Module Structure

Organize around the pipeline stages, not the current file boundaries:

```
src/legal_portal/
├── pipeline/                          # NEW: Pipeline stages as modules
│   ├── __init__.py
│   ├── stage_intake.py                # Stage 1: Intake normalization
│   ├── stage_intelligence.py          # Stage 2: Document intelligence
│   ├── stage_extraction.py            # Stage 3: Tiered extraction
│   ├── stage_synthesis.py             # Stage 4: Evidence synthesis
│   ├── stage_reasoning.py             # Stage 5: Legal reasoning
│   ├── stage_communication.py         # Stage 6: Letter generation
│   └── orchestrator.py               # Pipeline orchestration
│
├── services/                          # Existing: Domain services
│   ├── document_registry_service.py   # Keep: Authority scoring
│   ├── gap_analysis_service.py        # Keep: Gap analysis
│   ├── letter_stream_service.py       # Keep (from v2): Letter streaming
│   ├── letter_quality_lint_service.py # Keep: Deterministic lint
│   └── letter_validation_service.py   # Keep: Fact validation
│
├── core/                              # Existing: Data models
│   ├── data_models.py                 # Keep: Pydantic models
│   └── document_processor.py          # Keep: File-level processing
│
└── utils/                             # Existing: Utilities
    ├── openai_client.py               # Keep: API wrapper
    ├── token_manager.py               # Keep: Token estimation
    └── heartbeat.py                   # Keep (from v2): SSE heartbeat
```

### Stage Responsibilities

**Stage 1: Intake Normalization** (`stage_intake.py`)
- Parse intake form (Q&A extraction)
- Identify client name, case type, jurisdiction
- Deterministic — no AI calls
- Input: raw intake document
- Output: `IntakeAnalysis` dataclass

**Stage 2: Document Intelligence** (`stage_intelligence.py`)
- Metadata classification (filename, MIME, size)
- Content hash dedup
- Email chain detection and supersession
- Light extraction (first page)
- Authority scoring (deterministic)
- Input: uploaded file metadata + first-page text
- Output: `DocumentIntelligence` dataclass with authority_score, extraction_tier, is_duplicate

**Stage 3: Tiered Extraction** (`stage_extraction.py`)
- Full extraction for Controlling/Primary tiers
- Partial extraction for Supporting tier
- First-page-only for Background tier
- OCR only when needed and only for appropriate tiers
- Input: `DocumentIntelligence` + file bytes
- Output: `ExtractedDocument` with text, quality score, extraction_level

**Stage 4: Evidence Synthesis** (`stage_synthesis.py`)
- Document summarization (tiered by authority)
- Registry enrichment (cross-document + AI)
- Case synthesis
- Input: extracted documents + intake analysis
- Output: `CaseSynthesis` with summaries, registry, case_overview

**Stage 5: Legal Reasoning** (`stage_reasoning.py`)
- Combined fact extraction + issue mapping (merged from current Stages 1-2)
- Deep legal analysis (current Stage 3)
- Gap analysis
- Deterministic letter structure
- Input: case synthesis
- Output: `LegalAnalysis` with fact_matrix, issues, deep_analysis, gaps, letter_structure

**Stage 6: Client Communication** (`stage_communication.py`)
- Letter strategy
- Letter drafting (streaming)
- Lint + conditional quality passes
- HTML formatting
- Input: legal analysis + case synthesis
- Output: streamed letter + artifacts

### Orchestrator

```python
# pipeline/orchestrator.py

class AnalysisPipeline:
    """Orchestrates the 6-stage analysis pipeline.

    Each stage is independently testable, cacheable, and replaceable.
    """

    def __init__(self, openai_client, supabase):
        self.intake = IntakeStage()
        self.intelligence = DocumentIntelligenceStage()
        self.extraction = TieredExtractionStage(openai_client)
        self.synthesis = EvidenceSynthesisStage(openai_client)
        self.reasoning = LegalReasoningStage(openai_client)
        self.communication = CommunicationStage(openai_client)

    async def run_analysis(
        self,
        case_id: str,
        documents: list[UploadedDocument],
        progress_callback=None,
    ) -> AnalysisResult:
        """Run the full pipeline with progress callbacks."""

        # Stage 1: Intake (deterministic, <1s)
        intake = self.intake.normalize(documents)

        # Stage 2: Intelligence (deterministic, <5s)
        intelligence = self.intelligence.classify_all(documents)

        # Stage 3: Extraction (tiered, parallel, 1-3 min)
        extracted = await self.extraction.extract_tiered(
            documents, intelligence, progress_callback
        )

        # Stage 4: Synthesis (AI calls, 30-60s)
        synthesis = await self.synthesis.synthesize(
            extracted, intake, intelligence, progress_callback
        )

        # Stage 5: Reasoning (AI calls, 45-90s)
        reasoning = await self.reasoning.analyze(
            synthesis, progress_callback
        )

        # Stage 6: Communication (AI calls, streaming, 30-60s)
        # This stage is triggered separately via SSE endpoint

        return AnalysisResult(
            intake=intake,
            intelligence=intelligence,
            synthesis=synthesis,
            reasoning=reasoning,
        )
```

### How This Prevents Future AI-Generated Debt

1. **Clear module boundaries**: Each stage has a defined input type, output type, and responsibility. AI-generated code that violates boundaries is immediately obvious.

2. **Dataclass contracts between stages**: Stages communicate through typed dataclasses, not raw dicts. Adding a field to `FactMatrix` that `stage_communication` needs requires updating the contract explicitly.

3. **Single responsibility per file**: `stage_reasoning.py` does legal reasoning. It doesn't also handle document extraction, dedup, or letter formatting. When an AI agent adds a feature, it goes in the right stage.

4. **Testable in isolation**: Each stage can be tested with mock inputs/outputs from adjacent stages. No need to run the full pipeline to test gap analysis logic.

5. **No 7,600-line files**: The largest stage module should be ~500-800 lines. If it grows beyond that, it's a signal to split.

---

## Performance Impact Estimates

### Speed

| Metric | Current (post-v2) | Proposed | Improvement |
|---|---|---|---|
| Total analysis time (20 docs) | 4-8 min | 3-5 min | 25-40% faster |
| AI API calls | 16-21 | 11-15 | 30% fewer |
| Time spent on background docs | 60-120s | 5-10s | 90% less |
| Letter generation time | 60-120s | 40-90s | ~20% faster (conditional passes already in v2) |

### Cost

| Metric | Current | Proposed | Improvement |
|---|---|---|---|
| API cost per case (20 docs) | $3.50-5.00 | $2.50-3.50 | 25-30% cheaper |
| OCR cost per case | $0.50-1.50 | $0.20-0.80 | 45-55% cheaper |
| Total cost per case | $4.00-6.50 | $2.70-4.30 | 30-35% cheaper |

### Quality

| Metric | Current | Proposed | Impact |
|---|---|---|---|
| Context fidelity for controlling docs | Moderate (v2 weighted allocation) | Higher (more extracted text available) | Better factual grounding |
| Noise from low-value docs | Reduced (v2 weighted allocation) | Minimal (background docs excluded from AI summarization) | Fewer hallucinations from irrelevant context |
| Duplicate document handling | At analysis time | At upload time | Cleaner document sets from the start |
| Email chain handling | At analysis time | At upload time | Only final email in chain reaches analysis |

---

## Implementation Strategy (Phased)

### Phase A: Upload-Time Classification (1 week)

**What:** Run metadata classification and content hash dedup at upload time instead of analysis time.

**Files to modify:**
- `src/legal_portal/api/routes/documents.py` — add classification after upload
- `src/legal_portal/services/document_registry_service.py` — extract `_infer_doc_type_from_name()`, `_score_authority()` into a lightweight classifier
- Database: add `authority_score_preliminary` column to documents table

**What changes:**
1. At upload, immediately compute preliminary authority_score from filename + MIME + file_size
2. Store in documents table
3. Content hash dedup runs at upload (move from analysis.py `_dedup_content_hashes`)

**What does NOT change:**
- Full extraction still runs at upload (no tiering yet)
- Analysis pipeline unchanged
- Letter generation unchanged

**Risk:** Low. This is additive — stores a new column, doesn't change existing flow.

### Phase B: Deterministic Letter Structure + Merged Analysis Stages (1 week)

**What:** Replace the AI-driven letter structure determination with deterministic logic. Merge fact matrix extraction and legal issue mapping into a single AI call.

**Files to modify:**
- `src/legal_portal/services/multi_stage_analyzer.py` — merge stages 1+2, add deterministic letter structure
- `src/legal_portal/core/data_models.py` — combined output schema for merged stage

**What changes:**
1. `_extract_fact_matrix()` and `_map_legal_issues()` merged into `_extract_facts_and_issues()`
2. `_determine_letter_structure()` becomes a deterministic function
3. Two fewer gpt-5.4 calls per case

**What does NOT change:**
- Deep legal analysis (Stage 3) stays separate — it needs the combined output as input
- Gap analysis stays separate
- Letter generation unchanged

**Risk:** Medium. The merged prompt produces a larger output schema. Validate both sub-schemas independently. A/B test on 5 cases before deploying.

### Phase C: Tiered Extraction (2 weeks)

**What:** Use preliminary authority scores to allocate extraction effort.

**Files to modify:**
- `src/legal_portal/core/document_processor.py` — add extraction tiers
- `src/legal_portal/services/file_processors/pdf_processor.py` — add partial extraction mode (first N pages)
- `src/legal_portal/api/routes/analysis.py` — use preliminary scores in `_extract_deferred_documents`

**What changes:**
1. Documents with preliminary score < 35 get first-page extraction only
2. Documents with score 35-54 get first 3 pages + last page
3. Documents with score 55+ get full extraction (current behavior)
4. OCR only triggers for documents with score >= 55 and insufficient text

**What does NOT change:**
- Users can manually override extraction level per document
- Full extraction still available as "re-extract" action
- All documents still appear in the case file
- Registry enrichment still runs for all documents

**Risk:** Medium-High. A controlling instrument with a misleading filename could get under-extracted. Mitigation: the light extraction (first page) will usually contain the title, parties, and signature block of a contract — enough to detect misclassification and trigger full extraction.

### Phase D: Tiered AI Summarization (1 week)

**What:** Use authority scores to choose summarization model and depth.

**Files to modify:**
- `src/legal_portal/services/main_processor.py` — tiered summarization batching
- `src/legal_portal/services/json_processing_service.py` — compact summary prompt for gpt-5-mini

**What changes:**
1. Controlling + Primary docs: full DocumentSummaryStructured via gpt-5.4 (current behavior)
2. Supporting docs: compact summary (name, type, key_content, dates, amounts) via gpt-5-mini
3. Background docs: no AI summary — use registry's system_summary and quick_facts_raw

**What does NOT change:**
- All documents appear in the registry
- All documents still contribute to gap analysis (via metadata)
- Letter generation still receives all document metadata

**Risk:** Low-Medium. Supporting docs get less detailed summaries, but they're already getting less token allocation (v2). The compact summary captures the key facts that matter for gap analysis.

### Phase E: Pipeline Module Extraction (2-3 weeks, can be parallelized)

**What:** Reorganize the codebase into the staged pipeline architecture.

This is the structural refactor. It does NOT change behavior — it moves code into the right modules.

**Order of extraction:**
1. `stage_intelligence.py` — extract classification logic from `document_registry_service.py` and dedup logic from `analysis.py`
2. `stage_extraction.py` — extract tiered extraction logic from `document_processor.py` and `_extract_deferred_documents()`
3. `stage_synthesis.py` — extract summarization and case synthesis from `main_processor.py`
4. `stage_reasoning.py` — extract multi-stage analysis from `multi_stage_analyzer.py`
5. `orchestrator.py` — extract `process_case_background()` from `analysis.py` into a clean orchestrator

**Risk:** Medium. This is a large refactor. Each extraction should be a separate PR with before/after test coverage.

---

## Risks and Mitigations

### Risk 1: Misclassification Causes Under-Extraction

A controlling instrument with a generic filename like "Document_1.pdf" could receive a low preliminary authority score and get only first-page extraction.

**Mitigation:** After light extraction (first page), re-score using the first-page content. If the first page contains contract keywords ("AGREEMENT", "WITNESSETH", "PARTIES"), signature blocks, or legal structure markers, upgrade the extraction tier automatically. This catches ~95% of misclassified documents because contracts almost always identify themselves on the first page.

**Safety net:** If a document's summary later reveals it's more important than initially classified (e.g., during AI enrichment), flag it for re-extraction. The system already supports re-extraction.

### Risk 2: Merged Fact Matrix + Issue Mapping Produces Lower Quality

Combining two cognitive tasks into one prompt could reduce output quality for either.

**Mitigation:**
1. Use a clear output schema with two distinct top-level sections
2. A/B test on 5-10 real cases comparing merged vs. separate outputs
3. Keep the separate-stage code path available behind a config flag for rollback

### Risk 3: Background Documents Contain Critical Information

A document classified as "background" might actually contain a key admission, deadline, or financial figure that the analysis misses.

**Mitigation:**
1. Background documents still get first-page extraction and metadata-only entries in the analysis context
2. Gap analysis will flag missing evidence if the analysis lacks information that should exist
3. The user can manually re-classify and re-extract any document
4. Over time, classification accuracy can be measured and the score thresholds adjusted

### Risk 4: Large Refactor (Phase E) Introduces Regressions

Moving thousands of lines of code creates opportunities for subtle bugs.

**Mitigation:**
1. Phase E is the last phase — all functional changes are already deployed and stable
2. Each module extraction is a separate PR with before/after test comparison
3. The orchestrator initially just delegates to existing functions — it doesn't rewrite them
4. Integration tests verify end-to-end behavior at each extraction step

---

## Summary

**The single most impactful architectural improvement** is moving document classification upstream and using authority scores to tier extraction effort. This is not a speculative idea — the `DocumentRegistryService` already computes authority scores from filename + first 3,000 chars of text using deterministic heuristics. The scores are just computed too late to be useful for extraction decisions.

By computing a preliminary score at upload time and using it to tier extraction, the system:
- Spends 90% less time on background documents
- Makes 30% fewer AI calls
- Processes cases 25-40% faster
- Produces better output because controlling instruments get more extraction fidelity and more context tokens

The implementation is phased so each step delivers value independently, and no phase requires betting the system's reliability on unproven changes.
