"""Letter polishing - Second AI pass for formatting consistency.

Takes a generated letter and ensures perfect formatting, spacing, and layout.
"""

import asyncio
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
        """Load the formatting prompt for structured professional style."""
        return """You are a legal document formatting specialist.
Your job is to preserve legal substance while improving professional readability.

CRITICAL RULES:
1. Do NOT add, change, or invent facts, dates, amounts, party names, legal claims, or legal citations.
2. Do NOT remove concrete facts from the draft.
3. Keep names, numbers, deadlines, and document references accurate and unchanged.
4. You have style leeway only: improve format, tone, transitions, and readability.

TARGET STYLE:
- Professional attorney correspondence — measured, thorough, and confident.
- Language that a non-lawyer can follow without being talked down to.
- Clear paragraph structure within each section.

SECTION STRUCTURE (PRESERVE):
- The letter should have four labeled sections: Background & Issue, Key Provisions, Analysis, Recommended Next Steps.
- Do NOT remove or rename these section headers.
- Do NOT merge sections.
- Within Key Provisions, each doctrine should have a bold title followed by detailed explanation.

FORMATTING FIXES TO APPLY:
1. Remove any pipeline parenthetical artifacts (e.g., "(intake packet 01-11-2026)", "(photos, file)") — preserve the underlying fact in natural prose.
2. Replace any internal pipeline language ("client-reported", "per intake", "flagged in analysis") with natural attorney voice.
3. Smooth transitions between paragraphs within each section.
4. Keep one blank line between paragraphs.
5. Preserve greeting, signature, and confidentiality language.
6. Ensure consistent formatting of doctrine titles in Key Provisions (bold, followed by colon).
7. Ensure document references read naturally ("per the contract", "the inspection report documents") without citation-style parentheticals.

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
                model="gpt-5.2",
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

        # Check for pipeline artifact removal
        import re
        original_parens = len(re.findall(r"\([^)]*(?:intake|packet|photos|file|per intake|flagged)[^)]*\)", original, re.IGNORECASE))
        polished_parens = len(re.findall(r"\([^)]*(?:intake|packet|photos|file|per intake|flagged)[^)]*\)", polished, re.IGNORECASE))
        if original_parens > polished_parens:
            changes.append(f"Removed {original_parens - polished_parens} pipeline parenthetical artifact(s)")

        # Check for non-standard headers removed
        for header in ["FACTUAL SUMMARY", "LEGAL THEORIES", "TIMING RISK", "ACTION ITEMS"]:
            if header in original and header not in polished:
                changes.append(f"Removed non-standard header '{header}'")

        # Check for spacing improvements
        original_triple_newlines = original.count("\n\n\n")
        polished_triple_newlines = polished.count("\n\n\n")

        if original_triple_newlines > polished_triple_newlines:
            changes.append(
                f"Fixed {original_triple_newlines - polished_triple_newlines} excessive spacing issues"
            )

        # Check for doctrine title formatting consistency
        original_bold_bullets = original.count("• **")
        polished_bold_bullets = polished.count("• **")
        if polished_bold_bullets > original_bold_bullets:
            changes.append(
                f"Standardized {polished_bold_bullets - original_bold_bullets} doctrine title format(s)"
            )

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
    return await asyncio.to_thread(polisher.polish_letter, raw_letter)


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
