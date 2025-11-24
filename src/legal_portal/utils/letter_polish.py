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
        """Load the strict formatting prompt."""
        return """You are a legal document formatting specialist. Your ONLY job is to fix formatting and layout issues in the provided letter while preserving ALL legal content.

CRITICAL RULES:
1. Do NOT change any legal content, analysis, or wording
2. Do NOT add or remove legal information
3. ONLY fix formatting, spacing, and structure
4. Preserve all attorney signatures, dates, and case-specific details

REQUIRED FORMAT:

```
Subject: Legal Review and Recommended Next Steps – [Case Name]

Dear [Client Name],

[Opening paragraph]

1. FACTUAL SUMMARY

[Paragraphs describing facts]

Here are the key points of our analysis:

• **[Issue 1] ([Statute])**: [Explanation]
• **[Issue 2]**: [Explanation]
• **[Issue 3] ([Statute])**: [Explanation]

2. RECOMMENDED ACTION & NEXT STEPS

[Recommendations]

[Closing]

Thank you,

[Attorney Name]
[Title]

[Disclaimer]
```

FORMATTING FIXES TO APPLY:

1. SECTION NUMBERING:
   - Ensure section 1 is: "1. FACTUAL SUMMARY"
   - If you see "Key Findings" → change to "Here are the key points of our analysis:"
   - If you see numbered sections 2., 3., 4. for legal issues → convert to bullets (•)
   - Final section should be numbered for recommendations

2. BULLET FORMAT:
   - All legal issues must use bullet symbol: •
   - Format: • **[Title] ([Statute])**: [Content]
   - NO blank lines between consecutive bullets
   - Use dashes (-) for sub-items within a bullet

3. SPACING:
   - 1 blank line after greeting
   - 1 blank line before/after section headers
   - 1 blank line between paragraphs
   - NO blank lines between bullets (• items)
   - 1 blank line before closing

4. HEADERS:
   - Section headers: NUMBER. ALL CAPS (e.g., "1. FACTUAL SUMMARY")
   - Transition: "Here are the key points of our analysis:" (sentence case)
   - Legal issues: • **Title Case Bold** ([Statute]):

5. SUB-SECTIONS:
   - Use bold for sub-section titles (e.g., **Pre-Litigation Requirements:**)
   - Indent sub-items with dashes (-)
   - 1 blank line before sub-section, no blank line after title

EXAMPLES OF FIXES:

BEFORE:
```
Key Findings

2. IMPLIED WARRANTY & CONSTRUCTION DEFECTS

Under Florida law...

3. BREACH OF CONTRACT

A breach occurs...
```

AFTER:
```
Here are the key points of our analysis:

• **Implied Warranty & Construction Defects (Florida Statutes Chapter 558)**: Under Florida law...

• **Breach of Contract**: A breach occurs...
```

BEFORE (excessive spacing):
```
• **Issue 1**: Text


• **Issue 2**: Text


• **Issue 3**: Text
```

AFTER (correct spacing):
```
• **Issue 1**: Text
• **Issue 2**: Text
• **Issue 3**: Text
```

OUTPUT INSTRUCTIONS:
- Return ONLY the formatted letter
- No commentary, no explanations
- Preserve ALL legal content exactly
- Fix ONLY formatting and layout
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

            # Make the AI call
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a legal document formatting specialist. Fix formatting ONLY, preserve all content.",
                    },
                    {"role": "user", "content": full_prompt},
                ],
                temperature=0.1,  # Very low for consistency
                max_tokens=4000,
            )

            polished_letter = response.choices[0].message.content.strip()

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

        # Check for numbered sections converted to bullets
        original_numbered = len(
            [x for x in original.split("\n") if x.strip().startswith(("2.", "3.", "4.")) and x.isupper()]
        )
        polished_numbered = len(
            [x for x in polished.split("\n") if x.strip().startswith(("2.", "3.", "4.")) and x.isupper()]
        )

        if original_numbered > polished_numbered:
            changes.append(
                f"Converted {original_numbered - polished_numbered} numbered sections to bullet format"
            )

        # Check for bullet symbol changes
        original_bullets = original.count("• **")
        polished_bullets = polished.count("• **")

        if polished_bullets > original_bullets:
            changes.append(f"Added {polished_bullets - original_bullets} bullet symbols")

        # Check for spacing improvements
        original_triple_newlines = original.count("\n\n\n")
        polished_triple_newlines = polished.count("\n\n\n")

        if original_triple_newlines > polished_triple_newlines:
            changes.append(
                f"Fixed {original_triple_newlines - polished_triple_newlines} excessive spacing issues"
            )

        # Check for section 1 addition
        if "1. FACTUAL SUMMARY" not in original and "1. FACTUAL SUMMARY" in polished:
            changes.append("Added '1. FACTUAL SUMMARY' section header")

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
    """Synchronous letter polishing.

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
