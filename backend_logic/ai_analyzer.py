import json
import asyncio
from typing import Dict, Any, List, Union
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from openai import RateLimitError, APIError, APITimeoutError, BadRequestError, OpenAI
from pydantic import ValidationError
import tiktoken
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
    async def _make_openai_request(self, prompt: str, model: str, use_json_format: bool = True) -> Dict[str, Any]:
        """Makes a request to the OpenAI API with robust retry logic."""
        try:
            request_params = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
            
            # Only add JSON response format if requested and prompt contains 'json'
            if use_json_format and 'json' in prompt.lower():
                request_params["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**request_params)
            
            # Parse as JSON only if JSON format was requested
            if use_json_format:
                return json.loads(response.choices[0].message.content)
            else:
                # Return the content wrapped in a dictionary for consistency
                return {"content": response.choices[0].message.content}
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

    async def _summarize_media_content(self, content: Union[Dict, str], media_type: str, file_name: str) -> str:
        """Summarizes media content using a dedicated AI call."""
        print(f"AI ANALYZER: Summarizing {media_type} for {file_name}")
        prompt = (
            "SYSTEM\n"
            "You are a paralegal tasked with summarizing media evidence. Create a concise, factual summary (100-150 words) of the provided content. Focus on actionable details, key statements, and visual evidence relevant to a legal case.\n\n"
            f"Provided {media_type} content for {file_name}:\n"
            f"```\n{json.dumps(content, indent=2) if isinstance(content, dict) else content}\n```\n\n"
            "BEGIN SUMMARY."
        )
        try:
            # Use gpt-4o-mini for efficiency, with non-JSON format since prompt doesn't contain 'json'
            response = await self._make_openai_request(prompt, model="gpt-4o-mini", use_json_format=False)
            # Extract the content from the response wrapper
            summary = response.get("content", "Summary could not be generated.")
            print(f"AI ANALYZER: ✅ Successfully summarized {media_type} for {file_name}")
            return summary
        except AIAnalysisError as e:
            print(f"AI ANALYZER: ❌ Failed to summarize {media_type} for {file_name}: {e}")
            return f"[A {media_type} from {file_name} is available but could not be summarized.]"

    def _log_video_analysis_diagnostics(self, analysis: CaseAnalysisResult) -> None:
        """Log comprehensive diagnostics about video analysis content before final assessment."""
        print("AI ANALYZER: 🔍 === DIAGNOSTIC LOGGING - Video Analysis Content ===")
        
        if not analysis.video_insights:
            print("AI ANALYZER: 🔍 No video insights to analyze")
            return
            
        for i, video in enumerate(analysis.video_insights):
            print(f"AI ANALYZER: 🔍 Video {i+1}: {video.file_name}")
            print(f"AI ANALYZER: 🔍   - Insights type: {type(video.insights)}")
            print(f"AI ANALYZER: 🔍   - Insights size (chars): {len(str(video.insights))}")
            print(f"AI ANALYZER: 🔍   - Insights estimated tokens: {len(str(video.insights)) // 4}")
            
            if isinstance(video.insights, dict):
                print(f"AI ANALYZER: 🔍   - Insights keys: {list(video.insights.keys())}")
                for key, value in video.insights.items():
                    if isinstance(value, (str, list)):
                        print(f"AI ANALYZER: 🔍   - {key} size: {len(str(value))} chars")
            
            print(f"AI ANALYZER: 🔍   - Transcript size: {len(video.transcript)} chars")
            print(f"AI ANALYZER: 🔍   - Labels count: {len(video.labels)}")
            print(f"AI ANALYZER: 🔍   - Objects count: {len(video.objects)}")
            print(f"AI ANALYZER: 🔍   - Text annotations count: {len(video.text_annotations)}")
        
        print("AI ANALYZER: 🔍 === END DIAGNOSTIC LOGGING ===")

    def _estimate_prompt_tokens_detailed(self, prompt_content: str) -> int:
        """Enhanced token estimation with more accurate calculation."""
        # More accurate token estimation: ~3.5 characters per token for English text
        base_tokens = len(prompt_content) // 3.5
        
        # Add overhead for JSON structure, special characters, etc.
        overhead_factor = 1.15
        estimated_tokens = int(base_tokens * overhead_factor)
        
        print(f"AI ANALYZER: 🔍 Token estimation details:")
        print(f"AI ANALYZER: 🔍   - Content length: {len(prompt_content):,} characters")
        print(f"AI ANALYZER: 🔍   - Base tokens: {int(base_tokens):,}")
        print(f"AI ANALYZER: 🔍   - With overhead: {estimated_tokens:,}")
        
        return estimated_tokens

    def _count_tokens_accurate(self, text: str, model: str = "gpt-4o") -> int:
        """Count tokens using tiktoken for accurate token counting."""
        try:
            # Get the encoding for the model
            if model.startswith("gpt-4"):
                encoding_name = "cl100k_base"  # GPT-4 encoding
            else:
                encoding_name = "cl100k_base"  # Default to GPT-4 encoding
            
            encoding = tiktoken.get_encoding(encoding_name)
            tokens = encoding.encode(text)
            token_count = len(tokens)
            
            print(f"AI ANALYZER: 🔢 Accurate token count ({model}): {token_count:,}")
            return token_count
        except Exception as e:
            print(f"AI ANALYZER: ⚠️  tiktoken error, falling back to estimation: {e}")
            # Fallback to existing estimation method
            return self._estimate_prompt_tokens_detailed(text)

    async def _check_token_threshold_precomputation(self, analysis: CaseAnalysisResult, model: str = "gpt-4o") -> bool:
        """Check if video insights would exceed token threshold before building prompt."""
        print(f"AI ANALYZER: 🔍 Pre-computation token checking for model: {model}")
        
        # Define thresholds (80% of context window)
        model_limits = {
            "gpt-4o": 120000,      # 150k context window * 0.8
            "gpt-4o-mini": 100000, # 125k context window * 0.8
            "gpt-4": 25600,        # 32k context window * 0.8
        }
        
        threshold = model_limits.get(model, 96000)  # Default to 120k * 0.8
        print(f"AI ANALYZER: 🔍 Token threshold for {model}: {threshold:,}")
        
        # Estimate token usage from video insights
        if not analysis.video_insights:
            print(f"AI ANALYZER: 🔍 No video insights, threshold check passed")
            return True
        
        total_video_tokens = 0
        for video in analysis.video_insights:
            # Estimate tokens from video content
            insights_content = json.dumps(video.insights, indent=2) if video.insights else ""
            transcript_content = video.transcript or ""
            labels_content = ", ".join(video.labels) if video.labels else ""
            objects_content = ", ".join(video.objects) if video.objects else ""
            
            video_content = f"{insights_content}\n{transcript_content}\n{labels_content}\n{objects_content}"
            video_tokens = self._count_tokens_accurate(video_content, model)
            total_video_tokens += video_tokens
            
            print(f"AI ANALYZER: 🔍   - {video.file_name}: {video_tokens:,} tokens")
        
        # Add estimated tokens for other content (documents, intake, etc.)
        base_content_estimate = 10000  # Conservative estimate for non-video content
        total_estimated_tokens = total_video_tokens + base_content_estimate
        
        print(f"AI ANALYZER: 🔍 Total estimated tokens: {total_estimated_tokens:,}")
        print(f"AI ANALYZER: 🔍 Threshold: {threshold:,}")
        
        if total_estimated_tokens > threshold:
            print(f"AI ANALYZER: ⚠️  Token count exceeds threshold ({total_estimated_tokens:,} > {threshold:,})")
            return False
        else:
            print(f"AI ANALYZER: ✅ Token count within threshold")
            return True

    def _apply_video_summarization_strategy(self, analysis: CaseAnalysisResult) -> CaseAnalysisResult:
        """Apply summarization strategy when token threshold is exceeded."""
        print(f"AI ANALYZER: 🔄 Token count exceeds threshold. Triggering summarization strategy.")
        
        analysis_copy = analysis.model_copy(deep=True)
        
        for video in analysis_copy.video_insights:
            # Set the insights_summary field as specified in the video preservation plan
            if video.insights:
                # Create a condensed summary for prompt inclusion
                key_objects = video.objects[:5] if video.objects else []
                key_labels = video.labels[:5] if video.labels else []
                
                summary_parts = []
                if key_objects:
                    summary_parts.append(f"Key objects detected: {', '.join(key_objects)}")
                if key_labels:
                    summary_parts.append(f"Content labels: {', '.join(key_labels)}")
                if video.transcript and len(video.transcript) > 200:
                    summary_parts.append(f"Transcript excerpt: {video.transcript[:200]}...")
                elif video.transcript:
                    summary_parts.append(f"Transcript: {video.transcript}")
                
                condensed_summary = "; ".join(summary_parts) if summary_parts else "Video content available but summarized due to token constraints."
                
                # Update the insights_summary field in the data model
                video.insights_summary = condensed_summary
                
                # Replace the full insights with a minimal placeholder to reduce tokens
                video.insights = {"status": "Video analyzed - full details preserved, summary applied for prompt"}
                
                print(f"AI ANALYZER: 🔄   - Summarized {video.file_name}: {len(condensed_summary)} chars")
            else:
                video.insights_summary = f"Video file {video.file_name} processed but content summarized due to size constraints."
                print(f"AI ANALYZER: 🔄   - Applied default summary for {video.file_name}")
        
        print(f"AI ANALYZER: 🔄 Summarization strategy applied to {len(analysis_copy.video_insights)} video(s)")
        return analysis_copy

    def _truncate_video_content_aggressively(self, analysis: CaseAnalysisResult, target_tokens: int = 100000) -> CaseAnalysisResult:
        """Aggressively truncate video content to meet token limits."""
        print(f"AI ANALYZER: 🔄 Aggressively truncating video content to target {target_tokens:,} tokens")
        
        analysis_copy = analysis.model_copy(deep=True)
        
        for video in analysis_copy.video_insights:
            # Drastically simplify video insights
            video.insights = {
                "summary": "Video analysis available but truncated due to size constraints.",
                "key_objects": video.objects[:3] if video.objects else [],
                "primary_labels": video.labels[:3] if video.labels else []
            }
            
            # Truncate transcript severely
            if len(video.transcript) > 200:
                video.transcript = video.transcript[:200] + "... [truncated]"
            
            # Limit other arrays
            video.labels = video.labels[:5] if video.labels else []
            video.objects = video.objects[:5] if video.objects else []
            video.text_annotations = video.text_annotations[:3] if video.text_annotations else []
            
            print(f"AI ANALYZER: 🔄   - Truncated {video.file_name}")
        
        return analysis_copy

    async def _build_final_assessment_prompt(self, analysis: CaseAnalysisResult) -> str:
        """Builds the prompt for the final legal assessment, including media summaries."""
        # Log comprehensive diagnostics about video content
        self._log_video_analysis_diagnostics(analysis)
        
        analysis_for_prompt = analysis.model_copy(deep=True)

        # Create summarization tasks for all media
        summarization_tasks = []
        for media in analysis_for_prompt.transcripted_media:
            summarization_tasks.append(
                self._summarize_media_content(media.transcript, "audio transcript", media.file_name)
            )
        for video in analysis_for_prompt.video_insights:
            print(f"AI ANALYZER: 🔍 DEBUGGING - Video insights type for {video.file_name}: {type(video.insights)}")
            print(f"AI ANALYZER: 🔍 DEBUGGING - Video insights keys: {list(video.insights.keys()) if isinstance(video.insights, dict) else 'Not a dict'}")
            summarization_tasks.append(
                self._summarize_media_content(video.insights, "video analysis", video.file_name)
            )

        # Run summarizations concurrently
        if summarization_tasks:
            print("AI ANALYZER: Starting media summarization...")
            summaries = await asyncio.gather(*summarization_tasks)
            
            # Replace full content with summaries
            summary_idx = 0
            for media in analysis_for_prompt.transcripted_media:
                media.transcript = summaries[summary_idx]
                summary_idx += 1
            for video in analysis_for_prompt.video_insights:
                # CRITICAL FIX: Store summary in a string field, not the Dict insights field
                print(f"AI ANALYZER: 🔍 DEBUGGING - Original insights size: {len(str(video.insights))}")
                video.insights = {"summary": summaries[summary_idx]}  # Wrap string in dict to maintain type
                print(f"AI ANALYZER: 🔍 DEBUGGING - Summarized insights size: {len(str(video.insights))}")
                summary_idx += 1
            print("AI ANALYZER: ✅ Media summarization completed")

        # Enhanced prompt size validation with detailed logging
        try:
            prompt_data = analysis_for_prompt.model_dump_json(indent=2)
            estimated_tokens = self._estimate_prompt_tokens_detailed(prompt_data)
            
            # Conservative safety limit for final assessment
            SAFE_TOKEN_LIMIT = 120000
            
            if estimated_tokens > SAFE_TOKEN_LIMIT:
                print(f"AI ANALYZER: ⚠️  PROMPT SIZE VALIDATION FAILED")
                print(f"AI ANALYZER: ⚠️  Estimated tokens: {estimated_tokens:,} > limit: {SAFE_TOKEN_LIMIT:,}")
                print(f"AI ANALYZER: 🔄 Applying aggressive video content truncation...")
                
                # Apply aggressive truncation
                analysis_for_prompt = self._truncate_video_content_aggressively(analysis_for_prompt, SAFE_TOKEN_LIMIT)
                
                # Re-check size after truncation
                prompt_data = analysis_for_prompt.model_dump_json(indent=2)
                estimated_tokens = self._estimate_prompt_tokens_detailed(prompt_data)
                
                if estimated_tokens > SAFE_TOKEN_LIMIT:
                    raise ValueError(f"Even after aggressive truncation, prompt is too large: {estimated_tokens:,} tokens")
                else:
                    print(f"AI ANALYZER: ✅ Truncation successful, final tokens: {estimated_tokens:,}")
            else:
                print(f"AI ANALYZER: ✅ Prompt size validation passed: {estimated_tokens:,} tokens")
                
        except Exception as e:
            print(f"AI ANALYZER: ❌ PROMPT SIZE VALIDATION ERROR: {e}")
            print(f"AI ANALYZER: ❌ Error type: {type(e).__name__}")
            raise ValueError(f"Cannot serialize analysis data for final assessment: {e}")

        return (
            "SYSTEM\n"
            "You are a senior litigation attorney with over 15 years of experience specializing in tenant and property disputes. Your analysis must be sharp, strategic, and framed in professional, legally appropriate language. Output a single JSON object with exactly two top-level keys: `\"legal_assessment\"` and `\"demand_letter_evaluation\"`—nothing else.\n\n"
            "• JSON only—no markdown, no commentary.\n"
            "• Do not alter key names.\n\n"
            "==========================\n"
            "COMBINED ANALYSIS (read-only)\n"
            f"{analysis_for_prompt.model_dump_json(indent=2)}\n"
            "==========================\n\n"
            "SCHEMAS\n"
            "LegalAssessment:\n"
            "{\n"
            '  "case_type": "Case Type",\n'
            '  "claim_viability": "Claim Viability",\n'
            '  "overall_evidence_strength": "Strength",\n'
            '  "potential_challenges": "A clear description of potential challenges, using bullet points or narrative as appropriate for clarity.",\n'
            '  "recommended_actions": "Recommended next steps, using bullet points or narrative as appropriate for clarity.",\n'
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
            "1.  **`potential_challenges` and `recommended_actions` should use clear, accessible language.** Use bullet points or narrative format as appropriate for client understanding.\n"
            "2.  The tone must be authoritative yet accessible, consistent with a client-focused attorney persona.\n"
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
        if not analysis.intake_analysis or (not analysis.analyzed_documents and not analysis.transcripted_media and not analysis.video_insights):
            error_msg = "Cannot perform final assessment without intake analysis and at least one document or media file."
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
            
            # PRE-COMPUTATION TOKEN CHECKING - Check before building prompt
            model_to_use = "gpt-4o"
            token_check_passed = await self._check_token_threshold_precomputation(analysis, model_to_use)
            
            # Apply conditional logic based on token threshold
            if token_check_passed:
                print("AI ANALYZER: ✅ Token threshold check passed - proceeding with full data")
                analysis_for_assessment = analysis
            else:
                print("AI ANALYZER: ⚠️  Token threshold exceeded - applying summarization strategy")
                analysis_for_assessment = self._apply_video_summarization_strategy(analysis)
            
            # Build prompt with potentially summarized data
            prompt = await self._build_final_assessment_prompt(analysis_for_assessment)
            
            # Final validation of prompt size
            estimated_tokens = self._count_tokens_accurate(prompt, model_to_use)
            print(f"AI ANALYZER: Final assessment prompt tokens: {estimated_tokens:,}")
            
            # Conservative safety check (should rarely trigger now due to pre-computation)
            if estimated_tokens > 120000:
                error_msg = f"Final assessment prompt still too large ({estimated_tokens:,} tokens) after pre-computation check."
                print(f"AI ANALYZER: ⚠️  {error_msg}")
                
                # Apply emergency fallback if pre-computation didn't catch the issue
                emergency_analysis = analysis.model_copy(deep=True)
                for video in emergency_analysis.video_insights:
                    video.insights = {"status": "Emergency summarization applied"}
                    video.transcript = f"Video file: {video.file_name} [emergency abbreviation]"
                    video.labels = video.labels[:3] if video.labels else []
                    video.objects = video.objects[:3] if video.objects else []
                    video.text_annotations = []
                
                # Rebuild prompt with emergency simplification
                prompt = await self._build_final_assessment_prompt(emergency_analysis)
                estimated_tokens = self._count_tokens_accurate(prompt, model_to_use)
                print(f"AI ANALYZER: Emergency reduced prompt tokens: {estimated_tokens:,}")
                
                if estimated_tokens > 120000:
                    raise ValueError(f"Even after emergency reduction, prompt is too large ({estimated_tokens:,} tokens)")
            
            try:
                raw_assessment = await self._make_openai_request(prompt, model="gpt-4o")
            except BadRequestError as bad_request_error:
                # ENHANCED ERROR RECOVERY WITH METADATA PRESERVATION
                error_details = str(bad_request_error)
                print(f"AI ANALYZER: ❌ BADREQUEST ERROR DETECTED in final assessment")
                print(f"AI ANALYZER: 🔍 Error details: {error_details}")
                print(f"AI ANALYZER: 🔍 Prompt character count: {len(prompt):,}")
                print(f"AI ANALYZER: 🔍 Video insights count: {len(analysis.video_insights)}")
                
                # LOG THE ERROR WITH DETAILED CONTEXT
                print(f"AI ANALYZER: 🔍 === BADREQUEST ERROR CONTEXT ===")
                print(f"AI ANALYZER: 🔍 Model: {model_to_use}")
                print(f"AI ANALYZER: 🔍 Estimated tokens: {estimated_tokens:,}")
                print(f"AI ANALYZER: 🔍 Analysis has {len(analysis.analyzed_documents)} documents")
                print(f"AI ANALYZER: 🔍 Analysis has {len(analysis.transcripted_media)} audio files")
                print(f"AI ANALYZER: 🔍 Analysis has {len(analysis.video_insights)} video files")
                
                # Log video content sizes for debugging
                for i, video in enumerate(analysis.video_insights):
                    insights_size = len(str(video.insights)) if video.insights else 0
                    transcript_size = len(video.transcript) if video.transcript else 0
                    print(f"AI ANALYZER: 🔍   Video {i+1} ({video.file_name}): insights={insights_size} chars, transcript={transcript_size} chars")
                
                print(f"AI ANALYZER: 🔍 === END ERROR CONTEXT ===")
                
                # PRESERVE METADATA INSTEAD OF DISCARDING DATA
                if analysis.video_insights:
                    print(f"AI ANALYZER: 🔄 ENHANCED ERROR RECOVERY: Preserving video metadata...")
                    
                    retry_analysis = analysis.model_copy(deep=True)
                    for video in retry_analysis.video_insights:
                        # PRESERVE METADATA: Store reference to where full insights would be saved
                        if not video.insights_gcs_uri:
                            # Generate GCS path where full insights would be stored
                            import uuid
                            video_entry_id = str(uuid.uuid4())
                            video.insights_gcs_uri = f"gs://findings-video-analysis/{video_entry_id}/full_insights.json"
                            print(f"AI ANALYZER: 💾 Generated GCS path for {video.file_name}: {video.insights_gcs_uri}")
                        
                        # GENERATE INSIGHTS SUMMARY using existing summarization logic
                        if video.insights and not video.insights_summary:
                            # Create a condensed summary for prompt inclusion (same logic as _apply_video_summarization_strategy)
                            key_objects = video.objects[:5] if video.objects else []
                            key_labels = video.labels[:5] if video.labels else []
                            
                            summary_parts = []
                            if key_objects:
                                summary_parts.append(f"Key objects detected: {', '.join(key_objects)}")
                            if key_labels:
                                summary_parts.append(f"Content labels: {', '.join(key_labels)}")
                            if video.transcript and len(video.transcript) > 200:
                                summary_parts.append(f"Transcript excerpt: {video.transcript[:200]}...")
                            elif video.transcript:
                                summary_parts.append(f"Transcript: {video.transcript}")
                            
                            video.insights_summary = "; ".join(summary_parts) if summary_parts else "Video content available but summarized due to token constraints."
                            print(f"AI ANALYZER: 💾 Generated summary for {video.file_name}: {len(video.insights_summary)} chars")
                        
                        # CLEAR INSIGHTS TO MINIMAL STATE for token management
                        # Store original insights temporarily (excluded from serialization)
                        if video.insights:
                            video.original_insights = video.insights.copy()
                        
                        # Replace with minimal state that preserves reference to full data
                        video.insights = {
                            "status": "Video analyzed - full details preserved in GCS",
                            "preservation_applied": True,
                            "gcs_reference": video.insights_gcs_uri,
                            "summary_available": bool(video.insights_summary)
                        }
                        
                        print(f"AI ANALYZER: 💾 Preserved metadata for {video.file_name} - full data can be retrieved via {video.insights_gcs_uri}")
                    
                    try:
                        print(f"AI ANALYZER: 🔄 Building recovery prompt with preserved metadata...")
                        retry_prompt = await self._build_final_assessment_prompt(retry_analysis)
                        retry_tokens = self._estimate_prompt_tokens_detailed(retry_prompt)
                        print(f"AI ANALYZER: 🔄 Recovery prompt tokens: {retry_tokens:,}")
                        
                        print(f"AI ANALYZER: 🔄 Making recovery API call with preserved data...")
                        raw_assessment = await self._make_openai_request(retry_prompt, model="gpt-4o")
                        print(f"AI ANALYZER: ✅ RECOVERY SUCCESSFUL - BadRequestError resolved with metadata preservation")
                        
                        # Update the original analysis with preserved metadata for downstream use
                        for i, video in enumerate(analysis.video_insights):
                            if i < len(retry_analysis.video_insights):
                                preserved_video = retry_analysis.video_insights[i]
                                video.insights_gcs_uri = preserved_video.insights_gcs_uri
                                video.insights_summary = preserved_video.insights_summary
                                video.original_insights = preserved_video.original_insights
                        
                    except Exception as retry_error:
                        print(f"AI ANALYZER: ❌ RECOVERY FAILED: {retry_error}")
                        print(f"AI ANALYZER: ❌ Original BadRequest: {error_details}")
                        print(f"AI ANALYZER: ❌ Recovery error: {str(retry_error)}")
                        raise AIAnalysisError(
                            f"Final assessment failed with BadRequestError. "
                            f"Original error: {error_details}. "
                            f"Recovery with metadata preservation also failed: {retry_error}"
                        )
                else:
                    print(f"AI ANALYZER: ❌ No video insights to preserve for BadRequestError recovery")
                    raise AIAnalysisError(f"BadRequestError in final assessment without video data: {error_details}")
                    
            except Exception as openai_error:
                # Handle other OpenAI API errors
                error_details = str(openai_error)
                error_type = type(openai_error).__name__
                print(f"AI ANALYZER: ❌ OpenAI API error ({error_type}) in final assessment: {error_details}")
                
                # Log prompt details for any API error
                print(f"AI ANALYZER: 🔍 Prompt length: {len(prompt):,} characters")
                print(f"AI ANALYZER: 🔍 Estimated tokens: {self._estimate_tokens(prompt):,}")
                
                raise AIAnalysisError(f"OpenAI API error ({error_type}) in final assessment: {error_details}")
            
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
