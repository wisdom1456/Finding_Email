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
4. Improve format, tone, and flow only.

TARGET STYLE:
- Real attorney email voice — warm, direct, and confident.
- Plain English a non-lawyer can understand without feeling talked down to.
- Natural paragraphs that flow as continuous correspondence.
- No section headers.
- No bold labels.
- No bullet lists, except for client action items (things the client must do or provide) where a short numbered list genuinely aids clarity.
- No numbered lists elsewhere.

FORMATTING AND TONE FIXES TO APPLY:
1. Remove standalone section labels (for example: "Facts", "Legal Theories", "Timing and Risk", "Next Steps").
2. Convert bullet and numbered list items into paragraph prose while preserving all content. Exception: if a paragraph lists specific things the client must provide or do, a short numbered list is acceptable.
3. Smooth transitions so the letter reads as continuous correspondence.
4. Keep one blank line between paragraphs.
5. Preserve greeting, signature, and confidentiality language.
6. Remove all parenthetical document source citations from the body text. These are internal pipeline references, not client-facing prose. Any parenthetical that names a source document, date, or internal reference label should be deleted entirely. The substantive fact already stated in the sentence is sufficient — do not replace the parenthetical with anything.
7. Replace internal pipeline language with natural attorney voice. Any phrase that reads like a system label — such as "client-reported [X]", "per intake", "flagged in analysis", or similar — should be rewritten as natural first-person correspondence: "the deadline you mentioned", "the date you flagged", "based on what you've shared."
8. Remove all distancing or doubt-casting phrasing toward the client. Replace phrases like "you report", "you state", "you say", "you claim", "you allege", or "you indicate" — when referring to the client's account of events — with direct, trust-affirming language: "you have", "you invested", "as you described", "based on what you've shared." The attorney should sound like they believe their client.
9. Replace attorney and litigation shop talk with plain English throughout. This applies to any term a non-lawyer would not immediately understand. Examples: "build leverage" → "put pressure on the other side while protecting your rights"; "spoliation" or "prevent spoliation" → "prevent the other side from destroying records"; "standing" (in the procedural sense) → "your right to bring this claim"; "accrual" or "accrual points" → "when the deadline clock starts on each claim"; "plaintiff" when used in a client-facing letter → use the client's name or "you" / "your side"; "defendant" → use the other party's name or "the other side"; "cause of action" → "legal claim"; "counts" → "claims"; "filing posture" or "move into filing posture" → "ready to file" or "prepared to file suit"; "for limitations purposes" or "limitations deadline" → "for the filing deadline" or "given the deadline risk."
10. Replace abstract or clinical terms for people with human language. Words like "actors", "principals", "participants", or "entities" — when referring to individual people — should become "individuals", "people", or the person's actual name. Reserve formal terms for document or entity names only.
11. Integrate inline legal definitions naturally into the prose instead of using a textbook quotation style. Instead of '"Breach of contract" means one side failed to perform...', write something like 'breach of contract — meaning they failed to deliver on the written commitments — is the primary path forward.' Keep the plain-English explanation but make it read like an attorney explaining something, not a dictionary defining a term. This rule applies to every legal term that is formally defined in the letter.
12. Rewrite any em-dash sub-header opening lines into a warm, natural sentence greeting. For example, "Good afternoon Erica — brief summary and next steps after our review." should become "Good afternoon Erica, I wanted to share where things stand after our review of your file." The tone should feel like a thoughtful attorney reaching out, not a newsletter subject line.
13. If the letter contains a paragraph that defines a legal theory in one or more sentences and then separately explains how it applies to the client's situation, merge them into a single sentence or thought that states the theory and its practical meaning together. Do not separate "what the law says" from "what it means for you" — combine them.
14. If the letter has a paragraph that starts with or contains "To prevail", "To establish", "To succeed on this claim", or "The elements of" — rewrite it to lead with what the client needs to know practically, removing the element-listing structure entirely. Replace with a direct statement of the claim and why it applies.
15. If secondary legal theories each get their own full paragraph with definition + application, compress them into a combined paragraph that briefly mentions each in one sentence. Only the primary/strongest theory should get a full paragraph.
16. If there is a standalone paragraph that defines legal terms in sequence (like a glossary), remove it entirely — the terms should already be defined inline where they first appear in the letter.

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
