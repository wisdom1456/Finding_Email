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
    PropertyInfo,
    RiskAssessment,
)
from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.diagnostic_logger import DiagnosticLogger

logger = get_module_logger(__name__)


class MultiStageAnalyzer:
    """Orchestrates 4-stage analysis pipeline for comprehensive case evaluation."""

    def __init__(
        self,
        openai_client: OpenAIClient,
        statute_service: Optional[StatuteRecommendationService] = None,
    ):
        """Initialize the multi-stage analyzer."""
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
        jurisdiction: str = "Florida",
        diag_logger: Optional[DiagnosticLogger] = None,
    ) -> MultiStageAnalysisResult:
        """Execute 4-stage analysis pipeline."""
        start_time = time.time()
        logger.info(f"Starting multi-stage analysis pipeline for {jurisdiction}")

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
                stage={"id": "fact_matrix", "name": "Extracting Facts", "status": "active", "progress": 30}
            )

        stage_start = time.time()
        # Optimization: Pass limited context to fact matrix extraction to avoid timeouts
        fact_matrix = await self._extract_fact_matrix(intake_content, document_summaries, jurisdiction)
        self.stage_timings["fact_extraction"] = time.time() - stage_start
        
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
            
        logger.info(
            f"Stage 1 complete ({self.stage_timings['fact_extraction']:.1f}s): "
            f"{len(fact_matrix.parties)} parties, "
            f"{len(fact_matrix.timeline)} events"
        )

        # Stage 2: Map Legal Issues
        if progress_callback:
            await progress_callback(
                "Mapping legal issues and statutes...", 
                [], 
                "issue_mapping", 
                40,
                stage={"id": "issue_mapping", "name": "Legal Issues", "status": "active", "progress": 20}
            )

        stage_start = time.time()
        issue_map = await self._map_legal_issues(
            fact_matrix, intake_content, case_type, legal_issues, jurisdiction
        )
        self.stage_timings["issue_mapping"] = time.time() - stage_start
        
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
            
        logger.info(
            f"Stage 2 complete ({self.stage_timings['issue_mapping']:.1f}s): "
            f"{len(issue_map.primary_issues)} primary issues"
        )

        # Stage 3: Deep Legal Analysis
        if progress_callback:
            await progress_callback(
                "Performing deep legal analysis...", 
                [], 
                "deep_analysis", 
                70,
                stage={"id": "deep_analysis", "name": "Deep Analysis", "status": "active", "progress": 10}
            )

        stage_start = time.time()
        deep_analysis = await self._perform_deep_legal_analysis(
            fact_matrix, issue_map, intake_content, jurisdiction
        )
        self.stage_timings["deep_analysis"] = time.time() - stage_start
        
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
            
        logger.info(
            f"Stage 3 complete ({self.stage_timings['deep_analysis']:.1f}s): "
            f"{len(deep_analysis.issue_analyses)} issues analyzed"
        )

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
        letter_structure = self._determine_letter_structure(issue_map, deep_analysis)
        self.stage_timings["structure_determination"] = time.time() - stage_start
        
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
        verified_statutes = self.statute_service.recommend_statutes(
            case_facts=intake_content[:2000],
            legal_issues=[i.issue_name for i in issue_map.primary_issues],
            case_type=case_type,
            limit=10,
        )

        total_time = time.time() - start_time
        logger.info(f"Multi-stage analysis pipeline complete in {total_time:.2f}s")

        # Derive opposing parties
        opposing_parties = self._identify_opposing_parties(fact_matrix)

        return MultiStageAnalysisResult(
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            letter_structure=letter_structure,
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
            doc_dict = doc.model_dump()
            # Optimization: Limit content summary length to save tokens and avoid timeouts
            # Stage 1 only needs high-level facts to build the matrix
            summary = doc_dict.get("key_content", "")
            if len(summary) > 2500:
                summary = summary[:2500] + "... [truncated for brevity]"

            docs_context.append(
                {
                    "filename": doc_dict.get("source_document", "Unknown"),
                    "content_summary": summary,
                    "parties": doc_dict.get("parties_mentioned", []),
                    "dates": doc_dict.get("dates_mentioned", []),
                    "amounts": doc_dict.get("key_amounts", []),
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

        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-4o")
        response_dict = self.client.create_chat_completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a precise legal fact extractor for {jurisdiction} law. "
                        "Return only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.1,
        )

        raw_response = response_dict["content"].strip()
        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        fact_data = json.loads(raw_response)

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

        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-4o")
        response_dict = self.client.create_chat_completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are an expert {jurisdiction} legal analyst. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=3000,
            temperature=0.2,
        )

        raw_response = response_dict["content"].strip()
        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1])

        issue_data = json.loads(raw_response)

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
- The facts do not support any recognized legal claim under {jurisdiction} law
- The statute of limitations has clearly expired
- The client's own conduct bars recovery
- There is insufficient evidence to prove essential elements
- The opposing party has clear, unassailable defenses

CRITICAL INSTRUCTIONS:
- Use VERIFIED STATUTES PREFERENTIALLY
- For unverified statutes, use cautious language: "Under {jurisdiction} law..."
- Be specific with facts - use actual dates, amounts, names from fact matrix
- Be HONEST about case viability - do not give false hope.

Return ONLY valid JSON.
"""

        model = self.client.get_preferred_model("multi_stage_analysis", "gpt-4o")
        response_dict = self.client.create_chat_completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a senior {jurisdiction} attorney with 20+ years experience. "
                        "Provide comprehensive analysis."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=6000,
            temperature=0.3,
        )

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
