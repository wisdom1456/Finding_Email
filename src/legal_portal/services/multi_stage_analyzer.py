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
import time
from typing import Any, AsyncGenerator, Callable, List, Optional

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
from legal_portal.services.gap_analysis_service import GapAnalysisService
from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


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

    def _build_condensed_context(
        self,
        document_summaries: List[DocumentSummaryStructured],
        max_docs: int = 20,
    ) -> str:
        """Build token-efficient context from document summaries.
        
        Args:
            document_summaries: List of document summaries
            max_docs: Maximum number of documents to include
            
        Returns:
            Condensed string representation of documents

        """
        lines = []
        for i, summary in enumerate(document_summaries[:max_docs]):
            # Get the most important content from each document
            doc_name = summary.document_name
            exec_summary = (summary.executive_summary or "")[:300]
            doc_type = summary.document_type or "document"

            lines.append(f"[{i+1}] {doc_name} ({doc_type})")
            if exec_summary:
                lines.append(f"    Summary: {exec_summary}")
            lines.append("")

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
{intake_content[:4000]}

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
    "documented_damages": "$X,XXX.XX or null"
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
    ) -> AsyncGenerator[str, None]:
        """Stream comprehensive case analysis as markdown.
        
        Single API call that outputs readable markdown in real-time.
        Much faster than multi-stage analysis and eliminates timeout issues.
        
        Args:
            intake_content: Client intake form content
            document_summaries: List of document summaries
            jurisdiction: Legal jurisdiction
            
        Yields:
            Tokens as they are generated by the model

        """
        logger.info(
            f"[STREAMING] Starting streaming analysis | "
            f"jurisdiction={jurisdiction} docs={len(document_summaries)} "
            f"intake_chars={len(intake_content)}"
        )

        start_time = time.time()

        # Build condensed context to reduce tokens
        document_context = self._build_condensed_context(document_summaries)

        # Build the comprehensive prompt
        prompt = self._build_streaming_prompt(
            intake_content=intake_content,
            document_context=document_context,
            jurisdiction=jurisdiction,
        )

        logger.info(
            f"[STREAMING] Prompt built | "
            f"prompt_chars={len(prompt)} context_chars={len(document_context)}"
        )

        system_prompt = f"""You are a senior {jurisdiction} attorney with 20+ years of experience. 
Analyze cases thoroughly and provide actionable insights.
Always cite specific statutes and case law where applicable.
Be direct and specific - avoid vague language.
Output in clean markdown format."""

        token_count = 0

        try:
            # Use GPT-5.2 medium for high-quality analysis
            # 24K tokens allows for ~10-12K visible output after reasoning overhead
            async for token in self.client.create_chat_completion_stream(
                model="gpt-5.2",
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
    ) -> MultiStageAnalysisResult:
        """Execute 4-stage analysis pipeline."""
        start_time = time.time()
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
        if progress_callback:
            await progress_callback(
                "Extracting key facts and timeline...",
                [],
                "fact_extraction",
                20,
                stage={"id": "fact_matrix", "name": "Extracting Facts", "status": "active", "progress": 5}
            )

        stage_start = time.time()
        elapsed = time.time() - start_time
        logger.info(
            f"[STAGE:1] [ELAPSED:{elapsed:.1f}s] Starting fact_matrix extraction | "
            f"jurisdiction={jurisdiction}"
        )

        # Use heartbeat to show progress during long API call
        fact_matrix = await self._run_with_heartbeat(
            lambda: self._extract_fact_matrix(intake_content, document_summaries, jurisdiction),
            progress_callback,
            "fact_extraction",
            "Extracting Facts",
            20,
        )
        self.stage_timings["fact_extraction"] = time.time() - stage_start
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
                    "id": "fact_matrix",
                    "name": "Extracting Facts",
                    "status": "completed",
                    "progress": 100,
                    "extracted": {"type": "parties", "count": len(fact_matrix.parties)}
                }
            )

        if diag_logger:
            diag_logger.log_stage("multi_stage_1_fact_matrix", fact_matrix.model_dump(mode="json"))

        # Stage 2: Map Legal Issues
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

        # Use heartbeat to show progress during long API call
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

        # Use heartbeat to show progress during long API call
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
            case_facts=intake_content[:2000],
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
        )

    async def _extract_fact_matrix(
        self,
        intake_content: str,
        document_summaries: List[DocumentSummaryStructured],
        jurisdiction: str,
    ) -> FactMatrix:
        """Stage 1: Extract structured facts from documents."""
        docs_context = []
        for doc in document_summaries:
            doc_dict = doc.model_dump(mode="json")
            structured_data = doc_dict.get("structured_data") or {}

            summary = doc_dict.get("key_content") or doc_dict.get("executive_summary") or ""
            summary = self._condense_doc_summary_for_fact_matrix(summary)

            docs_context.append(
                {
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
            )

        prompt = f"""You are a precise legal fact extractor focusing on a matter in {jurisdiction}.
Extract ONLY factual information from the case materials. Do NOT perform legal analysis.

INTAKE INFORMATION:
{intake_content[:5000]}

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
        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-4.1-mini")

        logger.info(
            f"[STAGE:1:API] Calling OpenAI for fact_matrix | "
            f"model={model} prompt_chars={len(prompt)} max_tokens=4000"
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
            max_output_tokens=4000,  # GPT-4.1-mini doesn't need reasoning token overhead
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

        raw_response = (response_dict.get("content") or "").strip()

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
{intake_content[:3000]}

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
      "florida_statute_references": ["{jurisdiction} Statute § ..."],
      "confidence": "strong | moderate | weak"
    }}
  ],
  "secondary_issues": [
    {{
      "issue_name": "string",
      "category": "contract | tort | statutory | procedural",
      "elements": [],
      "potential_remedies": [],
      "florida_statute_references": [],
      "confidence": "weak"
    }}
  ],
  "statutory_framework": "Summary of the governing {jurisdiction} law for this case"
}}
"""

        # Use GPT-4.1-mini for fast issue mapping (0.5s latency vs 60s+ for GPT-5.2)
        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-4.1-mini")

        logger.info(
            f"[STAGE:2:API] Calling OpenAI for issue_mapping | "
            f"model={model} prompt_chars={len(prompt)} max_tokens=3000"
        )

        # Use asyncio.to_thread to avoid blocking the event loop during API call
        # GPT-4.1-mini: Fast pattern matching without reasoning overhead
        api_start = time.time()
        response_dict = await asyncio.to_thread(
            self.client.create_response,
            model=model,
            instructions=f"You are an expert {jurisdiction} legal analyst. Return only valid JSON.",
            input=prompt,
            max_output_tokens=3000,  # GPT-4.1-mini doesn't need reasoning token overhead
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

        raw_response = (response_dict.get("content") or "").strip()

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

        # Use GPT-4.1 (full model) for quality synthesis (0.5s latency vs 60s+ for GPT-5.2)
        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-4.1")

        logger.info(
            f"[STAGE:3:API] Calling OpenAI for deep_analysis | "
            f"model={model} prompt_chars={len(prompt)} max_tokens=6000"
        )

        # Use asyncio.to_thread to avoid blocking the event loop during API call
        # GPT-4.1: Higher quality synthesis without reasoning overhead
        api_start = time.time()
        response_dict = await asyncio.to_thread(
            self.client.create_response,
            model=model,
            instructions=(
                f"You are a senior {jurisdiction} attorney with 20+ years experience. "
                "Provide comprehensive analysis."
            ),
            input=prompt,
            max_output_tokens=6000,  # GPT-4.1 doesn't need reasoning token overhead
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

        raw_response = (response_dict.get("content") or "").strip()

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
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning=(
                f"Natural flow format with {num_primary_issues} issue(s). "
                f"Plain language explanations without formal headers."
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
