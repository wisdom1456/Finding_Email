"""This module provides lightweight quality assurance checks for generated findings letters."""
from typing import Any, Dict, List


def run_qa_heuristics(letter_content: str, analysis_json: Dict[str, Any]) -> List[str]:
    """Runs a series of lightweight, heuristic-based QA checks on the generated letter.

    Args:
    ----
        letter_content: The HTML content of the generated findings letter.
        analysis_json: The structured JSON data used to generate the letter.

    Returns:
    -------
        A list of warning strings for any potential issues found.

    """
    warnings = []

    # Check 1: No Florida broker-reg citations in seller-disclosure letters
    if "seller" in letter_content.lower() and "disclosure" in letter_content.lower():
        if "§ 475.25" in letter_content or "§ 475.278" in letter_content:
            warnings.append(
                "QA Warning: Letter appears to be about seller disclosure but contains a "
                "Florida broker-regulation citation (§ 475.25 or § 475.278). "
                "Verify this is not a mis-citation for Johnson v. Davis."
            )

    # Check 2: Presence of timelines where procedural statutes are referenced
    procedural_keywords = ["Chapter 558", "pre-suit", "notice and opportunity to cure"]
    if any(keyword in letter_content for keyword in procedural_keywords):
        timeline_keywords = ["days", "months", "timeline", "deadline", " respond"]
        if not any(timeline in letter_content for timeline in timeline_keywords):
            warnings.append(
                "QA Warning: Letter mentions a procedural process (e.g., Chapter 558) "
                "but does not appear to specify any timelines (e.g., '60 days'). "
                "Verify procedural timelines are included."
            )

    # Check 3: If lien risk is present, at least one owner tool is mentioned
    has_lien_risk = False
    if analysis_json and "documents" in analysis_json:
        for doc in analysis_json["documents"]:
            if "risk_items" in doc and doc["risk_items"]:
                if any("lien risk" in item.lower() for item in doc["risk_items"]):
                    has_lien_risk = True
                    break

    if has_lien_risk:
        owner_tools = ["waiver", "Notice of Contest", "transfer to bond", "joint check"]
        if not any(tool.lower() in letter_content.lower() for tool in owner_tools):
            warnings.append(
                "QA Warning: Analysis JSON indicates a lien risk, but the letter does not "
                "appear to mention any owner tools (e.g., lien waiver, Notice of Contest). "
                "Verify client has been advised on protective actions."
            )

    return warnings
