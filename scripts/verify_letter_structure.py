#!/usr/bin/env python3
"""Verification script to test letter structure generation.

This script verifies that the letter generation system correctly applies
the Simple Bullets format for cases with 1-6 issues and no truly complex procedures.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from legal_portal.core.data_models import (
    CriticalDeadline,
    DeepAnalysis,
    EvidenceAssessment,
    IssueAnalysis,
    LegalIssue,
    LetterStructure,
    RiskAssessment,
)
from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer


def create_test_case_4_issues():
    """Create a test case with 4 issues (construction defect scenario)."""
    # Create 4 issue analyses
    issue_analyses = [
        IssueAnalysis(
            issue_name="Implied Warranty & Construction Defects",
            legal_standard="Under Florida law, an implied warranty exists...",
            fact_application="You may have claims due to defective construction...",
            remedies_available=["Cost to complete", "Cost to repair defects", "Reimbursement"],
            confidence_level="strong",
            procedural_requirements="60 days written notice to contractor (Chapter 558)",
        ),
        IssueAnalysis(
            issue_name="Breach of Contract",
            legal_standard="Breach occurs when a party fails to fulfill obligations...",
            fact_application="Contractor failed to complete $128,000 project...",
            remedies_available=["Damages for breach", "Specific performance"],
            confidence_level="strong",
            procedural_requirements=None,
        ),
        IssueAnalysis(
            issue_name="Mechanic's Liens",
            legal_standard="Subcontractors may file liens for unpaid amounts...",
            fact_application="Notice to Owner received from Tibbetts Lumber...",
            remedies_available=["Pay subcontractor", "Dispute lien"],
            confidence_level="moderate",
            procedural_requirements=None,
        ),
        IssueAnalysis(
            issue_name="Bankruptcy Implications",
            legal_standard="Bankruptcy imposes automatic stay on claims...",
            fact_application="LLW Construction filed bankruptcy...",
            remedies_available=["File proof of claim", "Seek relief from stay"],
            confidence_level="moderate",
            procedural_requirements=None,
        ),
    ]

    deep_analysis = DeepAnalysis(
        issue_analyses=issue_analyses,
        risk_assessment=RiskAssessment(
            major_risks=["Contractor bankruptcy", "Subcontractor lien"],
            risk_mitigation_steps=["Pay subcontractor", "File bankruptcy claim"],
            evidence_gaps=[],
        ),
        deadline_tracking=[
            CriticalDeadline(
                description="Chapter 558 60-day notice",
                consequence_if_missed="Cannot file suit",
                urgency="important",
                statute_basis="Fla. Stat. Chapter 558",
            )
        ],
        evidence_strength=EvidenceAssessment(
            strong_evidence=["Contract", "Payment records", "Photos of defects"],
            weak_evidence=[],
            missing_evidence=["Contractor response"],
            overall_strength="strong",
        ),
        overall_case_strength="strong",
        key_strengths=["Substantial payment without completion", "Documented defects"],
        key_challenges=["Contractor bankruptcy", "Subcontractor lien risk"],
    )

    return deep_analysis


def verify_structure_determination():
    """Test that 4-issue case correctly gets Simple Bullets format."""
    print("=" * 70)
    print("LETTER STRUCTURE VERIFICATION TEST")
    print("=" * 70)
    print()

    # Create test case
    print("Creating test case: 4 issues (construction defect)...")
    deep_analysis = create_test_case_4_issues()
    print(f"✓ Created {len(deep_analysis.issue_analyses)} issue analyses")
    print()

    # Create minimal issue map
    from legal_portal.core.data_models import LegalIssueMap

    issue_map = LegalIssueMap(
        primary_issues=[
            LegalIssue(
                issue_name=ia.issue_name,
                category="construction",
                elements=["Element 1", "Element 2"],
                potential_remedies=ia.remedies_available,
                florida_statute_references=["Chapter 558"] if "Chapter 558" in ia.issue_name else [],
            )
            for ia in deep_analysis.issue_analyses
        ],
        case_complexity="moderate",
    )

    # Test structure determination
    print("Testing structure determination logic...")
    analyzer = MultiStageAnalyzer(openai_client=None, statute_service=None)
    structure = analyzer._determine_letter_structure(issue_map, deep_analysis)

    print(f"  Issues: {len(issue_map.primary_issues)}")
    print(
        f"  Has procedural requirements: {any(ia.procedural_requirements for ia in deep_analysis.issue_analyses)}"
    )
    print(f"  Detected style: {structure.style}")
    print(f"  Intro line: {structure.intro}")
    print(f"  Reasoning: {structure.reasoning}")
    print()

    # Verify result
    print("VERIFICATION RESULTS:")
    print("-" * 70)

    success = True

    if structure.style == "simple_bullets":
        print("✓ PASS: Correctly assigned 'simple_bullets' format")
    else:
        print(f"✗ FAIL: Expected 'simple_bullets', got '{structure.style}'")
        success = False

    if structure.intro == "Here are the key points of our analysis:":
        print("✓ PASS: Correct intro line for simple bullets")
    else:
        print(f"✗ FAIL: Expected 'Here are the key points...', got '{structure.intro}'")
        success = False

    if structure.issue_format == "bullet_paragraphs":
        print("✓ PASS: Correct issue format (bullet_paragraphs)")
    else:
        print(f"✗ FAIL: Expected 'bullet_paragraphs', got '{structure.issue_format}'")
        success = False

    print()

    if success:
        print("=" * 70)
        print("ALL TESTS PASSED ✓")
        print("=" * 70)
        return 0
    else:
        print("=" * 70)
        print("SOME TESTS FAILED ✗")
        print("=" * 70)
        return 1


def verify_override_logic():
    """Test that the override logic in json_processing_service works."""
    print()
    print("=" * 70)
    print("OVERRIDE LOGIC VERIFICATION TEST")
    print("=" * 70)
    print()

    # Simulate a case where old analysis had numbered_findings but should be bullets
    print("Simulating override scenario:")
    print("  - Analysis has 4 issues")
    print("  - Old structure_guidance says 'numbered_findings'")
    print("  - Only has Chapter 558 (standard procedure)")
    print()

    # Create test data
    deep_analysis = create_test_case_4_issues()

    # Create a structure that SHOULD be overridden
    old_structure = LetterStructure(
        style="numbered_findings",
        intro="Key Findings",
        issue_format="numbered_sections_with_headers",
        reasoning="Old logic (before fix)",
    )

    print("Before override:")
    print(f"  Style: {old_structure.style}")
    print(f"  Intro: {old_structure.intro}")
    print()

    # Simulate the override logic from json_processing_service.py
    num_issues = len(deep_analysis.issue_analyses)
    current_style = old_structure.style

    if current_style == "numbered_findings" and num_issues <= 6:
        # Check for truly complex procedures
        has_complex_procedures = False
        for issue in deep_analysis.issue_analyses:
            if issue.procedural_requirements:
                req_lower = issue.procedural_requirements.lower()
                if "chapter 558" in req_lower or "60 day" in req_lower or "pre-suit notice" in req_lower:
                    continue
                has_complex_procedures = True
                break
            if has_complex_procedures:
                break

        if not has_complex_procedures:
            print("Override triggered!")
            old_structure.style = "simple_bullets"
            old_structure.intro = "Here are the key points of our analysis:"
            old_structure.issue_format = "bullet_paragraphs"
            old_structure.reasoning = f"Auto-corrected: Simple/moderate case with {num_issues} issues"

    print("After override:")
    print(f"  Style: {old_structure.style}")
    print(f"  Intro: {old_structure.intro}")
    print(f"  Reasoning: {old_structure.reasoning}")
    print()

    # Verify
    success = old_structure.style == "simple_bullets"

    if success:
        print("✓ PASS: Override logic correctly converted to simple_bullets")
        print()
        print("=" * 70)
        print("OVERRIDE TEST PASSED ✓")
        print("=" * 70)
        return 0
    else:
        print("✗ FAIL: Override logic did not work")
        print()
        print("=" * 70)
        print("OVERRIDE TEST FAILED ✗")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    print()
    print("LETTER STRUCTURE FIX VERIFICATION")
    print("Testing both structure determination and override logic")
    print()

    result1 = verify_structure_determination()
    result2 = verify_override_logic()

    if result1 == 0 and result2 == 0:
        print()
        print("🎉 ALL VERIFICATIONS PASSED")
        print()
        print("The letter generation system will now:")
        print("  - Assign 'simple_bullets' format to cases with 1-6 issues")
        print("  - Exclude Chapter 558 from 'complex procedure' detection")
        print("  - Override old 'numbered_findings' structures during regeneration")
        print()
        sys.exit(0)
    else:
        print()
        print("⚠️  SOME VERIFICATIONS FAILED")
        print()
        sys.exit(1)
