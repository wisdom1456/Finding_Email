"""
Refactored AIAnalyzer - Streamlined orchestrator using modular components.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from openai import OpenAI

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
from backend.utils.validators import (
    create_fallback_demand_letter_evaluation,
    create_fallback_legal_assessment,
    preprocess_ai_output,
    safe_model_validate,
)

from .config_manager import ConfigManager
from .media_processor import MediaProcessor
from .openai_client import OpenAIClient
from .prompt_builder import PromptBuilder
from .timeline_analyzer import TimelineAnalyzer
from .token_manager import TokenManager


if TYPE_CHECKING:
    from ..document_processor import DocumentProcessor


class AIAnalyzer:
    """
    Streamlined orchestrator for AI analysis using modular components.
    
    This class delegates specific functionality to specialized modules:
    - ConfigManager: Configuration loading and management
    - PromptBuilder: AI prompt construction
    - TokenManager: Token counting and size management
    - MediaProcessor: Media file processing and analysis
    - OpenAIClient: OpenAI API interactions
    - TimelineAnalyzer: Timeline creation and analysis
    """

    def __init__(self, client: OpenAI, doc_processor: DocumentProcessor, config_path: str | None = None) -> None:
        """Initialize AIAnalyzer with modular components."""
        # Store core dependencies
        self.client = client
        self.doc_processor = doc_processor
        
        # Initialize modular components
        self.config_manager = ConfigManager(config_path)
        self.prompt_builder = PromptBuilder(self.config_manager)
        self.token_manager = TokenManager()
        self.media_processor = MediaProcessor()
        self.openai_client = OpenAIClient()
        self.timeline_analyzer = TimelineAnalyzer()
        
        print(f"AI ANALYZER: ✅ Initialized with modular architecture using config: {config_path or 'default'}")

    async def analyze_intake(self, intake_doc: ProcessedDocument) -> CaseAnalysisResult:
        """Analyzes a processed intake form and returns an initial CaseAnalysisResult object."""
        print("AI ANALYZER: 🔍 Starting intake analysis with modular architecture")
        analysis = CaseAnalysisResult()
        
        if not intake_doc or not intake_doc.content:
            print("AI ANALYZER: ❌ No intake document or content provided")
            analysis.errors.append(
                AnalysisError(
                    source="IntakeProcessing",
                    error_message="No valid intake content to analyze.",
                )
            )
            return analysis

        try:
            print(f"AI ANALYZER: 🔍 Building intake prompt for: {intake_doc.file_name}")
            
            # Use PromptBuilder to construct the prompt
            prompt = self.prompt_builder.build_intake_prompt(intake_doc.content)
            print(f"AI ANALYZER: 🔍 Prompt built successfully, length: {len(prompt)} characters")

            print("AI ANALYZER: 🔍 Making OpenAI request via OpenAIClient...")
            # Use OpenAIClient for the API interaction
            response = self.openai_client.analyze_intake_form(prompt, model="gpt-4o-mini")
            
            if not response["success"]:
                error_msg = f"OpenAI request failed: {response.get('error', 'Unknown error')}"
                raise AIAnalysisError(error_msg)
            
            raw_analysis = response["content"]
            print("AI ANALYZER: 🔍 OpenAI response received successfully")

            print("AI ANALYZER: 🔍 Preprocessing AI output...")
            # Parse JSON response if needed
            if isinstance(raw_analysis, str):
                json_response = self.openai_client.parse_json_response(raw_analysis)
                if json_response["success"]:
                    processed_analysis = preprocess_ai_output(json_response["data"])
                else:
                    # Fallback to treating the string as the response
                    processed_analysis = preprocess_ai_output(raw_analysis)
            else:
                processed_analysis = preprocess_ai_output(raw_analysis)

            print("AI ANALYZER: 🔍 Validating with EnhancedIntakeAnalysis schema...")
            analysis.intake_analysis = EnhancedIntakeAnalysis.model_validate(processed_analysis)
            print("AI ANALYZER: ✅ Intake analysis validation successful!")

        except AIAnalysisError as e:
            print(f"AI ANALYZER: ❌ AIAnalysisError during intake analysis: {e}")
            analysis.errors.append(
                AnalysisError(
                    source="IntakeAnalysis",
                    error_message=f"AI analysis failed for intake: {e}",
                    details=str(e),
                )
            )
        except Exception as e:
            print(f"AI ANALYZER: ❌ Unexpected error during intake analysis: {e}")
            analysis.errors.append(
                AnalysisError(
                    source="IntakeAnalysis",
                    error_message=f"Unexpected error during intake analysis: {e}",
                    details=f"Error type: {type(e).__name__}",
                )
            )
            
            # Re-raise critical errors
            error_msg = f"Critical intake analysis failure: {e}"
            raise AIAnalysisError(error_msg) from e

        print(f"AI ANALYZER: 🔍 Intake analysis complete. Success: {analysis.intake_analysis is not None}")
        return analysis

    async def analyze_case_documents(
        self, documents: list[ProcessedDocument], intake_context: EnhancedIntakeAnalysis
    ) -> list[AnalyzedDocument | AnalysisError]:
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
            if i < total_docs:
                print("AI ANALYZER: Waiting 3 seconds before next document...")
                await asyncio.sleep(3)

        print(f"AI ANALYZER: Completed analysis of all {total_docs} documents")
        return results

    async def _analyze_single_document(
        self, document: ProcessedDocument, intake_context: EnhancedIntakeAnalysis
    ) -> AnalyzedDocument | AnalysisError:
        """Analyzes a single case document, returning structured data or an error."""
        try:
            # Use TokenManager to check and truncate content if needed
            truncated_content = self.token_manager.truncate_content_if_needed(document.content)

            # Create a copy of the document with truncated content
            doc_for_analysis = ProcessedDocument(
                file_name=document.file_name,
                content=truncated_content,
                file_type=document.file_type,
                document_type=document.document_type,
            )

            # Use PromptBuilder to create the prompt
            prompt = self.prompt_builder.build_case_document_prompt(doc_for_analysis, intake_context)

            # Use TokenManager to estimate size and choose model
            total_estimated_tokens = self.token_manager.estimate_tokens(prompt)
            model_to_use = "gpt-4o-mini" if total_estimated_tokens > 20000 else "gpt-4o"

            if model_to_use == "gpt-4o-mini":
                print(f"AI ANALYZER: 🔄 Using gpt-4o-mini for large document: {document.file_name}")

            # Use OpenAIClient for the API interaction
            response = self.openai_client.analyze_case_documents(prompt, model=model_to_use)
            
            if not response["success"]:
                error_msg = f"OpenAI request failed: {response.get('error', 'Unknown error')}"
                raise AIAnalysisError(error_msg)
            
            # Parse and validate the response
            raw_analysis = response["content"]
            if isinstance(raw_analysis, str):
                json_response = self.openai_client.parse_json_response(raw_analysis)
                if json_response["success"]:
                    raw_analysis = json_response["data"]
                else:
                    raise AIAnalysisError(f"Failed to parse JSON response: {json_response.get('error')}")
            
            return AnalyzedDocument.model_validate(raw_analysis)
            
        except (AIAnalysisError, Exception) as e:
            details = str(e)
            return AnalysisError(
                source=f"doc:{document.file_name}",
                error_message=f"Failed to analyze document: {e}",
                details=details,
            )

    async def perform_final_assessment(self, analysis: CaseAnalysisResult) -> CaseAnalysisResult:
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

            print(f"AI ANALYZER: {error_msg} Providing fallback assessments...")
            analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())
            return analysis

        try:
            print("AI ANALYZER: Starting final legal assessment with modular architecture...")

            # Use TokenManager for pre-computation token checking
            model_to_use = "gpt-4o"
            token_check_passed = self.token_manager.check_token_threshold(analysis, model_to_use)

            # Apply conditional logic based on token threshold
            if token_check_passed:
                print("AI ANALYZER: ✅ Token threshold check passed - proceeding with full data")
                analysis_for_assessment = analysis
            else:
                print("AI ANALYZER: ⚠️  Token threshold exceeded - applying summarization strategy")
                analysis_for_assessment = self.token_manager.apply_summarization_strategy(analysis)

            # Create comprehensive timeline using TimelineAnalyzer
            print("AI ANALYZER: Creating comprehensive timeline...")
            timeline_data = self.timeline_analyzer.create_comprehensive_timeline(analysis_for_assessment)
            
            # Generate media summaries concurrently
            summarization_tasks = []
            for media in analysis_for_assessment.transcripted_media:
                summarization_tasks.append(
                    self._summarize_media_with_client(media.transcript, "audio transcript", media.file_name)
                )
            for video in analysis_for_assessment.video_insights:
                summarization_tasks.append(
                    self._summarize_media_with_client(video.insights, "video analysis", video.file_name)
                )

            # Run summarizations concurrently
            if summarization_tasks:
                print("AI ANALYZER: Starting media summarization...")
                summaries = await asyncio.gather(*summarization_tasks)

                # Replace full content with summaries
                summary_idx = 0
                for media in analysis_for_assessment.transcripted_media:
                    media.transcript = summaries[summary_idx]
                    summary_idx += 1
                for video in analysis_for_assessment.video_insights:
                    video.insights = {"summary": summaries[summary_idx]}
                    summary_idx += 1
                print("AI ANALYZER: ✅ Media summarization completed")

            # Use PromptBuilder to create the final assessment prompt
            prompt = self.prompt_builder.build_final_assessment_prompt(analysis_for_assessment, timeline_data)

            # Final validation of prompt size using TokenManager
            estimated_tokens = self.token_manager.count_tokens_accurate(prompt, model_to_use)
            print(f"AI ANALYZER: Final assessment prompt tokens: {estimated_tokens:,}")

            # Conservative safety check
            if estimated_tokens > 120000:
                print(f"AI ANALYZER: ⚠️  Prompt too large ({estimated_tokens:,} tokens), applying emergency truncation")
                analysis_for_assessment = self.token_manager.truncate_video_content_aggressively(analysis_for_assessment)
                prompt = self.prompt_builder.build_final_assessment_prompt(analysis_for_assessment, timeline_data)

            # Use OpenAIClient for the final assessment
            response = self.openai_client.generate_final_assessment(prompt, model=model_to_use)
            
            if not response["success"]:
                error_msg = f"Final assessment failed: {response.get('error', 'Unknown error')}"
                raise AIAnalysisError(error_msg)

            raw_assessment = response["content"]
            
            # Parse JSON response
            if isinstance(raw_assessment, str):
                json_response = self.openai_client.parse_json_response(raw_assessment)
                if json_response["success"]:
                    raw_assessment = json_response["data"]
                else:
                    raise AIAnalysisError(f"Failed to parse final assessment JSON: {json_response.get('error')}")

            # Process legal assessment with graceful degradation
            if "legal_assessment" in raw_assessment:
                print("AI ANALYZER: Processing legal assessment...")
                legal_assessment_data = raw_assessment["legal_assessment"]
                validated_assessment = safe_model_validate(
                    LegalAssessment, legal_assessment_data, create_fallback_legal_assessment
                )
                if validated_assessment:
                    analysis.legal_assessment = validated_assessment
                    print("AI ANALYZER: ✅ Legal assessment validated successfully")
                else:
                    print("AI ANALYZER: ⚠️  Legal assessment validation failed, using fallback")
                    analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
                    analysis.errors.append(
                        AnalysisError(
                            source="FinalAssessment",
                            error_message="Legal assessment validation failed, using fallback data",
                            details=str(legal_assessment_data),
                        )
                    )
            else:
                print("AI ANALYZER: ⚠️  No legal_assessment in response, using fallback")
                analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())

            # Process demand letter evaluation with graceful degradation
            if "demand_letter_evaluation" in raw_assessment:
                print("AI ANALYZER: Processing demand letter evaluation...")
                demand_eval_data = raw_assessment["demand_letter_evaluation"]
                validated_evaluation = safe_model_validate(
                    DemandLetterEvaluation, demand_eval_data, create_fallback_demand_letter_evaluation
                )
                if validated_evaluation:
                    analysis.demand_letter_evaluation = validated_evaluation
                    print("AI ANALYZER: ✅ Demand letter evaluation validated successfully")
                else:
                    print("AI ANALYZER: ⚠️  Demand letter evaluation validation failed, using fallback")
                    analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())
            else:
                print("AI ANALYZER: ⚠️  No demand_letter_evaluation in response, using fallback")
                analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())

        except Exception as e:
            error_msg = f"Final assessment failed: {e}"
            print(f"AI ANALYZER: ❌ {error_msg}")
            analysis.errors.append(
                AnalysisError(source="FinalAssessment", error_message=error_msg, details=str(e))
            )

            # Always provide fallback assessments to ensure system continues working
            print("AI ANALYZER: Providing fallback assessments due to error...")
            if not analysis.legal_assessment:
                analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
            if not analysis.demand_letter_evaluation:
                analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())

        print("AI ANALYZER: Final assessment completed with modular architecture")
        return analysis

    async def _summarize_media_with_client(self, content: dict | str, media_type: str, file_name: str) -> str:
        """Summarize media content using OpenAIClient."""
        print(f"AI ANALYZER: Summarizing {media_type} for {file_name}")
        
        # Use PromptBuilder to create the media summary prompt
        prompt = self.prompt_builder.build_media_summary_prompt(content, media_type, file_name)
        
        # Use OpenAIClient for summarization
        response = self.openai_client.summarize_media(prompt, model="gpt-4o-mini")
        
        if response["success"]:
            return response["content"]
        print(f"AI ANALYZER: ❌ Failed to summarize {media_type} for {file_name}: {response.get('error')}")
        return f"[A {media_type} from {file_name} is available but could not be summarized.]"
