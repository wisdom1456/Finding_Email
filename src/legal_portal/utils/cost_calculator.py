# Cost Calculator Service for Legal Document Analysis Portal.
# This service calculates actual costs incurred during processing based on
# API usage logs, token counts, and processing durations from various services.

from __future__ import annotations

from decimal import Decimal
from typing import Any

from legal_portal.core.data_models import (
    ActualCosts,
    AnalyzedDocument,
    EnhancedVideoInsight,
    ServiceCost,
    TranscriptedMedia,
    VideoInsight,
)


class CostCalculator:
    """Calculate actual processing costs from API usage and processing logs.

    Tracks real costs incurred during document analysis, audio transcription,
    and video processing to provide accurate cost summaries and variance analysis.
    """

    # Current API Pricing Rates (USD) - matches CostEstimator
    PRICING_RATES = {
        # OpenAI Pricing
        "openai_gpt4o": {
            "input_tokens": Decimal("5.00") / Decimal("1000000"),  # $5.00 per 1M tokens
            "output_tokens": Decimal("15.00") / Decimal("1000000"),  # $15.00 per 1M tokens
        },
        "openai_gpt4o_mini": {
            "input_tokens": Decimal("0.15") / Decimal("1000000"),  # $0.15 per 1M tokens
            "output_tokens": Decimal("0.60") / Decimal("1000000"),  # $0.60 per 1M tokens
        },
        "openai_whisper": {
            "per_minute": Decimal("0.006")  # $0.006 per minute
        },
        # Google Cloud Pricing
        "vertex_ai_gemini_flash": {
            "input_tokens": Decimal("0.075") / Decimal("1000000"),  # $0.075 per 1M tokens
            "output_tokens": Decimal("0.30") / Decimal("1000000"),  # $0.30 per 1M tokens
        },
        "vertex_ai_video": {
            "per_minute": Decimal("0.10")  # $0.10 per minute
        },
        "google_speech_to_text": {
            "per_minute": Decimal("0.024")  # $0.024 per minute
        },
    }

    def __init__(self):
        """Initialize the cost calculator."""

    def calculate_document_analysis_costs(
        self,
        analyzed_documents: list[AnalyzedDocument],
        processing_logs: dict[str, Any] | None = None,
    ) -> list[ServiceCost]:
        """Calculate actual costs for document analysis based on processing logs.

        Args:
        ----
            analyzed_documents: List of analyzed documents
            processing_logs: Optional logs containing token usage data

        Returns:
        -------
            List of ServiceCost objects for document analysis

        """
        document_costs = []

        if not processing_logs:
            processing_logs = {}

        for doc in analyzed_documents:
            # Extract actual token usage from logs if available
            doc_log = processing_logs.get(doc.file_name, {})

            if "token_usage" in doc_log:
                # Use actual token counts from OpenAI response
                input_tokens = doc_log["token_usage"].get("prompt_tokens", 0)
                output_tokens = doc_log["token_usage"].get("completion_tokens", 0)
                model_used = doc_log.get("model", "gpt-4o")
            else:
                # Fallback to estimation if logs not available
                analysis_text = doc.analysis if doc.analysis else ""
                key_points_text = " ".join(doc.key_points) if doc.key_points else ""
                full_text = analysis_text + key_points_text
                input_tokens = self._estimate_tokens(full_text)
                output_tokens = len(full_text) // 4
                model_used = "gpt-4o"

            # Determine pricing rates based on model used
            if "gpt-4o-mini" in model_used.lower():
                model_key = "openai_gpt4o_mini"
                model_name = "OpenAI GPT-4o-mini"
            else:
                model_key = "openai_gpt4o"
                model_name = "OpenAI GPT-4o"

            # Calculate costs
            input_cost = Decimal(str(input_tokens)) * self.PRICING_RATES[model_key]["input_tokens"]
            output_cost = Decimal(str(output_tokens)) * self.PRICING_RATES[model_key]["output_tokens"]
            total_cost = input_cost + output_cost

            # Calculate weighted rate for display
            total_tokens = input_tokens + output_tokens
            if total_tokens > 0:
                weighted_rate = total_cost / Decimal(str(total_tokens))
            else:
                weighted_rate = self.PRICING_RATES[model_key]["input_tokens"]

            document_costs.append(
                ServiceCost(
                    service_name=model_name,
                    cost=float(total_cost),
                    operation_type="document_analysis",
                    units_consumed=total_tokens,
                    unit_type="tokens",
                    rate_per_unit=float(weighted_rate),
                    total_cost=float(total_cost),
                    file_name=doc.file_name,
                )
            )

        return document_costs

    def calculate_audio_processing_costs(
        self,
        transcripted_media: list[TranscriptedMedia],
        processing_logs: dict[str, Any] | None = None,
    ) -> list[ServiceCost]:
        """Calculate actual costs for audio transcription.

        Args:
        ----
            transcripted_media: List of transcribed audio files
            processing_logs: Optional logs containing processing duration data

        Returns:
        -------
            List of ServiceCost objects for audio processing

        """
        audio_costs = []

        if not processing_logs:
            processing_logs = {}

        for audio in transcripted_media:
            # Get actual duration from processing or file metadata
            audio_log = processing_logs.get(audio.file_name, {})

            if "duration_minutes" in audio_log:
                actual_minutes = audio_log["duration_minutes"]
            elif audio.duration:
                actual_minutes = audio.duration / 60.0  # Convert seconds to minutes
            else:
                # Estimate from transcript length
                actual_minutes = max(1.0, len(audio.transcript) / 200)  # ~200 chars per minute speech

            # Calculate Whisper cost
            whisper_cost = Decimal(str(actual_minutes)) * self.PRICING_RATES["openai_whisper"]["per_minute"]

            audio_costs.append(
                ServiceCost(
                    service_name="OpenAI Whisper",
                    cost=float(whisper_cost),
                    operation_type="audio_transcription",
                    units_consumed=int(actual_minutes),
                    unit_type="minutes",
                    rate_per_unit=float(self.PRICING_RATES["openai_whisper"]["per_minute"]),
                    total_cost=float(whisper_cost),
                    file_name=audio.file_name,
                )
            )

        return audio_costs

    def calculate_video_processing_costs(
        self,
        video_insights: list[VideoInsight],
        processing_logs: dict[str, Any] | None = None,
    ) -> list[ServiceCost]:
        """Calculate actual costs for video processing.

        Args:
        ----
            video_insights: List of video analysis results
            processing_logs: Optional logs containing processing data

        Returns:
        -------
            List of ServiceCost objects for video processing

        """
        video_costs = []

        if not processing_logs:
            processing_logs = {}

        for video in video_insights:
            video_log = processing_logs.get(video.file_name, {})

            # Calculate video processing cost
            if "duration_minutes" in video_log:
                actual_minutes = video_log["duration_minutes"]
            elif video.duration:
                actual_minutes = video.duration / 60.0  # Convert seconds to minutes
            else:
                # Estimate from video file size if available in metadata
                file_size_mb = video.metadata.size / (1024 * 1024) if video.metadata.size else 50
                actual_minutes = max(1.0, file_size_mb / 7.5)  # Rough estimation

            # Vertex AI Video Processing cost
            video_cost = Decimal(str(actual_minutes)) * self.PRICING_RATES["vertex_ai_video"]["per_minute"]

            video_costs.append(
                ServiceCost(
                    service_name="Google Vertex AI Video",
                    cost=float(video_cost),
                    operation_type="video_processing",
                    units_consumed=int(actual_minutes),
                    unit_type="minutes",
                    rate_per_unit=float(self.PRICING_RATES["vertex_ai_video"]["per_minute"]),
                    total_cost=float(video_cost),
                    file_name=video.file_name,
                )
            )

            # Calculate Gemini analysis cost from actual token usage
            if "gemini_token_usage" in video_log:
                input_tokens = video_log["gemini_token_usage"].get("input_tokens", 1500)
                output_tokens = video_log["gemini_token_usage"].get("output_tokens", 3000)
            else:
                # Estimate based on insights complexity - Fixed: Proper None handling
                insights_str = str(video.insights) if video.insights is not None else ""
                labels_str = str(video.labels) if video.labels is not None else ""
                objects_str = str(video.objects) if video.objects is not None else ""
                insight_text = insights_str + labels_str + objects_str
                input_tokens = 1500  # Standard prompt
                output_tokens = max(1000, len(insight_text) // 4)

            gemini_input_cost = (
                Decimal(str(input_tokens)) * self.PRICING_RATES["vertex_ai_gemini_flash"]["input_tokens"]
            )
            gemini_output_cost = (
                Decimal(str(output_tokens)) * self.PRICING_RATES["vertex_ai_gemini_flash"]["output_tokens"]
            )
            total_gemini_cost = gemini_input_cost + gemini_output_cost

            # Calculate weighted rate
            total_tokens = input_tokens + output_tokens
            weighted_rate = (
                total_gemini_cost / Decimal(str(total_tokens))
                if total_tokens > 0
                else self.PRICING_RATES["vertex_ai_gemini_flash"]["input_tokens"]
            )

            video_costs.append(
                ServiceCost(
                    service_name="Google Vertex AI Gemini-2.5-flash",
                    cost=float(total_gemini_cost),
                    operation_type="video_analysis",
                    units_consumed=total_tokens,
                    unit_type="tokens",
                    rate_per_unit=float(weighted_rate),
                    total_cost=float(total_gemini_cost),
                    file_name=video.file_name,
                )
            )

            # Handle criminal video analysis if present
            if isinstance(video, EnhancedVideoInsight) and video.is_criminal_case and video.criminal_analysis:
                # Add cost for enhanced criminal analysis
                criminal_tokens = 2000  # Additional tokens for criminal analysis
                criminal_cost = (
                    Decimal(str(criminal_tokens))
                    * self.PRICING_RATES["vertex_ai_gemini_flash"]["output_tokens"]
                )

                video_costs.append(
                    ServiceCost(
                        service_name="Google Vertex AI Gemini-2.5-flash (Criminal Analysis)",
                        cost=float(criminal_cost),
                        operation_type="criminal_video_analysis",
                        units_consumed=criminal_tokens,
                        unit_type="tokens",
                        rate_per_unit=float(self.PRICING_RATES["vertex_ai_gemini_flash"]["output_tokens"]),
                        total_cost=float(criminal_cost),
                        file_name=video.file_name,
                    )
                )

        return video_costs

    def calculate_total_actual_costs(
        self,
        analyzed_documents: list[AnalyzedDocument] | None = None,
        transcripted_media: list[TranscriptedMedia] | None = None,
        video_insights: list[VideoInsight] | None = None,
        processing_logs: dict[str, Any] | None = None,
    ) -> ActualCosts:
        """Calculate total actual costs for all processing operations.

        Args:
        ----
            analyzed_documents: List of analyzed documents
            transcripted_media: List of transcribed audio files
            video_insights: List of video analysis results
            processing_logs: Optional detailed processing logs

        Returns:
        -------
            ActualCosts object with complete breakdown

        """
        document_analysis_costs = []
        media_processing_costs = []

        # Calculate document analysis costs
        if analyzed_documents:
            document_analysis_costs = self.calculate_document_analysis_costs(
                analyzed_documents,
                processing_logs.get("documents", {}) if processing_logs else {},
            )

        # Calculate audio processing costs
        if transcripted_media:
            audio_costs = self.calculate_audio_processing_costs(
                transcripted_media,
                processing_logs.get("audio", {}) if processing_logs else {},
            )
            media_processing_costs.extend(audio_costs)

        # Calculate video processing costs
        if video_insights:
            video_costs = self.calculate_video_processing_costs(
                video_insights,
                processing_logs.get("video", {}) if processing_logs else {},
            )
            media_processing_costs.extend(video_costs)

        # Calculate total - use cost field instead of total_cost
        total_document_cost = sum(cost.cost for cost in document_analysis_costs)
        total_media_cost = sum(cost.cost for cost in media_processing_costs)
        total_actual_cost = total_document_cost + total_media_cost

        # Combine all service costs into a single list
        all_service_costs = document_analysis_costs + media_processing_costs

        return ActualCosts(
            total_actual_cost=float(total_actual_cost),
            service_costs=all_service_costs,
        )

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text content.

        Args:
        ----
            text: Text content to estimate

        Returns:
        -------
            Estimated token count

        """
        if not text:
            return 0
        return max(1, len(text) // 4)

    def parse_openai_response_for_tokens(self, response_data: dict[str, Any]) -> dict[str, int]:
        """Parse OpenAI API response to extract token usage.

        Args:
        ----
            response_data: Raw response from OpenAI API

        Returns:
        -------
            Dictionary with token usage information

        """
        token_usage = {}

        if "usage" in response_data:
            usage = response_data["usage"]
            token_usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        return token_usage

    def parse_vertex_ai_response_for_tokens(self, response_data: dict[str, Any]) -> dict[str, int]:
        """Parse Vertex AI response to extract token usage.

        Args:
        ----
            response_data: Raw response from Vertex AI API

        Returns:
        -------
            Dictionary with token usage information containing:
            - prompt_tokens: Number of input tokens
            - completion_tokens: Number of output tokens
            - total_tokens: Total tokens used

        """
        token_usage = {}

        # Vertex AI token usage is typically in metadata
        if "usage_metadata" in response_data:
            metadata = response_data["usage_metadata"]
            token_usage = {
                "input_tokens": metadata.get("prompt_token_count", 0),
                "output_tokens": metadata.get("candidates_token_count", 0),
                "total_tokens": metadata.get("total_token_count", 0),
            }
        elif "metadata" in response_data and "tokenMetadata" in response_data["metadata"]:
            # Alternative structure
            metadata = response_data["metadata"]["tokenMetadata"]
            token_usage = {
                "input_tokens": metadata.get("inputTokenCount", 0),
                "output_tokens": metadata.get("outputTokenCount", 0),
                "total_tokens": metadata.get("totalTokenCount", 0),
            }

        return token_usage
