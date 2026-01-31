"""Gap Analysis Service - Identifies missing documents, contradictions, and weaknesses.

This service performs AI-powered analysis to identify gaps and inconsistencies in case materials,
providing attorneys with critical feedback about case completeness.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from legal_portal.core.data_models import (
    DeepAnalysis,
    DocumentSummaryStructured,
    FactMatrix,
    GapAnalysisResult,
    GapCategory,
    GapItem,
    GapSeverity,
    LegalIssueMap,
)
from legal_portal.utils.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class GapAnalysisService:
    """Service for analyzing case completeness and identifying gaps."""

    def __init__(self, openai_client: OpenAIClient):
        """Initialize the gap analysis service.

        Args:
            openai_client: OpenAI client for GPT model calls
        """
        self.client = openai_client

    async def analyze_gaps(
        self,
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        deep_analysis: DeepAnalysis,
        document_summaries: List[DocumentSummaryStructured],
        intake_content: Optional[str] = None,
    ) -> GapAnalysisResult:
        """Analyze case for gaps, contradictions, and weaknesses.

        This performs Stage 3.5 analysis - critical review of case completeness.

        Args:
            fact_matrix: Extracted facts from Stage 1
            issue_map: Legal issues from Stage 2
            deep_analysis: Deep analysis from Stage 3
            document_summaries: Summaries of all documents
            intake_content: Original intake form content

        Returns:
            GapAnalysisResult with identified gaps and completeness assessment
        """
        logger.info("[GAP_SERVICE] Starting gap analysis (Stage 3.5)")
        logger.info(f"[GAP_SERVICE] Inputs - fact_matrix parties: {len(fact_matrix.parties)}, issues: {len(issue_map.primary_issues)}, docs: {len(document_summaries)}")

        try:
            # Build the analysis prompt
            prompt = self._build_gap_analysis_prompt(
                fact_matrix=fact_matrix,
                issue_map=issue_map,
                deep_analysis=deep_analysis,
                document_summaries=document_summaries,
                intake_content=intake_content,
            )

            # Use GPT-4.1 for gap detection - faster and more reliable for structured JSON
            # GPT-5.2 with reasoning_effort spends tokens on internal reasoning, not output
            model = self.client.get_preferred_model("gap_analysis", "gpt-4.1")

            logger.info(
                f"[STAGE:3.5:API] Calling OpenAI for gap_analysis | "
                f"model={model} prompt_chars={len(prompt)} max_tokens=4000"
            )

            # Call OpenAI API
            api_start = time.time()
            response_dict = await asyncio.to_thread(
                self.client.create_response,
                model=model,
                instructions=(
                    "You are a critical legal analyst identifying gaps and inconsistencies in case materials. "
                    "Return only valid JSON matching the GapAnalysisResult schema. Do not include any text before or after the JSON."
                ),
                input=prompt,
                max_output_tokens=4000,
                # No reasoning_effort for GPT-4.x - it outputs content directly
            )
            api_duration = time.time() - api_start

            finish_reason = response_dict.get("finish_reason", "unknown")
            logger.info(
                f"[STAGE:3.5:API] OpenAI response received | "
                f"duration={api_duration:.1f}s finish_reason={finish_reason} "
                f"prompt_tokens={response_dict.get('usage', {}).get('prompt_tokens', 0)} "
                f"completion_tokens={response_dict.get('usage', {}).get('completion_tokens', 0)}"
            )

            # Check for API error
            if response_dict.get("success") is False:
                error_msg = response_dict.get("error", "Unknown API error")
                logger.error(f"[STAGE:3.5:ERROR] API returned error: {error_msg}")
                return self._create_fallback_result(error=error_msg)

            raw_response = (response_dict.get("content") or "").strip()

            if not raw_response:
                logger.warning("Gap analysis returned empty response")
                return self._create_fallback_result()

            # Parse JSON response
            response_json = json.loads(raw_response)
            result = GapAnalysisResult(**response_json)

            logger.info(
                f"Gap analysis completed: {result.total_gaps} gaps found "
                f"({result.critical_count} critical, {result.high_count} high)"
            )

            return result

        except Exception as e:
            logger.error(f"Gap analysis failed: {e}", exc_info=True)
            return self._create_fallback_result(error=str(e))

    def _build_gap_analysis_prompt(
        self,
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        deep_analysis: DeepAnalysis,
        document_summaries: List[DocumentSummaryStructured],
        intake_content: Optional[str],
    ) -> str:
        """Build the AI prompt for gap detection.

        Args:
            fact_matrix: Extracted facts
            issue_map: Legal issues
            deep_analysis: Deep analysis
            document_summaries: Document summaries
            intake_content: Intake form content

        Returns:
            Formatted prompt for GPT-5.2
        """
        # Prepare document list
        doc_list = "\n".join([f"- {doc.document_name}" for doc in document_summaries])

        # Prepare parties
        parties_list = "\n".join([f"- {p.name} ({p.role})" for p in fact_matrix.parties])

        # Prepare timeline events
        timeline_list = "\n".join(
            [
                f"- {event.date if event.date else 'Unknown date'}: {event.description}"
                for event in fact_matrix.timeline[:10]  # Limit to 10 most important
            ]
        )

        # Prepare legal issues
        issues_list = "\n".join(
            [f"- {issue.issue_name} (confidence: {issue.confidence})" for issue in issue_map.primary_issues]
        )

        # Evidence gaps from deep analysis
        evidence_gaps = "\n".join(deep_analysis.risk_assessment.evidence_gaps) if deep_analysis.risk_assessment.evidence_gaps else "None identified"

        prompt = f"""You are a critical legal analyst reviewing a case file for completeness and consistency.
Your role is to identify weaknesses, gaps, and concerns that an attorney should address BEFORE proceeding.

CONTEXT:

**Documents Provided:**
{doc_list}

**Parties Involved:**
{parties_list}

**Timeline (Key Events):**
{timeline_list}

**Legal Issues Identified:**
{issues_list}

**Known Evidence Gaps:**
{evidence_gaps}

**Case Viability Assessment:**
- Overall Strength: {deep_analysis.overall_case_strength}
- Is Viable: {deep_analysis.is_viable}
- Reasoning: {deep_analysis.viability_reasoning or 'Not provided'}

**Intake Information:**
{intake_content[:2000] if intake_content else 'No intake form provided'}

---

TASK: Identify gaps and inconsistencies in 4 categories:

1. **MISSING DOCUMENTS**
   - Documents referenced in other documents but not provided
   - Expected documents based on case type (e.g., lease agreement, contract, notice, invoices)
   - Critical evidence gaps that weaken the case

2. **FACTUAL CONTRADICTIONS**
   - Conflicting information across documents (e.g., different amounts, dates, terms)
   - Intake form vs. document discrepancies
   - Party name conflicts or inconsistencies

3. **TIMELINE GAPS**
   - Missing critical dates (e.g., when notice was sent, when contract was signed)
   - Out-of-sequence events that don't make logical sense
   - Statute of limitations concerns based on missing dates

4. **UNVERIFIABLE CLAIMS**
   - Assertions made in intake or analysis without supporting evidence
   - Claims that appear in one document but aren't corroborated by others
   - Assumptions that need verification

---

INSTRUCTIONS:

For each gap you identify:
- Assign severity: "critical" (case-breaking), "high" (significant impact), "medium" (notable concern), or "low" (minor issue)
- Provide a brief title (under 100 chars)
- Write a detailed description explaining the gap
- Explain the impact on the case
- Provide 1-3 specific recommendations to address the gap
- List related documents (if any)
- Identify which legal issue is affected (if applicable)

Be thorough but balanced:
- Don't invent problems that don't exist
- Focus on material gaps that actually affect case viability
- Consider whether the gap is truly critical or just "nice to have"

Calculate an overall completeness score (0-100):
- 90-100: Excellent documentation, minor gaps only
- 75-89: Good documentation, some notable gaps
- 60-74: Adequate documentation, significant gaps exist
- 40-59: Poor documentation, major gaps throughout
- 0-39: Critical documentation failures

Provide an attorney summary (2-3 sentences) about overall case completeness and most critical action items.

Return your analysis as structured JSON matching the GapAnalysisResult schema:
{{
    "total_gaps": <int>,
    "critical_count": <int>,
    "high_count": <int>,
    "medium_count": <int>,
    "low_count": <int>,
    "gaps_by_category": {{
        "missing_document": [<GapItem objects>],
        "factual_contradiction": [<GapItem objects>],
        "timeline_gap": [<GapItem objects>],
        "unverifiable_claim": [<GapItem objects>],
        "incomplete_info": [<GapItem objects>]
    }},
    "overall_completeness_score": <float 0-100>,
    "attorney_summary": "<string>"
}}

Each GapItem should have:
{{
    "gap_id": "<unique_id>",
    "category": "<GapCategory enum value>",
    "severity": "<GapSeverity enum value>",
    "title": "<brief description>",
    "description": "<detailed explanation>",
    "affected_issue": "<legal issue name or null>",
    "related_documents": [<document names>],
    "recommendations": [<action items>],
    "impact_on_case": "<explanation>"
}}

Begin your analysis now.
"""

        return prompt

    def _create_fallback_result(self, error: Optional[str] = None) -> GapAnalysisResult:
        """Create a fallback result when gap analysis fails.

        Args:
            error: Optional error message

        Returns:
            Basic GapAnalysisResult indicating analysis could not be performed
        """
        fallback_gaps: Dict[str, List[GapItem]] = {
            category.value: [] for category in GapCategory
        }

        if error:
            # Add a single gap indicating the analysis failed
            fallback_gaps[GapCategory.INCOMPLETE_INFO.value] = [
                GapItem(
                    gap_id="gap_analysis_error",
                    category=GapCategory.INCOMPLETE_INFO,
                    severity=GapSeverity.HIGH,
                    title="Gap Analysis Could Not Be Completed",
                    description=f"The automated gap analysis encountered an error: {error}",
                    affected_issue=None,
                    related_documents=[],
                    recommendations=[
                        "Manually review case materials for completeness",
                        "Verify all referenced documents are included",
                        "Check for factual inconsistencies across documents",
                    ],
                    impact_on_case="Unable to provide automated completeness assessment. Manual review recommended.",
                )
            ]

        return GapAnalysisResult(
            total_gaps=1 if error else 0,
            critical_count=0,
            high_count=1 if error else 0,
            medium_count=0,
            low_count=0,
            gaps_by_category=fallback_gaps,
            overall_completeness_score=50.0 if error else 100.0,
            attorney_summary=(
                "Gap analysis could not be completed due to a system error. Manual review recommended."
                if error
                else "No automated gap analysis was performed."
            ),
        )
