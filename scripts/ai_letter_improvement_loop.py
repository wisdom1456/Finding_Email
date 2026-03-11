#!/usr/bin/env python3
"""AI-Driven Letter Improvement Loop

Fully autonomous system that:
1. Generates letters using current prompt
2. Scores them against quality criteria
3. Uses AI to analyze failures and propose prompt fixes
4. Applies fixes iteratively until quality threshold met
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict

# Load .env file
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not required if env vars already set

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from test_letter_quality import LetterQualityScorer, load_gold_standard

# Import OpenAI
try:
    from openai import OpenAI
except ImportError:
    print("Error: openai library not found. Install with: pip install openai")
    sys.exit(1)


class AILetterImprover:
    """Uses AI to iteratively improve letter generation prompts."""

    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.scorer = LetterQualityScorer()
        self.gold_standard = load_gold_standard()
        self.iteration_count = 0
        self.max_iterations = 10

        # Load current prompt
        self.prompt_path = (
            Path(__file__).parent.parent / "src" / "legal_portal" / "prompts" / "findings_letter_prompt.txt"
        )
        with open(self.prompt_path, "r") as f:
            self.current_prompt = f.read()

    def generate_test_letter(self) -> str:
        """Generate a letter for Erik Devlin case using current prompt."""
        # Test case data (Erik Devlin construction defect)
        test_context = """
CLIENT: Erik Devlin and Ms. Bell
PROPERTY: 3414 South Belcher Drive, Tampa, Florida 33629
CONTRACT: LLW Construction, Inc. - $128,355.77 total, $100,000 paid
ISSUE: Incomplete construction, substandard work, contractor ceased work March 2025

SPECIFIC DOCUMENTS REVIEWED (LIST THESE IN OPENING):
1. Construction contract with LLW Construction, Inc. dated November 2024
2. Payment records showing $100,000 paid
3. Photos of defective bathroom framing
4. Notice to Owner from Tibbetts Lumber for $2,150.66

TIMELINE: Contract signed November 2024, work ceased March 2025 (8 months ago), only $70,000 worth of work completed
DEFECTS: Defective bathroom framing requiring complete reconstruction
LEGAL ISSUES: Implied warranty, Chapter 558 pre-suit requirements, breach of contract, mechanic's lien risk

REQUIRED: In opening paragraph, list the specific documents: "the construction contract with LLW Construction, Inc., payment records, and photos of defective work"
FORBIDDEN: Do NOT say "the documents you submitted" or "the documents" generically
"""

        generation_prompt = f"""Using the FINDINGS EMAIL PROMPT below, generate a client-ready findings email for this case.

CASE CONTEXT:
{test_context}

FINDINGS LETTER PROMPT:
{self.current_prompt}

CRITICAL FORMATTING REQUIREMENTS:
- Use PLAIN TEXT format, NOT markdown
- Section headers: "1. FACTUAL SUMMARY" (NO ## symbols)
- Use bullet symbols (•) for legal issues
- NO markdown headers (##), NO markdown bold (**text**) in section headers
- Plain text throughout

CRITICAL CONTENT REQUIREMENTS:
- ❌ FORBIDDEN: "As discussed, the primary concern..." (too vague)
- ✅ REQUIRED: Jump directly to "The primary concern is..." or give specific context
- ❌ FORBIDDEN: "the documents you submitted" (too generic)
- ✅ REQUIRED: List specific document names (see CASE CONTEXT above)
- ❌ FORBIDDEN: "Protective Action Checklist:" as a header
- ✅ REQUIRED: Integrate protective actions as regular bullets without special header

CRITICAL TONE REQUIREMENTS (Educational, NOT Formal/Legalistic):

❌ WRONG (Too formal/cold):
"Under Florida law, an implied warranty exists that all construction work will be performed in a competent and workmanlike manner."

✅ CORRECT (Educational/conversational):
"An 'implied warranty' is a legal concept. It is a warranty that is not explicitly stated in your contract but is implied by the law. Essentially, this means that the contractor guaranteed to do the work in a proper and workmanlike way, even if the contract doesn't say so directly."

PATTERN TO FOLLOW:
1. Define the legal term: "X is a legal concept..."
2. Explain what it means: "Essentially, this means..."
3. Apply to their case: "In your situation..."

CLOSING REQUIREMENTS (Keep it Simple & Direct):

❌ WRONG (Too formal/wordy):
"Based on the above, a negotiated resolution would likely be your most efficient and cost-effective path forward. One option would be to issue a demand letter to the contractor demanding completion of the project in accordance with the contract terms or reimbursement for amounts you may need to pay to hire another contractor. We recommend sending this demand promptly to preserve your legal position. Furthermore, you should reach out to Tibbetts Lumber and pay..."

✅ CORRECT (Simple & conversational):
"I recommend two immediate actions: (1) Send a Chapter 558 notice to the contractor, and (2) Pay Tibbetts Lumber directly and get a lien waiver. Let me know if you'd like to schedule a call to discuss these next steps."

CLOSING RULES:
- Maximum 3-4 sentences before the call-to-action
- Use numbered actions (1), (2) for clarity
- End with simple "Let me know if..." or "Please call to discuss..."
- NO "Based on the above" or similar formal transitions

LENGTH REQUIREMENTS (CRITICAL):
- TARGET: 400-650 words total
- Factual Summary: 200-250 words
- Key Legal Points: 200-300 words
- Recommended Actions: 100-150 words
- TOTAL SHOULD NOT EXCEED 650 WORDS

Generate ONLY the letter content (no meta-commentary).
"""

        print("🤖 Generating letter with current prompt...")

        response = self.openai_client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior legal writing assistant generating attorney-quality findings emails.",
                },
                {"role": "user", "content": generation_prompt},
            ],
            temperature=0.3,
            max_tokens=2500,
        )

        return response.choices[0].message.content.strip()

    def analyze_failures_with_ai(self, letter: str, results: Dict) -> Dict:
        """Use AI to analyze why letter failed and propose prompt fixes."""
        failed_criteria = [
            {
                "criterion": desc,
                "feedback": results["scores"][criterion_id]["feedback"],
                "weight": results["scores"][criterion_id]["max"],
            }
            for criterion_id, (desc, _, _) in zip(results["scores"].keys(), self.scorer.criteria)
            if not results["scores"][criterion_id]["passed"]
        ]

        # Sort by weight (fix high-value issues first)
        failed_criteria.sort(key=lambda x: x["weight"], reverse=True)
        top_failures = failed_criteria[:5]  # Focus on top 5

        analysis_prompt = f"""You are an expert at analyzing legal letter generation prompts.

CURRENT LETTER QUALITY SCORE: {results['percentage']:.1f}% (need 90%+)

TOP FAILURES:
{json.dumps(top_failures, indent=2)}

SAMPLE FROM GENERATED LETTER:
```
{letter[:1000]}...
```

GOLD STANDARD (Real Attorney Letter):
```
{self.gold_standard[:800]}...
```

Analyze what's wrong with the prompt that's causing these failures. For each failure:
1. Identify the ROOT CAUSE in the prompt (what instruction is missing, wrong, or conflicting?)
2. Propose a SPECIFIC FIX (exact text to add/remove/change)
3. Explain WHY this will fix the issue

Respond in JSON format:
{{
  "analysis": "Overall assessment of what's wrong",
  "prompt_fixes": [
    {{
      "failure": "criterion name",
      "root_cause": "what in the prompt is causing this",
      "fix_location": "where in the prompt to make changes",
      "fix_action": "add | remove | replace",
      "fix_content": "exact text/instruction to add or change",
      "expected_impact": "how this will improve the letter"
    }}
  ],
  "priority_order": ["fix 1", "fix 2", "fix 3"]
}}
"""

        print("🔍 Analyzing failures with AI...")

        response = self.openai_client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at prompt engineering for legal document generation.",
                },
                {"role": "user", "content": analysis_prompt},
            ],
            temperature=0.2,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    def apply_prompt_fixes_with_ai(self, analysis: Dict) -> str:
        """Use AI to apply the proposed fixes to the prompt."""
        improvement_prompt = f"""You are refactoring a legal letter generation prompt to fix quality issues.

CURRENT PROMPT:
```
{self.current_prompt}
```

ANALYSIS OF ISSUES:
{json.dumps(analysis, indent=2)}

Apply ALL the proposed fixes to the prompt. Make the changes precisely as specified in the analysis.

CRITICAL RULES:
1. Keep all existing good sections
2. Apply each fix exactly as described
3. Maintain the overall structure
4. Don't add unnecessary changes
5. Output the COMPLETE updated prompt (not just the changes)

Output the full updated prompt.
"""

        print("🔧 Applying fixes with AI...")

        response = self.openai_client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert prompt engineer applying precise improvements to legal document generation prompts.",
                },
                {"role": "user", "content": improvement_prompt},
            ],
            temperature=0.1,
            max_tokens=15000,
        )

        return response.choices[0].message.content.strip()

    def save_prompt_version(self, prompt: str, iteration: int, score: float):
        """Save a versioned copy of the prompt."""
        versions_dir = Path(__file__).parent.parent / "prompt_versions"
        versions_dir.mkdir(exist_ok=True)

        version_file = versions_dir / f"findings_letter_prompt_v{iteration}_{score:.0f}pct.txt"
        with open(version_file, "w") as f:
            f.write(prompt)

        print(f"💾 Saved prompt version: {version_file.name}")

    def run_improvement_loop(self, target_score: float = 90.0) -> bool:
        """Run the autonomous improvement loop."""
        print("\n" + "=" * 70)
        print("AI-DRIVEN LETTER IMPROVEMENT LOOP")
        print("=" * 70)
        print(f"Target Score: {target_score}%")
        print(f"Max Iterations: {self.max_iterations}")
        print()

        best_score = 0
        best_prompt = self.current_prompt

        for iteration in range(1, self.max_iterations + 1):
            self.iteration_count = iteration

            print(f"\n{'='*70}")
            print(f"ITERATION {iteration}/{self.max_iterations}")
            print(f"{'='*70}\n")

            # Step 1: Generate letter
            try:
                generated_letter = self.generate_test_letter()

                # Save generated letter for review
                letter_file = (
                    Path(__file__).parent.parent / "test_data" / f"generated_letter_iter{iteration}.txt"
                )
                letter_file.parent.mkdir(exist_ok=True)
                with open(letter_file, "w") as f:
                    f.write(generated_letter)
                print(f"✅ Letter generated and saved to: {letter_file.name}")

            except Exception as e:
                print(f"❌ Letter generation failed: {e}")
                import traceback

                traceback.print_exc()
                continue

            # Step 2: Score the letter
            results = self.scorer.score_letter(generated_letter, self.gold_standard)
            score = results["percentage"]

            print(f"\n📊 SCORE: {results['total_score']}/{results['max_possible']} ({score:.1f}%)")

            # Step 2b: Show letter preview
            print("\n📄 GENERATED LETTER PREVIEW (first 500 chars):")
            print("-" * 70)
            print(generated_letter[:500])
            print("...")
            print("-" * 70)

            if score > best_score:
                best_score = score
                best_prompt = self.current_prompt
                self.save_prompt_version(self.current_prompt, iteration, score)

            # Step 3: Check if target met
            if score >= target_score:
                print(f"\n🎉 TARGET ACHIEVED! Score: {score:.1f}% (target: {target_score}%)")
                print()
                print("FINAL RESULTS:")
                print("-" * 70)
                for criterion_id, result in results["scores"].items():
                    status = "✅" if result["passed"] else "❌"
                    print(f"{status} {result['description']} ({result['score']}/{result['max']})")

                # Save final prompt
                with open(self.prompt_path, "w") as f:
                    f.write(self.current_prompt)
                print(f"\n✅ Final prompt saved to: {self.prompt_path}")

                return True

            # Step 4: Show all results (pass and fail)
            print("\n" + "=" * 70)
            print("DETAILED TEST RESULTS")
            print("=" * 70)

            passed_tests = []
            failed_tests = []

            for criterion_id, result in results["scores"].items():
                if result["passed"]:
                    passed_tests.append(result)
                else:
                    failed_tests.append(result)

            # Show failures first (most important)
            if failed_tests:
                print(f"\n❌ FAILED ({len(failed_tests)} tests):")
                print("-" * 70)
                for i, result in enumerate(failed_tests, 1):
                    print(f"{i}. {result['description']} (worth {result['max']} points)")
                    print(f"   Feedback: {result['feedback']}")
                    print()

            # Show passes
            if passed_tests:
                print(f"✅ PASSED ({len(passed_tests)} tests):")
                print("-" * 70)
                for result in passed_tests:
                    print(f"   ✓ {result['description']} ({result['score']}/{result['max']})")

            print("=" * 70)

            # Step 5: AI analysis
            try:
                analysis = self.analyze_failures_with_ai(generated_letter, results)
                print(f"\n💡 AI ANALYSIS: {analysis.get('analysis', 'No analysis provided')}")

                if "prompt_fixes" in analysis:
                    print(f"\n🔧 PROPOSED FIXES ({len(analysis['prompt_fixes'])}):")
                    for i, fix in enumerate(analysis["prompt_fixes"][:3], 1):
                        print(f"   {i}. {fix['failure']}")
                        print(f"      → {fix['root_cause']}")
                        print(f"      → Fix: {fix['fix_action']} at '{fix['fix_location']}'")
            except Exception as e:
                print(f"❌ AI analysis failed: {e}")
                continue

            # Step 6: Apply fixes
            print("\n" + "=" * 70)
            print("APPLYING FIXES TO PROMPT")
            print("=" * 70)

            try:
                improved_prompt = self.apply_prompt_fixes_with_ai(analysis)

                # Show what changed
                old_size = len(self.current_prompt)
                new_size = len(improved_prompt)
                size_diff = new_size - old_size

                print(f"   Original prompt: {old_size} chars")
                print(f"   Updated prompt:  {new_size} chars")
                print(f"   Difference:      {size_diff:+d} chars")

                # Update current prompt
                self.current_prompt = improved_prompt
                print("\n✅ Fixes applied - ready for next iteration")
                print("=" * 70)

                # Pause to let user review
                import time

                print("\nWaiting 3 seconds before next iteration...")
                time.sleep(3)

            except Exception as e:
                print(f"❌ Fix application failed: {e}")
                import traceback

                traceback.print_exc()
                continue

        # Max iterations reached
        print(f"\n⚠️  MAX ITERATIONS REACHED ({self.max_iterations})")
        print(f"Best Score Achieved: {best_score:.1f}%")

        if best_score >= target_score * 0.85:  # Within 85% of target
            print("\nClose to target! Saving best prompt...")
            with open(self.prompt_path, "w") as f:
                f.write(best_prompt)
            print(f"✅ Best prompt saved to: {self.prompt_path}")

        return False


def main():
    """Run the AI improvement loop."""
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("   Set it with: export OPENAI_API_KEY='your-key'")
        return 1

    improver = AILetterImprover()

    target = 90.0
    if len(sys.argv) > 1:
        target = float(sys.argv[1])

    success = improver.run_improvement_loop(target_score=target)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
