"""Multi-Stage Legal Analysis Service.

This service orchestrates a 4-stage analysis pipeline for comprehensive case evaluation:
1. Fact Matrix Extraction - Structured facts from documents
2. Legal Issue Mapping - Identify applicable laws and issues
3. Deep Legal Analysis - Comprehensive analysis of each issue
4. Letter Structure Determination - Decide optimal letter format

Created: 2025-11-21
"""

from __future__ import annotations

import json
import time
from typing import Callable, List, Optional

from legal_portal.core.data_models import (
    CriticalDeadline,
    DeepAnalysis,
    DocumentSummaryStructured,
    Event,
    EvidenceAssessment,
    FactMatrix,
    FinancialItem,
    IssueAnalysis,
    KeyDocument,
    LegalIssue,
    LegalIssueMap,
    LetterStructure,
    MultiStageAnalysisResult,
    Party,
    ProceduralStep,
    PropertyInfo,
    RiskAssessment,
)
from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


class MultiStageAnalyzer:
    """Orchestrates 4-stage analysis pipeline for comprehensive case evaluation."""

    def __init__(
        self,
        openai_client: OpenAIClient,
        statute_service: Optional[StatuteRecommendationService] = None,
    ):
        """Initialize the multi-stage analyzer.

        Args:
        ----
            openai_client: OpenAI client for AI calls
            statute_service: Service for querying Florida statute corpus
        """
        self.client = openai_client
        self.statute_service = statute_service or StatuteRecommendationService()
        self.stage_timings = {}

    async def analyze_case(
        self,
        intake_content: str,
        document_summaries: List[DocumentSummaryStructured],
        progress_callback: Optional[Callable] = None,
        case_type: Optional[str] = None,
        legal_issues: Optional[List[str]] = None,
    ) -> MultiStageAnalysisResult:
        """Execute 4-stage analysis pipeline.

        Args:
        ----
            intake_content: Processed intake form content
            document_summaries: Structured summaries of case documents
            progress_callback: Optional callback for progress updates
            case_type: Optional case type hint
            legal_issues: Optional pre-identified legal issues

        Returns:
        -------
            MultiStageAnalysisResult with comprehensive analysis
        """
        start_time = time.time()
        logger.info("Starting multi-stage analysis pipeline")

        # Stage 1: Extract Fact Matrix
        if progress_callback:
            progress_callback("Extracting key facts and timeline...", [], "fact_extraction", 20)

        stage_start = time.time()
        fact_matrix = await self._extract_fact_matrix(intake_content, document_summaries)
        self.stage_timings["fact_extraction"] = time.time() - stage_start
        logger.info(
            f"Stage 1 complete: {len(fact_matrix.parties)} parties, "
            f"{len(fact_matrix.timeline)} events, "
            f"{len(fact_matrix.financial_data)} financial items"
        )

        # Stage 2: Map Legal Issues
        if progress_callback:
            progress_callback("Mapping legal issues and statutes...", [], "issue_mapping", 35)

        stage_start = time.time()
        issue_map = await self._map_legal_issues(fact_matrix, intake_content, case_type, legal_issues)
        self.stage_timings["issue_mapping"] = time.time() - stage_start
        logger.info(
            f"Stage 2 complete: {len(issue_map.primary_issues)} primary issues, "
            f"complexity={issue_map.case_complexity}"
        )

        # Query verified statutes from corpus
        verified_statutes = []
        if issue_map.relevant_statutes:
            try:
                recommendations = self.statute_service.recommend_statutes(
                    case_facts=intake_content[:2000],
                    legal_issues=legal_issues or [],
                    case_type=case_type,
                    limit=5,
                )
                verified_statutes = [
                    {
                        "citation": rec.citation,
                        "title": rec.title,
                        "summary": rec.summary,
                        "relevance": rec.relevance_reason,
                    }
                    for rec in recommendations
                ]
                logger.info(f"Retrieved {len(verified_statutes)} verified statutes from corpus")
            except Exception as e:
                logger.warning(f"Failed to retrieve verified statutes: {e}")

        # Stage 3: Deep Legal Analysis
        if progress_callback:
            progress_callback("Performing comprehensive legal analysis...", [], "deep_analysis", 60)

        stage_start = time.time()
        deep_analysis = await self._perform_deep_analysis(
            fact_matrix, issue_map, verified_statutes, document_summaries
        )
        self.stage_timings["deep_analysis"] = time.time() - stage_start
        logger.info(
            f"Stage 3 complete: {len(deep_analysis.issue_analyses)} issues analyzed, "
            f"overall strength={deep_analysis.overall_case_strength}"
        )

        # Stage 4: Determine Letter Structure
        stage_start = time.time()
        letter_structure = self._determine_letter_structure(issue_map, deep_analysis)
        self.stage_timings["structure_determination"] = time.time() - stage_start
        logger.info(f"Stage 4 complete: structure={letter_structure.style}")

        total_time = time.time() - start_time
        logger.info(f"Multi-stage analysis complete in {total_time:.2f} seconds")

        return MultiStageAnalysisResult(
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            letter_structure=letter_structure,
            verified_statutes=verified_statutes,
            processing_time_seconds=total_time,
            stage_timings=self.stage_timings,
        )

    async def _extract_fact_matrix(
        self,
        intake_content: str,
        document_summaries: List[DocumentSummaryStructured],
    ) -> FactMatrix:
        """Stage 1: Extract structured facts from documents.

        Uses high-precision AI call (temp=0.1) to build factual foundation.
        """
        # Prepare document summaries for context
        docs_context = []
        for doc in document_summaries:
            doc_dict = doc.model_dump()
            docs_context.append(
                {
                    "filename": doc_dict.get("source_document", "Unknown"),
                    "content_summary": doc_dict.get("key_content", ""),
                    "parties": doc_dict.get("parties_mentioned", []),
                    "dates": doc_dict.get("dates_mentioned", []),
                    "amounts": doc_dict.get("key_amounts", []),
                }
            )

        prompt = f"""You are a precise legal fact extractor. Extract ONLY factual information from the case materials. Do NOT perform legal analysis.

INTAKE INFORMATION:
{intake_content[:3000]}

DOCUMENT SUMMARIES:
{json.dumps(docs_context, indent=2)}

Extract and structure the following facts:

1. **PARTIES**: Identify all parties mentioned
   - Name (exact spelling)
   - Role (Client, Opposing Party, Contractor, Landlord, Tenant, Subcontractor, etc.)
   - First mentioned in which document

2. **TIMELINE**: Chronological events with dates
   - Date (be as specific as possible)
   - Description of event
   - Source document
   - Significance (why this event matters)

3. **FINANCIAL DATA**: All monetary amounts
   - Amount (exact number)
   - Description (what this money represents)
   - Date if applicable
   - Source document
   - Type (paid, owed, claimed, estimated)

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
      "first_mentioned_in": "string or null"
    }}
  ],
  "timeline": [
    {{
      "date": "YYYY-MM-DD or Month YYYY",
      "description": "string",
      "source_document": "string",
      "significance": "string or null"
    }}
  ],
  "financial_data": [
    {{
      "amount": number,
      "description": "string",
      "date": "string or null",
      "source_document": "string",
      "payment_type": "paid | owed | claimed | estimated"
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
- If unsure about a detail, note it in extraction_notes
- Return ONLY valid JSON, no markdown formatting
"""

        response_dict = self.client.create_chat_completion(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise legal fact extractor. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.1,  # High precision for facts
        )

        # Parse JSON response
        raw_response = response_dict["content"].strip()
        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        fact_data = json.loads(raw_response)

        # Convert to FactMatrix model
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

    async def _map_legal_issues(
        self,
        fact_matrix: FactMatrix,
        intake_content: str,
        case_type: Optional[str] = None,
        legal_issues_hint: Optional[List[str]] = None,
    ) -> LegalIssueMap:
        """Stage 2: Map all applicable legal issues and statutes.

        Uses moderate-precision AI call (temp=0.2) for classification.
        """
        prompt = f"""You are a Florida legal issue analyst. Based on the facts extracted, identify ALL applicable legal issues and statutes.

CASE TYPE: {case_type or "Unknown"}
PRELIMINARY ISSUES: {', '.join(legal_issues_hint or fact_matrix.preliminary_issues)}

FACTS:
- Parties: {len(fact_matrix.parties)} identified
- Timeline: {len(fact_matrix.timeline)} events
- Financial: {len(fact_matrix.financial_data)} items

INTAKE SUMMARY:
{intake_content[:1500]}

DETAILED FACTS:
{json.dumps(fact_matrix.model_dump(), indent=2, default=str)[:3000]}

Identify and classify all legal issues. Return JSON:

{{
  "primary_issues": [
    {{
      "issue_name": "Descriptive name (e.g., Implied Warranty Breach)",
      "category": "contract | tort | statutory | procedural",
      "elements": ["Element 1", "Element 2", "..."],
      "potential_remedies": ["Remedy 1", "Remedy 2"],
      "florida_statute_references": ["§83.51", "Chapter 558", "..."],
      "confidence": "strong | moderate | weak"
    }}
  ],
  "secondary_issues": [...same structure...],
  "relevant_statutes": ["§83.51", "Chapter 558", "§713.02", "..."],
  "procedural_requirements": [
    {{
      "requirement": "Description",
      "deadline": "Time limit or null",
      "statute_basis": "Florida Statute reference or null",
      "consequences_if_missed": "What happens"
    }}
  ],
  "case_complexity": "simple | moderate | complex",
  "complexity_reasoning": "Why this complexity level"
}}

COMPLEXITY CRITERIA:
- simple: 1-2 straightforward issues, no complex procedures
- moderate: 2-3 issues, some procedural requirements
- complex: 3+ issues, complex procedures, multiple parties

Return ONLY valid JSON.
"""

        response_dict = self.client.create_chat_completion(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a Florida legal issue analyst. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=3000,
            temperature=0.2,  # Balanced for classification
        )

        # Parse JSON response
        raw_response = response_dict["content"].strip()
        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        issue_data = json.loads(raw_response)

        return LegalIssueMap(
            primary_issues=[LegalIssue(**i) for i in issue_data.get("primary_issues", [])],
            secondary_issues=[LegalIssue(**i) for i in issue_data.get("secondary_issues", [])],
            relevant_statutes=issue_data.get("relevant_statutes", []),
            procedural_requirements=[
                ProceduralStep(**p) for p in issue_data.get("procedural_requirements", [])
            ],
            case_complexity=issue_data.get("case_complexity", "moderate"),
            complexity_reasoning=issue_data.get("complexity_reasoning"),
        )

    async def _perform_deep_analysis(
        self,
        fact_matrix: FactMatrix,
        issue_map: LegalIssueMap,
        verified_statutes: List[dict],
        document_summaries: List[DocumentSummaryStructured],
    ) -> DeepAnalysis:
        """Stage 3: Comprehensive analysis of each identified issue.

        Uses balanced AI call (temp=0.3) for legal reasoning.
        """
        # Format verified statutes for context
        statute_context = ""
        if verified_statutes:
            statute_context = "\n\nVERIFIED FLORIDA STATUTES:\n"
            for statute in verified_statutes:
                statute_context += f"\n{statute['citation']}: {statute['title']}\n"
                statute_context += f"Summary: {statute['summary']}\n"
                statute_context += f"Relevance: {statute['relevance']}\n"

        prompt = f"""You are a senior Florida attorney performing comprehensive legal analysis.

FACTS:
{json.dumps(fact_matrix.model_dump(), indent=2, default=str)}

IDENTIFIED LEGAL ISSUES:
{json.dumps([i.model_dump() for i in issue_map.primary_issues], indent=2)}

{statute_context}

For EACH primary issue, provide detailed analysis. Return JSON:

{{
  "issue_analyses": [
    {{
      "issue_name": "string (match issue from input)",
      "legal_standard": "Plain English explanation of the law",
      "fact_application": "How the facts meet or don't meet this standard - BE SPECIFIC with dates/amounts/citations",
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
  "key_challenges": ["Challenge 1", "Challenge 2"]
}}

CRITICAL INSTRUCTIONS:
- Use VERIFIED STATUTES PREFERENTIALLY - cite them confidently
- For unverified statutes, use cautious language: "Under Florida law..." without specific citation
- Integrate procedural requirements WITHIN substantive analysis
- Be specific with facts - use actual dates, amounts, names from fact matrix
- Explain consequences with real-world impact

Return ONLY valid JSON.
"""

        response_dict = self.client.create_chat_completion(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior Florida attorney with 20+ years experience. "
                        "Provide comprehensive, well-reasoned analysis."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=6000,
            temperature=0.3,  # Balanced for legal reasoning
        )

        # Parse JSON response
        raw_response = response_dict["content"].strip()
        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        analysis_data = json.loads(raw_response)

        return DeepAnalysis(
            issue_analyses=[IssueAnalysis(**a) for a in analysis_data.get("issue_analyses", [])],
            risk_assessment=RiskAssessment(**analysis_data.get("risk_assessment", {})),
            deadline_tracking=[CriticalDeadline(**d) for d in analysis_data.get("deadline_tracking", [])],
            evidence_strength=EvidenceAssessment(**analysis_data.get("evidence_strength", {})),
            overall_case_strength=analysis_data.get("overall_case_strength", "moderate"),
            key_strengths=analysis_data.get("key_strengths", []),
            key_challenges=analysis_data.get("key_challenges", []),
        )

    def _determine_letter_structure(
        self,
        issue_map: LegalIssueMap,
        analysis: DeepAnalysis,
    ) -> LetterStructure:
        """Stage 4: Decide optimal letter structure based on complexity.

        Logic-based determination (no AI call needed).
        """
        num_primary_issues = len(issue_map.primary_issues)
        has_complex_procedures = any(
            issue_analysis.procedural_requirements
            for issue_analysis in analysis.issue_analyses
            if issue_analysis.procedural_requirements
        )

        # Decision logic based on attorney examples
        if num_primary_issues <= 2 and not has_complex_procedures:
            # Simple cases: Use bullet list format (Miguel Velasco, Balaji Badam style)
            return LetterStructure(
                style="simple_bullets",
                intro="Here are the key points of our analysis:",
                issue_format="bullet_paragraphs",
                reasoning=f"Simple case with {num_primary_issues} issue(s), no complex procedures",
            )
        elif num_primary_issues >= 3 or has_complex_procedures:
            # Complex cases: Use numbered findings format (Christopher Eastman style)
            return LetterStructure(
                style="numbered_findings",
                intro="Key Findings",
                issue_format="numbered_sections_with_headers",
                reasoning=(
                    f"Complex case with {num_primary_issues} issues and "
                    f"{'complex procedural requirements' if has_complex_procedures else 'multiple legal theories'}"
                ),
            )
        else:
            # Hybrid approach for edge cases
            return LetterStructure(
                style="hybrid",
                intro="Here are the key points of our analysis:",
                issue_format="bullets_with_subheadings",
                reasoning=f"Moderate complexity with {num_primary_issues} issues",
            )
