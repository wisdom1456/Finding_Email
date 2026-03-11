"""Letter formatting validator and fixer.

Ensures all letters follow the structured professional format.
"""

import re
from typing import Tuple

_REQUIRED_SECTIONS = [
    ("BACKGROUND & ISSUE", r"(?im)^(?:BACKGROUND\s*(?:&|AND)\s*ISSUE|Background\s*(?:&|and)\s*Issue)\s*:?\s*$"),
    ("KEY LEGAL ISSUES", r"(?im)^(?:KEY\s*(?:PROVISIONS?|LEGAL\s*ISSUES?)|Key\s*(?:Provisions?|Legal\s*Issues?))\s*:?\s*$"),
    ("ANALYSIS", r"(?im)^(?:ANALYSIS|Analysis)\s*:?\s*$"),
    ("RECOMMENDED NEXT STEPS", r"(?im)^(?:RECOMMENDED\s*NEXT\s*STEPS?|Recommended\s*Next\s*Steps?)\s*:?\s*$"),
]

_NON_STANDARD_HEADER_PATTERN = re.compile(
    r"(?im)^\s*\d+\.\s+(?:FACTUAL\s+SUMMARY|RECOMMENDED\s+ACTION|LEGAL\s+THEORIES|TIMING\s+RISK)",
)


class LetterFormatter:
    """Validates and fixes letter formatting for structured professional style."""

    @staticmethod
    def validate_format(letter_text: str) -> Tuple[bool, list]:
        """Validate letter formatting against structured professional standards.

        Returns
        -------
            (is_valid, list_of_issues)

        """
        issues = []

        # Check 1: Should have required section headers
        for label, pattern in _REQUIRED_SECTIONS:
            if not re.search(pattern, letter_text):
                issues.append(f"Missing required section header: {label}")

        # Check 2: Should NOT have non-standard numbered headers
        if _NON_STANDARD_HEADER_PATTERN.search(letter_text):
            issues.append(
                "Has non-standard numbered section headers - use only: "
                "Background & Issue, Key Legal Issues, Analysis, Recommended Next Steps"
            )

        # Check 3: KEY LEGAL ISSUES (or KEY PROVISIONS) should have bold doctrine titles
        if re.search(r"(?im)^KEY\s*(?:PROVISIONS|LEGAL\s*ISSUES)", letter_text):
            bold_bullet_count = letter_text.count("• **")
            if bold_bullet_count == 0:
                issues.append("Key Legal Issues section has no bold-titled doctrine bullets")

        # Check 4: Should have greeting
        has_greeting = "Good afternoon" in letter_text or "Good morning" in letter_text or "Dear " in letter_text
        if not has_greeting:
            issues.append("Missing greeting - should start with 'Good afternoon/morning' or 'Dear'")

        # Check 5: Should have call to action
        if "Please let us know" not in letter_text and "please let us know" not in letter_text:
            issues.append("Missing call to action - should include 'Please let us know if you would like...'")

        # Check 6: Excessive spacing
        if re.search(r"\n\n\n+", letter_text):
            issues.append("Has excessive spacing (3+ blank lines in a row)")

        return (len(issues) == 0, issues)

    @staticmethod
    def fix_common_issues(letter_text: str) -> str:
        """Automatically fix common formatting issues.

        Args:
        ----
            letter_text: The letter text to fix

        Returns:
        -------
            Fixed letter text

        """
        text = letter_text

        # Fix 1: Remove non-standard numbered headers
        text = re.sub(r"^\d+\.\s+FACTUAL\s+SUMMARY\s*\n+", "BACKGROUND & ISSUE:\n\n", text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(
            r"^\d+\.\s+RECOMMENDED\s+ACTION.*?\n+",
            "RECOMMENDED NEXT STEPS:\n\n",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        # Fix 2: Remove excessive blank lines (3+ to 2)
        text = re.sub(r"\n\n\n+", "\n\n", text)

        return text

    @staticmethod
    def get_formatting_report(letter_text: str) -> dict:
        """Get a detailed formatting report.

        Returns
        -------
            dict with validation results and suggestions

        """
        is_valid, issues = LetterFormatter.validate_format(letter_text)

        # Count required section headers found
        section_headers_found = sum(
            1 for _, pattern in _REQUIRED_SECTIONS if re.search(pattern, letter_text)
        )

        # Count bullets
        bullet_count = letter_text.count("•")

        # Count bold doctrine titles in KEY LEGAL ISSUES
        bold_bullet_count = letter_text.count("• **")

        # Check spacing
        has_excessive_spacing = bool(re.search(r"\n\n\n+", letter_text))

        # Check for greeting
        has_greeting = "Good afternoon" in letter_text or "Good morning" in letter_text or "Dear " in letter_text

        # Word count
        word_count = len(letter_text.split())

        return {
            "is_valid": is_valid,
            "issues": issues,
            "section_headers_found": section_headers_found,
            "bullet_count": bullet_count,
            "bold_bullet_count": bold_bullet_count,
            "has_excessive_spacing": has_excessive_spacing,
            "has_greeting": has_greeting,
            "word_count": word_count,
            "suggestions": LetterFormatter._generate_suggestions(issues),
        }

    @staticmethod
    def _generate_suggestions(issues: list) -> list:
        """Generate actionable suggestions based on issues."""
        suggestions = []

        for issue in issues:
            if "Missing required section header" in issue:
                suggestions.append(f"Add the missing section header: {issue.split(': ')[-1]}")
            elif "non-standard" in issue:
                suggestions.append(
                    "Replace non-standard headers with: Background & Issue, Key Legal Issues, Analysis, Recommended Next Steps"
                )
            elif "bold-titled" in issue:
                suggestions.append(
                    "Add bold doctrine titles to Key Legal Issues bullets (e.g., '• **Breach of Contract:**')"
                )
            elif "excessive spacing" in issue:
                suggestions.append("Reduce blank lines to maximum 2 between sections")
            elif "greeting" in issue:
                suggestions.append("Add a professional greeting: 'Good afternoon [Name],' or 'Dear [Name],'")
            elif "call to action" in issue:
                suggestions.append("Add closing: 'Please let us know if you would like us to proceed...'")

        return suggestions


def format_letter(letter_text: str, auto_fix: bool = False) -> Tuple[str, dict]:
    """Main function to validate and optionally fix letter formatting.

    Args:
    ----
        letter_text: The letter to format
        auto_fix: Whether to automatically fix common issues

    Returns:
    -------
        (formatted_text, report)

    """
    formatter = LetterFormatter()

    # Get initial report
    report = formatter.get_formatting_report(letter_text)

    # Apply fixes if requested
    if auto_fix and not report["is_valid"]:
        letter_text = formatter.fix_common_issues(letter_text)
        # Get updated report
        report = formatter.get_formatting_report(letter_text)
        report["auto_fixed"] = True
    else:
        report["auto_fixed"] = False

    return letter_text, report
