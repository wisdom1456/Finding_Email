from __future__ import annotations

import re
from typing import Any, Dict

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


def regex_replace_filter(s, find, replace):
    """A custom Jinja2 filter for regex replacement."""
    if s is None:
        return ""
    return re.sub(find, replace, str(s))


class ContentFormattingService:
    """A service class for content formatting and HTML/text processing utilities."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the ContentFormattingService with the application configuration."""
        self.config = config

    def format_video_analysis_for_appendix(self, video_insight) -> str:
        """Format video analysis for appendix."""
        formatted_text = []

        if hasattr(video_insight, "insights") and video_insight.insights:
            insights = video_insight.insights

            if isinstance(insights, str):
                return f'<p style="margin: 0; font-size: 13px; line-height: 1.5;">{insights}</p>'

            if isinstance(insights, dict) and insights.get("summary"):
                formatted_text.append(f"<div><strong>Summary:</strong> {insights['summary']}</div>")

        return "".join(formatted_text) if formatted_text else "<p>Video analysis details available.</p>"

    def _apply_deadline_formatting(self, content: str) -> str:
        """Apply deadline and date formatting to content by bolding important dates and deadlines.

        This method replaces the Jinja2 regex_replace filter functionality by applying
        the same regex transformations in Python before template rendering.

        Args:
        ----
            content: The content to format

        Returns:
        -------
            Content with dates and deadlines formatted with <strong> aCgs

        """
        if not content:
            return content

        # Apply the same regex patterns that were used in the Jinja2 template
        # 1. Format date patterns (MM/DD/YYYY, MM-DD-YYYY)
        content = regex_replace_filter(
            content, r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", r"<strong>\1</strong>"
        )

        # 2. Format duration patterns (e.g., "14 days", "2 weeks")
        content = regex_replace_filter(
            content,
            r"\b(\d{1,2}\s+(days?|weeks?|months?|years?))\b",
            r"<strong>\1</strong>",
        )

        # 3. Format "within X time" patterns (e.g., "within 30 days")
        content = regex_replace_filter(
            content,
            r"\b(within\s+\d+\s+(days?|weeks?|months?|years?))\b",
            r"<strong>\1</strong>",
        )

        # 4. Format "by [date]" patterns (e.g., "by August 21, 2025")
        content = regex_replace_filter(content, r"\b(by\s+\w+\s+\d{1,2},?\s+\d{4})\b", r"<strong>\1</strong>")

        # 5. Format deadline references
        content = regex_replace_filter(content, r"\b(deadline:?\s*[^.!?]*)\b", r"<strong>\1</strong>")

        return content

    def _clean_ai_response(self, content: str, is_counter_intuitive: bool = False) -> str:
        """Enhanced AI response cleaning with new normalization pipeline.

        This method implements the new strategy of processing raw text BEFORE
        any HTML structure is applied to prevent corruption of HTML tags.
        """
        if not content:
            return ""

        # === NEW NORMALIZATION PIPELINE - PROCESS RAW TEXT FIRST ===

        # Step 0A: Apply enhanced citation filtering on raw text
        content = self._apply_enhanced_citation_filtering(content)

        # Step 0B: Apply sentence splitting logic on raw text
        content = self._apply_sentence_splitting_logic(content)

        # Step 0C: Apply optional AI simplification on raw text (if needed)
        content = self._apply_optional_ai_simplification(content)

        # Apply high-stakes advice protocol if needed (defensive against None values)
        if is_counter_intuitive:
            formatting_section = self.config.get("formatting") or {}
            protocol = formatting_section.get("high_stakes_advice_protocol", "")
            if protocol:
                content = f"{protocol}\n\n{content}"

        # Step 1: Remove markdown artifacts
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", content, flags=re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE)

        # Step 2: Apply enhanced sanitization rules
        cleaned = self._apply_enhanced_sanitization(cleaned)

        # Step 3: Apply comprehensive content processing
        cleaned = self._format_legal_analysis(cleaned)
        cleaned = self._format_recommendations(cleaned)
        cleaned = self._format_subsections(cleaned)
        cleaned = self._strip_citations(cleaned)  # Secondary citation removal for any missed cases
        cleaned = self._format_bullet_points(cleaned)
        cleaned = self._clean_section_numbering(cleaned)
        cleaned = self._ensure_proper_whitespace(cleaned)
        cleaned = self._trim_wordiness(cleaned)

        # Step 3.5: Apply grammar sanitization
        cleaned = self._sanitize_output_grammar(cleaned)

        # Step 4: Convert markdown formatting
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", cleaned)
        cleaned = re.sub(r"\*(.*?)\*", r"<em>\1</em>", cleaned)

        # Step 5: Fix HTML formatting issues
        cleaned = re.sub(r"<p>\s*<p>", "<p>", cleaned)
        cleaned = re.sub(r"</p>\s*</p>", "</p>", cleaned)
        cleaned = re.sub(r"<p>\s*</p>", "", cleaned)

        return cleaned.strip()

    def _apply_enhanced_sanitization(self, content: str) -> str:
        """Apply enhanced sanitization rules to clean AI response content.

        This method implements specific regex rules for:
        - Normalizing punctuation spacing
        - Removing duplicate intro phrases
        - Eliminating leading commas from lines
        """
        if not content:
            return content

        # Normalize punctuation spacing: Add space after punctuation if missing
        content = re.sub(r"([.,])([A-Za-z])", r"\1 \2", content)

        # Remove duplicate intro phrases (case-insensitive)
        # This removes repeated occurrences of "the path forward" within the same text
        content = re.sub(r"(\bthe path forward\b).*?\1", r"\1", content, flags=re.IGNORECASE)

        # Eliminate leading commas from lines
        lines = content.split("\n")
        cleaned_lines = []
        for line in lines:
            # Remove leading commas and whitespace from each line
            cleaned_line = re.sub(r"^\s*,\s*", "", line)
            cleaned_lines.append(cleaned_line)
        content = "\n".join(cleaned_lines)

        return content

    def _format_legal_analysis(self, content: str) -> str:
        """Format legal analysis content with proper structure and hierarchy."""
        if not content:
            return content

        # Ensure consistent header formatting for legal analysis sections
        content = re.sub(
            r"(?i)(legal\s+analysis|analysis\s+and\s+position|statutory\s+analysis)",
            lambda m: f"<strong>{m.group(1).upper()}</strong>",
            content,
        )

        # Format subsection headers (A, B, C, etc.)
        content = re.sub(
            r"^([A-Z])\.\s*([A-Z][^.]*?)(?=\n|$)",
            r"<strong>\1. \2</strong>",
            content,
            flags=re.MULTILINE,
        )

        return content

    def _format_recommendations(self, content: str) -> str:
        """Format recommendation sections with clear structure and emphasis."""
        if not content:
            return content

        # Format recommendation headers
        content = re.sub(
            r"(?i)(recommended?\s+(?:next\s+)?steps?|recommendations?|next\s+steps?)",
            lambda m: f"<strong>{m.group(1).upper()}</strong>",
            content,
        )

        # Format numbered recommendations
        content = re.sub(
            r"^(\d+)\.\s*([^.]+?)(?=\n|$)",
            r"<strong>\1.</strong> \2",
            content,
            flags=re.MULTILINE,
        )

        return content

    def _format_subsections(self, content: str) -> str:
        """Format subsections with proper indentation and hierarchy."""
        if not content:
            return content

        # Format lettered subsections (A, B, C)
        content = re.sub(
            r"^([A-Z])\.\s+(.+?)$",
            r"    <strong>\1.</strong> \2",
            content,
            flags=re.MULTILINE,
        )

        # Format numbered subsections with proper spacing
        content = re.sub(
            r"^(\d+)\.\s+(.+?)$",
            r"<strong>\1.</strong> \2",
            content,
            flags=re.MULTILINE,
        )

        return content

    def _strip_citations(self, content: str) -> str:
        """ENHANCED: Strip all legal citations using comprehensive regex pattern."""
        if not content:
            return content

        # Use the enhanced citation filter regex from configuration
        try:
            citation_filter_regex = self.config.get("citation_filter_regex", "")
            if citation_filter_regex:
                content = re.sub(citation_filter_regex, "", content, flags=re.IGNORECASE)

            # Additional comprehensive citation cleanup
            content = re.sub(
                r"\b(Fla\.?\s*Stat\.?|F\.S\.?)\s*§?\s*[\d\w\.\-\(\)]+",
                "",
                content,
                flags=re.IGNORECASE,
            )
            content = re.sub(r"\bChapter\s*\d+\b", "", content, flags=re.IGNORECASE)
            content = re.sub(r"§+\s*[\d\w\.\-\(\)]+", "", content)
            content = re.sub(r"\b\d+\.\d+\b", "", content)  # Remove section numbers like 123.45
            content = re.sub(r"\([^)]*§[^)]*\)", "", content)  # Remove parenthetical citations with §
            content = re.sub(r"\bFla\b\.?\s*R\.", "", content, flags=re.IGNORECASE)  # Florida Rules
            content = re.sub(r"\bFla\b\.?\s*Admin\.", "", content, flags=re.IGNORECASE)  # Florida Admin
            content = re.sub(r"\d{1,3}\s*So\.", "", content, flags=re.IGNORECASE)  # Southern Reporter
            content = re.sub(r"section\s*\d+", "", content, flags=re.IGNORECASE)  # Section references

            # Collapse extra spaces left behind
            content = re.sub(r"\s{2,}", " ", content).strip()
            return content

        except Exception as e:
            logger.error(
                "Enhanced citation filtering failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            # Fallback to basic filtering
            content = re.sub(
                r"\b(Fla\.?\s*Stat\.?|F\.S\.)\s*§?\s*[\d\w\.\-\(\)]+",
                "",
                content,
                flags=re.IGNORECASE,
            )
            content = re.sub(r"\bChapter\s*\d+\b", "", content, flags=re.IGNORECASE)
            content = re.sub(r"§+\s*[\d\w\.\-\(\)]+", "", content)
            content = re.sub(r"\s{2,}", " ", content).strip()
            return content

    def _format_bullet_points(self, content: str) -> str:
        """Format bullet points for professional presentation."""
        if not content:
            return content

        # Convert dashes and asterisks to proper bullet points
        content = re.sub(r"^[-*]\s+(.+?)$", r"• \1", content, flags=re.MULTILINE)

        # Wrap bullet points in proper HTML structure
        lines = content.split("\n")
        in_bullet_section = False
        formatted_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("•"):
                if not in_bullet_section:
                    formatted_lines.append("<ul>")
                    in_bullet_section = True
                formatted_lines.append(f"<li>{stripped[1:].strip()}</li>")
            else:
                if in_bullet_section:
                    formatted_lines.append("</ul>")
                    in_bullet_section = False
                formatted_lines.append(line)

        if in_bullet_section:
            formatted_lines.append("</ul>")

        return "\n".join(formatted_lines)

    def _clean_section_numbering(self, content: str) -> str:
        """Clean up redundant and repeated section numbering."""
        if not content:
            return content

        # Remove numbered section headers at the beginning of content (template handles headers)
        content = re.sub(r"^(\d+)\.\s*([A-Z][A-Z\s]+)(?:\n|$)", "", content, flags=re.MULTILINE)

        # Remove any remaining standalone section headers
        content = re.sub(r"^([A-Z][A-Z\s]{10,})(?:\n|$)", "", content, flags=re.MULTILINE)

        # Remove redundant section numbers at the beginning of content
        content = re.sub(
            r"^(\d+)\.\s*(\d+)\.\s*([A-Z][^.]*?)$",
            r"\1. \3",
            content,
            flags=re.MULTILINE,
        )

        # Clean up repeated headers
        content = re.sub(r"^([A-Z\s]+)\n\1$", r"\1", content, flags=re.MULTILINE)

        # Remove section numbers that appear mid-sentence
        content = re.sub(r"(\w+)\s+\d+\.\s+([A-Z])", r"\1 \2", content)

        return content

    def _ensure_proper_whitespace(self, content: str) -> str:
        """Ensure proper whitespace and line breaks for readability."""
        if not content:
            return content

        # Add proper spacing after headers
        content = re.sub(r"(<h[1-6][^>]*>.*?</h[1-6]>)(\w)", r"\1\n\n\2", content)

        # Add spacing before new paragraphs
        content = re.sub(r"(</p>)(<p[^>]*>)", r"\1\n\n\2", content)

        # Ensure proper spacing around bullet points
        content = re.sub(r"(</ul>)(<p[^>]*>)", r"\1\n\n\2", content)

        content = re.sub(r"(</p>)(<ul>)", r"\1\n\n\2", content)

        # Clean up excessive whitespace while preserving intentional breaks
        content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)
        content = re.sub(r"^\s+|\s+$", "", content, flags=re.MULTILINE)

        return content

    def _trim_wordiness(self, content: str) -> str:
        """Trim verbose and repetitive language for concise communication."""
        if not content:
            return content

        # Remove conversational filler
        wordy_patterns = [
            r"\b(?:it should be noted that|it is important to note that|please note that)\b",
            r"\b(?:in conclusion|to conclude|in summary)\b",
            r"\b(?:as mentioned above|as previously stated|as noted earlier)\b",
            r"\b(?:furthermore|moreover|additionally)\b(?=.*?furthermore|.*?moreover|.*?additionally)",
        ]

        for pattern in wordy_patterns:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE)

        # Simplify overly complex sentences
        content = re.sub(
            r"\b(?:in order to|for the purpose of)\b",
            "to",
            content,
            flags=re.IGNORECASE,
        )

        # Remove redundant disclaimers in the middle of content
        content = re.sub(
            r"(?i)\b(?:this is not legal advice|consult with an attorney|seek legal counsel)\b(?=.*?\w{10,})",
            "",
            content,
        )

        # Clean up extra spaces left by removals
        content = re.sub(r"\s{2,}", " ", content)
        content = re.sub(r"^\s+|\s+$", "", content, flags=re.MULTILINE)

        return content

    def _apply_enhanced_citation_filtering(self, content: str) -> str:
        """Apply enhanced citation filtering to raw text using comprehensive regex patterns.

        This method processes raw text BEFORE any HTML structure is applied,
        ensuring that citations are removed without corrupting HTML tags.

        Args:
        ----
            content: Raw text content to filter

        Returns:
        -------
            Content with citations removed

        """
        if not content:
            return content

        try:
            logger.info("Starting enhanced citation filtering on raw text")

            # Get citation filter regex from configuration
            citation_filter_regex = self.config.get("citation_filter_regex", "")

            if citation_filter_regex:
                logger.debug(
                    "Applying configured citation filter",
                    extra={"citation_filter_regex": citation_filter_regex},
                )
                content = re.sub(citation_filter_regex, "", content, flags=re.IGNORECASE)

            # Enhanced comprehensive citation cleanup on raw text
            original_length = len(content)

            # Remove Florida Statute references
            content = re.sub(
                r"\b(Fla\.?\s*Stat\.?|F\.S\.?)\s*§?\s*[\d\w\.\-\(\)]+",
                "",
                content,
                flags=re.IGNORECASE,
            )

            # Remove Chapter references
            content = re.sub(r"\bChapter\s*\d+\b", "", content, flags=re.IGNORECASE)

            # Remove section symbols and numbers
            content = re.sub(r"§+\s*[\d\w\.\-\(\)]+", "", content)

            # Remove decimal section numbers
            content = re.sub(r"\b\d{2,3}\.\d+\b", "", content)

            # Remove parenthetical citations with section symbols
            content = re.sub(r"\([^)]*§[^)]*\)", "", content)

            # Remove Florida Rules references
            content = re.sub(r"\bFla\b\.?\s*R\.", "", content, flags=re.IGNORECASE)

            # Remove Florida Admin references
            content = re.sub(r"\bFla\b\.?\s*Admin\.", "", content, flags=re.IGNORECASE)

            # Remove Southern Reporter citations
            content = re.sub(r"\d{1,3}\s*So\.", "", content, flags=re.IGNORECASE)

            # Remove generic section references
            content = re.sub(r"\bsection\s*\d+", "", content, flags=re.IGNORECASE)

            # Clean up extra spaces and normalize whitespace
            content = re.sub(r"\s{2,}", " ", content)
            content = content.strip()

            filtered_length = len(content)
            removed_chars = original_length - filtered_length

            if removed_chars > 0:
                logger.info(
                    "Enhanced citation filtering completed",
                    extra={"removed_characters": removed_chars},
                )
            else:
                logger.debug("Citation filtering completed - no citations found to remove")

            return content

        except re.error as e:
            logger.error(
                "Invalid citation filter regex",
                extra={"error": str(e), "error_type": "re.error"},
            )
            return content
        except Exception as e:
            logger.error(
                "Enhanced citation filtering failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return content

    def _apply_sentence_splitting_logic(self, content: str) -> str:
        """Apply sentence splitting logic to improve readability on raw text.

        This method processes raw text to normalize sentence structure and improve
        readability without affecting HTML structure.

        Args:
        ----
            content: Raw text content to process

        Returns:
        -------
            Content with improved sentence structure

        """
        if not content:
            return content

        try:
            logger.debug("Starting sentence splitting logic on raw text")

            original_length = len(content)

            # Split very long sentences at appropriate points
            # Target sentences over 15 words for splitting (aligned with validation criteria)
            sentences = re.split(r"(?<=[.!?])\s+", content)
            processed_sentences = []

            for sentence in sentences:
                word_count = len(sentence.split())

                if word_count > 15:
                    # Attempt to split at coordinating conjunctions or semicolons
                    split_points = [
                        r",\s+(and|but|or|however|moreover|furthermore|additionally)",
                        r";\s*",
                        r",\s+(?=which|that|where|when)",
                        r",\s+(?=because|since|although|while|if)",
                    ]

                    sentence_parts = [sentence]
                    for pattern in split_points:
                        new_parts = []
                        for part in sentence_parts:
                            # Only split if the part is still long
                            if len(part.split()) > 25:
                                split_parts = re.split(f"({pattern})", part, maxsplit=1)
                                if len(split_parts) > 1:
                                    # Rejoin the conjunction with the second part
                                    first_part = split_parts[0].strip()
                                    conjunction = split_parts[1] if len(split_parts) > 1 else ""
                                    remaining = split_parts[2] if len(split_parts) > 2 else ""

                                    if first_part:
                                        new_parts.append(first_part + ".")
                                    if remaining:
                                        # Capitalize first word of new sentence
                                        remaining = conjunction.strip() + " " + remaining.strip()
                                        remaining = remaining[0].upper() + remaining[1:] if remaining else ""
                                        new_parts.append(remaining)
                                else:
                                    new_parts.append(part)
                            else:
                                new_parts.append(part)
                        sentence_parts = new_parts
                        if len(sentence_parts) > 1:
                            break  # Found a good split point

                    processed_sentences.extend(sentence_parts)
                else:
                    processed_sentences.append(sentence)

            # Rejoin sentences with proper spacing
            content = " ".join(processed_sentences)

            # Clean up any formatting issues from splitting
            content = re.sub(r"\.\s*\.", ".", content)  # Remove double periods
            content = re.sub(r"\s+", " ", content)  # Normalize spacing
            content = content.strip()

            processed_length = len(content)

            if processed_length != original_length:
                logger.info(
                    "Sentence splitting applied",
                    extra={
                        "original_length": original_length,
                        "processed_length": processed_length,
                    },
                )
            else:
                logger.debug("Sentence splitting completed - no changes needed")

            return content

        except Exception as e:
            logger.error(
                "Sentence splitting logic failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return content

    def _apply_optional_ai_simplification(self, content: str) -> str:
        """Apply optional AI-based simplification to raw text for improved readability.

        This method can use OpenAI to simplify complex legal language while
        preserving accuracy, but only processes raw text before HTML structure.

        Args:
        ----
            content: Raw text content to potentially simplify

        Returns:
        -------
            Simplified content or original content if simplification is skipped

        """
        if not content:
            return content

        try:
            # Check if AI simplification is enabled in configuration
            simplification_config = self.config.get("simplification", {})
            enabled = simplification_config.get("enabled", False)

            if not enabled:
                logger.debug("AI simplification disabled in configuration")
                return content

            # For now, return original content as AI simplification is being removed in the refactor
            logger.debug("AI simplification functionality removed in refactor")
            return content

        except Exception as e:
            logger.error(
                "AI simplification failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return content

    @staticmethod
    def _sanitize_output_grammar(text: str) -> str:
        """Sanitize output grammar with specific regex operations.

        Performs the following operations:
        - Normalize punctuation spacing
        - Remove duplicate introductory phrases (case-insensitive)
        - Eliminate leading commas from each line

        Args:
        ----
            text: The text string to sanitize

        Returns:
        -------
            The processed text with grammar corrections applied

        """
        if not text:
            return text

        # Normalize punctuation spacing: Add space after punctuation if missing
        text = re.sub(r"([.,])([A-Za-z])", r"\1 \2", text)

        # Remove duplicate introductory phrases (case-insensitive)
        text = re.sub(r"(\bthe path forward\b).*?\1", r"\1", text, flags=re.IGNORECASE | re.DOTALL)

        # Eliminate leading commas from each line
        text = "\n".join([re.sub(r"^\s*,\s*", "", line) for line in text.splitlines()])

        return text
