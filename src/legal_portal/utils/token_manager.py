"""Token counting and size management for AI analysis components."""

from __future__ import annotations

import json
from typing import Any

import tiktoken
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class TokenManager:
    """Manages token counting and prompt size validation."""

    def __init__(self):
        """Initialize TokenManager."""
        self.model_limits = {
            "gpt-4o": 120000,  # 150k context window * 0.8
            "gpt-4o-mini": 100000,  # 125k context window * 0.8
            "gpt-4": 25600,  # 32k context window * 0.8
        }

    def estimate_tokens_detailed(self, prompt_content: str) -> int:
        """Enhanced token estimation with more accurate calculation."""
        # More accurate token estimation: ~3.5 characters per token for English text
        base_tokens = len(prompt_content) // 3.5

        # Add overhead for JSON structure, special characters, etc.
        overhead_factor = 1.15
        estimated_tokens = int(base_tokens * overhead_factor)

        logger.info("TOKEN MANAGER: 🔍 Token estimation details:")
        logger.info(f"TOKEN MANAGER: 🔍   - Content length: {len(prompt_content):,} characters")
        logger.info(f"TOKEN MANAGER: 🔍   - Base tokens: {int(base_tokens):,}")
        logger.info(f"TOKEN MANAGER: 🔍   - With overhead: {estimated_tokens:,}")

        return estimated_tokens

    def count_tokens_accurate(self, text: str, model: str = "gpt-4o") -> int:
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

            logger.info(f"TOKEN MANAGER: 🔢 Accurate token count ({model}): {token_count:,}")
            return token_count
        except (ImportError, AttributeError, ValueError, TypeError) as e:
            logger.error(f"TOKEN MANAGER: ⚠️  tiktoken error, falling back to estimation: {e}")
            # Fallback to existing estimation method
            return self.estimate_tokens_detailed(text)

    def check_token_threshold(self, analysis, model: str = "gpt-4o") -> bool:
        """Check if video insights would exceed token threshold before building prompt."""
        logger.debug(f"TOKEN MANAGER: 🔍 Pre-computation token checking for model: {model}")

        threshold = self.model_limits.get(model, 96000)  # Default to 120k * 0.8
        logger.info(f"TOKEN MANAGER: 🔍 Token threshold for {model}: {threshold:,}")

        # Estimate token usage from video insights
        if not analysis.video_insights:
            logger.info("TOKEN MANAGER: 🔍 No video insights, threshold check passed")
            return True

        total_video_tokens = 0
        for video in analysis.video_insights:
            # Estimate tokens from video content
            insights_content = json.dumps(video.insights, indent=2) if video.insights else ""
            transcript_content = video.transcript or ""
            labels_content = ", ".join(video.labels) if video.labels else ""
            objects_content = ", ".join(video.objects) if video.objects else ""

            video_content = f"{insights_content}\n{transcript_content}\n{labels_content}\n{objects_content}"
            video_tokens = self.count_tokens_accurate(video_content, model)
            total_video_tokens += video_tokens

            logger.info(f"TOKEN MANAGER: 🔍   - {video.file_name}: {video_tokens:,} tokens")

        # Add estimated tokens for other content (documents, intake, etc.)
        base_content_estimate = 10000  # Conservative estimate for non-video content
        total_estimated_tokens = total_video_tokens + base_content_estimate

        logger.info(f"TOKEN MANAGER: 🔍 Total estimated tokens: {total_estimated_tokens:,}")
        logger.info(f"TOKEN MANAGER: 🔍 Threshold: {threshold:,}")

        if total_estimated_tokens > threshold:
            logger.info(
                f"TOKEN MANAGER: ⚠️  Token count exceeds threshold ({total_estimated_tokens:,} > {threshold:,})"
            )
            return False

        logger.info("TOKEN MANAGER: ✅ Token count within threshold")
        return True

    def apply_summarization_strategy(self, analysis) -> Any:
        """Apply summarization strategy when token threshold is exceeded."""
        logger.info("TOKEN MANAGER: 🔄 Token count exceeds threshold. Triggering summarization strategy.")

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

                logger.info(
                    f"TOKEN MANAGER: 🔄   - Summarized {video.file_name}: {len(condensed_summary)} chars"
                )
            else:
                video.insights_summary = (
                    f"Video file {video.file_name} processed but content summarized due to size constraints."
                )
                logger.info(f"TOKEN MANAGER: 🔄   - Applied default summary for {video.file_name}")

        logger.info(
            f"TOKEN MANAGER: 🔄 Summarization strategy applied to {len(analysis_copy.video_insights)} video(s)"
        )
        return analysis_copy

    def truncate_video_content_aggressively(self, analysis, target_tokens: int = 100000) -> Any:
        """Aggressively truncate video content to meet token limits."""
        logger.info(
            f"TOKEN MANAGER: 🔄 Aggressively truncating video content to target {target_tokens:,} tokens"
        )

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
            video.text_annotations = video.text_annotations[:3] if video.text_annotations else []

            logger.info(f"TOKEN MANAGER: 🔄   - Truncated {video.file_name}")

        return analysis_copy

    def estimate_tokens(self, text: str) -> int:
        """Rough estimation of tokens (approximately 4 characters per token)."""
        return len(text) // 4

    def truncate_content_if_needed(self, content: str, max_tokens: int = 25000) -> str:
        """Truncate content if it exceeds token limit."""
        estimated_tokens = self.estimate_tokens(content)
        if estimated_tokens > max_tokens:
            # Keep first 80% and last 20% of content
            chars_to_keep = max_tokens * 4
            first_part_chars = int(chars_to_keep * 0.8)
            last_part_chars = int(chars_to_keep * 0.2)

            first_part = content[:first_part_chars]
            last_part = content[-last_part_chars:]

            truncated_content = f"{first_part}\n\n[... CONTENT TRUNCATED FOR SIZE ...]\n\n{last_part}"
            logger.info(
                f"TOKEN MANAGER: ⚠️  Content truncated from ~{estimated_tokens} to ~{max_tokens} tokens"
            )
            return truncated_content
        return content
