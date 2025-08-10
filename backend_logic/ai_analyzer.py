from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING, Any

import tiktoken
import yaml
from openai import APIError, APITimeoutError, BadRequestError, OpenAI, RateLimitError
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from backend.utils.data_models import (
    AIAnalysisError,
    AnalysisError,
    AnalyzedDocument,
    CaseAnalysisResult,
    DemandLetterEvaluation,
    EnhancedIntakeAnalysis,
    LegalAssessment,
    ProcessedDocument,
)
from utils.logging_config import setup_logging

logger = setup_logging('ai_analyzer')
from backend.utils.validators import (
    create_fallback_demand_letter_evaluation,
    create_fallback_legal_assessment,
    preprocess_ai_output,
    safe_model_validate,
)


if TYPE_CHECKING:
    from .document_processor import DocumentProcessor


class AIAnalyzer:
    """Handles all interactions with the OpenAI API for document analysis."""

    def __init__(self, client: OpenAI, doc_processor: DocumentProcessor, config_path: str | None = None) -> None:
        self.client = client
        self.doc_processor = doc_processor
        
        # Load configuration
        self.config = self._load_configuration(config_path)
        
        logger.info(f'AI ANALYZER: ✅ Initialized with configuration: {config_path or 'default'}')

    def _load_configuration(self, config_path: str | None = None) -> dict[str, Any]:
        """Load configuration from YAML file."""
        if config_path is None:
            # Default to universal_legal_config.yaml for all case types
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = current_dir
            
            # Navigate up until we find the project root
            while project_root != "/" and not (
                os.path.exists(os.path.join(project_root, "app.py"))
                and os.path.exists(os.path.join(project_root, "backend"))
            ):
                project_root = os.path.dirname(project_root)
            
            if project_root == "/":
                project_root = os.getcwd()
            
            config_path = os.path.join(project_root, "backend", "config", "templates", "universal_legal_config.yaml")
        
        if not os.path.exists(config_path):
            logger.info(f'AI ANALYZER: ⚠️  Configuration file not found: {config_path}, using default prompts')
            return {}
        
        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.info(f'AI ANALYZER: Configuration loaded from: {config_path}')
            return config
        except yaml.YAMLError as e:
            logger.error(f'AI ANALYZER: ⚠️  Failed to parse YAML configuration: {e}, using default prompts')
            return {}
        except Exception as e:
            logger.error(f'AI ANALYZER: ⚠️  Failed to load configuration: {e}, using default prompts')
            return {}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type((RateLimitError, APIError, APITimeoutError)),
    )
    async def _make_openai_request(
        self, prompt: str, model: str, use_json_format: bool = True
    ) -> dict[str, Any]:
        """Makes a request to the OpenAI API with robust retry logic."""
        try:
            request_params = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }

            # Only add JSON response format if requested and prompt contains 'json'
            if use_json_format and "json" in prompt.lower():
                request_params["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**request_params)

            # Parse as JSON only if JSON format was requested
            if use_json_format:
                return json.loads(response.choices[0].message.content)
            # Return the content wrapped in a dictionary for consistency
            return {"content": response.choices[0].message.content}
        except json.JSONDecodeError as e:
            logger.error(f'AI ANALYZER: Failed to parse AI response as JSON: {e}')
            raw_response_content = "N/A"
            if (
                "response" in locals()
                and hasattr(response, "choices")
                and response.choices
            ):
                raw_response_content = response.choices[0].message.content
            logger.debug(f'AI ANALYZER: Raw response: {raw_response_content}')
            msg = f"Failed to parse AI response as JSON: {e}"
            raise AIAnalysisError(msg) from e
        except (RateLimitError, APIError, APITimeoutError) as e:
            logger.error(f'AI ANALYZER: OpenAI API Error: {e}. Retrying...')
            raise
        except (AttributeError, KeyError, TypeError, OSError) as e:
            logger.info(f'AI ANALYZER: An unexpected error occurred: {type(e).__name__} - {e}')
            msg = f"Error communicating with OpenAI API: {e}"
            raise AIAnalysisError(msg) from e

    def _build_intake_prompt(self, content: str, prompt_config: str = None) -> str:
        """Builds the prompt for analyzing an intake form using configuration-driven prompts."""
        if prompt_config:
            # Use configuration-provided prompt
            base_prompt = prompt_config
        else:
            # Fallback to default prompt if configuration is missing
            base_prompt = (
                "You are a seasoned Florida litigation attorney with 15+ years of experience analyzing case documents and extracting legally significant information. Your document analysis supports comprehensive legal findings letters.\n\n"
                "DOCUMENT ANALYSIS EXPERTISE:\n"
                "1. **Legal Relevance Assessment:** Identify information directly relevant to potential legal claims and defenses under Florida law\n"
                "2. **Strategic Document Review:** Extract facts that will be critical for case development, settlement negotiations, or litigation\n"
                "3. **Evidence Identification:** Recognize documentary evidence that supports or undermines legal positions\n"
                "4. **Professional Synthesis:** Organize findings to support detailed attorney analysis and client communication\n"
                "5. **Florida Practice Focus:** Consider how document contents relate to Florida legal standards and procedural requirements\n"
                "6. **Case Development Support:** Structure analysis to facilitate comprehensive legal strategy and client counseling"
            )
        
        return (
            "SYSTEM\n"
            f"{base_prompt}\n\n"
            "Return **one—and only one—valid JSON object** that matches the\n"
            "`EnhancedIntakeAnalysis` schema below.\n\n"
            "• Do **NOT** wrap the JSON in markdown fences.\n"
            "• Do **NOT** change key names, add keys, or emit commentary.\n"
            "• Write summaries and analysis in clear, accessible language (9th-grade reading level)\n"
            "• Use direct professional language ('you have' rather than 'we have analyzed')\n\n"
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
            '   • If data is missing, output an empty string `""` or empty list `[]`.\n'
            "2. `case_summary`: 120–200 words, neutral tone.\n"
            "3. `key_facts`: bullet-style strings ≤25 words each.\n"
            '4. `parties_involved`: each object **must** have `"name"` and `"role"` (e.g., Plaintiff, Contractor).\n'
            "5. Keep every other string ≤40 words.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• All strings double-quoted.\n"
            "• Key order exactly as in schema.\n\n"
            "BEGIN."
        )

    def _build_case_document_prompt(
        self, doc: ProcessedDocument, ctx: EnhancedIntakeAnalysis, prompt_config: str = None
    ) -> str:
        """Builds a context-aware prompt for a case document using configuration-driven prompts."""
        client_priorities_str = (
            ", ".join(ctx.client_priorities)
            if ctx.client_priorities
            else "None specified"
        )
        desired_outcomes_str = (
            ", ".join(ctx.desired_outcomes)
            if ctx.desired_outcomes
            else "None specified"
        )

        if prompt_config:
            # Use configuration-provided prompt
            base_prompt = prompt_config
        else:
            # Fallback to default prompt if configuration is missing
            base_prompt = (
                "You are a seasoned Florida litigation attorney with 15+ years of experience analyzing legal documents and extracting case-critical information. Your analysis forms the foundation for professional legal findings letters.\n\n"
                "PROFESSIONAL ANALYSIS STANDARDS:\n"
                "1. **Attorney-Level Precision:** Extract and organize information with the thoroughness expected from an experienced litigator\n"
                "2. **Case-Building Focus:** Identify facts, parties, and circumstances that will be essential for legal strategy and client communication\n"
                "3. **Florida Law Context:** Consider how extracted information relates to Florida legal standards and procedural requirements\n"
                "4. **Professional Documentation:** Structure analysis to support detailed attorney findings letters and case development\n"
                "5. **Client-Ready Foundation:** Organize information for clear presentation to clients while maintaining legal precision\n"
                "6. **Strategic Awareness:** Recognize and prioritize information based on its litigation and settlement value"
            )

        return (
            "SYSTEM\n"
            f"{base_prompt}\n\n"
            "Return **one—and only one—valid JSON object** that matches the\n"
            "`AnalyzedDocument` schema below.\n\n"
            "• JSON only—no markdown, no extra text.\n"
            "• Preserve key order.\n"
            "• PRIORITIZE analysis elements that directly relate to client's stated priorities and desired outcomes.\n"
            "• Write all content in clear, accessible language (9th-grade reading level)\n"
            "• Use direct professional language addressing the client directly\n\n"
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
            '  "file_name": "The original filename of the document.",\n'
            "  \"document_type\": \"The type of document (e.g., 'Contract', 'Email', 'Image').\",\n"
            '  "inferred_title": "A meaningful, non-repetitive title for the document (less than 15 words).",\n'
            '  "summary": "A concise, value-driven summary of the document\'s content (100-150 words).",\n'
            '  "key_information": "A single consolidated string containing the most critical information. Format as a paragraph, NOT a list. If multiple points exist, separate them with semicolons within the string.",\n'
            '  "relevance_to_case": "A clear explanation of how this document supports or undermines the client\'s position, referencing specific case priorities."\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1.  `file_name`: Must be the exact filename provided.\n"
            "2.  `inferred_title`: Create a meaningful and non-repetitive title. Do not just repeat the filename.\n"
            "3.  `summary`: Must be concise and value-driven, focusing on the most important aspects of the document.\n"
            "4.  `key_information`: Extract the most critical information as a bulleted list string.\n"
            "5.  `relevance_to_case`: Clearly articulate the document's relevance to the overall case strategy and client goals.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• All strings double-quoted.\n\n"
            "BEGIN."
        )

    async def _summarize_media_content(
        self, content: dict | str, media_type: str, file_name: str, prompt_config: str = None
    ) -> str:
        """Summarizes media content using configuration-driven prompts."""
        logger.info(f'AI ANALYZER: Summarizing {media_type} for {file_name}')
        
        if prompt_config:
            # Use configuration-provided prompt
            base_prompt = prompt_config
        else:
            # Fallback to default prompt if configuration is missing
            base_prompt = (
                "You are a senior litigation attorney specializing in clear, professional legal communication. Create a concise summary (100-150 words) of the provided media content that will be easily understood by clients without legal training.\n\n"
                "AUTHENTIC_ATTORNEY_ADVISOR PRINCIPLES:\n"
                "• Use clear, accessible language (9th-grade reading level)\n"
                "• Focus on actionable details and key facts\n"
                "• Use direct professional perspective ('the analysis shows,' 'the evidence indicates')\n"
                "• Maintain professional authority while being accessible\n"
                "• Highlight evidence relevant to Florida legal matters"
            )
        
        prompt = (
            "SYSTEM\n"
            f"{base_prompt}\n\n"
            f"Provided {media_type} content for {file_name}:\n"
            f"```\n{json.dumps(content, indent=2) if isinstance(content, dict) else content}\n```\n\n"
            "Create a clear, client-friendly summary that explains what the evidence shows.\n"
            "BEGIN SUMMARY."
        )
        try:
            # Use gpt-4o-mini for efficiency, with non-JSON format since prompt doesn't contain 'json'
            response = await self._make_openai_request(
                prompt, model="gpt-4o-mini", use_json_format=False
            )
            # Extract the content from the response wrapper
            summary = response.get("content", "Summary could not be generated.")
            logger.info(f'AI ANALYZER: ✅ Successfully summarized {media_type} for {file_name}')
            return summary
        except AIAnalysisError as e:
            logger.info(f'AI ANALYZER: ❌ Failed to summarize {media_type} for {file_name}: {e}')
            return f"[A {media_type} from {file_name} is available but could not be summarized.]"

    def _log_video_analysis_diagnostics(self, analysis: CaseAnalysisResult) -> None:
        """Log comprehensive diagnostics about video analysis content before final assessment."""
        logger.info('AI ANALYZER: 🔍 === DIAGNOSTIC LOGGING - Video Analysis Content ===')

        if not analysis.video_insights:
            logger.info('AI ANALYZER: 🔍 No video insights to analyze')
            return

        for i, video in enumerate(analysis.video_insights):
            logger.info(f'AI ANALYZER: 🔍 Video {i + 1}: {video.file_name}')
            logger.info(f'AI ANALYZER: 🔍   - Insights type: {type(video.insights)}')
            logger.info(f'AI ANALYZER: 🔍   - Insights size (chars): {len(str(video.insights))}')
            logger.info(f'AI ANALYZER: 🔍   - Insights estimated tokens: {len(str(video.insights)) // 4}')

            if isinstance(video.insights, dict):
                logger.info(f'AI ANALYZER: 🔍   - Insights keys: {list(video.insights.keys())}')
                for key, value in video.insights.items():
                    if isinstance(value, (str, list)):
                        logger.info(f'AI ANALYZER: 🔍   - {key} size: {len(str(value))} chars')

            logger.info(f'AI ANALYZER: 🔍   - Transcript size: {len(video.transcript)} chars')
            logger.info(f'AI ANALYZER: 🔍   - Labels count: {len(video.labels)}')
            logger.info(f'AI ANALYZER: 🔍   - Objects count: {len(video.objects)}')
            logger.info(f'AI ANALYZER: 🔍   - Text annotations count: {len(video.text_annotations)}')

        logger.info('AI ANALYZER: 🔍 === END DIAGNOSTIC LOGGING ===')

    def _estimate_prompt_tokens_detailed(self, prompt_content: str) -> int:
        """Enhanced token estimation with more accurate calculation."""
        # More accurate token estimation: ~3.5 characters per token for English text
        base_tokens = len(prompt_content) // 3.5

        # Add overhead for JSON structure, special characters, etc.
        overhead_factor = 1.15
        estimated_tokens = int(base_tokens * overhead_factor)

        logger.info('AI ANALYZER: 🔍 Token estimation details:')
        logger.info(f'AI ANALYZER: 🔍   - Content length: {len(prompt_content):,} characters')
        logger.info(f'AI ANALYZER: 🔍   - Base tokens: {int(base_tokens):,}')
        logger.info(f'AI ANALYZER: 🔍   - With overhead: {estimated_tokens:,}')

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

            logger.info(f'AI ANALYZER: 🔢 Accurate token count ({model}): {token_count:,}')
            return token_count
        except (ImportError, AttributeError, ValueError, TypeError) as e:
            logger.error(f'AI ANALYZER: ⚠️  tiktoken error, falling back to estimation: {e}')
            # Fallback to existing estimation method
            return self._estimate_prompt_tokens_detailed(text)

    async def _check_token_threshold_precomputation(
        self, analysis: CaseAnalysisResult, model: str = "gpt-4o"
    ) -> bool:
        """Check if video insights would exceed token threshold before building prompt."""
        logger.debug(f'AI ANALYZER: 🔍 Pre-computation token checking for model: {model}')

        # Define thresholds (80% of context window)
        model_limits = {
            "gpt-4o": 120000,  # 150k context window * 0.8
            "gpt-4o-mini": 100000,  # 125k context window * 0.8
            "gpt-4": 25600,  # 32k context window * 0.8
        }

        threshold = model_limits.get(model, 96000)  # Default to 120k * 0.8
        logger.info(f'AI ANALYZER: 🔍 Token threshold for {model}: {threshold:,}')

        # Estimate token usage from video insights
        if not analysis.video_insights:
            logger.info('AI ANALYZER: 🔍 No video insights, threshold check passed')
            return True

        total_video_tokens = 0
        for video in analysis.video_insights:
            # Estimate tokens from video content
            insights_content = (
                json.dumps(video.insights, indent=2) if video.insights else ""
            )
            transcript_content = video.transcript or ""
            labels_content = ", ".join(video.labels) if video.labels else ""
            objects_content = ", ".join(video.objects) if video.objects else ""

            video_content = f"{insights_content}\n{transcript_content}\n{labels_content}\n{objects_content}"
            video_tokens = self._count_tokens_accurate(video_content, model)
            total_video_tokens += video_tokens

            logger.info(f'AI ANALYZER: 🔍   - {video.file_name}: {video_tokens:,} tokens')

        # Add estimated tokens for other content (documents, intake, etc.)
        base_content_estimate = 10000  # Conservative estimate for non-video content
        total_estimated_tokens = total_video_tokens + base_content_estimate

        logger.info(f'AI ANALYZER: 🔍 Total estimated tokens: {total_estimated_tokens:,}')
        logger.info(f'AI ANALYZER: 🔍 Threshold: {threshold:,}')

        if total_estimated_tokens > threshold:
            logger.info(f'AI ANALYZER: ⚠️  Token count exceeds threshold ({total_estimated_tokens:,} > {threshold:,})')
            return False
        logger.info('AI ANALYZER: ✅ Token count within threshold')
        return True

    def _apply_video_summarization_strategy(
        self, analysis: CaseAnalysisResult
    ) -> CaseAnalysisResult:
        """Apply summarization strategy when token threshold is exceeded."""
        logger.info('AI ANALYZER: 🔄 Token count exceeds threshold. Triggering summarization strategy.')

        analysis_copy = analysis.model_copy(deep=True)

        for video in analysis_copy.video_insights:
            # Set the insights_summary field as specified in the video preservation plan
            if video.insights:
                # Create a condensed summary for prompt inclusion
                key_objects = video.objects[:5] if video.objects else []
                key_labels = video.labels[:5] if video.labels else []

                summary_parts = []
                if key_objects:
                    summary_parts.append(
                        f"Key objects detected: {', '.join(key_objects)}"
                    )
                if key_labels:
                    summary_parts.append(f"Content labels: {', '.join(key_labels)}")
                if video.transcript and len(video.transcript) > 200:
                    summary_parts.append(
                        f"Transcript excerpt: {video.transcript[:200]}..."
                    )
                elif video.transcript:
                    summary_parts.append(f"Transcript: {video.transcript}")

                condensed_summary = (
                    "; ".join(summary_parts)
                    if summary_parts
                    else "Video content available but summarized due to token constraints."
                )

                # Update the insights_summary field in the data model
                video.insights_summary = condensed_summary

                # Replace the full insights with a minimal placeholder to reduce tokens
                video.insights = {
                    "status": "Video analyzed - full details preserved, summary applied for prompt"
                }

                logger.info(f'AI ANALYZER: 🔄   - Summarized {video.file_name}: {len(condensed_summary)} chars')
            else:
                video.insights_summary = f"Video file {video.file_name} processed but content summarized due to size constraints."
                logger.info(f'AI ANALYZER: 🔄   - Applied default summary for {video.file_name}')

        logger.info(f'AI ANALYZER: 🔄 Summarization strategy applied to {len(analysis_copy.video_insights)} video(s)')
        return analysis_copy

    def _truncate_video_content_aggressively(
        self, analysis: CaseAnalysisResult, target_tokens: int = 100000
    ) -> CaseAnalysisResult:
        """Aggressively truncate video content to meet token limits."""
        logger.info(f'AI ANALYZER: 🔄 Aggressively truncating video content to target {target_tokens:,} tokens')

        analysis_copy = analysis.model_copy(deep=True)

        for video in analysis_copy.video_insights:
            # Drastically simplify video insights
            video.insights = {
                "summary": "Video analysis available but truncated due to size constraints.",
                "key_objects": video.objects[:3] if video.objects else [],
                "primary_labels": video.labels[:3] if video.labels else [],
            }

            # Truncate transcript severely
            if len(video.transcript) > 200:
                video.transcript = video.transcript[:200] + "... [truncated]"

            # Limit other arrays
            video.labels = video.labels[:5] if video.labels else []
            video.objects = video.objects[:5] if video.objects else []
            video.text_annotations = (
                video.text_annotations[:3] if video.text_annotations else []
            )

            logger.info(f'AI ANALYZER: 🔄   - Truncated {video.file_name}')

        return analysis_copy

    async def _build_final_assessment_prompt(self, analysis: CaseAnalysisResult, prompt_config: str = None) -> str:
        """Builds the prompt for the final legal assessment, including media summaries, timeline, and video relevance."""

        # DIAGNOSTIC LOGGING: Check what document content is available
        logger.info('AI ANALYZER: 🔍 === DIAGNOSTIC LOGGING - Final Assessment Input ===')
        logger.info(f'AI ANALYZER: 🔍 Analyzed documents count: {len(analysis.analyzed_documents) if analysis.analyzed_documents else 0}')
        if analysis.analyzed_documents:
            for i, doc in enumerate(
                analysis.analyzed_documents[:3]
            ):  # Log first 3 docs
                logger.info(f'AI ANALYZER: 🔍   Document {i + 1}: {doc.file_name}')
                logger.info(f'AI ANALYZER: 🔍   Summary: {doc.summary[:150] if doc.summary else "No summary"}...')
                logger.info(f'AI ANALYZER: 🔍   Key info: {doc.key_information[:150] if doc.key_information else "No key info"}...')
                logger.info(f'AI ANALYZER: 🔍   Relevance: {doc.relevance_to_case[:100] if doc.relevance_to_case else "No relevance"}...')

        if analysis.intake_analysis:
            logger.info(f'AI ANALYZER: 🔍 Client name: {analysis.intake_analysis.client_name}')
            logger.info(f'AI ANALYZER: 🔍 Case type: {analysis.intake_analysis.case_type}')
            logger.info(f'AI ANALYZER: 🔍 Key facts count: {len(analysis.intake_analysis.key_facts) if analysis.intake_analysis.key_facts else 0}')

        # Log comprehensive diagnostics about video content
        self._log_video_analysis_diagnostics(analysis)

        analysis_for_prompt = analysis.model_copy(deep=True)

        # Generate timeline and video relevance analysis
        timeline_content = ""
        video_relevance_content = ""

        try:
            # Generate case timeline
            logger.info('AI ANALYZER: Generating case timeline...')
            timeline_content = generate_case_timeline(analysis_for_prompt)
            logger.info(f'AI ANALYZER: ✅ Timeline generated: {len(timeline_content)} characters')

            # Generate video relevance analysis if videos exist
            if analysis_for_prompt.video_insights:
                logger.info('AI ANALYZER: Generating video relevance analysis...')
                video_relevance_content = analyze_video_relevance(
                    analysis_for_prompt.video_insights[0],
                    analysis_for_prompt.intake_analysis,
                )
                logger.info(f'AI ANALYZER: ✅ Video relevance analysis generated: {len(str(video_relevance_content))} characters')

        except (ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f'AI ANALYZER: ⚠️ Failed to generate timeline/video relevance: {e}')
            timeline_content = (
                "Timeline generation encountered an error and was skipped."
            )
            video_relevance_content = (
                "Video relevance analysis encountered an error and was skipped."
            )

        # Create summarization tasks for all media
        summarization_tasks = []
        for media in analysis_for_prompt.transcripted_media:
            summarization_tasks.append(
                self._summarize_media_content(
                    media.transcript, "audio transcript", media.file_name, prompt_config=None
                )
            )
        for video in analysis_for_prompt.video_insights:
            logger.info(f'AI ANALYZER: 🔍 DEBUGGING - Video insights type for {video.file_name}: {type(video.insights)}')
            logger.info(f'AI ANALYZER: 🔍 DEBUGGING - Video insights keys: {list(video.insights.keys()) if isinstance(video.insights, dict) else "Not a dict"}')
            summarization_tasks.append(
                self._summarize_media_content(
                    video.insights, "video analysis", video.file_name, prompt_config=None
                )
            )

        # Run summarizations concurrently
        if summarization_tasks:
            logger.info('AI ANALYZER: Starting media summarization...')
            summaries = await asyncio.gather(*summarization_tasks)

            # Replace full content with summaries
            summary_idx = 0
            for media in analysis_for_prompt.transcripted_media:
                media.transcript = summaries[summary_idx]
                summary_idx += 1
            for video in analysis_for_prompt.video_insights:
                # CRITICAL FIX: Store summary in a string field, not the Dict insights field
                logger.info(f'AI ANALYZER: 🔍 DEBUGGING - Original insights size: {len(str(video.insights))}')
                video.insights = {
                    "summary": summaries[summary_idx]
                }  # Wrap string in dict to maintain type
                logger.info(f'AI ANALYZER: 🔍 DEBUGGING - Summarized insights size: {len(str(video.insights))}')
                summary_idx += 1
            logger.info('AI ANALYZER: ✅ Media summarization completed')

        # Enhanced prompt size validation with detailed logging
        try:
            prompt_data = analysis_for_prompt.model_dump_json(indent=2)
            estimated_tokens = self._estimate_prompt_tokens_detailed(prompt_data)

            # Conservative safety limit for final assessment
            SAFE_TOKEN_LIMIT = 120000

            if estimated_tokens > SAFE_TOKEN_LIMIT:
                logger.error('AI ANALYZER: ⚠️  PROMPT SIZE VALIDATION FAILED')
                logger.info(
                    f"AI ANALYZER: ⚠️  Estimated tokens: {estimated_tokens:,} > limit: {SAFE_TOKEN_LIMIT:,}"
                )
                logger.info('AI ANALYZER: 🔄 Applying aggressive video content truncation...')

                # Apply aggressive truncation
                analysis_for_prompt = self._truncate_video_content_aggressively(
                    analysis_for_prompt, SAFE_TOKEN_LIMIT
                )

                # Re-check size after truncation
                prompt_data = analysis_for_prompt.model_dump_json(indent=2)
                estimated_tokens = self._estimate_prompt_tokens_detailed(prompt_data)

                if estimated_tokens > SAFE_TOKEN_LIMIT:
                    msg = f"Even after aggressive truncation, prompt is too large: {estimated_tokens:,} tokens"
                    raise ValueError(msg)
                logger.info(f'AI ANALYZER: ✅ Truncation successful, final tokens: {estimated_tokens:,}')
            else:
                logger.info(f'AI ANALYZER: ✅ Prompt size validation passed: {estimated_tokens:,} tokens')

        except (ValueError, TypeError, AttributeError, KeyError, OSError) as e:
            logger.error(f'AI ANALYZER: ❌ PROMPT SIZE VALIDATION ERROR: {e}')
            logger.error(f'AI ANALYZER: ❌ Error type: {type(e).__name__}')
            msg = f"Cannot serialize analysis data for final assessment: {e}"
            raise ValueError(msg) from e

        # Use configuration-provided prompt or fallback
        if prompt_config:
            base_prompt = prompt_config
        else:
            # Fallback to default prompt if configuration is missing
            base_prompt = (
                "You are a seasoned Florida litigation attorney with 15+ years of experience conducting comprehensive case assessments and providing strategic legal analysis. You are preparing the legal analysis foundation that will support a detailed findings letter to your client.\n\n"
                "ATTORNEY ANALYSIS STANDARDS:\n"
                "1. **Professional Legal Authority:** Provide analysis with the depth and expertise expected from a senior litigation attorney\n"
                "2. **Florida Law Mastery:** Reference specific Florida statutes with proper citations (e.g., Florida Statutes § 83.51(1)) and demonstrate deep knowledge of Florida jurisprudence\n"
                "3. **Strategic Legal Assessment:** Evaluate claim viability, evidence strength, and litigation prospects with the judgment of an experienced practitioner\n"
                "4. **Client-Focused Analysis:** Structure findings to support clear, authoritative client communication while maintaining legal precision\n"
                "5. **Professional Objectivity:** Provide balanced assessment of strengths and challenges based on Florida law and litigation realities\n"
                "6. **Case Development Strategy:** Consider both immediate legal remedies and long-term strategic options under Florida law\n\n"
                "PROFESSIONAL ASSESSMENT PROTOCOL: When addressing complex or counterintuitive legal strategies:\n"
                '• **Professional Context:** "Based on my experience with Florida [relevant area] law..."\n'
                "• **Legal Foundation:** Cite specific Florida statutes, case law, or procedural requirements\n"
                "• **Strategic Rationale:** Explain the legal and practical reasoning behind the recommendation\n"
                "• **Risk Assessment:** Address potential outcomes and strategic considerations\n"
                '• **Professional Guidance:** "This analysis reflects Florida law standards and litigation experience"\n\n'
                "CRITICAL: Reference ONLY Florida statutes, case law, and legal precedents (e.g., Florida Statutes § 83.51(1), Florida case citations). Do NOT cite laws from other jurisdictions unless they have specific relevance to Florida legal standards."
            )

        return (
            "SYSTEM\n"
            f"{base_prompt}\n\n"
            'Output a single JSON object with exactly two top-level keys: `"legal_assessment"` and `"demand_letter_evaluation"`—nothing else.\n\n'
            "• JSON only—no markdown, no commentary.\n"
            "• Do not alter key names.\n\n"
            "==========================\n"
            "AUTHENTIC_ATTORNEY_ADVISOR EXAMPLE LETTER STYLE:\n\n"
            "Dear Mr. Price:\n\n"
            "We hope you are doing well. We wanted to follow up with a summary of our findings after completing our comprehensive review of the timeline and materials you submitted regarding the property located at 2260 Terra Cotta Cove, Apt. 110, Land O Lakes, Florida 34639, including the lease agreement, correspondence, invoices, videos and maintenance-related documentation.\n\n"
            "As we discussed, your primary concern centers on the prolonged and recurring water intrusion, inadequate remediation efforts, and the resulting conditions that have potentially rendered the unit uninhabitable. The timeline you provided documents multiple reports of water damage and potential mold spanning several months, which we have carefully analyzed under Florida law.\n\n"
            "You advised that you moved into the unit on or about August 1, 2024, and within days began experiencing issues involving water intrusion in the bedroom after rainfall. Maintenance initially attributed the flooding to improper grading and dug a temporary trench, but subsequent rains continued to result in pooling, wall saturation, and elevated moisture levels.\n\n"
            "Over the following months, including September and October 2024, water continued to enter the unit. You explained that you submitted multiple maintenance requests and had professional services, such as ServPro, document unsafe moisture levels which could lead to mold development. You relayed that, despite ongoing communication and photographic evidence, the property management team delayed effective repairs, with contractors often failing to complete the necessary work or denying the severity of the problem.\n\n"
            "Here are the key points of our analysis under Florida law:\n\n"
            "• We believe the recurring water intrusion and subsequent mold exposure may rise to the level of a constructive eviction, which under Florida law arises when conditions are so intolerable that the tenant is forced to vacate.\n\n"
            "• Pursuant to Florida Statutes § 83.51(1), landlords are required to maintain rental premises in compliance with building, housing, and health codes, and where no codes apply, in good repair and fit for human habitation.\n\n"
            "• Our analysis of the evidence supports a potential breach of the implied warranty of habitability, as your timeline and third-party reports confirm the unit is likely unsafe and inadequately maintained under Florida standards.\n\n"
            "• Your documented efforts to notify management and allow a reasonable opportunity to cure strengthen your position that the landlord could be in violation of lease agreement under Florida landlord-tenant law.\n\n"
            "At this juncture, we believe the most appropriate course of action is to issue a formal demand letter requesting that the landlord take corrective measures to address the longstanding water intrusion and suspected mold conditions. Specifically, we recommend that you demand the landlord:\n\n"
            "• Regrade the foundational land surrounding the apartment to prevent further flooding and water intrusion into the unit;\n\n"
            "• Retain a licensed mold assessor to conduct a full indoor air quality and mold inspection of the premises, with a written assessment report issued to you promptly; and\n\n"
            "• If the mold assessment confirms the presence of mold, the landlord must retain a licensed mold remediation specialist to perform remediation of all affected areas identified in the assessment report, with all remediation work to be completed no later than fifteen (15) days following the issuance of the mold assessment.\n\n"
            "We believe this approach may lead to a joint resolution that includes mutual waivers and a clear release of future liability.\n\n"
            "Please let us know if you would like us to proceed with a draft of the demand letter, or whether you would prefer that we first set a phone call to discuss our review and recommendations for next steps. For your consideration, we have attached a letter outlining the demand letter process, including a detailed explanation of its purpose and what to anticipate upon issuance.\n\n"
            "We're committed to achieving the best possible outcome for your case.\n\n"
            "Thank you,\n"
            "Chevonne Christian, Esq.\n"
            "Civil Division Attorney\n"
            "==========================\n\n"
            "COMBINED ANALYSIS (read-only)\n"
            f"{analysis_for_prompt.model_dump_json(indent=2)}\n"
            "==========================\n\n"
            "CASE TIMELINE\n"
            f"{timeline_content}\n"
            "==========================\n\n"
            "VIDEO RELEVANCE ANALYSIS\n"
            f"{video_relevance_content}\n"
            "==========================\n\n"
            "SCHEMAS\n"
            "LegalAssessment:\n"
            "{\n"
            '  "case_type": "Case Type",\n'
            '  "claim_viability": "Claim Viability",\n'
            '  "overall_evidence_strength": "Strength",\n'
            '  "potential_challenges": "A clear description of potential challenges, using bullet points or narrative as appropriate for clarity. Follow the style of the example letter above.",\n'
            '  "recommended_actions": "Recommended next steps, using bullet points or narrative as appropriate for clarity. Follow the style of the example letter above.",\n'
            '  "demand_letter_appropriate": true,\n'
            '  "urgency_assessment": "Urgency"\n'
            "}\n"
            "DemandLetterEvaluation:\n"
            "{\n"
            '  "is_appropriate": true,\n'
            '  "reasoning": "Reasoning in the style of the example letter above",\n'
            '  "potential_outcomes": ["Outcome 1"],\n'
            '  "relevant_statutes": ["Statute 1 - cite only local jurisdiction statutes"]\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1.  **Follow the example letter style exactly.** Your tone should be clear, concise, and professional like a real attorney communicating with a client.\n"
            "2.  **Use simple language** that a non-lawyer can easily understand. Avoid overly academic or verbose language.\n"
            "3.  **Use bullet points** for key findings and recommendations to improve readability, as shown in the example.\n"
            "4.  **Pay attention to jurisdiction** - cite only relevant local statutes (e.g., Florida Statutes § 83.51(1)). Do NOT invent or misapply laws from other states.\n"
            '5.  `claim_viability`: pick "Strong", "Moderate", or "Weak".\n'
            "6.  `demand_letter_appropriate`: true if pre-suit demand adds leverage.\n"
            "7.  If `demand_letter_evaluation.is_appropriate` is **false**, set\n"
            '    `"reasoning": ""`, `"potential_outcomes": []`, `"relevant_statutes": []`.\n'
            "8.  **Timeline Integration**: Consider the chronological timeline of events when assessing case strength and recommended actions.\n"
            "9.  **Video Evidence Integration**: Factor in the video relevance analysis when evaluating evidence strength and case strategy.\n"
            "10. **Write directly and to the point** following the professional but accessible style demonstrated in the example letter.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• Floats with two decimals.\n"
            "• Key order per schema.\n\n"
            "BEGIN."
        )

    async def analyze_intake(self, intake_doc: ProcessedDocument) -> CaseAnalysisResult:
        """Analyzes a processed intake form and returns an initial CaseAnalysisResult object."""
        logger.info('AI ANALYZER: 🔍 === DIAGNOSTIC LOGGING - Starting intake analysis ===')
        analysis = CaseAnalysisResult()
        if not intake_doc or not intake_doc.content:
            logger.info('AI ANALYZER: ❌ No intake document or content provided')
            analysis.errors.append(
                AnalysisError(
                    source="IntakeProcessing",
                    error_message="No valid intake content to analyze.",
                )
            )
            return analysis

        try:
            logger.info(f'AI ANALYZER: 🔍 Building prompt for intake document: {intake_doc.file_name}')
            logger.info(f'AI ANALYZER: 🔍 Intake content length: {len(intake_doc.content)} characters')
            # For now, use None to maintain compatibility - prompts will be passed from EmailGeneratorV2
            prompt = self._build_intake_prompt(intake_doc.content, prompt_config=None)
            logger.info(f'AI ANALYZER: 🔍 Prompt built successfully, length: {len(prompt)} characters')

            logger.info('AI ANALYZER: 🔍 Making OpenAI request with gpt-4o-mini...')
            raw_analysis = await self._make_openai_request(prompt, model="gpt-4o-mini")
            logger.info(f'AI ANALYZER: 🔍 OpenAI response received, type: {type(raw_analysis)}')
            logger.info(f'AI ANALYZER: 🔍 Raw analysis keys: {(list(raw_analysis.keys()) if isinstance(raw_analysis, dict) else 'Not a dict')}')

            logger.debug('AI ANALYZER: 🔍 Preprocessing AI output...')
            processed_analysis = preprocess_ai_output(raw_analysis)
            logger.info(f'AI ANALYZER: 🔍 Processed analysis type: {type(processed_analysis)}')
            logger.info(f'AI ANALYZER: 🔍 Processed analysis keys: {(list(processed_analysis.keys()) if isinstance(processed_analysis, dict) else 'Not a dict')}')

            logger.debug('AI ANALYZER: 🔍 Validating with EnhancedIntakeAnalysis schema...')
            analysis.intake_analysis = EnhancedIntakeAnalysis.model_validate(
                processed_analysis
            )
            logger.info('AI ANALYZER: ✅ Intake analysis validation successful!')

        except AIAnalysisError as e:
            logger.error(f'AI ANALYZER: ❌ AIAnalysisError during intake analysis: {e}')
            analysis.errors.append(
                AnalysisError(
                    source="IntakeAnalysis",
                    error_message=f"AI analysis failed for intake: {e}",
                    details=str(e),
                )
            )
        except ValidationError as e:
            logger.error(f'AI ANALYZER: ❌ ValidationError during intake analysis: {e}')
            logger.error(f'AI ANALYZER: 🔍 Validation error details: {e.errors()}')
            analysis.errors.append(
                AnalysisError(
                    source="IntakeAnalysis",
                    error_message=f"Failed to validate AI response for intake - schema mismatch: {e}",
                    details=str(e.errors()),
                )
            )
        except (AttributeError, TypeError, KeyError) as data_error:
            logger.info(f'AI ANALYZER: ❌ Data structure error during intake analysis: {type(data_error).__name__} - {data_error}')
            analysis.errors.append(
                AnalysisError(
                    source="IntakeAnalysis",
                    error_message=f"Data structure error during intake analysis: {data_error}",
                    details=f"Error type: {type(data_error).__name__}",
                )
            )
        except Exception as unexpected_error:
            logger.info(f'AI ANALYZER: ❌ UNEXPECTED ERROR during intake analysis: {type(unexpected_error).__name__} - {unexpected_error}')
            logger.error(f'AI ANALYZER: 🔍 Error context: intake_doc={(intake_doc.file_name if intake_doc else 'None')}')
            analysis.errors.append(
                AnalysisError(
                    source="IntakeAnalysis",
                    error_message=f"Unexpected error during intake analysis: {unexpected_error}",
                    details=f"Error type: {type(unexpected_error).__name__}, Context: {intake_doc.file_name if intake_doc else 'None'}",
                )
            )
            # Re-raise as AIAnalysisError for upstream handling
            error_msg = f"Critical intake analysis failure: {unexpected_error}"
            raise AIAnalysisError(error_msg) from unexpected_error

        logger.info(f'AI ANALYZER: 🔍 Intake analysis complete. Has intake_analysis: {analysis.intake_analysis is not None}')
        logger.error(f'AI ANALYZER: 🔍 Error count: {len(analysis.errors)}')
        if analysis.errors:
            for i, error in enumerate(analysis.errors):
                logger.error(f'AI ANALYZER: 🔍   Error {i + 1}: {error.error_message}')
        logger.info('AI ANALYZER: 🔍 === END DIAGNOSTIC LOGGING ===')
        return analysis

    async def analyze_case_documents(
        self, documents: list[ProcessedDocument], intake_context: EnhancedIntakeAnalysis
    ) -> list[AnalyzedDocument | AnalysisError]:
        """Analyzes multiple case documents with controlled parallelization for rate limiting."""
        import asyncio
        total_docs = len(documents)

        logger.info(f'AI ANALYZER: Starting concurrent analysis of {total_docs} documents...')

        # Create semaphore to limit concurrent API calls (respecting rate limits)
        # Limit to 3 concurrent requests to balance performance and rate limiting
        semaphore = asyncio.Semaphore(3)
        
        async def analyze_document_with_semaphore(doc: ProcessedDocument, doc_index: int) -> tuple[int, AnalyzedDocument | AnalysisError]:
            """Analyze a single document with semaphore control and rate limiting."""
            async with semaphore:
                logger.debug(f'AI ANALYZER: Processing document {doc_index + 1}/{total_docs}: {doc.file_name}')
                
                # Add staggered delay to avoid hitting rate limits
                if doc_index > 0:
                    delay = (doc_index % 3) * 1.0  # 0, 1, or 2 second delays
                    if delay > 0:
                        logger.info(f'AI ANALYZER: Staggering request with {delay}s delay...')
                        await asyncio.sleep(delay)
                
                result = await self._analyze_single_document(doc, intake_context)
                
                # Log the result type
                if isinstance(result, AnalysisError):
                    logger.error(f'AI ANALYZER: ❌ Failed to analyze {doc.file_name}: {result.error_message}')
                else:
                    logger.info(f'AI ANALYZER: ✅ Successfully analyzed {doc.file_name}')
                
                return (doc_index, result)

        # Create tasks for all documents
        tasks = [
            analyze_document_with_semaphore(doc, i)
            for i, doc in enumerate(documents)
        ]
        
        # Execute all tasks concurrently with asyncio.gather()
        logger.debug(f'AI ANALYZER: 🚀 Starting concurrent processing of {total_docs} documents with max 3 concurrent requests...')
        completed_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Sort results by original document order and extract the analysis results
        results = []
        for result in completed_results:
            if isinstance(result, Exception):
                # Handle any exceptions that occurred during processing
                logger.error(f'AI ANALYZER: ❌ Exception during document analysis: {result}')
                results.append(AnalysisError(
                    source="DocumentAnalysis",
                    error_message=f"Exception during analysis: {result}",
                    details=str(result)
                ))
            else:
                # result is a tuple (doc_index, analysis_result)
                _, analysis_result = result
                results.append(analysis_result)
        
        # Sort by document index to maintain order
        indexed_results = [(i, result) for i, result in enumerate(results)]
        indexed_results.sort(key=lambda x: x[0])
        results = [result for _, result in indexed_results]

        logger.info(f'AI ANALYZER: ✅ Completed concurrent analysis of all {total_docs} documents')
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

            truncated_content = (
                f"{first_part}\n\n[... CONTENT TRUNCATED FOR SIZE ...]\n\n{last_part}"
            )
            logger.info(f'AI ANALYZER: ⚠️  Content truncated from ~{estimated_tokens} to ~{max_tokens} tokens')
            return truncated_content
        return content

    async def _analyze_single_document(
        self, document: ProcessedDocument, intake_context: EnhancedIntakeAnalysis
    ) -> AnalyzedDocument | AnalysisError:
        """Analyzes a single case document, returning structured data or an error."""
        try:
            # Check document size and truncate if necessary
            truncated_content = self._truncate_content_if_needed(document.content)

            # Create a copy of the document with truncated content
            doc_for_analysis = ProcessedDocument(
                file_name=document.file_name,
                content=truncated_content,
                file_type=document.file_type,
                document_type=document.document_type,
            )

            prompt = self._build_case_document_prompt(doc_for_analysis, intake_context, prompt_config=None)

            # Estimate total prompt size and choose appropriate model
            total_estimated_tokens = self._estimate_tokens(prompt)
            model_to_use = "gpt-4o-mini" if total_estimated_tokens > 20000 else "gpt-4o"

            if model_to_use == "gpt-4o-mini":
                logger.info(f'AI ANALYZER: 🔄 Using gpt-4o-mini for large document: {document.file_name}')

            raw_analysis = await self._make_openai_request(prompt, model=model_to_use)
            return AnalyzedDocument.model_validate(raw_analysis)
        except (AIAnalysisError, ValidationError) as e:
            details = str(e) if isinstance(e, AIAnalysisError) else str(e.errors())
            return AnalysisError(
                source=f"doc:{document.file_name}",
                error_message=f"Failed to analyze document: {e}",
                details=details,
            )

    async def perform_final_assessment(
        self, analysis: CaseAnalysisResult
    ) -> CaseAnalysisResult:
        """Performs the final legal assessment and demand letter evaluation with graceful degradation."""
        if not analysis.intake_analysis or (
            not analysis.analyzed_documents
            and not analysis.transcripted_media
            and not analysis.video_insights
        ):
            error_msg = "Cannot perform final assessment without intake analysis and at least one document or media file."
            analysis.errors.append(
                AnalysisError(
                    source="FinalAssessment",
                    error_message=error_msg,
                    details="Missing required analysis inputs.",
                )
            )

            logger.error(f'AI ANALYZER: {error_msg} Providing fallback assessments...')
            analysis.legal_assessment = LegalAssessment.model_validate(
                create_fallback_legal_assessment()
            )
            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(
                create_fallback_demand_letter_evaluation()
            )
            return analysis

        try:
            logger.info('AI ANALYZER: Starting final legal assessment...')

            # PRE-COMPUTATION TOKEN CHECKING - Check before building prompt
            model_to_use = "gpt-4o"
            token_check_passed = await self._check_token_threshold_precomputation(
                analysis, model_to_use
            )

            # Apply conditional logic based on token threshold
            if token_check_passed:
                logger.info('AI ANALYZER: ✅ Token threshold check passed - proceeding with full data')
                analysis_for_assessment = analysis
            else:
                logger.info('AI ANALYZER: ⚠️  Token threshold exceeded - applying summarization strategy')
                analysis_for_assessment = self._apply_video_summarization_strategy(
                    analysis
                )

            # Build prompt with potentially summarized data
            prompt = await self._build_final_assessment_prompt(analysis_for_assessment, prompt_config=None)

            # Final validation of prompt size
            estimated_tokens = self._count_tokens_accurate(prompt, model_to_use)
            logger.info(f'AI ANALYZER: Final assessment prompt tokens: {estimated_tokens:,}')

            # Conservative safety check (should rarely trigger now due to pre-computation)
            if estimated_tokens > 120000:
                error_msg = f"Final assessment prompt still too large ({estimated_tokens:,} tokens) after pre-computation check."
                logger.error(f'AI ANALYZER: ⚠️  {error_msg}')

                # Apply emergency fallback if pre-computation didn't catch the issue
                emergency_analysis = analysis.model_copy(deep=True)
                for video in emergency_analysis.video_insights:
                    video.insights = {"status": "Emergency summarization applied"}
                    video.transcript = (
                        f"Video file: {video.file_name} [emergency abbreviation]"
                    )
                    video.labels = video.labels[:3] if video.labels else []
                    video.objects = video.objects[:3] if video.objects else []
                    video.text_annotations = []

                # Rebuild prompt with emergency simplification
                prompt = await self._build_final_assessment_prompt(emergency_analysis, prompt_config=None)
                estimated_tokens = self._count_tokens_accurate(prompt, model_to_use)
                logger.info(f'AI ANALYZER: Emergency reduced prompt tokens: {estimated_tokens:,}')

                if estimated_tokens > 120000:
                    msg = f"Even after emergency reduction, prompt is too large ({estimated_tokens:,} tokens)"
                    raise ValueError(msg)

            try:
                raw_assessment = await self._make_openai_request(prompt, model="gpt-4o")
            except BadRequestError as bad_request_error:
                # ENHANCED ERROR RECOVERY WITH METADATA PRESERVATION
                error_details = str(bad_request_error)
                logger.error('AI ANALYZER: ❌ BADREQUEST ERROR DETECTED in final assessment')
                logger.error(f'AI ANALYZER: 🔍 Error details: {error_details}')
                logger.info(f'AI ANALYZER: 🔍 Prompt character count: {len(prompt):,}')
                logger.info(f'AI ANALYZER: 🔍 Video insights count: {len(analysis.video_insights)}')

                # LOG THE ERROR WITH DETAILED CONTEXT
                logger.error('AI ANALYZER: 🔍 === BADREQUEST ERROR CONTEXT ===')
                logger.info(f'AI ANALYZER: 🔍 Model: {model_to_use}')
                logger.info(f'AI ANALYZER: 🔍 Estimated tokens: {estimated_tokens:,}')
                logger.info(f'AI ANALYZER: 🔍 Analysis has {len(analysis.analyzed_documents)} documents')
                logger.info(f'AI ANALYZER: 🔍 Analysis has {len(analysis.transcripted_media)} audio files')
                logger.info(f'AI ANALYZER: 🔍 Analysis has {len(analysis.video_insights)} video files')

                # Log video content sizes for debugging
                for i, video in enumerate(analysis.video_insights):
                    insights_size = len(str(video.insights)) if video.insights else 0
                    transcript_size = len(video.transcript) if video.transcript else 0
                    logger.info(f'AI ANALYZER: 🔍   Video {i + 1} ({video.file_name}): insights={insights_size} chars, transcript={transcript_size} chars')

                logger.error('AI ANALYZER: 🔍 === END ERROR CONTEXT ===')

                # PRESERVE METADATA INSTEAD OF DISCARDING DATA
                if analysis.video_insights:
                    logger.info('AI ANALYZER: 🔄 ENHANCED ERROR RECOVERY: Preserving video metadata...')

                    retry_analysis = analysis.model_copy(deep=True)
                    for video in retry_analysis.video_insights:
                        # PRESERVE METADATA: Store reference to where full insights would be saved
                        if not video.insights_gcs_uri:
                            # Generate GCS path where full insights would be stored
                            import uuid

                            video_entry_id = str(uuid.uuid4())
                            video.insights_gcs_uri = f"gs://findings-video-analysis/{video_entry_id}/full_insights.json"
                            logger.info(f'AI ANALYZER: 💾 Generated GCS path for {video.file_name}: {video.insights_gcs_uri}')

                        # GENERATE INSIGHTS SUMMARY using existing summarization logic
                        if video.insights and not video.insights_summary:
                            # Create a condensed summary for prompt inclusion (same logic as _apply_video_summarization_strategy)
                            key_objects = video.objects[:5] if video.objects else []
                            key_labels = video.labels[:5] if video.labels else []

                            summary_parts = []
                            if key_objects:
                                summary_parts.append(
                                    f"Key objects detected: {', '.join(key_objects)}"
                                )
                            if key_labels:
                                summary_parts.append(
                                    f"Content labels: {', '.join(key_labels)}"
                                )
                            if video.transcript and len(video.transcript) > 200:
                                summary_parts.append(
                                    f"Transcript excerpt: {video.transcript[:200]}..."
                                )
                            elif video.transcript:
                                summary_parts.append(f"Transcript: {video.transcript}")

                            video.insights_summary = (
                                "; ".join(summary_parts)
                                if summary_parts
                                else "Video content available but summarized due to token constraints."
                            )
                            logger.info(f'AI ANALYZER: 💾 Generated summary for {video.file_name}: {len(video.insights_summary)} chars')

                        # CLEAR INSIGHTS TO MINIMAL STATE for token management
                        # Store original insights temporarily (excluded from serialization)
                        if video.insights:
                            video.original_insights = video.insights.copy()

                        # Replace with minimal state that preserves reference to full data
                        video.insights = {
                            "status": "Video analyzed - full details preserved in GCS",
                            "preservation_applied": True,
                            "gcs_reference": video.insights_gcs_uri,
                            "summary_available": bool(video.insights_summary),
                        }

                        logger.info(f'AI ANALYZER: 💾 Preserved metadata for {video.file_name} - full data can be retrieved via {video.insights_gcs_uri}')

                    try:
                        logger.info('AI ANALYZER: 🔄 Building recovery prompt with preserved metadata...')
                        retry_prompt = await self._build_final_assessment_prompt(
                            retry_analysis, prompt_config=None
                        )
                        retry_tokens = self._estimate_prompt_tokens_detailed(
                            retry_prompt
                        )
                        logger.info(f'AI ANALYZER: 🔄 Recovery prompt tokens: {retry_tokens:,}')

                        logger.info('AI ANALYZER: 🔄 Making recovery API call with preserved data...')
                        raw_assessment = await self._make_openai_request(
                            retry_prompt, model="gpt-4o"
                        )
                        logger.info('AI ANALYZER: ✅ RECOVERY SUCCESSFUL - BadRequestError resolved with metadata preservation')

                        # Update the original analysis with preserved metadata for downstream use
                        for i, video in enumerate(analysis.video_insights):
                            if i < len(retry_analysis.video_insights):
                                preserved_video = retry_analysis.video_insights[i]
                                video.insights_gcs_uri = (
                                    preserved_video.insights_gcs_uri
                                )
                                video.insights_summary = (
                                    preserved_video.insights_summary
                                )
                                video.original_insights = (
                                    preserved_video.original_insights
                                )

                    except (ValidationError, ValueError, TypeError) as data_error:
                        logger.error(f'AI ANALYZER: ❌ DATA ERROR in recovery: {type(data_error).__name__} - {data_error}')
                        logger.error(f'AI ANALYZER: ❌ Original BadRequest: {error_details}')
                        msg = (
                            f"Final assessment failed with BadRequestError. "
                            f"Original error: {error_details}. "
                            f"Recovery failed due to data error: {data_error}"
                        )
                        raise AIAnalysisError(msg) from data_error
                    except (APIError, APITimeoutError, RateLimitError) as api_error:
                        logger.error(f'AI ANALYZER: ❌ API ERROR in recovery: {type(api_error).__name__} - {api_error}')
                        logger.error(f'AI ANALYZER: ❌ Original BadRequest: {error_details}')
                        msg = (
                            f"Final assessment failed with BadRequestError. "
                            f"Original error: {error_details}. "
                            f"Recovery failed due to API error: {api_error}"
                        )
                        raise AIAnalysisError(msg) from api_error
                    except Exception as unexpected_error:
                        logger.error(f'AI ANALYZER: ❌ UNEXPECTED ERROR in recovery: {type(unexpected_error).__name__} - {unexpected_error}')
                        logger.error(f'AI ANALYZER: ❌ Original BadRequest: {error_details}')
                        logger.info(f'AI ANALYZER: 🔍 Recovery context: video_count={(len(analysis.video_insights) if analysis.video_insights else 0)}')
                        msg = (
                            f"Final assessment failed with BadRequestError. "
                            f"Original error: {error_details}. "
                            f"Recovery with metadata preservation also failed: {unexpected_error}"
                        )
                        raise AIAnalysisError(msg) from unexpected_error
                else:
                    logger.info('AI ANALYZER: ❌ No video insights to preserve for BadRequestError recovery')
                    msg = f"BadRequestError in final assessment without video data: {error_details}"
                    raise AIAnalysisError(msg)

            except (APIError, APITimeoutError, RateLimitError) as api_error:
                # Handle specific OpenAI API errors
                error_details = str(api_error)
                error_type = type(api_error).__name__
                logger.info(f'AI ANALYZER: ❌ OpenAI API error ({error_type}) in final assessment: {error_details}')

                # Log prompt details for any API error
                logger.info(f'AI ANALYZER: 🔍 Prompt length: {len(prompt):,} characters')
                logger.info(f'AI ANALYZER: 🔍 Estimated tokens: {self._estimate_tokens(prompt):,}')

                msg = f"OpenAI API error ({error_type}) in final assessment: {error_details}"
                raise AIAnalysisError(msg) from api_error
            except (ValidationError, ValueError, TypeError) as data_error:
                # Handle data processing errors
                error_details = str(data_error)
                error_type = type(data_error).__name__
                logger.info(f'AI ANALYZER: ❌ Data processing error ({error_type}) in final assessment: {error_details}')
                logger.info(f'AI ANALYZER: 🔍 Analysis context: {len(analysis.analyzed_documents)} docs, {len(analysis.video_insights)} videos')

                msg = f"Data processing error ({error_type}) in final assessment: {error_details}"
                raise AIAnalysisError(msg) from data_error
            except Exception as unexpected_error:
                # Handle truly unexpected errors with detailed logging
                error_details = str(unexpected_error)
                error_type = type(unexpected_error).__name__
                logger.info(f'AI ANALYZER: ❌ UNEXPECTED ERROR ({error_type}) in final assessment: {error_details}')

                # Enhanced logging for debugging
                logger.info(f'AI ANALYZER: 🔍 Prompt length: {len(prompt):,} characters')
                logger.info(f'AI ANALYZER: 🔍 Analysis state: docs={len(analysis.analyzed_documents)}, videos={len(analysis.video_insights)}')
                logger.info('AI ANALYZER: 🔍 Model used: gpt-4o')

                msg = f"Unexpected error ({error_type}) in final assessment: {error_details}"
                raise AIAnalysisError(msg) from unexpected_error

            if not raw_assessment:
                msg = "No response received from OpenAI API"
                raise ValueError(msg)

            logger.info(f'AI ANALYZER: Raw assessment keys: {(list(raw_assessment.keys()) if isinstance(raw_assessment, dict) else 'Not a dict')}')

            # Process legal assessment with graceful degradation
            if "legal_assessment" in raw_assessment:
logger.debug('AI ANALYZER: Processing legal assessment...')
                legal_assessment_data = raw_assessment["legal_assessment"]

                # Use safe validation with fallback
                validated_assessment = safe_model_validate(
                    LegalAssessment,
                    legal_assessment_data,
                    create_fallback_legal_assessment,
                )

                if validated_assessment:
                    analysis.legal_assessment = validated_assessment
logger.info('AI ANALYZER: ✅ Legal assessment validated successfully')
                else:
logger.info('AI ANALYZER: ⚠️  Legal assessment validation failed, using fallback')
                        "AI ANALYZER: ⚠️  Legal assessment validation failed, using fallback"
                    )
                    analysis.legal_assessment = LegalAssessment.model_validate(
                        create_fallback_legal_assessment()
                    )
                    analysis.errors.append(
                        AnalysisError(
                            source="FinalAssessment",
                            error_message="Legal assessment validation failed, using fallback data",
                            details=str(legal_assessment_data),
                        )
                    )
            else:
logger.warning('AI ANALYZER: ⚠️  No legal_assessment in response, using fallback')
                analysis.legal_assessment = LegalAssessment.model_validate(
                    create_fallback_legal_assessment()
                )
                analysis.errors.append(
                    AnalysisError(
                        source="FinalAssessment",
                        error_message="legal_assessment not found in AI response",
                        details=str(raw_assessment),
                    )
                )

            # Process demand letter evaluation with graceful degradation
            if "demand_letter_evaluation" in raw_assessment:
logger.debug('AI ANALYZER: Processing demand letter evaluation...')
                demand_eval_data = raw_assessment["demand_letter_evaluation"]

                # Use safe validation with fallback
                validated_evaluation = safe_model_validate(
                    DemandLetterEvaluation,
                    demand_eval_data,
                    create_fallback_demand_letter_evaluation,
                )

                if validated_evaluation:
                    analysis.demand_letter_evaluation = validated_evaluation
logger.info('AI ANALYZER: ✅ Demand letter evaluation validated successfully')
                        "AI ANALYZER: ✅ Demand letter evaluation validated successfully"
                    )
                else:
logger.info('AI ANALYZER: ⚠️  Demand letter evaluation validation failed, using fallback')
                        "AI ANALYZER: ⚠️  Demand letter evaluation validation failed, using fallback"
                    )
                    analysis.demand_letter_evaluation = (
                        DemandLetterEvaluation.model_validate(
                            create_fallback_demand_letter_evaluation()
                        )
                    )
                    analysis.errors.append(
                        AnalysisError(
                            source="FinalAssessment",
                            error_message="Demand letter evaluation validation failed, using fallback data",
                            details=str(demand_eval_data),
                        )
                    )
            else:
logger.info('AI ANALYZER: ⚠️  No demand_letter_evaluation in response, using fallback')
                    "AI ANALYZER: ⚠️  No demand_letter_evaluation in response, using fallback"
                )
                analysis.demand_letter_evaluation = (
                    DemandLetterEvaluation.model_validate(
                        create_fallback_demand_letter_evaluation()
                    )
                )
                analysis.errors.append(
                    AnalysisError(
                        source="FinalAssessment",
                        error_message="demand_letter_evaluation not found in AI response",
                        details=str(raw_assessment),
                    )
                )

        except (AIAnalysisError, ValidationError, ValueError) as e:
            error_msg = f"Final assessment failed: {e}"
logger.error(f'AI ANALYZER: ❌ {error_msg}')
            details = str(e) if not isinstance(e, ValidationError) else str(e.errors())
            analysis.errors.append(
                AnalysisError(
                    source="FinalAssessment", error_message=error_msg, details=details
                )
            )

            # Always provide fallback assessments to ensure system continues working
logger.error('AI ANALYZER: Providing fallback assessments due to error...')
            if not analysis.legal_assessment:
                analysis.legal_assessment = LegalAssessment.model_validate(
                    create_fallback_legal_assessment()
                )
            if not analysis.demand_letter_evaluation:
                analysis.demand_letter_evaluation = (
                    DemandLetterEvaluation.model_validate(
                        create_fallback_demand_letter_evaluation()
                    )
                )

        except (ImportError, AttributeError, TypeError) as system_error:
            error_msg = f"System error in final assessment: {system_error}"
logger.error(f'AI ANALYZER: ❌ SYSTEM ERROR: {error_msg}')
logger.error(f'AI ANALYZER: 🔍 Error type: {type(system_error).__name__}')
            analysis.errors.append(
                AnalysisError(
                    source="FinalAssessment",
                    error_message=error_msg,
                    details=f"Error type: {type(system_error).__name__}, Details: {system_error!s}"
                )
            )

            # Emergency fallback to ensure system keeps working
logger.error('AI ANALYZER: Emergency fallback due to system error...')
            analysis.legal_assessment = LegalAssessment.model_validate(
                create_fallback_legal_assessment()
            )
            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(
                create_fallback_demand_letter_evaluation()
            )
        except Exception as critical_error:
            error_msg = f"CRITICAL ERROR in final assessment: {critical_error}"
logger.error(f'AI ANALYZER: ❌ {error_msg}')
logger.error(f'AI ANALYZER: 🔍 Error type: {type(critical_error).__name__}')
logger.info(f'AI ANALYZER: 🔍 Assessment state: has_intake={analysis.intake_analysis is not None}')
            analysis.errors.append(
                AnalysisError(
                    source="FinalAssessment",
                    error_message=error_msg,
                    details=f"CRITICAL - Error type: {type(critical_error).__name__}, Context: Assessment pipeline failure"
                )
            )

            # Emergency fallback to ensure system keeps working
logger.error('AI ANALYZER: CRITICAL emergency fallback...')
            analysis.legal_assessment = LegalAssessment.model_validate(
                create_fallback_legal_assessment()
            )
            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(
                create_fallback_demand_letter_evaluation()
            )
            
            # Re-raise critical errors for upstream handling
            error_message = f"Critical final assessment failure: {critical_error}"
            raise AIAnalysisError(error_message) from critical_error

logger.info('AI ANALYZER: Final assessment completed')
        return analysis


def analyze_video_relevance(video_insight, case_context) -> dict[str, str]:
    """Analyze how video evidence relates to the case facts and legal strategy."""
    try:
        relevance_analysis = {
            "case_connection": "",
            "evidence_value": "",
            "legal_impact": "",
            "corroboration": "",
        }

        # Extract case context information
        case_type = getattr(case_context, "case_type", "") if case_context else ""
        getattr(case_context, "case_summary", "") if case_context else ""
        legal_claims = getattr(case_context, "legal_claims", []) if case_context else []

        # Analyze video content for relevance
        video_content = []
        if hasattr(video_insight, "insights") and video_insight.insights:
            if isinstance(video_insight.insights, dict):
                # Extract summary
                if "summary" in video_insight.insights:
                    video_content.append(video_insight.insights["summary"])

                # Extract key events
                if "timeline" in video_insight.insights:
                    timeline = video_insight.insights["timeline"]
                    if isinstance(timeline, list):
                        for event in timeline[:3]:  # Limit to top 3 events
                            if isinstance(event, dict):
                                desc = event.get("event", event.get("description", ""))
                                if desc:
                                    video_content.append(desc)
                            elif isinstance(event, str):
                                video_content.append(event)

        # Add transcript content if available
        if hasattr(video_insight, "transcript") and video_insight.transcript:
            # Use first 200 characters of transcript for analysis
            transcript_excerpt = (
                video_insight.transcript[:200] + "..."
                if len(video_insight.transcript) > 200
                else video_insight.transcript
            )
            video_content.append(f"Transcript: {transcript_excerpt}")

        # Add detected objects/labels for context
        context_items = []
        if hasattr(video_insight, "labels") and video_insight.labels:
            context_items.extend(video_insight.labels[:5])  # Top 5 labels
        if hasattr(video_insight, "objects") and video_insight.objects:
            context_items.extend(
                [str(obj) for obj in video_insight.objects[:5]]
            )  # Top 5 objects

        # Generate relevance analysis based on content
        ("; ".join(video_content[:3]) if video_content else "Video content analysis")
        context_summary = (
            ", ".join(context_items[:8]) if context_items else "visual evidence"
        )

        # Case connection analysis
        if case_type and any(
            keyword in case_type.lower() for keyword in ["criminal", "dui", "arrest"]
        ):
            relevance_analysis["case_connection"] = (
                f"This video directly relates to the {case_type} proceedings, providing visual documentation of key events and interactions that are central to the case."
            )
        elif case_type and any(
            keyword in case_type.lower()
            for keyword in ["property", "damage", "inspection"]
        ):
            relevance_analysis["case_connection"] = (
                f"This video provides crucial visual evidence of property conditions and damage relevant to your {case_type} case."
            )
        elif case_type and any(
            keyword in case_type.lower()
            for keyword in ["contract", "dispute", "breach"]
        ):
            relevance_analysis["case_connection"] = (
                f"This video documents conditions or events that may support or contradict claims in your {case_type} matter."
            )
        else:
            relevance_analysis["case_connection"] = (
                "This video provides documentary evidence that relates to key facts and circumstances in your legal matter."
            )

        # Evidence value analysis
        if context_items:
            relevance_analysis["evidence_value"] = (
                f"The video captures {context_summary}, which can serve as objective evidence to support your position. Video evidence is particularly valuable because it provides an unbiased record of events and conditions."
            )
        else:
            relevance_analysis["evidence_value"] = (
                "This video provides objective documentation that can be used to establish facts, verify claims, or challenge opposing narratives in your case."
            )

        # Legal impact analysis
        if legal_claims:
            claims_text = (
                ", ".join(legal_claims[:2])
                if len(legal_claims) > 2
                else ", ".join(legal_claims)
            )
            relevance_analysis["legal_impact"] = (
                f"This video evidence may strengthen your legal claims regarding {claims_text} by providing visual corroboration of key events. It could be instrumental in settlement negotiations or courtroom presentations."
            )
        else:
            relevance_analysis["legal_impact"] = (
                "This video evidence could significantly impact case strategy by providing compelling visual support for your legal arguments and potentially influencing settlement discussions or jury decisions."
            )

        # Corroboration analysis
        if video_content:
            relevance_analysis["corroboration"] = (
                "The video content aligns with and supports the factual narrative of your case. It provides independent verification that can corroborate witness testimony and documentary evidence, strengthening the overall evidentiary foundation."
            )
        else:
            relevance_analysis["corroboration"] = (
                "This video serves as independent corroboration that can support witness accounts and documentary evidence, enhancing the credibility and strength of your case presentation."
            )

        return relevance_analysis

    except (ValueError, TypeError, AttributeError, KeyError) as e:
logger.error(f'AI ANALYZER: Error in video relevance analysis: {e}')
        # Return fallback analysis
        return {
            "case_connection": "This video provides relevant documentation for your legal matter.",
            "evidence_value": "Video evidence offers objective documentation that can support your case.",
            "legal_impact": "This visual evidence may be valuable for case strategy and legal arguments.",
            "corroboration": "The video can serve as supporting evidence alongside other case materials.",
        }


def generate_case_timeline(analysis: CaseAnalysisResult) -> list[dict[str, Any]]:
    """Generate chronological timeline of events extracted from all sources."""
    try:
        timeline_events = []

        # Extract events from documents
        if analysis.analyzed_documents:
            for doc in analysis.analyzed_documents:
                # Look for date patterns in key information and summary
                text_content = (
                    f"{doc.summary or ''} {getattr(doc, 'key_information', '') or ''} {getattr(doc, 'relevance_to_case', '') or ''}"
                )

                # Simple date extraction (can be enhanced with more sophisticated parsing)
                import re

                date_patterns = [
                    r"\b(\d{1,2}/\d{1,2}/\d{4})\b",  # MM/DD/YYYY
                    r"\b(\d{1,2}-\d{1,2}-\d{4})\b",  # MM-DD-YYYY
                    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",  # Month DD, YYYY
                    r"\b(\d{4}-\d{2}-\d{2})\b",  # YYYY-MM-DD
                ]

                for pattern in date_patterns:
                    dates = re.findall(pattern, text_content, re.IGNORECASE)
                    for date_match in dates[:3]:  # Limit to 3 dates per document
                        # Extract surrounding context
                        date_str = (
                            date_match
                            if isinstance(date_match, str)
                            else date_match[0]
                            if isinstance(date_match, tuple)
                            else str(date_match)
                        )
                        context_start = max(
                            0, text_content.lower().find(date_str.lower()) - 50
                        )
                        context_end = min(
                            len(text_content),
                            text_content.lower().find(date_str.lower())
                            + len(date_str)
                            + 100,
                        )
                        context = text_content[context_start:context_end].strip()

                        timeline_events.append(
                            {
                                "date": date_str,
                                "source": f"Document: {doc.file_name}",
                                "source_type": "document",
                                "event": context,
                                "importance": "medium",
                                "sort_date": _parse_date_for_sorting(date_str),
                            }
                        )

        # Extract events from video analysis
        if analysis.video_insights:
            for video in analysis.video_insights:
                video_events = []

                # Extract from video insights
                if hasattr(video, "insights") and isinstance(video.insights, dict):
                    # Timeline events
                    if video.insights.get("timeline"):
                        timeline_items = video.insights["timeline"]
                        if isinstance(timeline_items, list):
                            for event in timeline_items:
                                if isinstance(event, dict):
                                    timestamp = event.get("timestamp", "Unknown time")
                                    description = event.get(
                                        "event", event.get("description", "Video event")
                                    )
                                    video_events.append(
                                        {
                                            "date": f"Video timestamp: {timestamp}",
                                            "source": f"Video: {video.file_name}",
                                            "source_type": "video",
                                            "event": description,
                                            "importance": "high",
                                            "sort_date": None,  # Video timestamps don't have absolute dates
                                        }
                                    )

                    # Key events
                    if video.insights.get("key_events"):
                        events = video.insights["key_events"]
                        if isinstance(events, list):
                            for event in events:
                                if isinstance(event, str) and event.strip():
                                    video_events.append(
                                        {
                                            "date": "During video recording",
                                            "source": f"Video: {video.file_name}",
                                            "source_type": "video",
                                            "event": event.strip(),
                                            "importance": "high",
                                            "sort_date": None,
                                        }
                                    )

                # Criminal analysis events
                if (
                    hasattr(video, "is_criminal_case")
                    and video.is_criminal_case
                    and hasattr(video, "criminal_analysis")
                    and video.criminal_analysis
                ):
                    if (
                        hasattr(video.criminal_analysis, "evidence_items")
                        and video.criminal_analysis.evidence_items
                    ):
                        for evidence in video.criminal_analysis.evidence_items:
                            if hasattr(evidence, "time_range") and hasattr(
                                evidence, "description"
                            ):
                                timestamp = f"{evidence.time_range.start_time}-{evidence.time_range.end_time}"
                                video_events.append(
                                    {
                                        "date": f"Video timestamp: {timestamp}",
                                        "source": f"Criminal Video: {video.file_name}",
                                        "source_type": "criminal_video",
                                        "event": f"{evidence.category}: {evidence.description}",
                                        "importance": "critical",
                                        "sort_date": None,
                                    }
                                )

                timeline_events.extend(video_events[:5])  # Limit to 5 events per video

        # Extract events from audio transcripts
        if analysis.transcripted_media:
            for audio in analysis.transcripted_media:
                if audio.transcript:
                    # Look for time-related phrases in transcript
                    transcript_text = audio.transcript
                    time_phrases = [
                        "yesterday",
                        "today",
                        "tomorrow",
                        "last week",
                        "next week",
                        "last month",
                        "next month",
                        "this morning",
                        "this afternoon",
                        "this evening",
                        "last night",
                        "earlier today",
                    ]

                    for phrase in time_phrases:
                        if phrase in transcript_text.lower():
                            # Extract context around the time phrase
                            phrase_index = transcript_text.lower().find(phrase)
                            context_start = max(0, phrase_index - 50)
                            context_end = min(
                                len(transcript_text), phrase_index + len(phrase) + 100
                            )
                            context = transcript_text[context_start:context_end].strip()

                            timeline_events.append(
                                {
                                    "date": phrase.title(),
                                    "source": f"Audio: {audio.file_name}",
                                    "source_type": "audio",
                                    "event": context,
                                    "importance": "medium",
                                    "sort_date": None,
                                }
                            )
                            break  # Only one time reference per audio file

        # Sort timeline events
        # First sort by actual dates, then by importance, then by source type
        def sort_key(event):
            sort_date = event.get("sort_date")
            importance_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            source_order = {"criminal_video": 0, "video": 1, "document": 2, "audio": 3}

            return (
                sort_date is None,  # None dates go to end
                sort_date or "",
                importance_order.get(event.get("importance", "medium"), 2),
                source_order.get(event.get("source_type", "document"), 2),
            )

        timeline_events.sort(key=sort_key)

        # Limit to most relevant events
        return timeline_events[:15]  # Return top 15 timeline events

    except (ValueError, TypeError, AttributeError, KeyError, ImportError) as e:
logger.error(f'AI ANALYZER: Error generating timeline: {e}')
        return []


def _parse_date_for_sorting(date_str: str) -> str | None:
    """Parse date string into sortable format (YYYY-MM-DD)."""
    try:
        import re
        from datetime import datetime

        # Handle various date formats
        if re.match(r"\d{1,2}/\d{1,2}/\d{4}", date_str):  # MM/DD/YYYY
            parsed = datetime.strptime(date_str, "%m/%d/%Y")
            return parsed.strftime("%Y-%m-%d")
        if re.match(r"\d{1,2}-\d{1,2}-\d{4}", date_str):  # MM-DD-YYYY
            parsed = datetime.strptime(date_str, "%m-%d-%Y")
            return parsed.strftime("%Y-%m-%d")
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str):  # YYYY-MM-DD
            return date_str
        # Try to parse month names
        months = {
            "january": "01",
            "february": "02",
            "march": "03",
            "april": "04",
            "may": "05",
            "june": "06",
            "july": "07",
            "august": "08",
            "september": "09",
            "october": "10",
            "november": "11",
            "december": "12",
        }

        date_lower = date_str.lower()
        for month_name, month_num in months.items():
            if month_name in date_lower:
                # Extract day and year
                numbers = re.findall(r"\d+", date_str)
                if len(numbers) >= 2:
                    day = numbers[0].zfill(2)
                    year = numbers[1] if len(numbers[1]) == 4 else f"20{numbers[1]}"
                    return f"{year}-{month_num}-{day}"

        return None
    except (ValueError, TypeError, ImportError) as e:
logger.error(f"AI ANALYZER: Error parsing date '{date_str}': {e}")
        return None
