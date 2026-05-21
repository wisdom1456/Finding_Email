"""Multi-Stage Legal Analysis Service.

This service orchestrates a 4-stage analysis pipeline for comprehensive case evaluation:
1. Fact Matrix Extraction - Structured facts from documents
2. Legal Issue Mapping - Identify applicable laws and issues
3. Deep Legal Analysis - Comprehensive analysis of each issue
4. Letter Structure Determination - Decide optimal letter format

Created: 2025-11-21
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

from legal_portal.core.data_models import (
    CriticalDeadline,
    DeepAnalysis,
    DocumentSummaryStructured,
    Event,
    EvidenceAssessment,
    FactMatrix,
    FinancialItem,
    GapAnalysisResult,
    IssueAnalysis,
    KeyDocument,
    LegalIssue,
    LegalIssueMap,
    LetterStructure,
    MultiStageAnalysisResult,
    Party,
    PropertyInfo,
    RiskAssessment,
)
from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService
from legal_portal.services.shared.statute_recommendation_service import StatuteRecommendationService
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.type_safety import safe_str_required

logger = get_module_logger(__name__)

# --- Token-budget context building constants ---
_DOC_TYPE_PRIORITY = {
    "intake": 0,
    "controlling_instrument": 1,
    "contract": 2, "agreement": 2, "lease": 2, "deed": 2,
    "medical": 3, "evidence": 3, "report": 3, "assessment": 3,
    "correspondence": 4, "letter": 4, "notice": 4,
}

_MAX_ENTRY_TOKENS = 1_000       # Hard cap per document entry (~4K chars)
_DEFAULT_BUDGET_TOKENS = 50_000  # Total context budget in tokens
_PROMPT_GUARD_TOKENS = 200_000   # Abort if total prompt would exceed this

# --- Batched fact extraction constants ---
# Reduced from 25K → 18K after Devlin v2 verification: batch 5 at 24K chars
# produced a 41K-char prompt (batch + template + registry + intake overhead)
# that timed out at 240s × 3 retries.  At 18K, the worst-case prompt is
# ~30K chars, completing in 100-130s with headroom.
_FACT_BATCH_MAX_CHARS = 18_000   # Max serialized chars per batch
_FACT_BATCH_MAX_DOCS = 8         # Hard cap docs per batch
_FACT_BATCH_CONCURRENCY = 2      # Max parallel batch LLM calls
_FACT_BATCH_DOC_THRESHOLD = 12   # Use batching when doc count exceeds this
_FACT_BATCH_CHAR_THRESHOLD = 30_000  # Or when total summary chars exceed this

# --- Per-document cap for fact extraction ---
# Large OCR-heavy documents can produce oversized per-doc dicts (summary +
# important_details + legal_significance + parties/dates/amounts) that dominate
# a batch and trigger provider timeouts.  Cap total serialized per-doc JSON to
# _FACT_DOC_MAX_SERIALIZED_CHARS; if exceeded, progressively truncate
# content_summary using head/tail preservation (signatures live near the end).
_FACT_DOC_MAX_SERIALIZED_CHARS = 8_000
_FACT_DOC_HEAD_CHARS = 6_000
_FACT_DOC_TAIL_CHARS = 2_000


@dataclass(frozen=True)
class ContextBuildResult:
    """Immutable result from context building — no mutable instance state."""
    context_text: str
    docs_in_scope: int
    docs_omitted: int
    total_tokens: int
    omitted_doc_names: list[str] = field(default_factory=list)
    omission_reason: str = ""


class MultiStageAnalyzer:
    """Orchestrates 4-stage analysis pipeline for comprehensive case evaluation."""

    def __init__(
        self,
        openai_client: OpenAIClient,
        statute_service: Optional[StatuteRecommendationService] = None,
        gap_analysis_service: Optional[GapAnalysisService] = None,
    ):
        """Initialize the multi-stage analyzer."""
        self.client = openai_client
        self.statute_service = statute_service or StatuteRecommendationService()
        self.stage_timings = {}

        # Initialize gap analysis service if not provided
        try:
            if gap_analysis_service:
                self.gap_service = gap_analysis_service
                logger.info("[INIT] Using provided GapAnalysisService")
            else:
                logger.info("[INIT] Creating new GapAnalysisService")
                self.gap_service = GapAnalysisService(openai_client=openai_client)
                logger.info(f"[INIT] GapAnalysisService created successfully: {self.gap_service is not None}")
        except Exception as e:
            logger.error(f"[INIT] FAILED to create GapAnalysisService: {e}", exc_info=True)
            self.gap_service = None  # Explicitly set to None on failure

    # =========================================================================
    # STREAMING SINGLE-PASS ANALYSIS (New - replaces multi-stage for speed)
    # =========================================================================

    @staticmethod
    def _get_doc_priority(summary: DocumentSummaryStructured) -> int:
        """Return priority bucket for sorting.

        Lower bucket = higher importance. Original index preserves
        insertion order within the same bucket.
        """
        doc_type = (summary.document_type or "").lower()
        doc_name = (summary.document_name or "").lower()
        # Intake forms always first
        if "intake" in doc_name:
            return 0
        for key, pri in _DOC_TYPE_PRIORITY.items():
            if key in doc_type:
                return pri
        return 5  # default: lowest

    @staticmethod
    def _score_to_priority(authority_score: int) -> int:
        """Map authority_score to priority bucket (same scale as _get_doc_priority)."""
        if authority_score >= 80:
            return 1
        if authority_score >= 60:
            return 2
        if authority_score >= 40:
            return 3
        return 4

    def _build_condensed_context(
        self,
        document_summaries: List[DocumentSummaryStructured],
        max_tokens: int = _DEFAULT_BUDGET_TOKENS,
        group_summaries: Optional[List] = None,
        preview_classifications: Optional[List[Dict[str, Any]]] = None,
    ) -> ContextBuildResult:
        """Build token-budget context from document summaries and optional group summaries.

        Uses TokenManager.estimate_tokens for speed (tiktoken per-doc would be slow).
        Sorts by priority bucket, preserving original order within each bucket.
        Caps each entry at its token budget. Stops when budget is reached.

        When group_summaries are provided, they compete in the same priority queue
        as individual documents, using authority_score mapped to priority buckets.
        """
        import math

        from legal_portal.utils.token_manager import TokenManager
        tm = TokenManager()

        # Build unified priority queue: groups + individual docs
        # Each entry: (priority, index, entry_text, token_budget, name)
        entries: list[tuple] = []

        # Add group entries
        if group_summaries:
            for idx, gs in enumerate(group_summaries):
                auth = gs.authority_score or 50
                pri = self._score_to_priority(auth)

                # Group token budget: proportional to members but compressed
                # sqrt(member_count) rewards compression (12 stmts -> ~3.5x budget, not 12x)
                group_budget = min(
                    int(_MAX_ENTRY_TOKENS * math.sqrt(gs.member_count)),
                    3000,  # hard cap
                )

                entry_text = (
                    f"{gs.label} ({gs.group_type.value}, "
                    f"{gs.member_count} docs: {', '.join(gs.member_document_names[:5])})\n"
                    f"    {gs.combined_narrative}\n"
                )
                if gs.key_findings:
                    entry_text += "    Findings: " + "; ".join(gs.key_findings[:5]) + "\n"
                if gs.legal_significance:
                    entry_text += f"    Significance: {gs.legal_significance}\n"

                entries.append((pri, idx, entry_text, group_budget, gs.label))

        # Build relevance lookup from preview classifications
        _relevance_by_name: dict[str, dict] = {}
        if preview_classifications:
            for cls in preview_classifications:
                cname = (cls.get("document_name") or "").strip()
                if cname:
                    _relevance_by_name[cname] = cls
            _bg_count = sum(1 for c in preview_classifications if c.get("relevance_level") == "background")
            if _bg_count:
                logger.info(f"[ANALYSIS:CONTEXT] Preview-guided reduction: {_bg_count} background docs will use one-line summaries")

        # Add individual document entries
        group_offset = len(group_summaries or [])
        for idx, summary in enumerate(document_summaries):
            pri = self._get_doc_priority(summary)
            doc_name = (summary.document_name or "unknown").strip()
            doc_type = summary.document_type or "document"

            # If preview classified this doc as "background", use one-line summary
            cls_info = _relevance_by_name.get(doc_name)
            if cls_info and cls_info.get("relevance_level") == "background":
                one_liner = cls_info.get("one_line_summary", "background document")
                entry_text = f"{doc_name} ({doc_type}) — {one_liner}\n"
                entry_budget = 100  # minimal token budget for background docs
            else:
                content = (summary.key_content or summary.executive_summary or "")[:4000]
                entry_text = f"{doc_name} ({doc_type})\n    {content}\n"
                entry_budget = _MAX_ENTRY_TOKENS
            entries.append((pri, group_offset + idx, entry_text, entry_budget, doc_name))

        # Sort by priority (lower = higher importance), then index
        entries.sort(key=lambda x: (x[0], x[1]))

        lines: list[str] = []
        total_tokens = 0
        included = 0
        omitted_names: list[str] = []

        for _pri, _idx, entry_text, budget, name in entries:
            entry = f"[{included + 1}] {entry_text}"
            entry_tokens = tm.estimate_tokens_detailed(entry)

            if entry_tokens > budget:
                ratio = budget / entry_tokens
                entry = entry[:int(len(entry) * ratio)]
                entry_tokens = tm.estimate_tokens_detailed(entry)

            if total_tokens + entry_tokens > max_tokens:
                omitted_names.append(name)
                continue  # keep collecting names for reporting

            lines.append(entry)
            total_tokens += entry_tokens
            included += 1

        total_entries = len(document_summaries) + len(group_summaries or [])
        docs_omitted = total_entries - included
        omission_reason = ""
        if docs_omitted > 0:
            omission_reason = (
                f"Token budget ({max_tokens:,} tokens) reached after {included} entries. "
                f"{docs_omitted} lower-priority entries excluded."
            )
            logger.warning(f"[ANALYSIS:BUDGET] {omission_reason}")

        logger.info(
            f"[ANALYSIS:CONTEXT] Included {included}/{total_entries} entries | "
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

    @staticmethod
    def _condense_intake_for_prompt(
        intake_content: str,
        max_chars: int,
        tail_chars: Optional[int] = None,
    ) -> str:
        """Condense intake content while retaining both head and tail context."""
        text = intake_content or ""
        if len(text) <= max_chars:
            return text

        if max_chars < 120:
            return text[:max_chars]

        separator = "\n... [middle omitted for prompt budget] ...\n"
        tail = tail_chars if tail_chars is not None else max(300, max_chars // 3)
        if tail >= max_chars:
            tail = max_chars // 2

        head = max_chars - tail - len(separator)
        if head < 200:
            head = max_chars // 2
            tail = max_chars - head - len(separator)

        return text[:head] + separator + text[-tail:]

    @staticmethod
    def _build_document_registry_context(
        document_registry: Optional[List[Dict[str, Any]]],
        max_docs: int = 40,
    ) -> str:
        """Render compact document-registry context for stage prompts."""
        rows = [row for row in (document_registry or []) if isinstance(row, dict)]
        if not rows:
            return "No authoritative document registry provided."

        sorted_rows = sorted(
            rows,
            key=lambda row: (
                -int(row.get("authority_score") or 0),
                str(row.get("document_name") or "").lower(),
            ),
        )
        lines: List[str] = []
        for row in sorted_rows[:max_docs]:
            name = row.get("document_name") or "Unknown document"
            doc_type = row.get("document_type") or "Unknown"
            authority = row.get("authority_level") or "supporting_evidence"
            execution = row.get("execution_status") or "unknown"
            instrument = row.get("primary_instrument") or "n/a"
            is_key = bool(row.get("is_key_document"))
            role = row.get("role_in_case") or "general case support"
            lines.append(
                f"- {name} | type={doc_type} | authority={authority} | "
                f"execution={execution} | key_doc={is_key} | instrument={instrument} | role={role}"
            )
        if len(sorted_rows) > max_docs:
            omitted = len(sorted_rows) - max_docs
            lines.append(f"... {omitted} additional registry items omitted.")
            logger.warning(
                f"[REGISTRY:TRUNCATED] _build_document_registry_context capped at {max_docs} of "
                f"{len(sorted_rows)} docs. {omitted} documents excluded from registry context."
            )
        return "\n".join(lines)

    def _build_streaming_prompt(
        self,
        intake_content: str,
        document_context: str,
        jurisdiction: str,
    ) -> str:
        """Build the comprehensive single-pass analysis prompt.
        
        Args:
            intake_content: Client intake form content
            document_context: Condensed document summaries
            jurisdiction: Legal jurisdiction (e.g., "New Mexico")
            
        Returns:
            Complete prompt for streaming analysis

        """
        return f"""Analyze this {jurisdiction} legal case. Output your analysis in clear markdown format with the sections below.

Be specific - use actual names, dates, and dollar amounts from the documents. Cite specific {jurisdiction} statutes where applicable.

---
CLIENT INTAKE:
{self._condense_intake_for_prompt(intake_content, max_chars=4000)}

---
CASE DOCUMENTS:
{document_context}

---
OUTPUT YOUR ANALYSIS WITH THESE EXACT SECTIONS:

## Case Overview
Summarize the client, opposing parties, core dispute, and jurisdiction in 2-3 sentences.

## Key Facts Extracted
List the most important facts organized by:
- **Parties Involved**: Names and roles
- **Timeline**: Key dates and events in chronological order
- **Financial Details**: Dollar amounts, payments, property values
- **Key Documents**: Most important documents and what they establish

## Legal Issues Identified

### Primary Issues
For each primary legal issue (2-4 issues):
- Issue name and category (contract, tort, property, statutory)
- Applicable {jurisdiction} statutes or rules
- Elements that must be proven
- Current strength: Strong / Moderate / Weak

### Secondary Issues
Brief list of additional legal considerations.

## Risk Assessment

### Strengths
What works in the client's favor (evidence, law, facts)

### Weaknesses  
Challenges and potential defenses the other side may raise

### Case Viability
Overall assessment: Viable / Conditionally Viable / Weak
Brief explanation of viability determination.

## Recommended Actions
Numbered list of specific next steps with deadlines if applicable.
Prioritize the most urgent items first.

---

## Structured Data

At the end of your analysis, include a JSON block with structured data for the system.
This block MUST be valid JSON wrapped in a code fence:

```json
{{
  "client_name": "Full name of the client",
  "practice_area": "Primary practice area (e.g., Real Estate, Contract, Personal Injury)",
  "case_strength": "Strong" | "Moderate" | "Weak",
  "primary_issues": [
    {{
      "name": "Issue name",
      "category": "contract | tort | property | statutory",
      "statutes": ["Statute 1", "Statute 2"],
      "strength": "Strong | Moderate | Weak"
    }}
  ],
  "key_dates": [
    {{
      "date": "YYYY-MM-DD or Month YYYY",
      "event": "What happened"
    }}
  ],
  "financial_summary": {{
    "total_claimed": "$X,XXX.XX or null if not applicable",
    "documented_damages": "$X,XXX.XX or null",
    "financial_items": [
      {{"amount": "$X,XXX.XX", "description": "What this amount is for", "category": "contract_price | payment_made | damages_claimed | fees_owed | refund_owed | other", "payment_type": "paid | owed | claimed | estimated"}}
    ]
  }},
  "parties": [
    {{
      "name": "Party name",
      "role": "client | opposing | third_party"
    }}
  ],
  "recommended_letter_type": "findings | demand | demand_with_findings",
  "urgency": "high | medium | low"
}}
```
"""

    async def analyze_streaming(
        self,
        intake_content: str,
        document_summaries: List[DocumentSummaryStructured],
        jurisdiction: str = "Florida",
        group_summaries: Optional[List] = None,
        preview_classifications: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[AsyncGenerator[str, None], ContextBuildResult]:
        """Build context and return (token_generator, context_result).

        Single API call that outputs readable markdown in real-time.
        Much faster than multi-stage analysis and eliminates timeout issues.

        Args:
            intake_content: Client intake form content
            document_summaries: List of document summaries
            jurisdiction: Legal jurisdiction
            group_summaries: Optional list of GroupSummary objects (gated by feature flag)

        Returns:
            Tuple of (async token generator, ContextBuildResult with scope metadata)
        """
        _t_streaming_start = time.time()
        logger.info(
            f"[STREAMING] Starting streaming analysis | "
            f"jurisdiction={jurisdiction} docs={len(document_summaries)} "
            f"intake_chars={len(intake_content)}"
        )

        # Build condensed context with token budget
        from legal_portal.config.default import get_settings as _get_settings
        _settings = _get_settings()

        _t_ctx = time.time()
        ctx = self._build_condensed_context(
            document_summaries,
            group_summaries=group_summaries if _settings.enable_group_context else None,
            preview_classifications=preview_classifications,
        )
        document_context = ctx.context_text
        logger.info(
            f"[STREAM:CONTEXT_BUILT] elapsed={time.time()-_t_ctx:.2f}s "
            f"docs_in_scope={ctx.docs_in_scope} docs_omitted={ctx.docs_omitted} "
            f"context_tokens={ctx.total_tokens:,} context_chars={len(document_context):,}"
        )

        # Preflight guard
        if ctx.total_tokens > _PROMPT_GUARD_TOKENS:
            logger.error(
                f"[ANALYSIS:GUARD] Context alone is {ctx.total_tokens:,} tokens, "
                f"exceeding guard limit of {_PROMPT_GUARD_TOKENS:,}. Aborting."
            )
            raise ValueError(f"Document context too large: {ctx.total_tokens:,} tokens")

        # Build the comprehensive prompt
        prompt = self._build_streaming_prompt(
            intake_content=intake_content,
            document_context=document_context,
            jurisdiction=jurisdiction,
        )

        logger.info(
            f"[STREAM:PROMPT_STATS] prompt_chars={len(prompt):,} "
            f"model=gpt-5.4 reasoning_effort=medium max_tokens=24000 "
            f"setup_elapsed={time.time()-_t_streaming_start:.2f}s"
        )

        system_prompt = f"""You are a senior {jurisdiction} attorney with 20+ years of experience.
Analyze cases thoroughly and provide actionable insights.
Always cite specific statutes and case law where applicable.
Be direct and specific - avoid vague language.
Output in clean markdown format.
IMPORTANT: Your response MUST end with the ```json structured data block as specified in the instructions."""

        start_time = time.time()

        async def _generate() -> AsyncGenerator[str, None]:
            token_count = 0
            try:
                async for token in self.client.create_chat_completion_stream(
                    model="gpt-5.5",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=24000,
                    reasoning_effort="medium",
                ):
                    token_count += 1
                    yield token

            except Exception as e:
                logger.error(f"[STREAMING] Error during streaming: {e}")
                raise

            elapsed = time.time() - start_time
            logger.info(
                f"[STREAMING] Complete | "
                f"duration={elapsed:.1f}s tokens={token_count}"
            )

        return _generate(), ctx

    async def quick_preview_streaming(
        self,
        document_summaries: List[DocumentSummaryStructured],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Emit a quick case preview + document classifications via gpt-5-mini.

        Yields dicts with either:
          {"token": "..."}       — preview prose tokens
          {"classifications": []} — structured doc classifications
          {"done": True}          — signals preview complete
        """
        from legal_portal.core.constants import FALLBACK_MODEL

        # Build a compact doc manifest for the prompt
        doc_lines = []
        for i, ds in enumerate(document_summaries):
            name = (ds.document_name or "unknown").strip()
            snippet = (ds.executive_summary or ds.key_content or "")[:300]
            doc_lines.append(f"[{i+1}] {name}: {snippet}")
        doc_manifest = "\n".join(doc_lines)

        prompt = f"""You are a legal case analyst. Given these {len(document_summaries)} documents, respond in two parts.

First, write a 2-3 sentence case summary followed by a bullet list of key findings (injuries, treatments, financial impacts, key dates). Keep it concise. Do NOT include any headings like "PART 1" or "CASE PREVIEW" — just start with the summary text directly.

Then, on a new line, output a JSON array inside a ```json fence with document classifications:
```json
[{{"doc_index": 0, "document_name": "...", "document_type": "...", "relevance_level": "critical|supporting|background", "one_line_summary": "..."}}]
```

document_type must be one of: medical_record, billing_record, police_report, correspondence, intake_form, case_summary, legal_filing, insurance_document, photograph, contract, other

DOCUMENTS:
{doc_manifest}"""

        logger.info(
            f"[PREVIEW] Starting quick preview | docs={len(document_summaries)} "
            f"model={FALLBACK_MODEL}"
        )
        _t_start = time.time()
        full_text = ""
        token_count = 0

        try:
            async for token in self.client.create_chat_completion_stream(
                model=FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a fast, accurate legal document analyst."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                reasoning_effort="low",
            ):
                token_count += 1
                full_text += token
                # Stream tokens until we hit the JSON fence
                if "```json" not in full_text:
                    yield {"token": token}

            # Log what the model actually produced
            logger.info(
                f"[PREVIEW] Raw output | tokens={token_count} "
                f"has_json_fence={'```json' in full_text} "
                f"first_100={full_text[:100]!r}"
            )

            # Extract classifications from the JSON block
            classifications = []
            if "```json" in full_text:
                try:
                    json_start = full_text.index("```json") + 7
                    json_end = full_text.index("```", json_start)
                    raw_json = full_text[json_start:json_end].strip()
                    classifications = json.loads(raw_json)
                except (ValueError, json.JSONDecodeError) as e:
                    logger.warning(f"[PREVIEW] Failed to parse classifications JSON: {e}")

            if classifications:
                yield {"classifications": classifications}

            elapsed = time.time() - _t_start
            logger.info(
                f"[PREVIEW] Complete | duration={elapsed:.1f}s tokens={token_count} "
                f"classifications={len(classifications)}"
            )

        except Exception as e:
            logger.error(f"[PREVIEW] Error during quick preview: {e}")
            # Preview failure is non-fatal — full analysis will proceed

        yield {"done": True}

    # =========================================================================
    # LEGACY MULTI-STAGE ANALYSIS (kept for backward compatibility)
    # =========================================================================

    async def _run_with_heartbeat(
        self,
        api_call: Callable,
        progress_callback: Optional[Callable],
        stage_id: str,
        stage_name: str,
        base_progress: int,
        heartbeat_interval: float = 10.0,
    ) -> Any:
        """Run an API call with periodic heartbeat progress updates.
        
        This prevents the UI from showing stale progress during long API calls.
        """
        result = None
        error = None
        start_time = time.time()

        async def heartbeat():
            """Send periodic progress updates while API call is running."""
            progress = 0
            while True:
                await asyncio.sleep(heartbeat_interval)
                elapsed = time.time() - start_time
                # Progress slowly increases during wait (max 80% of stage)
                progress = min(80, int(elapsed / 2))  # ~2s per percent, cap at 80%
                if progress_callback:
                    await progress_callback(
                        f"AI analyzing ({int(elapsed)}s)...",
                        [],
                        stage_id,
                        base_progress + int(progress * 0.2),  # Scale to fit stage
                        stage={
                            "id": stage_id,
                            "name": stage_name,
                            "status": "active",
                            "progress": progress,
                            "detail": f"AI analyzing ({int(elapsed)}s)..."
                        }
                    )

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(heartbeat())

        try:
            # Run the actual API call
            result = await api_call()
        except Exception as e:
            error = e
        finally:
            # Cancel heartbeat
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        if error:
            raise error
        return result

    # Monotonic stage ordering — checkpoint writes must never go backward.
    _STAGE_RANK: Dict[str, int] = {
        "fact_extraction": 1,
        "issue_mapping": 2,
        "deep_analysis": 3,
    }

    async def analyze_case(
        self,
        intake_content: str,
        document_summaries: List[DocumentSummaryStructured],
        progress_callback: Optional[Callable] = None,
        case_type: Optional[str] = None,
        legal_issues: Optional[List[str]] = None,
        jurisdiction: str = "Florida",
        diag_logger: Optional[DiagnosticLogger] = None,
        signature_evidence: Optional[List[Dict[str, Any]]] = None,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        checkpoint: Optional[Dict[str, Any]] = None,
        checkpoint_callback: Optional[Callable] = None,
    ) -> MultiStageAnalysisResult:
        """Execute 4-stage analysis pipeline.

        Args:
            checkpoint: Previously saved checkpoint dict from analysis_jobs.
                If provided, stages with existing results are skipped.
            checkpoint_callback: async callable(stage, data) that persists
                checkpoint data. Called after each stage completes.
        """
        start_time = time.time()
        checkpoint = checkpoint or {}
        logger.info(
            f"[PIPELINE:START] [ELAPSED:0s] Starting multi-stage analysis | "
            f"jurisdiction={jurisdiction} docs={len(document_summaries)} "
            f"intake_chars={len(intake_content)} case_type={case_type}"
        )

        # Stage 2: Log Intake Content (if not already logged)
        if diag_logger:
            diag_logger.log_stage("stage2_intake_content", intake_content)

        # Ensure statute service is initialized for the correct jurisdiction
        if self.statute_service.jurisdiction != jurisdiction:
            self.statute_service = StatuteRecommendationService(jurisdiction=jurisdiction)

        # Stage 1: Extract Fact Matrix
        fact_matrix_recovered = False
        if checkpoint.get("fact_matrix"):
            try:
                fact_matrix = FactMatrix(**checkpoint["fact_matrix"])
                fact_matrix_recovered = True
                self.stage_timings["fact_extraction"] = 0.0
                logger.info(
                    f"[CHECKPOINT:RESUME] Skipping fact_extraction — "
                    f"recovered from checkpoint (parties={len(fact_matrix.parties)})"
                )
            except Exception as e:
                logger.warning(
                    f"[CHECKPOINT:DESER_FAIL] fact_matrix deserialization failed: {e} — re-running"
                )

        if not fact_matrix_recovered:
            if progress_callback:
                await progress_callback(
                    "Extracting key facts and timeline...",
                    [],
                    "fact_extraction",
                    20,
                    stage={"id": "fact_extraction", "name": "Extracting Facts", "status": "active", "progress": 5}
                )

            stage_start = time.time()
            elapsed = time.time() - start_time
            logger.info(
                f"[STAGE:1] [ELAPSED:{elapsed:.1f}s] Starting fact_matrix extraction | "
                f"jurisdiction={jurisdiction}"
            )

            # Decide: batched vs single-call fact extraction
            total_summary_chars = sum(
                len(json.dumps(d.model_dump(mode="json"))) for d in document_summaries
            )
            use_batched = (
                len(document_summaries) > _FACT_BATCH_DOC_THRESHOLD
                or total_summary_chars > _FACT_BATCH_CHAR_THRESHOLD
            )

            if use_batched:
                logger.info(
                    f"[STAGE:1] Using BATCHED fact extraction | "
                    f"docs={len(document_summaries)} summary_chars={total_summary_chars}"
                )
                fact_matrix = await self._extract_fact_matrix_batched(
                    intake_content, document_summaries, jurisdiction,
                    document_registry, progress_callback,
                )
            else:
                fact_matrix = await self._run_with_heartbeat(
                    lambda: self._extract_fact_matrix(
                        intake_content, document_summaries, jurisdiction, document_registry
                    ),
                    progress_callback,
                    "fact_extraction",
                    "Extracting Facts",
                    20,
                )
            self.stage_timings["fact_extraction"] = time.time() - stage_start

            if checkpoint_callback:
                await checkpoint_callback("fact_matrix", fact_matrix.model_dump(mode="json"))
        elapsed = time.time() - start_time

        logger.info(
            f"[STAGE:1] [ELAPSED:{elapsed:.1f}s] fact_matrix complete | "
            f"duration={self.stage_timings['fact_extraction']:.1f}s "
            f"parties={len(fact_matrix.parties)} events={len(fact_matrix.timeline)} "
            f"financial_items={len(fact_matrix.financial_data)}"
        )

        if progress_callback:
            await progress_callback(
                "Fact extraction complete.",
                [],
                "fact_extraction",
                35,
                stage={
                    "id": "fact_extraction",
                    "name": "Extracting Facts",
                    "status": "completed",
                    "progress": 100,
                    "extracted": {"type": "parties", "count": len(fact_matrix.parties)}
                }
            )

        if diag_logger:
            diag_logger.log_stage("multi_stage_1_fact_matrix", fact_matrix.model_dump(mode="json"))

        # Stage 2: Map Legal Issues
        issue_map_recovered = False
        if checkpoint.get("issue_map"):
            try:
                issue_map = LegalIssueMap(**checkpoint["issue_map"])
                issue_map_recovered = True
                self.stage_timings["issue_mapping"] = 0.0
                logger.info(
                    f"[CHECKPOINT:RESUME] Skipping issue_mapping — "
                    f"recovered from checkpoint (primary={len(issue_map.primary_issues)})"
                )
            except Exception as e:
                logger.warning(
                    f"[CHECKPOINT:DESER_FAIL] issue_map deserialization failed: {e} — re-running"
                )

        if not issue_map_recovered:
            if progress_callback:
                await progress_callback(
                    "Mapping legal issues and statutes...",
                    [],
                    "issue_mapping",
                    40,
                    stage={"id": "issue_mapping", "name": "Legal Issues", "status": "active", "progress": 5}
                )

            stage_start = time.time()
            elapsed = time.time() - start_time
            logger.info(
                f"[STAGE:2] [ELAPSED:{elapsed:.1f}s] Starting issue_mapping | "
                f"parties={len(fact_matrix.parties)} case_type={case_type}"
            )

            issue_map = await self._run_with_heartbeat(
                lambda: self._map_legal_issues(
                    fact_matrix, intake_content, case_type, legal_issues, jurisdiction
                ),
                progress_callback,
                "issue_mapping",
                "Legal Issues",
                40,
            )
            self.stage_timings["issue_mapping"] = time.time() - stage_start

            if checkpoint_callback:
                await checkpoint_callback("issue_map", issue_map.model_dump(mode="json"))
        elapsed = time.time() - start_time

        logger.info(
            f"[STAGE:2] [ELAPSED:{elapsed:.1f}s] issue_mapping complete | "
            f"duration={self.stage_timings['issue_mapping']:.1f}s "
            f"primary_issues={len(issue_map.primary_issues)} "
            f"secondary_issues={len(issue_map.secondary_issues)}"
        )

        if progress_callback:
            await progress_callback(
                "Issue mapping complete.",
                [],
                "issue_mapping",
                55,
                stage={
                    "id": "issue_mapping",
                    "name": "Legal Issues",
                    "status": "completed",
                    "progress": 100,
                    "extracted": {"type": "issues", "count": len(issue_map.primary_issues)}
                }
            )

        if diag_logger:
            diag_logger.log_stage("multi_stage_2_issue_map", issue_map.model_dump(mode="json"))

        # Stage 3: Deep Legal Analysis
        deep_analysis_recovered = False
        if checkpoint.get("deep_analysis"):
            try:
                deep_analysis = DeepAnalysis(**checkpoint["deep_analysis"])
                deep_analysis_recovered = True
                self.stage_timings["deep_analysis"] = 0.0
                logger.info(
                    f"[CHECKPOINT:RESUME] Skipping deep_analysis — "
                    f"recovered from checkpoint (analyses={len(deep_analysis.issue_analyses)})"
                )
            except Exception as e:
                logger.warning(
                    f"[CHECKPOINT:DESER_FAIL] deep_analysis deserialization failed: {e} — re-running"
                )

        if not deep_analysis_recovered:
            if progress_callback:
                await progress_callback(
                    "Performing deep legal analysis...",
                    [],
                    "deep_analysis",
                    70,
                    stage={"id": "deep_analysis", "name": "Deep Analysis", "status": "active", "progress": 5}
                )

            stage_start = time.time()
            elapsed = time.time() - start_time
            logger.info(
                f"[STAGE:3] [ELAPSED:{elapsed:.1f}s] Starting deep_analysis | "
                f"issues_to_analyze={len(issue_map.primary_issues)}"
            )

            deep_analysis = await self._run_with_heartbeat(
                lambda: self._perform_deep_legal_analysis(
                    fact_matrix, issue_map, intake_content, jurisdiction
                ),
                progress_callback,
                "deep_analysis",
                "Deep Analysis",
                70,
            )
            self.stage_timings["deep_analysis"] = time.time() - stage_start

            if checkpoint_callback:
                await checkpoint_callback("deep_analysis", deep_analysis.model_dump(mode="json"))
        elapsed = time.time() - start_time

        logger.info(
            f"[STAGE:3] [ELAPSED:{elapsed:.1f}s] deep_analysis complete | "
            f"duration={self.stage_timings['deep_analysis']:.1f}s "
            f"analyses_generated={len(deep_analysis.issue_analyses)}"
        )

        if progress_callback:
            await progress_callback(
                "Deep legal analysis complete.",
                [],
                "deep_analysis",
                90,
                stage={
                    "id": "deep_analysis",
                    "name": "Deep Analysis",
                    "status": "completed",
                    "progress": 100,
                    "extracted": {"type": "analysis", "count": len(deep_analysis.issue_analyses)}
                }
            )

        if diag_logger:
            diag_logger.log_stage("multi_stage_3_deep_analysis", deep_analysis.model_dump(mode="json"))

        # Stage 3.5: Gap Analysis (NEW)
        gap_analysis: Optional[GapAnalysisResult] = None
        logger.info(f"[STAGE:3.5] Gap service exists: {self.gap_service is not None}, Type: {type(self.gap_service)}")
        if self.gap_service:
            if progress_callback:
                await progress_callback(
                    "Analyzing case completeness and gaps...",
                    [],
                    "gap_analysis",
                    92,
                    stage={"id": "gap_analysis", "name": "Gap Analysis", "status": "active", "progress": 10}
                )

            stage_start = time.time()
            elapsed = time.time() - start_time
            logger.info(
                f"[STAGE:3.5] [ELAPSED:{elapsed:.1f}s] Starting gap_analysis"
            )

            try:
                logger.info("[STAGE:3.5] Calling gap_service.analyze_gaps...")
                gap_analysis = await self.gap_service.analyze_gaps(
                    fact_matrix=fact_matrix,
                    issue_map=issue_map,
                    deep_analysis=deep_analysis,
                    document_summaries=document_summaries,
                    intake_content=intake_content,
                    signature_evidence=signature_evidence,
                    document_registry=document_registry,
                )
                logger.info(f"[STAGE:3.5] Gap analysis returned: {gap_analysis is not None}")
                self.stage_timings["gap_analysis"] = time.time() - stage_start
                elapsed = time.time() - start_time

                logger.info(
                    f"[STAGE:3.5] [ELAPSED:{elapsed:.1f}s] gap_analysis complete | "
                    f"duration={self.stage_timings['gap_analysis']:.1f}s "
                    f"total_gaps={gap_analysis.total_gaps} "
                    f"critical={gap_analysis.critical_count} high={gap_analysis.high_count}"
                )

                if progress_callback:
                    await progress_callback(
                        "Gap analysis complete.",
                        [],
                        "gap_analysis",
                        94,
                        stage={
                            "id": "gap_analysis",
                            "name": "Gap Analysis",
                            "status": "completed",
                            "progress": 100,
                            "extracted": {"type": "gaps", "count": gap_analysis.total_gaps}
                        }
                    )

                if diag_logger:
                    diag_logger.log_stage("multi_stage_3.5_gap_analysis", gap_analysis.model_dump(mode="json"))

            except Exception as e:
                logger.error(f"[STAGE:3.5] Gap analysis failed: {e}", exc_info=True)
                logger.error(f"[STAGE:3.5] Error type: {type(e).__name__}, Details: {str(e)}")
                # Continue without gap analysis
                gap_analysis = None
        else:
            logger.warning("[STAGE:3.5] Gap service is None or False, skipping gap analysis")

        # Stage 4: Letter Structure Determination
        if progress_callback:
            await progress_callback(
                "Determining optimal letter structure...",
                [],
                "structure_determination",
                95,
                stage={"id": "letter_structure", "name": "Letter Structure", "status": "active", "progress": 50}
            )

        stage_start = time.time()
        elapsed = time.time() - start_time
        logger.info(
            f"[STAGE:4] [ELAPSED:{elapsed:.1f}s] Starting letter_structure determination"
        )

        letter_structure = self._determine_letter_structure(issue_map, deep_analysis)
        self.stage_timings["structure_determination"] = time.time() - stage_start
        elapsed = time.time() - start_time

        logger.info(
            f"[STAGE:4] [ELAPSED:{elapsed:.1f}s] letter_structure complete | "
            f"duration={self.stage_timings['structure_determination']:.1f}s"
        )

        if progress_callback:
            await progress_callback(
                "Letter structure determined.",
                [],
                "structure_determination",
                100,
                stage={"id": "letter_structure", "name": "Letter Structure", "status": "completed", "progress": 100}
            )

        if diag_logger:
            diag_logger.log_stage("multi_stage_4_letter_structure", letter_structure.model_dump(mode="json"))

        # Collect verified statutes from the service for inclusion in result
        # Run in thread to avoid potential blocking
        verified_statutes_raw = await asyncio.to_thread(
            self.statute_service.recommend_statutes,
            case_facts=self._condense_intake_for_prompt(intake_content, max_chars=2000, tail_chars=600),
            legal_issues=[i.issue_name for i in issue_map.primary_issues],
            case_type=case_type,
            limit=10,
        )
        # Convert StatuteRecommendation dataclass objects to dicts for JSON serialization
        from dataclasses import asdict
        verified_statutes = [asdict(s) for s in verified_statutes_raw] if verified_statutes_raw else []

        total_time = time.time() - start_time

        # Derive opposing parties
        opposing_parties = self._identify_opposing_parties(fact_matrix)

        logger.info(
            f"[PIPELINE:COMPLETE] [ELAPSED:{total_time:.1f}s] Multi-stage analysis complete | "
            f"fact_extraction={self.stage_timings.get('fact_extraction', 0):.1f}s "
            f"issue_mapping={self.stage_timings.get('issue_mapping', 0):.1f}s "
            f"deep_analysis={self.stage_timings.get('deep_analysis', 0):.1f}s "
            f"structure_determination={self.stage_timings.get('structure_determination', 0):.1f}s | "
            f"results: parties={len(fact_matrix.parties)} issues={len(issue_map.primary_issues)} "
            f"analyses={len(deep_analysis.issue_analyses)} statutes={len(verified_statutes)}"
        )

        return MultiStageAnalysisResult(
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            letter_structure=letter_structure,
            gap_analysis=gap_analysis,
            verified_statutes=verified_statutes,
            processing_time_seconds=total_time,
            stage_timings=self.stage_timings,
            opposing_parties=opposing_parties,
            document_registry=document_registry or [],
        )

    async def _extract_fact_matrix(
        self,
        intake_content: str,
        document_summaries: List[DocumentSummaryStructured],
        jurisdiction: str,
        document_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> FactMatrix:
        """Stage 1: Extract structured facts from documents."""
        docs_context = []
        for doc in document_summaries:
            doc_dict = doc.model_dump(mode="json")
            structured_data = doc_dict.get("structured_data") or {}

            summary = doc_dict.get("key_content") or doc_dict.get("executive_summary") or ""
            summary = self._condense_doc_summary_for_fact_matrix(summary)

            entry = {
                    "filename": doc_dict.get("document_name") or doc_dict.get("source_document") or "Unknown",
                    "document_type": doc_dict.get("document_type") or "Unknown",
                    "content_summary": summary,
                    "important_details": doc_dict.get("important_details", [])[:8],
                    "legal_significance": doc_dict.get("legal_significance"),
                    # Prefer schema-backed fields, with compatibility fallbacks.
                    "parties": (
                        doc_dict.get("parties")
                        or structured_data.get("parties")
                        or doc_dict.get("parties_mentioned")
                        or []
                    ),
                    "dates": (
                        doc_dict.get("key_dates")
                        or structured_data.get("dates")
                        or doc_dict.get("dates_mentioned")
                        or []
                    ),
                    "amounts": (
                        doc_dict.get("key_amounts")
                        or structured_data.get("amounts")
                        or []
                    ),
                }
            # Cap total serialized per-doc contribution (same as batched path)
            docs_context.append(self._cap_doc_for_fact_extraction(entry))

        registry_context = self._build_document_registry_context(document_registry)

        prompt = f"""You are a precise legal fact extractor focusing on a matter in {jurisdiction}.
Extract ONLY factual information from the case materials. Do NOT perform legal analysis.

INTAKE INFORMATION:
{self._condense_intake_for_prompt(intake_content, max_chars=5000)}

DOCUMENT REGISTRY (AUTHORITATIVE CLASSIFICATION/EXECUTION SIGNALS):
{registry_context}

DOCUMENT SUMMARIES:
{json.dumps(docs_context, indent=2)}

Extract and structure the following facts:

1. **PARTIES**: Identify all parties mentioned
   - Name (exact spelling)
   - Role (Client, Opposing Party, Contractor, Landlord, Tenant, Subcontractor, etc.)
   - First mentioned in which document
   - Is this an opposing party? (true/false)
   - Entity type (individual, LLC, corporation, partnership, government, or unknown)

2. **TIMELINE**: Chronological events with dates
   - Date (be as specific as possible; if unknown, use null)
   - Description of event
   - Source document
   - Significance (why this event matters)
   - Supporting evidence (list of document names that prove the event)

3. **FINANCIAL DATA**: All monetary amounts
   - Amount (exact number)
   - Description (what this money represents)
   - Date if applicable
   - Source document
   - Type (paid, owed, claimed, estimated)
   - Category (contract_price, payment_made, damages_claimed, fees_owed, refund_owed, other)

4. **KEY DOCUMENTS**: Important documents referenced
   - Document name
   - Type (Contract, Notice, Correspondence, Evidence, etc.)
   - Date if known
   - Why this document is significant

5. **PROPERTY INFO** (if applicable):
   - Full address
   - Property type

6. **PRELIMINARY ISSUES**: Initial legal issues you can identify (just list, no analysis)

Return a JSON object with this EXACT structure:
{{
  "parties": [
    {{
      "name": "string",
      "role": "string",
      "contact_info": "string or null",
      "first_mentioned_in": "string or null",
      "is_opposing_party": true,
      "entity_type": "individual | LLC | corporation | partnership | government | unknown"
    }}
  ],
  "timeline": [
    {{
      "date": "YYYY-MM-DD or Month YYYY or null",
      "description": "string",
      "source_document": "string",
      "significance": "string or null",
      "supporting_evidence": ["DocumentA.pdf"]
    }}
  ],
  "financial_data": [
    {{
      "amount": number,
      "description": "string",
      "date": "string or null",
      "source_document": "string",
      "payment_type": "paid | owed | claimed | estimated",
      "category": "contract_price | payment_made | damages_claimed | fees_owed | refund_owed | other"
    }}
  ],
  "key_documents": [
    {{
      "document_name": "string",
      "document_type": "Contract | Notice | Correspondence | Evidence | Other",
      "date": "string or null",
      "significance": "string"
    }}
  ],
  "property_details": {{
    "address": "string",
    "property_type": "string or null",
    "additional_details": {{}}
  }} or null,
  "preliminary_issues": ["string"],
  "extraction_notes": "string or null"
}}

RULES:
- Be extremely precise with dates, amounts, names
- Include source document for everything
- Do NOT invent facts - only extract what's clearly stated
- If date is truly unknown, use null - do NOT guess
- If unsure about a detail, note it in extraction_notes
- Return ONLY valid JSON, no markdown formatting
"""

        # Use GPT-4.1-mini for fast extraction (0.5s latency vs 40s+ for GPT-5.2)
        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-5.4-mini")

        logger.info(
            f"[STAGE:1:API] Calling OpenAI for fact_matrix | "
            f"model={model} prompt_chars={len(prompt)} max_tokens=16000"
        )

        # Use asyncio.to_thread to avoid blocking the event loop during API call
        # GPT-4.1-mini: Fast extraction without reasoning overhead
        api_start = time.time()
        response_dict = await asyncio.to_thread(
            self.client.create_response,
            model=model,
            instructions=(
                f"You are a precise legal fact extractor for {jurisdiction} law. "
                "Return only valid JSON."
            ),
            input=prompt,
            max_output_tokens=16000,  # Large cases (30+ docs) can exceed 4k tokens
        )
        api_duration = time.time() - api_start

        finish_reason = response_dict.get("finish_reason", "unknown")
        logger.info(
            f"[STAGE:1:API] OpenAI response received | "
            f"duration={api_duration:.1f}s finish_reason={finish_reason} "
            f"prompt_tokens={response_dict.get('usage', {}).get('prompt_tokens', 0)} "
            f"completion_tokens={response_dict.get('usage', {}).get('completion_tokens', 0)} "
            f"response_chars={len(response_dict.get('content', '') or '')}"
        )

        # Check for API error response
        if response_dict.get("success") is False:
            error_msg = response_dict.get("error", "Unknown API error")
            logger.error(f"[STAGE:1:ERROR] API returned error: {error_msg}")
            raise ValueError(f"GPT API error in fact extraction: {error_msg}")

        raw_response = safe_str_required(response_dict.get("content"), "")

        # Handle empty responses with detailed diagnostics
        if not raw_response:
            logger.error(
                f"[STAGE:1:ERROR] Empty response from GPT API | "
                f"finish_reason={finish_reason} "
                f"prompt_tokens={response_dict.get('usage', {}).get('prompt_tokens', 0)} "
                f"completion_tokens={response_dict.get('usage', {}).get('completion_tokens', 0)}"
            )
            raise ValueError(
                f"GPT API returned an empty response for fact extraction (finish_reason={finish_reason})"
            )

        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        try:
            fact_data = json.loads(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"[STAGE:1:ERROR] JSON parse failed: {e}. Response: {raw_response[:500]}")
            raise ValueError(f"Failed to parse fact extraction response as JSON: {e}")

        # Log null source_document values before Pydantic coerces them
        for category, items in [
            ("timeline", fact_data.get("timeline", [])),
            ("financial_data", fact_data.get("financial_data", [])),
        ]:
            for item in items:
                if item.get("source_document") is None:
                    logger.warning(
                        f"[STAGE:1] Null source_document in {category} | "
                        f"description={str(item.get('description', ''))[:80]} — coercing to 'Unknown'"
                    )

        return FactMatrix(
            parties=[Party(**p) for p in fact_data.get("parties", [])],
            timeline=[Event(**e) for e in fact_data.get("timeline", [])],
            financial_data=[FinancialItem(**f) for f in fact_data.get("financial_data", [])],
            key_documents=[KeyDocument(**d) for d in fact_data.get("key_documents", [])],
            preliminary_issues=fact_data.get("preliminary_issues", []),
            property_details=(
                PropertyInfo(**fact_data["property_details"]) if fact_data.get("property_details") else None
            ),
            extraction_notes=fact_data.get("extraction_notes"),
        )

    @staticmethod
    def _condense_doc_summary_for_fact_matrix(
        summary: str,
        max_chars: int = 5000,
        tail_chars: int = 1600,
    ) -> str:
        """Condense long summaries while preserving tail content (often signature pages)."""
        if not summary:
            return ""
        if len(summary) <= max_chars:
            return summary

        # Preserve both beginning and ending context; signatures are often near document end.
        separator = "\n... [middle omitted for brevity] ...\n"
        if tail_chars >= max_chars:
            tail_chars = max_chars // 2
        head_chars = max_chars - tail_chars - len(separator)
        if head_chars < 500:
            head_chars = max_chars // 2
            tail_chars = max_chars - head_chars - len(separator)

        return summary[:head_chars] + separator + summary[-tail_chars:]

    @staticmethod
    def _cap_doc_for_fact_extraction(doc: dict) -> dict:
        """Cap total per-document serialized JSON for fact extraction prompts.

        If the serialized dict exceeds _FACT_DOC_MAX_SERIALIZED_CHARS, truncate
        content_summary using head/tail preservation until it fits.  Structured
        fields (parties, dates, amounts) are left intact because they are already
        small and high-signal.

        Returns the (potentially mutated) doc dict.  Logs when truncation occurs.
        """
        original_chars = len(json.dumps(doc))
        if original_chars <= _FACT_DOC_MAX_SERIALIZED_CHARS:
            return doc

        filename = doc.get("filename", "Unknown")

        # Calculate how much to shave off content_summary
        summary = doc.get("content_summary", "")
        overhead = original_chars - len(summary)  # non-summary bytes
        target_summary_chars = max(
            _FACT_DOC_MAX_SERIALIZED_CHARS - overhead - 100,  # 100 char margin
            500,  # absolute minimum to preserve some context
        )

        if target_summary_chars < len(summary):
            head = min(_FACT_DOC_HEAD_CHARS, int(target_summary_chars * 0.75))
            tail = min(_FACT_DOC_TAIL_CHARS, target_summary_chars - head)
            if tail < 200:
                tail = min(200, target_summary_chars // 4)
                head = target_summary_chars - tail
            separator = "\n... [truncated for fact extraction] ...\n"
            doc["content_summary"] = (
                summary[:head] + separator + summary[-tail:]
                if tail > 0 else summary[:target_summary_chars]
            )

        capped_chars = len(json.dumps(doc))
        logger.info(
            f"[FACT_CAP] {filename}: {original_chars} -> {capped_chars} chars "
            f"(summary: {len(summary)} -> {len(doc.get('content_summary', ''))})"
        )
        return doc

    # -------------------------------------------------------------------------
    # Batched fact extraction: map-reduce over document batches
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_docs_context(
        document_summaries: List[DocumentSummaryStructured],
    ) -> List[dict]:
        """Build the docs_context list used by fact extraction prompts.

        Extracted as a static method so both single-call and batched paths
        produce identical per-document context dicts.
        """
        docs_context = []
        for doc in document_summaries:
            doc_dict = doc.model_dump(mode="json")
            structured_data = doc_dict.get("structured_data") or {}
            summary = doc_dict.get("key_content") or doc_dict.get("executive_summary") or ""
            summary = MultiStageAnalyzer._condense_doc_summary_for_fact_matrix(summary)

            entry = {
                "filename": doc_dict.get("document_name") or doc_dict.get("source_document") or "Unknown",
                "document_type": doc_dict.get("document_type") or "Unknown",
                "content_summary": summary,
                "important_details": doc_dict.get("important_details", [])[:8],
                "legal_significance": doc_dict.get("legal_significance"),
                "parties": (
                    doc_dict.get("parties")
                    or structured_data.get("parties")
                    or doc_dict.get("parties_mentioned")
                    or []
                ),
                "dates": (
                    doc_dict.get("key_dates")
                    or structured_data.get("dates")
                    or doc_dict.get("dates_mentioned")
                    or []
                ),
                "amounts": (
                    doc_dict.get("key_amounts")
                    or structured_data.get("amounts")
                    or []
                ),
            }
            # Cap total serialized per-doc contribution to prevent oversized batches
            docs_context.append(MultiStageAnalyzer._cap_doc_for_fact_extraction(entry))
        return docs_context

    @staticmethod
    def _partition_fact_batches(docs_context: List[dict]) -> List[List[dict]]:
        """Partition docs_context into batches respecting char and doc-count budgets."""
        batches: List[List[dict]] = []
        current: List[dict] = []
        current_chars = 0

        for doc in docs_context:
            doc_chars = len(json.dumps(doc))
            if (current_chars + doc_chars > _FACT_BATCH_MAX_CHARS and current) \
                    or len(current) >= _FACT_BATCH_MAX_DOCS:
                batches.append(current)
                current = [doc]
                current_chars = doc_chars
            else:
                current.append(doc)
                current_chars += doc_chars

        if current:
            batches.append(current)
        return batches

    async def _extract_fact_matrix_batched(
        self,
        intake_content: str,
        document_summaries: List[DocumentSummaryStructured],
        jurisdiction: str,
        document_registry: Optional[List[Dict[str, Any]]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> FactMatrix:
        """Stage 1 (batched): Extract facts via map-reduce over document batches.

        Used when document count > _FACT_BATCH_DOC_THRESHOLD or total summary
        chars > _FACT_BATCH_CHAR_THRESHOLD. Each batch gets the same prompt
        template as the single-call path, scoped to its subset of documents.
        Partial results are merged with deterministic deduplication.
        """
        docs_context = self._build_docs_context(document_summaries)
        batches = self._partition_fact_batches(docs_context)
        registry_context = self._build_document_registry_context(document_registry)

        # Log per-doc serialized sizes for observability / cap verification
        doc_sizes = [(d.get("filename", "?"), len(json.dumps(d))) for d in docs_context]
        over_cap = [(n, s) for n, s in doc_sizes if s > _FACT_DOC_MAX_SERIALIZED_CHARS]
        logger.info(
            f"[STAGE:1:BATCHED] Starting batched fact extraction | "
            f"docs={len(document_summaries)} batches={len(batches)} "
            f"total_chars={sum(s for _, s in doc_sizes)} "
            f"max_doc={max(s for _, s in doc_sizes) if doc_sizes else 0} "
            f"over_cap={len(over_cap)}"
        )
        if over_cap:
            for name, size in over_cap:
                logger.warning(
                    f"[STAGE:1:BATCHED] Doc over cap: {name} = {size} chars "
                    f"(cap={_FACT_DOC_MAX_SERIALIZED_CHARS})"
                )

        semaphore = asyncio.Semaphore(_FACT_BATCH_CONCURRENCY)
        batch_metrics: List[dict] = []

        async def run_batch(batch_idx: int, batch_docs: List[dict]) -> Optional[FactMatrix]:
            batch_chars = sum(len(json.dumps(d)) for d in batch_docs)
            metric = {
                "batch": batch_idx + 1,
                "docs": len(batch_docs),
                "chars": batch_chars,
                "duration_s": 0,
                "success": False,
                "error": None,
            }
            batch_metrics.append(metric)

            async with semaphore:
                batch_start = time.time()
                logger.info(
                    f"[STAGE:1:BATCH:{batch_idx+1}/{len(batches)}] Starting | "
                    f"docs={len(batch_docs)} chars={batch_chars}"
                )
                try:
                    result = await self._extract_fact_matrix_single_batch(
                        intake_content, batch_docs, jurisdiction,
                        registry_context, batch_idx, len(batches),
                    )
                    metric["duration_s"] = round(time.time() - batch_start, 1)
                    metric["success"] = True
                    logger.info(
                        f"[STAGE:1:BATCH:{batch_idx+1}/{len(batches)}] Complete | "
                        f"duration={metric['duration_s']}s "
                        f"parties={len(result.parties)} events={len(result.timeline)}"
                    )
                    return result
                except Exception as e:
                    metric["duration_s"] = round(time.time() - batch_start, 1)
                    metric["error"] = str(e)[:200]
                    logger.error(
                        f"[STAGE:1:BATCH:{batch_idx+1}/{len(batches)}] Failed | "
                        f"duration={metric['duration_s']}s error={e}"
                    )
                    return None

        # Run batches with concurrency limit
        tasks = [run_batch(i, batch) for i, batch in enumerate(batches)]
        results = await asyncio.gather(*tasks)

        # Emit progress after all batches complete
        if progress_callback:
            await progress_callback(
                "Fact extraction batches complete, merging results...",
                [], "fact_extraction", 30,
                stage={"id": "fact_extraction", "name": "Extracting Facts",
                       "status": "active", "progress": 85}
            )

        # Filter successes
        successful = [r for r in results if r is not None]
        failed_count = len(results) - len(successful)

        if not successful:
            logger.error(
                f"[STAGE:1:BATCHED] ALL {len(batches)} batches failed | "
                f"metrics={json.dumps(batch_metrics)}"
            )
            raise ValueError(
                f"All {len(batches)} fact extraction batches failed. "
                f"Batch errors: {[m.get('error') for m in batch_metrics]}"
            )

        if failed_count > 0:
            logger.warning(
                f"[STAGE:1:BATCHED] {failed_count}/{len(batches)} batches failed, "
                f"merging {len(successful)} successful batches"
            )

        merged = self._merge_fact_matrices(successful)

        logger.info(
            f"[STAGE:1:BATCHED] Merge complete | "
            f"batches={len(successful)}/{len(batches)} "
            f"parties={len(merged.parties)} timeline={len(merged.timeline)} "
            f"financial={len(merged.financial_data)} "
            f"batch_metrics={json.dumps(batch_metrics)}"
        )

        return merged

    async def _extract_fact_matrix_single_batch(
        self,
        intake_content: str,
        batch_docs: List[dict],
        jurisdiction: str,
        registry_context: str,
        batch_idx: int,
        total_batches: int,
    ) -> FactMatrix:
        """Extract facts from a single batch of documents.

        Uses the same prompt template as _extract_fact_matrix, scoped to
        the batch's subset of documents.
        """
        prompt = f"""You are a precise legal fact extractor focusing on a matter in {jurisdiction}.
Extract ONLY factual information from the case materials. Do NOT perform legal analysis.

INTAKE INFORMATION:
{self._condense_intake_for_prompt(intake_content, max_chars=3000)}

DOCUMENT REGISTRY (AUTHORITATIVE CLASSIFICATION/EXECUTION SIGNALS):
{registry_context}

DOCUMENT SUMMARIES (batch {batch_idx + 1} of {total_batches}):
{json.dumps(batch_docs, indent=2)}

Extract and structure the following facts FROM THESE DOCUMENTS ONLY:

1. **PARTIES**: Identify all parties mentioned
   - Name (exact spelling)
   - Role (Client, Opposing Party, Contractor, Landlord, Tenant, Subcontractor, etc.)
   - First mentioned in which document
   - Is this an opposing party? (true/false)
   - Entity type (individual, LLC, corporation, partnership, government, or unknown)

2. **TIMELINE**: Chronological events with dates
   - Date (be as specific as possible; if unknown, use null)
   - Description of event
   - Source document
   - Significance (why this event matters)
   - Supporting evidence (list of document names that prove the event)

3. **FINANCIAL DATA**: All monetary amounts
   - Amount (exact number)
   - Description (what this money represents)
   - Date if applicable
   - Source document
   - Type (paid, owed, claimed, estimated)
   - Category (contract_price, payment_made, damages_claimed, fees_owed, refund_owed, other)

4. **KEY DOCUMENTS**: Important documents referenced
   - Document name
   - Type (Contract, Notice, Correspondence, Evidence, etc.)
   - Date if known
   - Why this document is significant

5. **PROPERTY INFO** (if applicable):
   - Full address
   - Property type

6. **PRELIMINARY ISSUES**: Initial legal issues you can identify (just list, no analysis)

Return a JSON object with this EXACT structure:
{{
  "parties": [
    {{
      "name": "string",
      "role": "string",
      "contact_info": "string or null",
      "first_mentioned_in": "string or null",
      "is_opposing_party": true,
      "entity_type": "individual | LLC | corporation | partnership | government | unknown"
    }}
  ],
  "timeline": [
    {{
      "date": "YYYY-MM-DD or Month YYYY or null",
      "description": "string",
      "source_document": "string",
      "significance": "string or null",
      "supporting_evidence": ["DocumentA.pdf"]
    }}
  ],
  "financial_data": [
    {{
      "amount": number,
      "description": "string",
      "date": "string or null",
      "source_document": "string",
      "payment_type": "paid | owed | claimed | estimated",
      "category": "contract_price | payment_made | damages_claimed | fees_owed | refund_owed | other"
    }}
  ],
  "key_documents": [
    {{
      "document_name": "string",
      "document_type": "Contract | Notice | Correspondence | Evidence | Other",
      "date": "string or null",
      "significance": "string"
    }}
  ],
  "property_details": {{
    "address": "string",
    "property_type": "string or null",
    "additional_details": {{}}
  }} or null,
  "preliminary_issues": ["string"],
  "extraction_notes": "string or null"
}}

RULES:
- Be extremely precise with dates, amounts, names
- Include source document for everything
- Do NOT invent facts - only extract what's clearly stated
- If date is truly unknown, use null - do NOT guess
- If unsure about a detail, note it in extraction_notes
- Return ONLY valid JSON, no markdown formatting
"""

        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-5.4-mini")

        response_dict = await asyncio.to_thread(
            self.client.create_response,
            model=model,
            instructions=(
                f"You are a precise legal fact extractor for {jurisdiction} law. "
                "Return only valid JSON."
            ),
            input=prompt,
            max_output_tokens=16000,
        )

        if response_dict.get("success") is False:
            raise ValueError(f"API error in batch {batch_idx+1}: {response_dict.get('error')}")

        raw_response = safe_str_required(response_dict.get("content"), "")
        if not raw_response:
            raise ValueError(f"Empty response from API for batch {batch_idx+1}")

        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        try:
            fact_data = json.loads(raw_response)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parse failed for batch {batch_idx+1}: {e}")

        # Log null source_document values before Pydantic coerces them
        for category, items in [
            ("timeline", fact_data.get("timeline", [])),
            ("financial_data", fact_data.get("financial_data", [])),
        ]:
            for item in items:
                if item.get("source_document") is None:
                    logger.warning(
                        f"[STAGE:1:BATCH:{batch_idx+1}] Null source_document in {category} | "
                        f"description={str(item.get('description', ''))[:80]} — coercing to 'Unknown'"
                    )

        return FactMatrix(
            parties=[Party(**p) for p in fact_data.get("parties", [])],
            timeline=[Event(**e) for e in fact_data.get("timeline", [])],
            financial_data=[FinancialItem(**f) for f in fact_data.get("financial_data", [])],
            key_documents=[KeyDocument(**d) for d in fact_data.get("key_documents", [])],
            preliminary_issues=fact_data.get("preliminary_issues", []),
            property_details=(
                PropertyInfo(**fact_data["property_details"])
                if fact_data.get("property_details") else None
            ),
            extraction_notes=fact_data.get("extraction_notes"),
        )

    @staticmethod
    def _normalize_party_name(name: str) -> str:
        """Normalize party name for deduplication."""
        n = name.strip().lower()
        n = re.sub(r'\s+', ' ', n)
        for suffix in [', inc.', ', llc', ', corp.', ', ltd.', ' inc', ' llc', ' corp']:
            if n.endswith(suffix):
                n = n[:-len(suffix)]
        return n

    @staticmethod
    def _merge_fact_matrices(matrices: List[FactMatrix]) -> FactMatrix:
        """Merge partial FactMatrix results from batched extraction.

        Deduplication rules:
        - Parties: by normalized name; is_opposing_party sticky-true; role conflicts logged
        - Timeline: by (date, description[:80] lowered)
        - Financial: by (amount_cents, description[:60] lowered)
        - Key documents: by normalized filename
        - Issues: by normalized text
        """
        parties: Dict[str, Party] = {}
        timeline_seen: set = set()
        timeline: List[Event] = []
        financial_seen: set = set()
        financial: List[FinancialItem] = []
        key_docs: Dict[str, KeyDocument] = {}
        issues: set = set()

        for m in matrices:
            for p in m.parties:
                key = MultiStageAnalyzer._normalize_party_name(p.name)
                if key in parties:
                    existing = parties[key]
                    if p.is_opposing_party and not existing.is_opposing_party:
                        parties[key] = existing.model_copy(
                            update={"is_opposing_party": True}
                        )
                    if p.contact_info and not existing.contact_info:
                        parties[key] = parties[key].model_copy(
                            update={"contact_info": p.contact_info}
                        )
                    if p.name.strip() != existing.name.strip():
                        logger.info(
                            f"[MERGE] Party alias: '{p.name}' matches existing '{existing.name}'"
                        )
                    if p.role != existing.role:
                        logger.info(
                            f"[MERGE] Party '{p.name}' role conflict: "
                            f"'{existing.role}' vs '{p.role}' — keeping '{existing.role}'"
                        )
                else:
                    parties[key] = p

            for event in m.timeline:
                date_str = str(event.date) if event.date else ""
                tkey = (date_str, event.description[:80].strip().lower())
                if tkey not in timeline_seen:
                    timeline_seen.add(tkey)
                    timeline.append(event)

            for f in m.financial_data:
                amount_cents = round((f.amount or 0) * 100)
                fkey = (amount_cents, f.description[:60].strip().lower())
                if fkey not in financial_seen:
                    financial_seen.add(fkey)
                    financial.append(f)

            for d in m.key_documents:
                dkey = d.document_name.strip().lower()
                if dkey not in key_docs:
                    key_docs[dkey] = d

            for issue in m.preliminary_issues:
                issues.add(issue.strip().lower())

        timeline.sort(key=lambda e: str(e.date) if e.date else "9999-99-99")

        property_details = next(
            (m.property_details for m in matrices if m.property_details), None
        )

        return FactMatrix(
            parties=list(parties.values()),
            timeline=timeline,
            financial_data=financial,
            key_documents=list(key_docs.values()),
            preliminary_issues=list(issues),
            property_details=property_details,
        )

    async def _map_legal_issues(
        self,
        fact_matrix: FactMatrix,
        intake_content: str,
        case_type: Optional[str],
        legal_issues_hint: Optional[List[str]],
        jurisdiction: str,
    ) -> LegalIssueMap:
        """Stage 2: Map all applicable legal issues and statutes."""
        prompt = f"""You are a {jurisdiction} legal issue analyst. Based on the facts
extracted, identify ALL applicable legal issues and statutes under {jurisdiction} law.

CASE TYPE: {case_type or "Unknown"}
PRELIMINARY ISSUES: {", ".join(legal_issues_hint or fact_matrix.preliminary_issues)}

FACTS:
- Parties: {len(fact_matrix.parties)} identified
- Timeline: {len(fact_matrix.timeline)} events
- Financial: {len(fact_matrix.financial_data)} items

        INTAKE SUMMARY:
{self._condense_intake_for_prompt(intake_content, max_chars=3000)}

DETAILED FACTS:
{json.dumps(fact_matrix.model_dump(), indent=2, default=str)[:4000]}

Your task:
1. Identify primary legal issues (3-5)
2. Map applicable {jurisdiction} statutes or rules
3. Identify secondary issues (2-4)
4. List key facts supporting each primary issue

Return JSON:
{{
  "primary_issues": [
    {{
      "issue_name": "string (e.g. Breach of Implied Warranty)",
      "category": "contract | tort | statutory | procedural",
      "elements": ["Element 1 that must be proven", "Element 2"],
      "potential_remedies": ["Remedy 1", "Remedy 2"],
      "statute_references": ["{jurisdiction} Statute § ..."],
      "confidence": "strong | moderate | weak"
    }}
  ],
  "secondary_issues": [
    {{
      "issue_name": "string",
      "category": "contract | tort | statutory | procedural",
      "elements": [],
      "potential_remedies": [],
      "statute_references": [],
      "confidence": "weak"
    }}
  ],
  "statutory_framework": "Summary of the governing {jurisdiction} law for this case"
}}
"""

        # Use GPT-4.1-mini for fast issue mapping (0.5s latency vs 60s+ for GPT-5.2)
        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-5.4-mini")

        logger.info(
            f"[STAGE:2:API] Calling OpenAI for issue_mapping | "
            f"model={model} prompt_chars={len(prompt)} max_tokens=12000"
        )

        # Use asyncio.to_thread to avoid blocking the event loop during API call
        api_start = time.time()
        response_dict = await asyncio.to_thread(
            self.client.create_response,
            model=model,
            instructions=f"You are an expert {jurisdiction} legal analyst. Return only valid JSON.",
            input=prompt,
            max_output_tokens=12000,  # Complex cases need room for detailed issue mapping
        )
        api_duration = time.time() - api_start

        logger.info(
            f"[STAGE:2:API] OpenAI response received | "
            f"duration={api_duration:.1f}s "
            f"prompt_tokens={response_dict.get('usage', {}).get('prompt_tokens', 0)} "
            f"completion_tokens={response_dict.get('usage', {}).get('completion_tokens', 0)} "
            f"response_chars={len(response_dict.get('content', '') or '')}"
        )

        # Check for API error response
        if response_dict.get("success") is False:
            error_msg = response_dict.get("error", "Unknown API error")
            logger.error(f"[STAGE:2:ERROR] API returned error: {error_msg}")
            raise ValueError(f"GPT API error in issue mapping: {error_msg}")

        raw_response = safe_str_required(response_dict.get("content"), "")

        # Handle empty responses
        if not raw_response:
            logger.error("[STAGE:2:ERROR] Empty response from GPT API")
            raise ValueError("GPT API returned an empty response for issue mapping")

        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        try:
            issue_data = json.loads(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"[STAGE:2:ERROR] JSON parse failed: {e}. Response: {raw_response[:500]}")
            raise ValueError(f"Failed to parse issue mapping response as JSON: {e}")

        return LegalIssueMap(
            primary_issues=[LegalIssue(**i) for i in issue_data.get("primary_issues", [])],
            secondary_issues=[LegalIssue(**i) for i in issue_data.get("secondary_issues", [])],
            statutory_framework=issue_data.get("statutory_framework", ""),
        )

    async def _perform_deep_legal_analysis(
        self,
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        intake_content: str,
        jurisdiction: str,
    ) -> DeepAnalysis:
        """Stage 3: Comprehensive analysis of each issue using factual matrix."""
        # Prepare context
        issues_to_analyze = [i.model_dump() for i in issue_map.primary_issues]

        prompt = f"""You are a senior {jurisdiction} attorney. Perform a deep legal
analysis of the identified issues based on the factual matrix.

JURISDICTION: {jurisdiction}
ISSUES TO ANALYZE:
{json.dumps(issues_to_analyze, indent=2)}

FACTUAL MATRIX:
{json.dumps(fact_matrix.model_dump(), indent=2, default=str)[:5000]}

Return JSON:
{{
  "issue_analyses": [
    {{
      "issue_name": "string (match issue from input)",
      "legal_standard": "Plain English explanation of the law",
      "fact_application": "How the facts meet this standard - BE SPECIFIC with dates/amounts",
      "statute_analysis": "Analysis with verified statute citations (if applicable)",
      "case_law_support": "Case law if applicable or null",
      "remedies_available": ["Specific remedy 1", "Specific remedy 2"],
      "procedural_requirements": "Natural integration of procedures (if applicable) or null",
      "confidence_level": "strong | moderate | weak",
      "supporting_evidence": ["Key evidence item 1", "Key evidence item 2"]
    }}
  ],
  "risk_assessment": {{
    "major_risks": ["Risk 1", "Risk 2"],
    "risk_mitigation_steps": ["Step 1", "Step 2"],
    "statute_of_limitations_concerns": "string or null",
    "evidence_gaps": ["Gap 1", "Gap 2"]
  }},
  "deadline_tracking": [
    {{
      "deadline_date": "date string or null",
      "description": "What must be done",
      "consequence_if_missed": "What happens",
      "urgency": "critical | important | normal",
      "statute_basis": "statute reference or null"
    }}
  ],
  "evidence_strength": {{
    "strong_evidence": ["Evidence 1", "Evidence 2"],
    "weak_evidence": ["Evidence 1", "Evidence 2"],
    "missing_evidence": ["Needed 1", "Needed 2"],
    "overall_strength": "strong | moderate | weak"
  }},
  "overall_case_strength": "strong | moderate | weak",
  "key_strengths": ["Strength 1", "Strength 2"],
  "key_challenges": ["Challenge 1", "Challenge 2"],
  "is_viable": true | false,
  "viability_reasoning": "Detailed explanation of why the case is or is not viable under {jurisdiction} law.",
  "recommend_demand_letter": true | false
}}

CASE VIABILITY CRITERIA:
Set "is_viable" to FALSE if ANY of the following apply:

LEGAL VIABILITY:
- The facts do not support any recognized legal claim under {jurisdiction} law
- The statute of limitations has clearly expired
- The client's own conduct bars recovery (e.g., comparative fault > 50% in applicable states)
- There is insufficient evidence to prove essential elements
- The opposing party has clear, unassailable defenses (e.g., valid contract disclaimer, proper notice)

PRACTICAL VIABILITY:
- The defendant cannot be identified or located for service
- The potential recovery is significantly less than the cost to pursue ($5,000+ case costs vs. $2,000 recovery)
- Essential procedural requirements cannot be met (e.g., required statutory notice not sent, deadline passed)
- The client lacks standing to bring the claim (e.g., not party to contract, no injury)
- The claim is barred by res judicata or collateral estoppel (previously litigated)
- The defendant appears judgment-proof (no assets, bankrupt)

DOCUMENT COMPLETENESS:
- Critical documents referenced in the case are missing (e.g., the contract itself, the lease, the notice)
- The client's version of events is contradicted by their own documents
- Key evidence has been lost, destroyed, or is unavailable

CRITICAL INSTRUCTIONS:
- Use VERIFIED STATUTES PREFERENTIALLY
- For unverified statutes, use cautious language: "Under {jurisdiction} law..."
- Be specific with facts - use actual dates, amounts, names from fact matrix
- Be HONEST about case viability - do not give false hope.

Return ONLY valid JSON.
"""

        # Stage 3 synthesis hardcoded to gpt-5.4 (not 5.5): the 5.5 reasoning
        # loop on long multi-issue prompts intermittently returns empty
        # completions after ~500s. Bypass user_preferences here because a
        # multi_stage_analysis=gpt-5.5 pref would otherwise reintroduce the bug.
        model = "gpt-5.4"

        logger.info(
            f"[STAGE:3:API] Calling OpenAI for deep_analysis | "
            f"model={model} prompt_chars={len(prompt)} max_tokens=8000"
        )

        # Use asyncio.to_thread to avoid blocking the event loop during API call
        api_start = time.time()
        response_dict = await asyncio.to_thread(
            self.client.create_response,
            model=model,
            instructions=(
                f"You are a senior {jurisdiction} attorney with 20+ years experience. "
                "Provide comprehensive analysis."
            ),
            input=prompt,
            max_output_tokens=8000,
        )
        api_duration = time.time() - api_start

        logger.info(
            f"[STAGE:3:API] OpenAI response received | "
            f"duration={api_duration:.1f}s "
            f"prompt_tokens={response_dict.get('usage', {}).get('prompt_tokens', 0)} "
            f"completion_tokens={response_dict.get('usage', {}).get('completion_tokens', 0)} "
            f"response_chars={len(response_dict.get('content', '') or '')}"
        )

        # Check for API error response
        if response_dict.get("success") is False:
            error_msg = response_dict.get("error", "Unknown API error")
            logger.error(f"[STAGE:3:ERROR] API returned error: {error_msg}")
            raise ValueError(f"GPT API error in deep analysis: {error_msg}")

        raw_response = safe_str_required(response_dict.get("content"), "")

        # Handle empty responses
        if not raw_response:
            logger.error("[STAGE:3:ERROR] Empty response from GPT API")
            raise ValueError("GPT API returned an empty response for deep analysis")

        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        try:
            analysis_data = json.loads(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"[STAGE:3:ERROR] JSON parse failed: {e}. Response: {raw_response[:500]}")
            raise ValueError(f"Failed to parse deep analysis response as JSON: {e}")

        return DeepAnalysis(
            issue_analyses=[IssueAnalysis(**a) for a in analysis_data.get("issue_analyses", [])],
            risk_assessment=RiskAssessment(**analysis_data.get("risk_assessment", {})),
            deadline_tracking=[CriticalDeadline(**d) for d in analysis_data.get("deadline_tracking", [])],
            evidence_strength=EvidenceAssessment(**analysis_data.get("evidence_strength", {})),
            overall_case_strength=analysis_data.get("overall_case_strength", "moderate"),
            key_strengths=analysis_data.get("key_strengths", []),
            key_challenges=analysis_data.get("key_challenges", []),
            is_viable=analysis_data.get("is_viable", True),
            viability_reasoning=analysis_data.get("viability_reasoning"),
            recommend_demand_letter=analysis_data.get("recommend_demand_letter", True),
        )

    def _determine_letter_structure(
        self,
        issue_map: LegalIssueMap,
        analysis: DeepAnalysis,
    ) -> LetterStructure:
        """Stage 4: Decide optimal letter structure."""
        num_primary_issues = len(issue_map.primary_issues)

        return LetterStructure(
            style="structured_professional",
            intro="",
            issue_format="bold_titled_bullet_provisions",
            reasoning=(
                f"Structured professional format with {num_primary_issues} issue(s). "
                f"Four sections: Background & Issue, Key Legal Issues, Analysis, Recommended Next Steps."
            ),
        )

    def _identify_opposing_parties(self, fact_matrix: FactMatrix) -> List[Party]:
        """Identify opposing parties based on flags or roles."""
        opposing = [
            party
            for party in fact_matrix.parties
            if party.is_opposing_party or (party.role and "oppos" in party.role.lower())
        ]

        if not opposing:
            opposing = [
                party
                for party in fact_matrix.parties
                if party.role and party.role.lower() not in {"client", "law firm", "attorney", "counsel"}
            ]

        return opposing
