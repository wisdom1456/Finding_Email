"""Letter polishing - Second AI pass for formatting consistency.

Takes a generated letter and ensures perfect formatting, spacing, and layout.
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class LetterPolisher:
    """Second-pass AI formatter for consistent letter layout."""

    def __init__(self, openai_client):
        """Initialize the polisher.

        Args:
        ----
            openai_client: OpenAI client instance

        """
        self.client = openai_client
        self.formatting_prompt = self._load_formatting_prompt()

    def _load_formatting_prompt(self) -> str:
        """Load the formatting prompt for natural flow style."""
        return """You are a legal document formatting specialist.
Your job is to preserve legal substance while improving client-facing readability.

CRITICAL RULES:
1. Do NOT add new facts, dates, amounts, legal claims, or citations.
2. Do NOT remove material legal analysis.
3. Keep names, numbers, and document references accurate.
4. Improve format and flow only.

TARGET STYLE:
- Real attorney email voice.
- Plain English.
- Natural paragraphs.
- No section headers.
- No bold labels.
- No bullet lists.
- No numbered lists.

FORMATTING FIXES TO APPLY:
1. Remove standalone section labels (for example: "Facts", "Legal Theories", "Timing and Risk", "Next Steps").
2. Convert bullet and numbered list items into paragraph prose while preserving all content.
3. Smooth transitions so the letter reads as continuous correspondence.
4. Keep one blank line between paragraphs.
5. Preserve greeting, signature, and confidentiality language.

OUTPUT INSTRUCTIONS:
- Return ONLY the formatted letter text.
- No commentary.
- Keep markdown-safe paragraph text (no code fences).
"""

    def polish_letter(self, raw_letter: str) -> Dict:
        """Polish a generated letter for consistent formatting.

        Args:
        ----
            raw_letter: The unpolished letter text

        Returns:
        -------
            dict with polished_letter, changes_made, and success status

        """
        try:
            logger.info("Starting letter polish pass")

            # Prepare the prompt
            full_prompt = f"""{self.formatting_prompt}

LETTER TO FORMAT:

{raw_letter}

FORMATTED LETTER:"""

            # Make the AI call using the OpenAIClient wrapper
            response = self.client.create_chat_completion(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a legal document formatting specialist. "
                            "Fix formatting ONLY, preserve all content."
                        ),
                    },
                    {"role": "user", "content": full_prompt},
                ],
                temperature=0.1,  # Very low for consistency
                max_tokens=4000,
            )

            polished_letter = response["content"].strip()

            # Detect what changed
            changes = self._detect_changes(raw_letter, polished_letter)

            logger.info(f"Letter polishing complete. Changes made: {len(changes)}")

            return {
                "success": True,
                "polished_letter": polished_letter,
                "changes_made": changes,
                "original_length": len(raw_letter),
                "polished_length": len(polished_letter),
            }

        except Exception as e:
            logger.error(f"Letter polishing failed: {e}")
            return {
                "success": False,
                "polished_letter": raw_letter,  # Return original on failure
                "changes_made": [],
                "error": str(e),
            }

    def _detect_changes(self, original: str, polished: str) -> list:
        """Detect what formatting changes were made."""
        changes = []

        # Check for Key Findings → Here are the key points
        if "Key Findings" in original and "Here are the key points" in polished:
            changes.append("Changed 'Key Findings' to 'Here are the key points of our analysis:'")

        # Check for formal headers removed
        if "FACTUAL SUMMARY" in original and "FACTUAL SUMMARY" not in polished:
            changes.append("Removed formal 'FACTUAL SUMMARY' header for natural flow")

        if "RECOMMENDED ACTION" in original and "RECOMMENDED ACTION" not in polished:
            changes.append("Removed formal 'RECOMMENDED ACTION' header for natural flow")

        # Check for bold issue titles removed
        original_bold_bullets = original.count("• **")
        polished_bold_bullets = polished.count("• **")

        if original_bold_bullets > polished_bold_bullets:
            changes.append(
                (
                    f"Converted {original_bold_bullets - polished_bold_bullets} "
                    f"bold bullet headers to flowing paragraphs"
                )
            )

        # Check for spacing improvements
        original_triple_newlines = original.count("\n\n\n")
        polished_triple_newlines = polished.count("\n\n\n")

        if original_triple_newlines > polished_triple_newlines:
            changes.append(
                f"Fixed {original_triple_newlines - polished_triple_newlines} excessive spacing issues"
            )

        # Check for greeting improvement
        if "Dear " in original and ("Good afternoon" in polished or "Good morning" in polished):
            changes.append("Updated greeting to warmer time-of-day style")

        return changes


async def polish_letter_async(openai_client, raw_letter: str) -> Dict:
    """Async wrapper for letter polishing.

    Args:
    ----
        openai_client: OpenAI client instance
        raw_letter: The unpolished letter text

    Returns:
    -------
        dict with polished letter and metadata

    """
    polisher = LetterPolisher(openai_client)
    return polisher.polish_letter(raw_letter)


def polish_letter_sync(openai_client, raw_letter: str) -> Dict:
    """Polish letter synchronously.

    Args:
    ----
        openai_client: OpenAI client instance
        raw_letter: The unpolished letter text

    Returns:
    -------
        dict with polished letter and metadata

    """
    polisher = LetterPolisher(openai_client)
    return polisher.polish_letter(raw_letter)
