"""Letter formatting validator and fixer.

Ensures all letters follow the standard professional format.
"""

import re
from typing import Tuple


class LetterFormatter:
    """Validates and fixes letter formatting."""

    @staticmethod
    def validate_format(letter_text: str) -> Tuple[bool, list]:
        """Validate letter formatting against standards.

        Returns
        -------
            (is_valid, list_of_issues)
        """
        issues = []

        # Check 1: Has section 1
        if not re.search(r"^1\.\s+FACTUAL\s+SUMMARY", letter_text, re.MULTILINE | re.IGNORECASE):
            issues.append("Missing '1. FACTUAL SUMMARY' section header")

        # Check 2: Has transition line (not "Key Findings")
        if "Key Findings" in letter_text and "Here are the key points" not in letter_text:
            issues.append("Uses 'Key Findings' instead of 'Here are the key points of our analysis:'")

        # Check 3: No numbered legal issues (2., 3., 4. for legal topics)
        # Look for patterns like "2. IMPLIED" or "3. BREACH"
        numbered_issues = re.findall(
            r"^\d+\.\s+[A-Z]{2,}[A-Z\s&]+(?:WARRANTY|CONTRACT|LIEN|BANKRUPTCY)", letter_text, re.MULTILINE
        )
        if numbered_issues:
            issues.append(
                f"Found numbered legal issue headers (should be bullets): {', '.join(numbered_issues[:3])}"
            )

        # Check 4: Has bullet symbols for legal issues
        if "• **" not in letter_text and "•**" not in letter_text:
            issues.append("Missing bullet symbols (•) for legal issues")

        # Check 5: Excessive spacing between bullets
        if re.search(r"• \*\*.*\n\n\n+• \*\*", letter_text):
            issues.append("Too many blank lines between bullet items (should be 0)")

        # Check 6: Has final recommendations section
        if not re.search(r"^\d+\.\s+RECOMMENDED\s+ACTION", letter_text, re.MULTILINE | re.IGNORECASE):
            issues.append("Missing numbered 'RECOMMENDED ACTION' section")

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

        # Fix 1: Replace "Key Findings" with correct transition
        if "Key Findings" in text and "Here are the key points" not in text:
            text = text.replace("Key Findings", "Here are the key points of our analysis:")

        # Fix 2: Remove excessive blank lines between bullets
        # Replace 2+ blank lines between bullets with 0 blank lines
        text = re.sub(r"(• \*\*[^\n]+)\n\n+(?=• \*\*)", r"\1\n", text)

        # Fix 3: Ensure proper spacing after section headers
        # Should be exactly 1 blank line
        text = re.sub(r"(^\d+\.\s+[A-Z\s]+)\n\n+", r"\1\n\n", text, flags=re.MULTILINE)

        # Fix 4: Ensure proper spacing before section headers
        # Should be exactly 1 blank line
        text = re.sub(r"\n\n\n+(^\d+\.\s+[A-Z\s]+)", r"\n\n\1", text, flags=re.MULTILINE)

        # Fix 5: Fix bullet symbols if using wrong ones
        text = text.replace("- **", "• **")  # Replace dash bullets
        text = text.replace("* **", "• **")  # Replace asterisk bullets

        # Fix 6: Remove extra spaces in section headers
        text = re.sub(r"^\d+\.\s{2,}", lambda m: m.group(0)[:3], text, flags=re.MULTILINE)

        return text

    @staticmethod
    def get_formatting_report(letter_text: str) -> dict:
        """Get a detailed formatting report.

        Returns
        -------
            dict with validation results and suggestions
        """
        is_valid, issues = LetterFormatter.validate_format(letter_text)

        # Count sections
        section_count = len(re.findall(r"^\d+\.\s+[A-Z]", letter_text, re.MULTILINE))

        # Count bullets
        bullet_count = letter_text.count("• **")

        # Check spacing
        has_excessive_spacing = bool(re.search(r"\n\n\n+", letter_text))

        # Word count
        word_count = len(letter_text.split())

        return {
            "is_valid": is_valid,
            "issues": issues,
            "section_count": section_count,
            "bullet_count": bullet_count,
            "has_excessive_spacing": has_excessive_spacing,
            "word_count": word_count,
            "suggestions": LetterFormatter._generate_suggestions(issues),
        }

    @staticmethod
    def _generate_suggestions(issues: list) -> list:
        """Generate actionable suggestions based on issues."""
        suggestions = []

        for issue in issues:
            if "Key Findings" in issue:
                suggestions.append("Change 'Key Findings' to 'Here are the key points of our analysis:'")
            elif "numbered legal issue" in issue:
                suggestions.append("Convert numbered sections (2., 3., 4.) to bullet format (•)")
            elif "FACTUAL SUMMARY" in issue:
                suggestions.append("Add '1. FACTUAL SUMMARY' as the first main section")
            elif "bullet symbols" in issue:
                suggestions.append("Use bullet symbols (•) for legal issues, not dashes or numbers")
            elif "blank lines" in issue:
                suggestions.append("Remove extra blank lines between consecutive bullet items")
            elif "RECOMMENDED ACTION" in issue:
                suggestions.append("Add a final numbered section for recommendations")

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
