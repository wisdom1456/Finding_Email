#!/usr/bin/env python3
"""Quick test for current letter quality.
Paste the generated letter text when prompted.
"""

import sys
from pathlib import Path

# Add scripts to path to import test_letter_quality
sys.path.insert(0, str(Path(__file__).parent))

from test_letter_quality import LetterQualityScorer, load_gold_standard, print_comparison


def main():
    """Test letter quality with manual input."""
    print("\n" + "=" * 70)
    print("LETTER QUALITY QUICK TEST")
    print("=" * 70)
    print()
    print("Paste the generated letter text below, then press Enter twice:")
    print()

    # Read multi-line input
    lines = []
    empty_count = 0

    while empty_count < 2:
        try:
            line = input()
            if not line.strip():
                empty_count += 1
            else:
                empty_count = 0
            lines.append(line)
        except EOFError:
            break

    generated_letter = "\n".join(lines).strip()

    if not generated_letter:
        print("❌ No letter text provided")
        return 1

    print()
    print("Testing letter...")
    print()

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
    print("TOP ISSUES TO FIX")
    print("=" * 70)
    print()

    # Show top 5 failures
    failed_criteria = [
        (result["description"], result["feedback"], result["max"])
        for result in results["scores"].values()
        if not result["passed"]
    ]

    failed_criteria.sort(key=lambda x: x[2], reverse=True)  # Sort by weight

    for i, (desc, feedback, weight) in enumerate(failed_criteria[:5], 1):
        print(f"{i}. {desc} (worth {weight} points)")
        print(f"   → {feedback}")
        print()

    # Comparison
    if gold_standard:
        print_comparison(generated_letter, gold_standard)

    print()
    print("=" * 70)

    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
