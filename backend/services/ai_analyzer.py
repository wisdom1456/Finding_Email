import json
import asyncio
from typing import Dict, Any, List, Union
from fastapi import UploadFile, HTTPException
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from openai import RateLimitError, APIError, APITimeoutError, OpenAI
from pydantic import ValidationError
from backend.utils.data_models import (
    EnhancedIntakeAnalysis,
    EnhancedCaseAnalysis,
    LegalAssessment,
    DemandLetterEvaluation,
    ProcessedDocument,
    CombinedAnalysis,
    AnalysisError,
)
from backend.services.document_processor import DocumentProcessor
from backend.utils.validators import preprocess_ai_output


class AIAnalyzer:
    """Handles all interactions with the OpenAI API for document analysis."""

    def __init__(self, client: OpenAI, doc_processor: DocumentProcessor):
        self.client = client
        self.doc_processor = doc_processor

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type((RateLimitError, APIError, APITimeoutError)),
    )
    async def _make_openai_request(self, prompt: str, model: str) -> Dict[str, Any]:
        """Makes a request to the OpenAI API with robust retry logic."""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as e:
            print(f"AI ANALYZER: Failed to parse AI response as JSON: {e}")
            print(f"AI ANALYZER: Raw response: {response.choices[0].message.content}")
            raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON: {e}")
        except (RateLimitError, APIError, APITimeoutError) as e:
            print(f"AI ANALYZER: OpenAI API Error: {e}. Retrying...")
            raise
        except Exception as e:
            print(f"AI ANALYZER: An unexpected error occurred: {type(e).__name__} - {e}")
            raise HTTPException(status_code=500, detail="Error communicating with OpenAI API.")

    def _build_intake_prompt(self, content: str) -> str:
        """Builds the prompt for analyzing an intake form."""
        return (
            "SYSTEM\n"
            "You are a senior litigation attorney performing intake triage.\n"
            "Return **one—and only one—valid JSON object** that matches the\n"
            "`EnhancedIntakeAnalysis` schema below.\n\n"
            "• Do **NOT** wrap the JSON in markdown fences.\n"
            "• Do **NOT** change key names, add keys, or emit commentary.\n\n"
            "==========================\n"
            "SOURCE INTAKE FORM (read-only)\n"
            f"{{content}}\n"
            "==========================\n\n"
            "SCHEMA — EnhancedIntakeAnalysis\n"
            "{\n"
            '  "client_name": "Client Name",\n'
            '  "attorney_name": "Attorney Name",\n'
            '  "case_summary": "Case summary.",\n'
            '  "case_type": "Case Type",\n'
            '  "urgency_level": "Urgency",\n'
            '  "client_priorities": ["Priority 1"],\n'
            '  "desired_outcomes": ["Outcome 1"],\n'
            '  "key_facts": ["Fact 1"],\n'
            '  "parties_involved": [{"name": "Name", "role": "Role"}],\n'
            '  "financial_impact": "Financial impact summary.",\n'
            '  "legal_claims": ["Claim 1"]\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1. Capture every field—even if absent in the form.\n"
            "   • If data is missing, output an empty string `\"\"` or empty list `[]`.\n"
            "2. `case_summary`: 120–200 words, neutral tone.\n"
            "3. `key_facts`: bullet-style strings ≤25 words each.\n"
            "4. `parties_involved`: each object **must** have `\"name\"` and `\"role\"` (e.g., Plaintiff, Contractor).\n"
            "5. Keep every other string ≤40 words.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• All strings double-quoted.\n"
            "• Key order exactly as in schema.\n\n"
            "BEGIN."
        )

    def _build_case_document_prompt(self, doc: ProcessedDocument, ctx: EnhancedIntakeAnalysis) -> str:
        """Builds a context-aware prompt for a case document."""
        return (
            "SYSTEM\n"
            "You are a litigation associate assessing a single case document.\n"
            "Return **one—and only one—valid JSON object** that matches the\n"
            "`EnhancedCaseAnalysis` schema below.\n\n"
            "• JSON only—no markdown, no extra text.\n"
            "• Preserve key order.\n\n"
            "==========================\n"
            "DOCUMENT (read-only)\n"
            f"{{doc.content}}\n"
            "==========================\n"
            "INTAKE CONTEXT\n"
            f"{{ctx.model_dump_json(indent=2)}}\n"
            "==========================\n\n"
            "SCHEMA — EnhancedCaseAnalysis\n"
            "{\n"
            '  "document_title": "Document Title",\n'
            '  "document_type": "Document Type",\n'
            '  "key_entities": [{"name": "Name", "role": "Role"}],\n'
            '  "summary": "Document summary.",\n'
            '  "timeline_events": [{"date": "Date", "event": "Event"}],\n'
            '  "evidence_strength": "Strength",\n'
            '  "legal_significance": "Legal significance.",\n'
            '  "relevance_to_intake": "Relevance to intake.",\n'
            '  "potential_challenges": ["Challenge 1"]\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1. `document_title`: use true title; if none, craft a concise (<10 words) title.\n"
            "2. `summary`: 100–150 words, objective.\n"
            "3. `timeline_events`: chronological; date as `YYYY-MM-DD` or `\"Unknown\"`.\n"
            "4. `evidence_strength`: choose “Strong”, “Moderate”, or “Weak”.\n"
            "5. `potential_challenges`: short phrases (≤8 words) describing foreseeable hurdles.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• All strings double-quoted.\n\n"
            "BEGIN."
        )

    def _build_final_assessment_prompt(self, analysis: CombinedAnalysis) -> str:
        """Builds the prompt for the final legal assessment."""
        return (
            "SYSTEM\n"
            "You are senior counsel delivering the final legal assessment.\n"
            "Output a single JSON object with exactly two top-level keys:\n"
            '`"legal_assessment"` and `"demand_letter_evaluation"`—nothing else.\n\n'
            "• JSON only—no markdown, no commentary.\n"
            "• Do not alter key names.\n\n"
            "==========================\n"
            "COMBINED ANALYSIS (read-only)\n"
            f"{{analysis.model_dump_json(indent=2)}}\n"
            "==========================\n\n"
            "SCHEMAS\n"
            "LegalAssessment:\n"
            "{\n"
            '  "case_type": "Case Type",\n'
            '  "claim_viability": "Claim Viability",\n'
            '  "overall_evidence_strength": "Strength",\n'
            '  "potential_challenges": [{\n'
            '    "category": "Challenge Category",\n'
            '    "description": "Description",\n'
            '    "mitigation_strategy": "Strategy",\n'
            '    "confidence_score": 0.00\n'
            "  }],\n"
            '  "recommended_actions": ["Action 1"],\n'
            '  "demand_letter_appropriate": true,\n'
            '  "urgency_assessment": "Urgency"\n'
            "}\n"
            "DemandLetterEvaluation:\n"
            "{\n"
            '  "is_appropriate": true,\n'
            '  "reasoning": "Reasoning",\n'
            '  "potential_outcomes": ["Outcome 1"],\n'
            '  "relevant_statutes": ["Statute 1"]\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            '1. `claim_viability`: pick “Strong”, “Moderate”, or “Weak”.\n'
            "2. For each `potential_challenges` item:\n"
            "   • `category` must be a string.\n"
            "   • Map risk to `confidence_score`—High → 0.85, Medium → 0.60, Low → 0.30.\n"
            "3. `recommended_actions`: imperative verb first, ≤20 words each.\n"
            "4. `demand_letter_appropriate`: true if pre-suit demand adds leverage.\n"
            '5. If `demand_letter_evaluation.is_appropriate` is **false**, set\n'
            '   `"reasoning": ""`, `"potential_outcomes": []`, `"relevant_statutes": []`.\n\n'
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• Floats with two decimals.\n"
            "• Key order per schema.\n\n"
            "BEGIN."
        )

    async def analyze_intake(self, intake_doc: ProcessedDocument) -> CombinedAnalysis:
        """Analyzes a processed intake form and returns an initial CombinedAnalysis object."""
        analysis = CombinedAnalysis()
        try:
            if not intake_doc or not intake_doc.content:
                analysis.errors.append(AnalysisError(source="IntakeProcessing", error_message="No valid intake content to analyze."))
                return analysis

            prompt = self._build_intake_prompt(intake_doc.content)
            raw_analysis = await self._make_openai_request(prompt, model="gpt-4o-mini")
            processed_analysis = preprocess_ai_output(raw_analysis)
            analysis.intake_analysis = EnhancedIntakeAnalysis.model_validate(processed_analysis)
            
        except (HTTPException, ValidationError) as e:
            details = e.detail if isinstance(e, HTTPException) else e.errors()
            analysis.errors.append(AnalysisError(source="IntakeAnalysis", error_message=str(e), details=details))
        return analysis

    async def analyze_case_documents(self, documents: List[ProcessedDocument], intake_context: EnhancedIntakeAnalysis) -> List[Union[EnhancedCaseAnalysis, AnalysisError]]:
        """Analyzes multiple case documents in parallel, returning either analysis or an error."""
        tasks = [self._analyze_single_document(doc, intake_context) for doc in documents]
        return await asyncio.gather(*tasks)

    async def _analyze_single_document(self, document: ProcessedDocument, intake_context: EnhancedIntakeAnalysis) -> Union[EnhancedCaseAnalysis, AnalysisError]:
        """Analyzes a single case document, returning structured data or an error."""
        try:
            prompt = self._build_case_document_prompt(document, intake_context)
            raw_analysis = await self._make_openai_request(prompt, model="gpt-4o")
            return EnhancedCaseAnalysis.model_validate(raw_analysis)
        except (HTTPException, ValidationError) as e:
            return AnalysisError(
                source=f"doc:{document.file_name}",
                error_message=f"Failed to analyze document: {e}",
                details=getattr(e, 'detail', None)
            )

    async def perform_final_assessment(self, analysis: CombinedAnalysis) -> CombinedAnalysis:
        """Performs the final legal assessment and demand letter evaluation."""
        if not analysis.intake_analysis or not analysis.case_analyses:
            analysis.errors.append(AnalysisError(source="FinalAssessment", error_message="Cannot perform final assessment without intake and case analyses."))
            return analysis

        try:
            prompt = self._build_final_assessment_prompt(analysis)
            raw_assessment = await self._make_openai_request(
                prompt, model="gpt-4o"
            )
            
            if "legal_assessment" in raw_assessment:
                analysis.legal_assessment = LegalAssessment.model_validate(
                    raw_assessment["legal_assessment"]
                )
            if "demand_letter_evaluation" in raw_assessment:
                analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(
                    raw_assessment["demand_letter_evaluation"]
                )
                
        except (HTTPException, ValidationError) as e:
            analysis.errors.append(AnalysisError(source="FinalAssessment", error_message=str(e), details=getattr(e, 'detail', None)))
            
        return analysis
