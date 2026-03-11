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
2. Do NOT remove concrete facts that appear in the draft. Every factual statement (names, dates, amounts, key events) must remain present after polishing.
3. Keep names, numbers, deadlines, and document references accurate and unchanged.
4. You have style leeway only: improve format, tone, transitions, and readability without changing factual substance.

TARGET STYLE:
- Professional attorney correspondence — measured, thorough, and confident.
- Plain English a non-lawyer can understand without feeling talked down to.
- Clear paragraph structure within each section.
- Natural paragraphs that flow as continuous correspondence.

SECTION STRUCTURE (PRESERVE):
- The email should have four labeled sections: Background & Issue, Key Legal Issues, Analysis, Recommended Next Steps.
- Do NOT remove or rename these section headers. (Legacy "Key Provisions" headers are also acceptable.)
- Do NOT merge sections.
- Within Key Legal Issues, each doctrine should have a bold title followed by an analytical paragraph.

FORMATTING FIXES TO APPLY:
1. Remove internal pipeline parentheticals and source-label artifacts from the body text (e.g., "(intake packet 01-11-2026)", "(photos, file)") — preserve the underlying fact in natural prose.
2. Replace any internal pipeline language ("client-reported", "per intake", "flagged in analysis") with natural attorney voice.
3. Smooth transitions between paragraphs within each section.
4. Keep one blank line between paragraphs.
5. Preserve greeting, signature, and confidentiality language.
6. Ensure consistent formatting of doctrine titles in Key Legal Issues (bold, followed by colon).
7. Ensure document references read naturally ("per the contract", "the inspection report documents") without citation-style parentheticals.
8. Remove all distancing or doubt-casting phrasing toward the client. Replace phrases like "you report", "you state", "you say", "you claim", "you allege", or "you indicate" — when referring to the client's account of events — with direct, trust-affirming language: "you have", "you invested", "as you described", "based on what you've shared."
9. Replace attorney and litigation shop talk with plain English throughout. This applies to any term a non-lawyer would not immediately understand. Examples: "spoliation" → "prevent the other side from destroying records"; "standing" → "your right to bring this claim"; "accrual" → "when the deadline clock starts"; "plaintiff" → use the client's name or "you"; "cause of action" → "legal claim"; "filing posture" → "ready to file"; "for limitations purposes" → "for the filing deadline."
10. Replace abstract or clinical terms for people with human language. Words like "actors", "principals", "participants", or "entities" — when referring to individual people — should become "individuals", "people", or the person's actual name.
11. Integrate inline legal definitions naturally into prose instead of using a textbook or dictionary quotation style. Instead of '"Breach of contract" means one side failed to perform...', write it as 'breach of contract — meaning they failed to deliver on the written commitments — is the primary path forward.'
12. Rewrite any em-dash sub-header opening lines into a warm, natural sentence greeting. For example, "Good afternoon — brief summary after review." should become "Good afternoon, I wanted to share where things stand after our review."

OUTPUT INSTRUCTIONS:
- Return ONLY the formatted letter text.
- No commentary.
- Keep markdown-safe paragraph text (no code fences).
"""

    def polish_letter(self, raw_letter: str, timeout: float | None = None) -> Dict:
        """Polish a generated letter for consistent formatting.

        Args:
        ----
            raw_letter: The unpolished letter text
            timeout: Optional HTTP timeout in seconds for the OpenAI call

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
                timeout=timeout,
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

        # Check for bold bullet formatting changes
        original_bold_bullets = original.count("• **")
        polished_bold_bullets = polished.count("• **")
        if polished_bold_bullets > original_bold_bullets:
            changes.append(
                f"Standardized {polished_bold_bullets - original_bold_bullets} doctrine title format(s)"
            )
        elif original_bold_bullets > polished_bold_bullets:
            removed = original_bold_bullets - polished_bold_bullets
            changes.append(
                f"Converted {removed} bold bullet(s) to prose format"
            )

        return changes


async def polish_letter_async(openai_client, raw_letter: str, timeout_seconds: float = 55.0) -> Dict:
    """Async wrapper for letter polishing.

    Always attempts polish. Hard-bounded at timeout_seconds. Falls back to original on timeout.

    Args:
    ----
        openai_client: OpenAI client instance
        raw_letter: The unpolished letter text
        timeout_seconds: Hard asyncio timeout; falls back to pre-polish draft on expiry

    Returns:
    -------
        dict with polished letter and metadata

    """
    polisher = LetterPolisher(openai_client)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(polisher.polish_letter, raw_letter, timeout=timeout_seconds - 5),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("[POLISH] Timed out after %.1fs — using pre-polish draft", timeout_seconds)
        return {"success": False, "polished_letter": raw_letter, "changes_made": [], "error": "timeout"}


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
