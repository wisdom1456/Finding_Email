"""Letter formatting validator and fixer.

Ensures all letters follow the standard professional format.
"""

import re
from typing import Tuple


class LetterFormatter:
    """Validates and fixes letter formatting for natural flow style."""

    @staticmethod
    def validate_format(letter_text: str) -> Tuple[bool, list]:
        """Validate letter formatting against natural flow standards.

        Returns
        -------
            (is_valid, list_of_issues)

        """
        issues = []

        # Check 1: Should NOT have formal section headers (natural flow)
        if re.search(r"^1\.\s+FACTUAL\s+SUMMARY", letter_text, re.MULTILINE | re.IGNORECASE):
            issues.append(
                "Has formal 'FACTUAL SUMMARY' header - should flow naturally without formal headers"
            )

        if re.search(r"^\d+\.\s+RECOMMENDED\s+ACTION", letter_text, re.MULTILINE | re.IGNORECASE):
            issues.append(
                "Has formal 'RECOMMENDED ACTION' header - should start with 'Based on the above...'"
            )

        # Check 2: Should NOT use "Key Findings"
        if "Key Findings" in letter_text:
            issues.append("Uses 'Key Findings' - should use 'Here are the key points of our analysis:'")

        # Check 3: Should have the transition line
        if "Here are the key points of our analysis" not in letter_text:
            issues.append("Missing transition line 'Here are the key points of our analysis:'")

        # Check 4: Should have bullet points for legal analysis
        if "•" not in letter_text:
            issues.append("Missing bullet points (•) for legal analysis")

        # Check 5: Bullets should NOT have bold headers (natural flow)
        bold_bullet_count = letter_text.count("• **")
        if bold_bullet_count > 0:
            issues.append(
                f"Has {bold_bullet_count} bold bullet headers - bullets should flow naturally without bold titles"
            )

        # Check 6: Should have warm greeting
        has_warm_greeting = "Good afternoon" in letter_text or "Good morning" in letter_text
        has_dear = "Dear " in letter_text
        if not has_warm_greeting and not has_dear:
            issues.append("Missing greeting - should start with 'Good afternoon/morning' or 'Dear'")

        # Check 7: Should have call to action
        if "Please let us know" not in letter_text and "please let us know" not in letter_text:
            issues.append("Missing call to action - should include 'Please let us know if you would like...'")

        # Check 8: Excessive spacing
        if re.search(r"\n\n\n+", letter_text):
            issues.append("Has excessive spacing (3+ blank lines in a row)")

        return (len(issues) == 0, issues)

    @staticmethod
    def fix_common_issues(letter_text: str) -> str:
        """Automatically fix common formatting issues for natural flow style.

        Args:
        ----
            letter_text: The letter text to fix

        Returns:
        -------
            Fixed letter text

        """
        text = letter_text

        # Fix 1: Replace "Key Findings" with correct transition
        if "Key Findings" in text:
            text = text.replace("Key Findings", "Here are the key points of our analysis:")

        # Fix 2: Remove formal section headers
        text = re.sub(r"^\d+\.\s+FACTUAL\s+SUMMARY\s*\n+", "", text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(
            r"^\d+\.\s+RECOMMENDED\s+ACTION.*?\n+",
            "Based on the above, ",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        # Fix 3: Remove excessive blank lines (3+ to 2)
        text = re.sub(r"\n\n\n+", "\n\n", text)

        # Fix 4: Fix bullet symbols if using wrong ones
        text = text.replace("- ", "• ")  # Replace dash bullets at line start
        text = text.replace("* ", "• ")  # Replace asterisk bullets

        # Fix 5: Ensure proper greeting format
        if text.strip().startswith("Dear "):
            # Keep Dear format as acceptable alternative
            pass

        return text

    @staticmethod
    def get_formatting_report(letter_text: str) -> dict:
        """Get a detailed formatting report for natural flow style.

        Returns
        -------
            dict with validation results and suggestions

        """
        is_valid, issues = LetterFormatter.validate_format(letter_text)

        # Count formal headers (should be 0 for natural flow)
        formal_header_count = len(re.findall(r"^\d+\.\s+[A-Z]{2,}", letter_text, re.MULTILINE))

        # Count bullets
        bullet_count = letter_text.count("•")

        # Count bold bullet headers (should be 0 for natural flow)
        bold_bullet_count = letter_text.count("• **")

        # Check spacing
        has_excessive_spacing = bool(re.search(r"\n\n\n+", letter_text))

        # Check for warm greeting
        has_warm_greeting = "Good afternoon" in letter_text or "Good morning" in letter_text

        # Word count
        word_count = len(letter_text.split())

        return {
            "is_valid": is_valid,
            "issues": issues,
            "formal_header_count": formal_header_count,
            "bullet_count": bullet_count,
            "bold_bullet_count": bold_bullet_count,
            "has_excessive_spacing": has_excessive_spacing,
            "has_warm_greeting": has_warm_greeting,
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
            elif "FACTUAL SUMMARY" in issue:
                suggestions.append("Remove formal 'FACTUAL SUMMARY' header - let the letter flow naturally")
            elif "RECOMMENDED ACTION" in issue:
                suggestions.append(
                    "Remove formal 'RECOMMENDED ACTION' header - start with 'Based on the above...'"
                )
            elif "bold bullet headers" in issue:
                suggestions.append(
                    "Remove bold headers from bullets - each bullet should flow as a paragraph"
                )
            elif "bullet points" in issue:
                suggestions.append("Add bullet points (•) for each legal concept in the analysis")
            elif "excessive spacing" in issue:
                suggestions.append("Reduce blank lines to maximum 2 between sections")
            elif "greeting" in issue:
                suggestions.append("Add a warm greeting: 'Good afternoon [Name],' or 'Dear [Name],'")
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
