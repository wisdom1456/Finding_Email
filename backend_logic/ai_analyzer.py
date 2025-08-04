import json
import asyncio
from typing import Dict, Any, List, Union
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from openai import RateLimitError, APIError, APITimeoutError, OpenAI
from pydantic import ValidationError
from backend.utils.data_models import (
    EnhancedIntakeAnalysis,
    AnalyzedDocument,
    LegalAssessment,
    DemandLetterEvaluation,
    ProcessedDocument,
    CaseAnalysisResult,
    AnalysisError,
    AIAnalysisError,
)
from .document_processor import DocumentProcessor
from backend.utils.validators import (
    preprocess_ai_output,
    safe_model_validate,
    create_fallback_legal_assessment,
    create_fallback_demand_letter_evaluation
)


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
            raw_response_content = "N/A"
            if 'response' in locals() and hasattr(response, 'choices') and response.choices:
                raw_response_content = response.choices[0].message.content
            print(f"AI ANALYZER: Raw response: {raw_response_content}")
            raise AIAnalysisError(f"Failed to parse AI response as JSON: {e}")
        except (RateLimitError, APIError, APITimeoutError) as e:
            print(f"AI ANALYZER: OpenAI API Error: {e}. Retrying...")
            raise
        except Exception as e:
            print(f"AI ANALYZER: An unexpected error occurred: {type(e).__name__} - {e}")
            raise AIAnalysisError(f"Error communicating with OpenAI API: {e}")

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
            f"{content}\n"
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
        client_priorities_str = ", ".join(ctx.client_priorities) if ctx.client_priorities else "None specified"
        desired_outcomes_str = ", ".join(ctx.desired_outcomes) if ctx.desired_outcomes else "None specified"
        
        return (
            "SYSTEM\n"
            "You are a senior litigation attorney with over 15 years of experience specializing in tenant and property disputes. Your analysis must be sharp, strategic, and framed in professional, legally appropriate language.\n"
            "Return **one—and only one—valid JSON object** that matches the\n"
            "`AnalyzedDocument` schema below.\n\n"
            "• JSON only—no markdown, no extra text.\n"
            "• Preserve key order.\n"
            "• PRIORITIZE analysis elements that directly relate to client's stated priorities and desired outcomes.\n\n"
            "==========================\n"
            "DOCUMENT (read-only)\n"
            f"Filename: {doc.file_name}\n"
            f"Content: {doc.content}\n"
            "==========================\n"
            "CLIENT PRIORITIES FOR THIS ANALYSIS:\n"
            f"• Priorities: {client_priorities_str}\n"
            f"• Desired Outcomes: {desired_outcomes_str}\n"
            f"• Case Type: {ctx.case_type or 'Not specified'}\n"
            f"• Urgency Level: {ctx.urgency_level or 'Not specified'}\n"
            "==========================\n"
            "FULL INTAKE CONTEXT\n"
            f"{ctx.model_dump_json(indent=2)}\n"
            "==========================\n\n"
            "SCHEMA — AnalyzedDocument\n"
            "{\n"
            '  "filename": "The original filename of the document.",\n'
            '  "document_type": "The type of document (e.g., \'Contract\', \'Email\', \'Image\').",\n'
            '  "inferred_title": "A meaningful, non-repetitive title for the document (less than 15 words).",\n'
            '  "summary": "A concise, value-driven summary of the document\'s content (100-150 words).",\n'
            '  "key_information": "A single consolidated string containing the most critical information. Format as a paragraph, NOT a list. If multiple points exist, separate them with semicolons within the string.",\n'
            '  "relevance_to_case": "A clear explanation of how this document supports or undermines the client\'s position, referencing specific case priorities."\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1.  `filename`: Must be the exact filename provided.\n"
            "2.  `inferred_title`: Create a meaningful and non-repetitive title. Do not just repeat the filename.\n"
            "3.  `summary`: Must be concise and value-driven, focusing on the most important aspects of the document.\n"
            "4.  `key_information`: Extract the most critical information as a bulleted list string.\n"
            "5.  `relevance_to_case`: Clearly articulate the document's relevance to the overall case strategy and client goals.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• All strings double-quoted.\n\n"
            "BEGIN."
        )

    def _build_final_assessment_prompt(self, analysis: CaseAnalysisResult) -> str:
        """Builds the prompt for the final legal assessment."""
        return (
            "SYSTEM\n"
            "You are a senior litigation attorney with over 15 years of experience specializing in tenant and property disputes. Your analysis must be sharp, strategic, and framed in professional, legally appropriate language. Output a single JSON object with exactly two top-level keys: `\"legal_assessment\"` and `\"demand_letter_evaluation\"`—nothing else.\n\n"
            "• JSON only—no markdown, no commentary.\n"
            "• Do not alter key names.\n\n"
            "==========================\n"
            "COMBINED ANALYSIS (read-only)\n"
            f"{analysis.model_dump_json(indent=2)}\n"
            "==========================\n\n"
            "SCHEMAS\n"
            "LegalAssessment:\n"
            "{\n"
            '  "case_type": "Case Type",\n'
            '  "claim_viability": "Claim Viability",\n'
            '  "overall_evidence_strength": "Strength",\n'
            '  "potential_challenges": "A narrative paragraph describing potential challenges. NO BULLET POINTS.",\n'
            '  "recommended_actions": "A narrative paragraph detailing recommended next steps. NO BULLET POINTS.",\n'
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
            "1.  **`potential_challenges` and `recommended_actions` must be full, narrative paragraphs.** Do not use bullet points or lists.\n"
            "2.  The tone must be authoritative and advisory, consistent with a senior attorney persona.\n"
            '3.  `claim_viability`: pick “Strong”, “Moderate”, or “Weak”.\n'
            "4.  `demand_letter_appropriate`: true if pre-suit demand adds leverage.\n"
            '5.  If `demand_letter_evaluation.is_appropriate` is **false**, set\n'
            '    `"reasoning": ""`, `"potential_outcomes": []`, `"relevant_statutes": []`.\n\n'
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• Floats with two decimals.\n"
            "• Key order per schema.\n\n"
            "BEGIN."
        )
    async def analyze_intake(self, intake_doc: ProcessedDocument) -> CaseAnalysisResult:
        """Analyzes a processed intake form and returns an initial CaseAnalysisResult object."""
        analysis = CaseAnalysisResult()
        if not intake_doc or not intake_doc.content:
            analysis.errors.append(AnalysisError(source="IntakeProcessing", error_message="No valid intake content to analyze."))
            return analysis

        try:
            prompt = self._build_intake_prompt(intake_doc.content)
            raw_analysis = await self._make_openai_request(prompt, model="gpt-4o-mini")
            processed_analysis = preprocess_ai_output(raw_analysis)
            analysis.intake_analysis = EnhancedIntakeAnalysis.model_validate(processed_analysis)

        except (AIAnalysisError, ValidationError) as e:
            details = str(e) if isinstance(e, AIAnalysisError) else e.errors()
            analysis.errors.append(AnalysisError(source="IntakeAnalysis", error_message=f"Failed to validate AI response for intake: {e}", details=details))
        
        return analysis

    async def analyze_case_documents(self, documents: List[ProcessedDocument], intake_context: EnhancedIntakeAnalysis) -> List[Union[AnalyzedDocument, AnalysisError]]:
        """Analyzes multiple case documents sequentially to avoid rate limiting."""
        results = []
        total_docs = len(documents)
        
        print(f"AI ANALYZER: Starting analysis of {total_docs} documents...")
        
        for i, doc in enumerate(documents, 1):
            print(f"AI ANALYZER: Processing document {i}/{total_docs}: {doc.file_name}")
            result = await self._analyze_single_document(doc, intake_context)
            results.append(result)
            
            # Log the result type
            if isinstance(result, AnalysisError):
                print(f"AI ANALYZER: ❌ Failed to analyze {doc.file_name}: {result.error_message}")
            else:
                print(f"AI ANALYZER: ✅ Successfully analyzed {doc.file_name}")
            
            # Add delay between requests to respect rate limits
            if i < total_docs:  # Don't delay after the last document
                print(f"AI ANALYZER: Waiting 3 seconds before next document...")
                await asyncio.sleep(3)
        
        print(f"AI ANALYZER: Completed analysis of all {total_docs} documents")
        return results

    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of tokens (approximately 4 characters per token)."""
        return len(text) // 4
    
    def _truncate_content_if_needed(self, content: str, max_tokens: int = 25000) -> str:
        """Truncate content if it exceeds token limit."""
        estimated_tokens = self._estimate_tokens(content)
        if estimated_tokens > max_tokens:
            # Keep first 80% and last 20% of content
            chars_to_keep = max_tokens * 4
            first_part_chars = int(chars_to_keep * 0.8)
            last_part_chars = int(chars_to_keep * 0.2)
            
            first_part = content[:first_part_chars]
            last_part = content[-last_part_chars:]
            
            truncated_content = f"{first_part}\n\n[... CONTENT TRUNCATED FOR SIZE ...]\n\n{last_part}"
            print(f"AI ANALYZER: ⚠️  Content truncated from ~{estimated_tokens} to ~{max_tokens} tokens")
            return truncated_content
        return content

    async def _analyze_single_document(self, document: ProcessedDocument, intake_context: EnhancedIntakeAnalysis) -> Union[AnalyzedDocument, AnalysisError]:
        """Analyzes a single case document, returning structured data or an error."""
        try:
            # Check document size and truncate if necessary
            truncated_content = self._truncate_content_if_needed(document.content)
            
            # Create a copy of the document with truncated content
            doc_for_analysis = ProcessedDocument(
                file_name=document.file_name,
                content=truncated_content,
                file_type=document.file_type,
                document_type=document.document_type
            )
            
            prompt = self._build_case_document_prompt(doc_for_analysis, intake_context)
            
            # Estimate total prompt size and choose appropriate model
            total_estimated_tokens = self._estimate_tokens(prompt)
            model_to_use = "gpt-4o-mini" if total_estimated_tokens > 20000 else "gpt-4o"
            
            if model_to_use == "gpt-4o-mini":
                print(f"AI ANALYZER: 🔄 Using gpt-4o-mini for large document: {document.file_name}")
            
            raw_analysis = await self._make_openai_request(prompt, model=model_to_use)
            return AnalyzedDocument.model_validate(raw_analysis)
        except (AIAnalysisError, ValidationError) as e:
            return AnalysisError(
                source=f"doc:{document.file_name}",
                error_message=f"Failed to analyze document: {e}",
                details=str(e)
            )

    async def perform_final_assessment(self, analysis: CaseAnalysisResult) -> CaseAnalysisResult:
        """Performs the final legal assessment and demand letter evaluation with graceful degradation."""
        if not analysis.intake_analysis or not analysis.analyzed_documents:
            error_msg = "Cannot perform final assessment without both intake and case document analyses."
            analysis.errors.append(
                AnalysisError(
                    source="FinalAssessment",
                    error_message=error_msg,
                    details="Missing required analysis inputs."
                )
            )
            
            print(f"AI ANALYZER: {error_msg} Providing fallback assessments...")
            analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())
            return analysis

        try:
            print("AI ANALYZER: Starting final legal assessment...")
            prompt = self._build_final_assessment_prompt(analysis)
            raw_assessment = await self._make_openai_request(prompt, model="gpt-4o")
            
            if not raw_assessment:
                raise ValueError("No response received from OpenAI API")
            
            print(f"AI ANALYZER: Raw assessment keys: {list(raw_assessment.keys()) if isinstance(raw_assessment, dict) else 'Not a dict'}")
            
            # Process legal assessment with graceful degradation
            if "legal_assessment" in raw_assessment:
                print("AI ANALYZER: Processing legal assessment...")
                legal_assessment_data = raw_assessment["legal_assessment"]
                
                # Use safe validation with fallback
                validated_assessment = safe_model_validate(
                    LegalAssessment,
                    legal_assessment_data,
                    create_fallback_legal_assessment
                )
                
                if validated_assessment:
                    analysis.legal_assessment = validated_assessment
                    print("AI ANALYZER: ✅ Legal assessment validated successfully")
                else:
                    print("AI ANALYZER: ⚠️  Legal assessment validation failed, using fallback")
                    analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
                    analysis.errors.append(AnalysisError(
                        source="FinalAssessment",
                        error_message="Legal assessment validation failed, using fallback data",
                        details=str(legal_assessment_data)
                    ))
            else:
                print("AI ANALYZER: ⚠️  No legal_assessment in response, using fallback")
                analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
                analysis.errors.append(AnalysisError(
                    source="FinalAssessment",
                    error_message="legal_assessment not found in AI response",
                    details=str(raw_assessment)
                ))
            
            # Process demand letter evaluation with graceful degradation
            if "demand_letter_evaluation" in raw_assessment:
                print("AI ANALYZER: Processing demand letter evaluation...")
                demand_eval_data = raw_assessment["demand_letter_evaluation"]
                
                # Use safe validation with fallback
                validated_evaluation = safe_model_validate(
                    DemandLetterEvaluation,
                    demand_eval_data,
                    create_fallback_demand_letter_evaluation
                )
                
                if validated_evaluation:
                    analysis.demand_letter_evaluation = validated_evaluation
                    print("AI ANALYZER: ✅ Demand letter evaluation validated successfully")
                else:
                    print("AI ANALYZER: ⚠️  Demand letter evaluation validation failed, using fallback")
                    analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())
                    analysis.errors.append(AnalysisError(
                        source="FinalAssessment",
                        error_message="Demand letter evaluation validation failed, using fallback data",
                        details=str(demand_eval_data)
                    ))
            else:
                print("AI ANALYZER: ⚠️  No demand_letter_evaluation in response, using fallback")
                analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())
                analysis.errors.append(AnalysisError(
                    source="FinalAssessment",
                    error_message="demand_letter_evaluation not found in AI response",
                    details=str(raw_assessment)
                ))
                
        except (AIAnalysisError, ValidationError, ValueError) as e:
            error_msg = f"Final assessment failed: {e}"
            print(f"AI ANALYZER: ❌ {error_msg}")
            analysis.errors.append(AnalysisError(
                source="FinalAssessment",
                error_message=error_msg,
                details=str(e)
            ))
            
            # Always provide fallback assessments to ensure system continues working
            print("AI ANALYZER: Providing fallback assessments due to error...")
            if not analysis.legal_assessment:
                analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
            if not analysis.demand_letter_evaluation:
                analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())
        
        except Exception as e:
            error_msg = f"Unexpected error in final assessment: {e}"
            print(f"AI ANALYZER: ❌ {error_msg}")
            analysis.errors.append(AnalysisError(
                source="FinalAssessment",
                error_message=error_msg,
                details=str(e)
            ))
            
            # Emergency fallback to ensure system keeps working
            print("AI ANALYZER: Emergency fallback due to unexpected error...")
            analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())
            
        print("AI ANALYZER: Final assessment completed")
        return analysis
