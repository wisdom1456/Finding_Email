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
Your ONLY job is to ensure the letter flows naturally while preserving
ALL legal content.

CRITICAL RULES:
1. Do NOT change any legal content, analysis, or wording
2. Do NOT add or remove legal information
3. ONLY improve natural flow and readability
4. Preserve all attorney signatures, dates, and case-specific details

TARGET FORMAT - NATURAL FLOW (NOT formal legal memo):

```
Subject: Legal Review and Recommended Next Steps – [Case Name]

Good afternoon [Client Name],

I hope you are doing well. I wanted to follow up with a summary of our
findings after reviewing [documents], regarding your property at [address].

As discussed, the primary concern is [plain English statement].

[2-3 paragraphs describing the factual situation - NO formal headers]

Here are the key points of our analysis:

• [Complete paragraph explaining legal concept in plain English. What this means for you: practical impact.]

• [Next complete paragraph - NO bold headers at start of bullets]

• [Additional points as needed]

Based on the above, [recommendations paragraph].

[Protective checklist if applicable]

Please let us know if you would like us to proceed with [action].

Thank you,

[Attorney Name]
[Title]

[Disclaimer]
```

FORMATTING FIXES TO APPLY:

1. REMOVE FORMAL HEADERS:
   - If you see "FACTUAL SUMMARY" or "1. FACTUAL SUMMARY" → REMOVE IT, let facts flow naturally
   - If you see "RECOMMENDED ACTION & NEXT STEPS" → REMOVE IT, start with "Based on the above..."
   - If you see "Key Findings" → change to "Here are the key points of our analysis:"

2. REMOVE BOLD ISSUE TITLES:
   - If you see "• **Implied Warranty**:" → change to "• Under Florida law, there's a protection called..."
   - Bullets should be flowing paragraphs, NOT formatted headers
   - Each bullet should read like a conversation, not a legal outline

3. ENSURE PLAIN LANGUAGE:
   - Every legal term should have an explanation
   - Look for "What this means for you:" or similar practical impact statements
   - If missing, the content is fine - don't add, just ensure good flow

4. SPACING:
   - 1 blank line between paragraphs
   - 1 blank line after "Here are the key points of our analysis:"
   - Minimal blank lines between bullet items (0-1)
   - 1 blank line before closing

5. GREETING:
   - Prefer "Good afternoon [Name]," or "Good morning [Name],"
   - "Dear [Name]:" is acceptable but less warm

EXAMPLES OF FIXES:

BEFORE (too formal):
```
1. FACTUAL SUMMARY

Based on our review...

Here are the key points of our analysis:

• **Implied Warranty & Construction Defects (Florida Statutes Chapter 558)**:
  Under Florida law, an implied warranty exists...

2. RECOMMENDED ACTION & NEXT STEPS

Based on the above...
```

AFTER (natural flow):
```
Based on our review, we understand that...

Here are the key points of our analysis:

• Under Florida law, there's an important protection called an "implied warranty
  of workmanlike construction." This means contractors are legally required to
  do competent work, even if your contract doesn't say so. In your case,
  [application]. What this means for you: [impact].

Based on the above, a negotiated resolution would likely be your most efficient path forward...
```

OUTPUT INSTRUCTIONS:
- Return ONLY the formatted letter
- No commentary, no explanations
- Preserve ALL legal content exactly
- Improve natural flow and remove formal headers
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
