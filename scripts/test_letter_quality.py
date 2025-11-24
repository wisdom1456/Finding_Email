#!/usr/bin/env python3
"""Letter Quality Test Suite

Automated testing framework that:
- Loads real attorney letters as "gold standard"
- Generates letter for test case using current system
- Compares formatting, tone, length, structure
- Scores letter quality on 14 criteria (0-100 scale)
- Outputs detailed comparison and issues
"""

import re
import sys
from pathlib import Path
from typing import Dict, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class LetterQualityScorer:
    """Scores generated letters against 14 quality criteria."""

    def __init__(self):
        self.criteria = [
            ("section_numbering", "Proper section numbering (1., 2.)", 10),
            ("bullet_intro", "'Here are the key points...' not 'Key Findings'", 10),
            ("bullet_symbols", "Bullet symbols (•) for legal issues", 10),
            ("no_caps_headers", "No ALL CAPS headers", 5),
            ("conversational_tone", "Conversational-educational tone", 10),
            ("specific_opening", "Specific documents/address in opening", 8),
            ("no_as_discussed", "Avoids vague 'As discussed'", 5),
            ("timeline_durations", "Date math with durations calculated", 10),
            ("educational_explanations", "Explains legal concepts educationally", 10),
            ("integrated_procedures", "Procedures integrated, not standalone", 7),
            ("simple_closing", "Simple, conversational closing", 5),
            ("length_appropriate", "Length similar to attorney letters (±20%)", 5),
            ("no_formal_checklists", "No 'Protective Action Checklist:' headers", 3),
            ("proper_issue_integration", "Minor issues integrated, not separate", 2),
        ]

    def score_letter(self, letter_text: str, gold_standard: str = None) -> Dict:
        """Score letter on all criteria and return detailed results."""
        scores = {}
        issues = []
        total_score = 0
        max_possible = sum(weight for _, _, weight in self.criteria)

        # Run each criterion check
        for criterion_id, description, weight in self.criteria:
            method = getattr(self, f"check_{criterion_id}")
            passed, feedback = method(letter_text, gold_standard)

            score = weight if passed else 0
            scores[criterion_id] = {
                "passed": passed,
                "score": score,
                "max": weight,
                "description": description,
                "feedback": feedback,
            }

            total_score += score
            if not passed:
                issues.append(f"❌ {description}: {feedback}")

        # Calculate percentage
        percentage = (total_score / max_possible) * 100

        return {
            "total_score": total_score,
            "max_possible": max_possible,
            "percentage": percentage,
            "scores": scores,
            "issues": issues,
            "passed": percentage >= 90,
        }

    def check_section_numbering(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check for proper section numbering (1., 2., 3., etc.)"""
        # Look for numbered sections (flexible - can be 1., 2. or 1., 2., 3.)
        has_section_1 = bool(re.search(r"^1\.\s+[A-Z]", text, re.MULTILINE))
        has_section_2 = bool(re.search(r"^2\.\s+[A-Z]", text, re.MULTILINE))

        # Also check for RECOMMENDED ACTION section (can be 2. or 3.)
        has_recommendations = bool(
            re.search(r"^\d+\.\s+RECOMMENDED\s+ACTION", text, re.MULTILINE | re.IGNORECASE)
        )

        if has_section_1 and has_section_2 and has_recommendations:
            return True, "Proper section numbering found"
        elif not has_section_1:
            return False, "Missing section 1"
        elif not has_section_2:
            return False, "Missing section 2"
        elif not has_recommendations:
            return False, "Missing RECOMMENDED ACTION section"
        else:
            return False, "Inconsistent section numbering"

    def check_bullet_intro(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check for correct intro line vs. 'Key Findings'."""
        has_correct_intro = "Here are the key points of our analysis:" in text
        has_wrong_intro = "Key Findings" in text and "Here are the key points" not in text

        if has_correct_intro:
            return True, "Correct intro line found"
        elif has_wrong_intro:
            return False, "Using 'Key Findings' instead of 'Here are the key points...'"
        else:
            return False, "Missing intro line entirely"

    def check_bullet_symbols(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check for bullet symbols (•) for legal issues."""
        # Count bullet symbols
        bullet_count = text.count("•")

        # Check for ALL CAPS headers (wrong format)
        caps_headers = len(re.findall(r"^[A-Z\s&]+\(Fla\.|^\d+\.\s+[A-Z\s&]+\(", text, re.MULTILINE))

        if bullet_count >= 3:  # Expect at least 3 legal issues as bullets
            return True, f"Found {bullet_count} bullet symbols"
        elif caps_headers > 0:
            return False, f"Found {caps_headers} ALL CAPS headers instead of bullets"
        else:
            return False, "No bullet symbols found for legal issues"

    def check_no_caps_headers(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check that there are no ALL CAPS section headers."""
        # Look for patterns like "IMPLIED WARRANTY & CONSTRUCTION DEFECTS"
        caps_legal_headers = re.findall(
            r"^([A-Z][A-Z\s&]+(?:DEFECTS|CONTRACT|LIENS|BANKRUPTCY|WARRANTY))", text, re.MULTILINE
        )

        # Filter out legitimate headers (FACTUAL SUMMARY, RECOMMENDED ACTION)
        invalid_caps = [
            h
            for h in caps_legal_headers
            if "FACTUAL" not in h and "RECOMMENDED" not in h and "ACTION" not in h
        ]

        if not invalid_caps:
            return True, "No inappropriate ALL CAPS headers"
        else:
            return False, f"Found ALL CAPS headers: {', '.join(invalid_caps[:2])}"

    def check_conversational_tone(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check for conversational-educational tone vs. stiff-formal."""
        # Indicators of stiff-formal tone
        formal_indicators = [
            r"Under Florida law, an implied warranty exists",
            r"A breach of contract occurs when",
            r"Pursuant to Florida Statute",
        ]

        # Indicators of conversational-educational tone
        conversational_indicators = [
            r"is a legal concept that",
            r"It is a warranty that",
            r"Essentially",
            r"This means that",
        ]

        formal_count = sum(1 for pattern in formal_indicators if re.search(pattern, text))
        conversational_count = sum(
            1 for pattern in conversational_indicators if re.search(pattern, text, re.IGNORECASE)
        )

        if conversational_count >= 2:
            return True, "Good conversational-educational tone"
        elif formal_count >= 2:
            return False, "Too formal/legalistic (cold starts)"
        else:
            return False, "Neutral tone, could be more educational"

    def check_specific_opening(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check if opening lists specific documents and property address."""
        # Extract first 400 characters (opening section)
        opening = text[:400]

        # Check for specific document mentions (multiple patterns)
        # Look for patterns like "reviewing the contract", "including payment records", etc.
        doc_patterns = [
            r"(?:contract|agreement).*(?:with|dated)",  # "contract with X" or "contract dated"
            r"payment\s+records",  # "payment records"
            r"photos?\s+of",  # "photos of" or "photo of"
            r"(?:reviewing|submitted|provided).*(?:contract|agreement|payment|photo)",  # after reviewing X
        ]

        has_specific_docs = any(re.search(pattern, opening, re.IGNORECASE) for pattern in doc_patterns)

        # Check for property address
        has_address = bool(
            re.search(r"\d+\s+[A-Za-z\s]+(?:Street|Drive|Road|Avenue|Lane|Court|Way)", opening)
        )

        # Count specific document types mentioned
        doc_types = ["contract", "agreement", "payment", "photo", "email", "correspondence", "records"]
        docs_mentioned = sum(1 for doc in doc_types if doc in opening.lower())

        if has_specific_docs and has_address and docs_mentioned >= 2:
            return True, f"Opening mentions {docs_mentioned} document types and property address"
        elif has_specific_docs and docs_mentioned >= 2:
            return False, "Has specific documents but missing property address"
        elif has_address:
            return False, f"Has address but not enough specific documents (found {docs_mentioned}, need 2+)"
        else:
            return False, "Generic opening (no specific docs or address)"

    def check_no_as_discussed(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check that letter avoids vague 'As discussed' transitions."""
        has_as_discussed = bool(re.search(r"^As discussed,", text, re.MULTILINE))

        if not has_as_discussed:
            return True, "Avoids vague 'As discussed' transition"
        else:
            return False, "Uses vague 'As discussed' (assumes prior conversation)"

    def check_timeline_durations(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check that dates include calculated durations."""
        # Look for date patterns
        dates = re.findall(
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
            text,
        )

        # Look for duration calculations
        duration_patterns = [
            r"—over \d+ months? ago",
            r"—\d+ months? later",
            r"a span of \d+ months?",
            r"—\d+ days? (?:later|beyond|after)",
            r"Between .+ and .+—a span of",
        ]

        duration_count = sum(1 for pattern in duration_patterns if re.search(pattern, text))

        if duration_count >= 1:
            return True, f"Found {duration_count} duration calculations"
        elif len(dates) > 0:
            return False, f"Found {len(dates)} dates but no duration calculations"
        else:
            return True, "No dates to calculate (may be acceptable)"

    def check_educational_explanations(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check that legal concepts are explained educationally."""
        # Look for educational patterns
        educational_patterns = [
            r"(?:is a|means a|refers to) (?:legal )?(?:concept|warranty|requirement|right)",
            r"Essentially.*means",
            r"In plain English",
            r"To put it simply",
        ]

        educational_count = sum(
            1 for pattern in educational_patterns if re.search(pattern, text, re.IGNORECASE)
        )

        if educational_count >= 1:
            return True, "Explains concepts educationally"
        else:
            return False, "Legal concepts stated without explanation"

    def check_integrated_procedures(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check that procedural requirements are integrated, not standalone sections."""
        # Look for standalone procedural section headers
        standalone_patterns = [
            r"^\d+\.\s+PRE-?LITIGATION REQUIREMENTS",
            r"^\d+\.\s+PROCEDURAL REQUIREMENTS",
            r"^PRE-?LITIGATION REQUIREMENTS:?\s*$",
        ]

        has_standalone = any(
            re.search(pattern, text, re.MULTILINE | re.IGNORECASE) for pattern in standalone_patterns
        )

        # Look for integrated format
        integrated_pattern = r"\*\*Pre-Litigation Requirements:\*\*"
        has_integrated = bool(re.search(integrated_pattern, text))

        if has_integrated and not has_standalone:
            return True, "Procedures integrated within legal analysis"
        elif has_standalone:
            return False, "Has standalone 'Procedural Requirements' section"
        else:
            return False, "Procedural requirements missing or unclear"

    def check_simple_closing(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check for simple, conversational closing."""
        # Extract last 200 characters before signature
        closing_section = text[-400:-100]

        # Check for complex closing
        complex_patterns = [
            r"proceed with (?:these actions|drafting)",
            r"or whether you would prefer that we",
        ]

        # Check for simple closing
        simple_patterns = [
            r"set a phone call to discuss",
            r"discuss our review and recommendations",
        ]

        has_complex = any(re.search(pattern, closing_section, re.IGNORECASE) for pattern in complex_patterns)
        has_simple = any(re.search(pattern, closing_section, re.IGNORECASE) for pattern in simple_patterns)

        if has_simple and not has_complex:
            return True, "Simple, conversational closing"
        elif has_complex:
            return False, "Closing is too formal/wordy"
        else:
            return False, "Closing pattern unclear"

    def check_length_appropriate(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check that letter length is appropriate (within ±20% of gold standard)."""
        word_count = len(text.split())

        # Target based on real attorney letters (400-550 words)
        target_min = 400
        target_max = 650

        if target_min <= word_count <= target_max:
            return True, f"Length appropriate ({word_count} words)"
        elif word_count > target_max:
            pct_over = ((word_count - target_max) / target_max) * 100
            return False, f"Too long ({word_count} words, {pct_over:.0f}% over target)"
        else:
            return False, f"Too short ({word_count} words)"

    def check_no_formal_checklists(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check that there are no formal 'Checklist:' headers."""
        has_checklist_header = bool(re.search(r"Protective Action Checklist:", text))

        if not has_checklist_header:
            return True, "No formal 'Checklist:' headers"
        else:
            return False, "Uses formal 'Protective Action Checklist:' header"

    def check_proper_issue_integration(self, text: str, gold: str = None) -> Tuple[bool, str]:
        """Check that minor issues (bankruptcy) are integrated, not separate bullets."""
        # Look for standalone bankruptcy sections
        bankruptcy_as_section = bool(
            re.search(r"(?:^•\s*\*\*Bankruptcy|^\d+\.\s+BANKRUPTCY)", text, re.MULTILINE | re.IGNORECASE)
        )

        # Look for integrated mention
        bankruptcy_integrated = bool(
            re.search(r"(?:Note that.*bankruptcy|contractor.*filed.*bankruptcy)", text, re.IGNORECASE)
        )

        if bankruptcy_integrated and not bankruptcy_as_section:
            return True, "Minor issues integrated properly"
        elif bankruptcy_as_section:
            return False, "Bankruptcy treated as separate major issue (should integrate)"
        else:
            return True, "No minor issues to integrate (acceptable)"


def load_gold_standard() -> str:
    """Load the real Erik Devlin attorney letter as gold standard."""
    gold_path = Path(__file__).parent.parent / "docs" / "real_findings_letters" / "erik-devlin"

    if not gold_path.exists():
        print(f"Warning: Gold standard not found at {gold_path}")
        return ""

    with open(gold_path, "r") as f:
        return f.read()


def print_comparison(generated_text: str, gold_text: str):
    """Print side-by-side comparison."""
    print("\n" + "=" * 70)
    print("LENGTH COMPARISON")
    print("=" * 70)

    gen_words = len(generated_text.split())
    gold_words = len(gold_text.split())
    pct_diff = ((gen_words - gold_words) / gold_words) * 100

    print(f"Generated:  {gen_words} words")
    print(f"Gold:       {gold_words} words")
    print(f"Difference: {pct_diff:+.1f}%")


def main():
    """Run letter quality test."""
    print("\n" + "=" * 70)
    print("LETTER QUALITY TEST SUITE")
    print("=" * 70)
    print()

    # For now, load from a test file if it exists
    test_letter_path = Path(__file__).parent.parent / "test_data" / "generated_letter.txt"

    if not test_letter_path.exists():
        print("❌ No generated letter found")
        print(f"   Expected at: {test_letter_path}")
        print()
        print("USAGE:")
        print("1. Generate a letter and save to test_data/generated_letter.txt")
        print("2. Run this script to score it")
        print()
        return 1

    with open(test_letter_path, "r") as f:
        generated_letter = f.read()

    # Load gold standard
    gold_standard = load_gold_standard()

    # Score the letter
    scorer = LetterQualityScorer()
    results = scorer.score_letter(generated_letter, gold_standard)

    # Print results
    print(f"OVERALL SCORE: {results['total_score']}/{results['max_possible']} ({results['percentage']:.1f}%)")
    print()

    if results["passed"]:
        print("✅ PASSED - Quality threshold met (≥90%)")
    else:
        print("❌ FAILED - Below quality threshold (<90%)")

    print()
    print("=" * 70)
    print("DETAILED RESULTS")
    print("=" * 70)
    print()

    # Group by passed/failed
    passed_criteria = []
    failed_criteria = []

    for criterion_id, result in results["scores"].items():
        if result["passed"]:
            passed_criteria.append(result)
        else:
            failed_criteria.append(result)

    # Show failed first
    if failed_criteria:
        print("ISSUES FOUND:")
        print("-" * 70)
        for result in failed_criteria:
            print(f"❌ {result['description']}")
            print(f"   {result['feedback']}")
            print(f"   Score: 0/{result['max']}")
            print()

    # Show passed
    if passed_criteria:
        print("PASSING CRITERIA:")
        print("-" * 70)
        for result in passed_criteria:
            print(f"✅ {result['description']} ({result['score']}/{result['max']})")

    print()

    # Comparison
    if gold_standard:
        print_comparison(generated_letter, gold_standard)

    print()
    print("=" * 70)

    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
