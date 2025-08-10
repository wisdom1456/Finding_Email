"""
Cost Estimator Service for Legal Document Analysis Portal

This service provides pre-processing cost estimation for document analysis,
audio transcription, and video processing based on current API pricing rates
and file characteristics.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from backend.utils.data_models import CostEstimate, ProcessedDocument, ServiceCost


class CostEstimator:
    """
    Estimates processing costs for legal document analysis pipeline.

    Provides accurate cost estimates based on current API pricing rates
    and intelligent algorithms for token counting, duration estimation,
    and processing complexity assessment.
    """

    # Current API Pricing Rates (USD)
    PRICING_RATES = {
        # OpenAI Pricing
        "openai_gpt4o": {
            "input_tokens": Decimal("5.00") / Decimal("1000000"),  # $5.00 per 1M tokens
            "output_tokens": Decimal("15.00")
            / Decimal("1000000"),  # $15.00 per 1M tokens
        },
        "openai_gpt4o_mini": {
            "input_tokens": Decimal("0.15") / Decimal("1000000"),  # $0.15 per 1M tokens
            "output_tokens": Decimal("0.60")
            / Decimal("1000000"),  # $0.60 per 1M tokens
        },
        "openai_whisper": {
            "per_minute": Decimal("0.006")  # $0.006 per minute
        },
        # Google Cloud Pricing
        "vertex_ai_gemini_flash": {
            "input_tokens": Decimal("0.075")
            / Decimal("1000000"),  # $0.075 per 1M tokens
            "output_tokens": Decimal("0.30")
            / Decimal("1000000"),  # $0.30 per 1M tokens
        },
        "vertex_ai_video": {
            "per_minute": Decimal("0.10")  # $0.10 per minute
        },
        "google_speech_to_text": {
            "per_minute": Decimal("0.024")  # $0.024 per minute
        },
    }

    def __init__(self):
        """Initialize the cost estimator with current pricing rates."""
        self.confidence_level = 0.8  # Default estimation confidence

    def estimate_document_processing_costs(
        self, documents: List[ProcessedDocument]
    ) -> List[ServiceCost]:
        """
        Estimate costs for document processing using OpenAI models.

        Args:
            documents: List of processed documents to analyze

        Returns:
            List of ServiceCost objects for document analysis
        """
        document_costs = []

        for doc in documents:
            # Estimate tokens for document content
            input_tokens = self._estimate_tokens(doc.content)

            # Determine which model to use based on document size
            if input_tokens > 20000:
                model_key = "openai_gpt4o_mini"
                model_name = "OpenAI GPT-4o-mini"
                # Smaller output for mini model
                output_tokens = min(2000, input_tokens // 4)
            else:
                model_key = "openai_gpt4o"
                model_name = "OpenAI GPT-4o"
                # Standard output estimation
                output_tokens = min(4000, input_tokens // 3)

            # Calculate input cost
            input_cost = (
                Decimal(str(input_tokens))
                * self.PRICING_RATES[model_key]["input_tokens"]
            )

            # Calculate output cost
            output_cost = (
                Decimal(str(output_tokens))
                * self.PRICING_RATES[model_key]["output_tokens"]
            )

            total_cost = input_cost + output_cost

            document_costs.append(
                ServiceCost(
                    service_name=model_name,
                    cost=float(total_cost),
                    operation_type="document_analysis",
                    units_consumed=input_tokens + output_tokens,
                    unit_type="tokens",
                    rate_per_unit=float(self.PRICING_RATES[model_key]["input_tokens"]),
                    total_cost=float(total_cost),
                    file_name=doc.file_name,
                )
            )

        return document_costs

    def estimate_audio_processing_costs(
        self, audio_files: List[Dict[str, Any]]
    ) -> List[ServiceCost]:
        """
        Estimate costs for audio transcription using OpenAI Whisper.

        Args:
            audio_files: List of audio file metadata

        Returns:
            List of ServiceCost objects for audio processing
        """
        audio_costs = []

        for audio_file in audio_files:
            file_name = audio_file.get("filename", "unknown_audio.mp3")
            file_size_mb = audio_file.get("size", 0) / (1024 * 1024)

            # Estimate duration from file size (rough approximation)
            estimated_minutes = self._estimate_audio_duration_from_size(file_size_mb)

            # Calculate Whisper cost
            whisper_cost = (
                Decimal(str(estimated_minutes))
                * self.PRICING_RATES["openai_whisper"]["per_minute"]
            )

            audio_costs.append(
                ServiceCost(
                    service_name="OpenAI Whisper",
                    cost=float(whisper_cost),
                    operation_type="audio_transcription",
                    units_consumed=int(estimated_minutes),
                    unit_type="minutes",
                    rate_per_unit=float(
                        self.PRICING_RATES["openai_whisper"]["per_minute"]
                    ),
                    total_cost=float(whisper_cost),
                    file_name=file_name,
                )
            )

        return audio_costs

    def estimate_video_processing_costs(
        self, video_files: List[Dict[str, Any]]
    ) -> List[ServiceCost]:
        """
        Estimate costs for video processing using Google Vertex AI.

        Args:
            video_files: List of video file metadata

        Returns:
            List of ServiceCost objects for video processing
        """
        video_costs = []

        for video_file in video_files:
            file_name = video_file.get("filename", "unknown_video.mp4")
            file_size_mb = video_file.get("size", 0) / (1024 * 1024)

            # Estimate duration from file size
            estimated_minutes = self._estimate_video_duration_from_size(file_size_mb)

            # Vertex AI Video Processing cost
            video_cost = (
                Decimal(str(estimated_minutes))
                * self.PRICING_RATES["vertex_ai_video"]["per_minute"]
            )

            video_costs.append(
                ServiceCost(
                    service_name="Google Vertex AI Video",
                    cost=float(video_cost),
                    operation_type="video_processing",
                    units_consumed=int(estimated_minutes),
                    unit_type="minutes",
                    rate_per_unit=float(
                        self.PRICING_RATES["vertex_ai_video"]["per_minute"]
                    ),
                    total_cost=float(video_cost),
                    file_name=file_name,
                )
            )

            # Add Gemini analysis cost (token-based)
            # Estimate tokens for video analysis prompt and response
            analysis_input_tokens = 1500  # Standard video analysis prompt
            analysis_output_tokens = 3000  # Detailed video analysis response

            gemini_input_cost = (
                Decimal(str(analysis_input_tokens))
                * self.PRICING_RATES["vertex_ai_gemini_flash"]["input_tokens"]
            )
            gemini_output_cost = (
                Decimal(str(analysis_output_tokens))
                * self.PRICING_RATES["vertex_ai_gemini_flash"]["output_tokens"]
            )

            gemini_total_cost = gemini_input_cost + gemini_output_cost
            video_costs.append(
                ServiceCost(
                    service_name="Google Vertex AI Gemini-2.5-flash",
                    cost=float(gemini_total_cost),
                    operation_type="video_analysis",
                    units_consumed=analysis_input_tokens + analysis_output_tokens,
                    unit_type="tokens",
                    rate_per_unit=float(
                        self.PRICING_RATES["vertex_ai_gemini_flash"]["input_tokens"]
                    ),
                    total_cost=float(gemini_total_cost),
                    file_name=file_name,
                )
            )

        return video_costs

    def generate_cost_estimate(
        self,
        documents: Optional[List[ProcessedDocument]] = None,
        audio_files: Optional[List[Dict[str, Any]]] = None,
        video_files: Optional[List[Dict[str, Any]]] = None,
    ) -> CostEstimate:
        """
        Generate comprehensive cost estimate for case processing.

        Args:
            documents: List of documents to process
            audio_files: List of audio file metadata
            video_files: List of video file metadata

        Returns:
            CostEstimate object with detailed breakdown
        """
        estimated_document_costs = []
        estimated_media_costs = []

        # Estimate document costs
        if documents:
            estimated_document_costs = self.estimate_document_processing_costs(
                documents
            )

        # Estimate audio costs
        if audio_files:
            audio_costs = self.estimate_audio_processing_costs(audio_files)
            estimated_media_costs.extend(audio_costs)

        # Estimate video costs
        if video_files:
            video_costs = self.estimate_video_processing_costs(video_files)
            estimated_media_costs.extend(video_costs)

        # Calculate total estimated cost - use cost field instead of total_cost
        total_document_cost = sum(cost.cost for cost in estimated_document_costs)
        total_media_cost = sum(cost.cost for cost in estimated_media_costs)
        total_estimated_cost = total_document_cost + total_media_cost

        return CostEstimate(
            estimated_cost=float(total_estimated_cost),
            breakdown={
                "documents": float(total_document_cost),
                "media": float(total_media_cost),
                "confidence": self.confidence_level,
            },
        )

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text content.

        Uses approximation of 4 characters per token for English text.

        Args:
            text: Text content to estimate

        Returns:
            Estimated token count
        """
        if not text:
            return 0
        return max(1, len(text) // 4)

    def _estimate_audio_duration_from_size(self, file_size_mb: float) -> float:
        """
        Estimate audio duration from file size.

        Uses typical compression ratios for different audio qualities.
        Assumes average quality MP3 encoding (~1MB per minute).

        Args:
            file_size_mb: File size in megabytes

        Returns:
            Estimated duration in minutes
        """
        if file_size_mb <= 0:
            return 1.0  # Minimum billable unit

        # Rough estimation: 1MB ≈ 1 minute for compressed audio
        estimated_minutes = file_size_mb

        # Add 20% buffer for estimation uncertainty
        return max(1.0, estimated_minutes * 1.2)

    def _estimate_video_duration_from_size(self, file_size_mb: float) -> float:
        """
        Estimate video duration from file size.

        Uses typical compression ratios for different video qualities.
        Assumes average quality video encoding (~5-10MB per minute).

        Args:
            file_size_mb: File size in megabytes

        Returns:
            Estimated duration in minutes
        """
        if file_size_mb <= 0:
            return 1.0  # Minimum billable unit

        # Rough estimation based on typical video compression
        # Assume 7.5MB per minute for average quality video
        estimated_minutes = file_size_mb / 7.5

        # Add 15% buffer for estimation uncertainty
        return max(1.0, estimated_minutes * 1.15)

    def update_confidence_level(self, new_confidence: float) -> None:
        """
        Update estimation confidence level.

        Args:
            new_confidence: New confidence level (0.0-1.0)
        """
        if 0.0 <= new_confidence <= 1.0:
            self.confidence_level = new_confidence
        else:
            msg = "Confidence level must be between 0.0 and 1.0"
            raise ValueError(msg)
