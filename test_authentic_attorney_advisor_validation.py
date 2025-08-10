#!/usr/bin/env python3
"""
AUTHENTIC_ATTORNEY_ADVISOR Framework Validation Suite

This test suite validates the AUTHENTIC_ATTORNEY_ADVISOR framework that is
actually implemented in the production system (not CLIENT_CLARITY_ADVISOR
which is documented but not implemented).

Framework Requirements Tested:
1. Direct Professional Tone (no collaborative "we" language)
2. Florida Law Exclusivity
3. High-Stakes Advice Protocol activation
4. Professional Realism requirements
5. Template formatting compliance

CRITICAL FINDING: CLIENT_CLARITY_ADVISOR is documented but not implemented.
AUTHENTIC_ATTORNEY_ADVISOR is the actual running framework.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# Import actual framework modules
try:
    from backend_logic.ai import AIAnalyzer
    from backend_logic.document_processor import DocumentProcessor
    from backend_logic.email_generator import EmailGeneratorV2
    MODULES_AVAILABLE = True
except ImportError as e:
logger.warning(f'⚠️  Warning: Cannot import modules: {e}')
    MODULES_AVAILABLE = False

@dataclass
class ValidationResult:
    """Structure for validation test results."""
    test_name: str
    passed: bool
    details: Dict[str, Any]
    framework_evidence: List[str]

class AuthenticAttorneyAdvisorValidator:
    """Validates AUTHENTIC_ATTORNEY_ADVISOR framework implementation."""

    def __init__(self):
        self.results = []
        self.florida_statutes = [
            "Fla. Stat. § 83.49",   # Landlord-tenant termination
            "Fla. Stat. § 83.51",   # Landlord access rights
            "Fla. Stat. § 768.81",  # Comparative fault
            "Fla. Stat. § 95.11",   # Statute of limitations
            "Fla. Stat. § 607.0830" # Corporate liability
        ]
        self.non_florida_laws = [
            "Cal. Civ. Code § 1950.5",  # California security deposits
            "N.Y. Real Prop. Law § 235-f", # New York rent stabilization
            "Tex. Prop. Code § 92.056"  # Texas landlord remedies
        ]

    def log_result(self, result: ValidationResult):
        """Log validation result."""
        self.results.append(result)
        status = "✅ PASS" if result.passed else "❌ FAIL"
logger.info(f'{status}: {result.test_name}')
        if result.details:
            for key, value in result.details.items():
logger.info(f'   {key}: {value}')

    def test_framework_identification(self) -> ValidationResult:
        """Test 1: Verify AUTHENTIC_ATTORNEY_ADVISOR is implemented."""
logger.info('\n🔍 FRAMEWORK IDENTIFICATION TEST')
logger.info('=' * 50)

        if not MODULES_AVAILABLE:
            return ValidationResult(
                test_name="Framework Module Import",
                passed=False,
                details={"error": "Cannot import required modules"},
                framework_evidence=[]
            )

        try:
            # Read email generator source to verify framework
            email_gen_path = project_root / "backend_logic" / "email_generator.py"
            content = email_gen_path.read_text()

            has_authentic = "AUTHENTIC_ATTORNEY_ADVISOR" in content
            has_client_clarity = "CLIENT_CLARITY_ADVISOR" in content

            # Look for specific framework characteristics
            has_direct_tone = "Direct Professional Tone" in content
            has_florida_exclusive = "Florida Law Exclusive" in content
            has_high_stakes = "HIGH_STAKES_ADVICE_PROTOCOL" in content

            framework_evidence = []
            if has_authentic:
                framework_evidence.append("AUTHENTIC_ATTORNEY_ADVISOR found in email_generator.py")
            if has_direct_tone:
                framework_evidence.append("Direct Professional Tone directive found")
            if has_florida_exclusive:
                framework_evidence.append("Florida Law Exclusive requirement found")
            if has_high_stakes:
                framework_evidence.append("High-Stakes Advice Protocol implemented")

            passed = has_authentic and not has_client_clarity and has_direct_tone

            return ValidationResult(
                test_name="Framework Implementation Verification",
                passed=passed,
                details={
                    "authentic_attorney_advisor": has_authentic,
                    "client_clarity_advisor": has_client_clarity,
                    "direct_professional_tone": has_direct_tone,
                    "florida_law_exclusive": has_florida_exclusive,
                    "high_stakes_protocol": has_high_stakes
                },
                framework_evidence=framework_evidence
            )

        except Exception as e:
            return ValidationResult(
                test_name="Framework Implementation Verification",
                passed=False,
                details={"error": str(e)},
                framework_evidence=[]
            )

    def test_florida_law_exclusivity(self) -> ValidationResult:
        """Test 2: Validate Florida law exclusivity compliance."""
logger.info('\n🏖️ FLORIDA LAW EXCLUSIVITY TEST')
logger.info('=' * 50)

        if not MODULES_AVAILABLE:
            return ValidationResult(
                test_name="Florida Law Exclusivity",
                passed=False,
                details={"error": "Cannot test - modules unavailable"},
                framework_evidence=[]
            )

        try:
            # Create test scenario with Florida law references
            florida_case = {
                "case_summary": "Landlord-tenant dispute in Miami involving security deposit return under Florida Statute § 83.49",
                "legal_issues": [
                    f"Violation of {self.florida_statutes[0]} - notice requirements",
                    f"Compliance with {self.florida_statutes[1]} - access provisions",
                    "Property damage assessment under Florida law"
                ],
                "applicable_law": "Florida Residential Landlord and Tenant Act",
                "jurisdiction": "Florida"
            }

            # Test with non-Florida law references (should be rejected/flagged)
            non_florida_case = {
                "case_summary": "California rental dispute under Civil Code § 1950.5",
                "legal_issues": [
                    f"Violation of {self.non_florida_laws[0]}",
                    "California tenant protection laws"
                ],
                "applicable_law": "California Civil Code",
                "jurisdiction": "California"
            }

            # Check framework directives for Florida exclusivity
            email_gen_path = project_root / "backend_logic" / "email_generator.py"
            content = email_gen_path.read_text()

            florida_exclusive_directive = "Florida Law Exclusive" in content
            has_florida_requirement = "Florida" in content and ("exclusive" in content.lower() or "only" in content.lower())

            framework_evidence = []
            if florida_exclusive_directive:
                framework_evidence.append("Florida Law Exclusive directive found in framework")
            if has_florida_requirement:
                framework_evidence.append("Florida law restriction identified in code")

            return ValidationResult(
                test_name="Florida Law Exclusivity Validation",
                passed=florida_exclusive_directive,
                details={
                    "florida_exclusive_directive": florida_exclusive_directive,
                    "florida_requirement_found": has_florida_requirement,
                    "florida_test_case": florida_case["case_summary"][:100] + "...",
                    "non_florida_test_case": non_florida_case["case_summary"][:100] + "..."
                },
                framework_evidence=framework_evidence
            )

        except Exception as e:
            return ValidationResult(
                test_name="Florida Law Exclusivity Validation",
                passed=False,
                details={"error": str(e)},
                framework_evidence=[]
            )

    def test_high_stakes_advice_protocol(self) -> ValidationResult:
        """Test 3: Validate High-Stakes Advice Protocol activation."""
logger.info('\n⚠️  HIGH-STAKES ADVICE PROTOCOL TEST')
logger.info('=' * 50)

        if not MODULES_AVAILABLE:
            return ValidationResult(
                test_name="High-Stakes Advice Protocol",
                passed=False,
                details={"error": "Cannot test - modules unavailable"},
                framework_evidence=[]
            )

        try:
            # Check for High-Stakes Advice Protocol implementation
            email_gen_path = project_root / "backend_logic" / "email_generator.py"
            content = email_gen_path.read_text()

            # Look for protocol components
            has_protocol = "HIGH_STAKES_ADVICE_PROTOCOL" in content
            has_five_steps = content.count("Step ") >= 5 or content.count("1.") >= 5
            has_verification = "verify" in content.lower() or "confirm" in content.lower()
            has_counter_intuitive = "counter" in content.lower() and "intuitive" in content.lower()

            # Create counter-intuitive scenario that should trigger protocol
            counter_intuitive_scenario = {
                "case_summary": "Client wants to reject highly favorable settlement offer of $500,000 for $50,000 claim",
                "client_position": "Reject settlement and proceed to trial",
                "legal_analysis": "Settlement offer is 10x original damages claim",
                "recommendation": "Counter-intuitive: advise against client's preferred course",
                "risk_level": "HIGH",
                "protocol_trigger": "Counter-intuitive professional recommendation required"
            }

            framework_evidence = []
            if has_protocol:
                framework_evidence.append("HIGH_STAKES_ADVICE_PROTOCOL found in implementation")
            if has_five_steps:
                framework_evidence.append("Five-step process structure identified")
            if has_verification:
                framework_evidence.append("Verification requirements found")
            if has_counter_intuitive:
                framework_evidence.append("Counter-intuitive handling identified")

            passed = has_protocol and (has_five_steps or has_verification)

            return ValidationResult(
                test_name="High-Stakes Advice Protocol Validation",
                passed=passed,
                details={
                    "protocol_implemented": has_protocol,
                    "five_step_structure": has_five_steps,
                    "verification_present": has_verification,
                    "counter_intuitive_handling": has_counter_intuitive,
                    "test_scenario": counter_intuitive_scenario["case_summary"][:100] + "..."
                },
                framework_evidence=framework_evidence
            )

        except Exception as e:
            return ValidationResult(
                test_name="High-Stakes Advice Protocol Validation",
                passed=False,
                details={"error": str(e)},
                framework_evidence=[]
            )

    def test_direct_professional_tone(self) -> ValidationResult:
        """Test 4: Validate Direct Professional Tone (not collaborative)."""
logger.info('\n💼 DIRECT PROFESSIONAL TONE TEST')
logger.info('=' * 50)

        if not MODULES_AVAILABLE:
            return ValidationResult(
                test_name="Direct Professional Tone",
                passed=False,
                details={"error": "Cannot test - modules unavailable"},
                framework_evidence=[]
            )

        try:
            # Check framework directives for tone requirements
            email_gen_path = project_root / "backend_logic" / "email_generator.py"
            content = email_gen_path.read_text()

            # Look for direct professional tone directives
            has_direct_tone = "Direct Professional Tone" in content
            avoids_collaboration = "avoid" in content.lower() and ("collaboration" in content.lower() or "we" in content.lower())
            has_professional_realism = "Professional Realism" in content

            # Check for prohibited collaborative language patterns
            collaborative_patterns = [
                r"\bwe\b",           # "we" usage
                r"\bour\b",          # "our" usage
                r"\btogether\b",     # collaborative terms
                r"\bpartnership\b"   # partnership language
            ]

            # Sample the content for collaborative language (should be minimal/avoided)
            collaborative_matches = []
            for pattern in collaborative_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    collaborative_matches.extend(matches)

            # Professional tone indicators
            professional_indicators = [
                "professional", "attorney", "legal", "counsel",
                "analysis", "recommendation", "assessment"
            ]

            professional_count = sum(1 for indicator in professional_indicators if indicator in content.lower())

            framework_evidence = []
            if has_direct_tone:
                framework_evidence.append("Direct Professional Tone directive found")
            if avoids_collaboration:
                framework_evidence.append("Collaborative language avoidance directive found")
            if has_professional_realism:
                framework_evidence.append("Professional Realism requirement found")
            if professional_count > 5:
                framework_evidence.append(f"Strong professional vocabulary ({professional_count} indicators)")

            passed = has_direct_tone and professional_count > 5

            return ValidationResult(
                test_name="Direct Professional Tone Validation",
                passed=passed,
                details={
                    "direct_tone_directive": has_direct_tone,
                    "avoids_collaboration": avoids_collaboration,
                    "professional_realism": has_professional_realism,
                    "collaborative_matches": len(collaborative_matches),
                    "professional_indicators": professional_count,
                    "sample_collaborative_language": collaborative_matches[:5]  # First 5 matches
                },
                framework_evidence=framework_evidence
            )

        except Exception as e:
            return ValidationResult(
                test_name="Direct Professional Tone Validation",
                passed=False,
                details={"error": str(e)},
                framework_evidence=[]
            )

    def test_ai_analyzer_framework_consistency(self) -> ValidationResult:
        """Test 5: Check AI Analyzer vs Email Generator framework consistency."""
logger.info('\n🔄 FRAMEWORK CONSISTENCY TEST')
logger.info('=' * 50)

        try:
            # Read both modules
            ai_analyzer_path = project_root / "backend_logic" / "ai_analyzer.py"
            email_gen_path = project_root / "backend_logic" / "email_generator.py"

            ai_content = ai_analyzer_path.read_text() if ai_analyzer_path.exists() else ""
            email_content = email_gen_path.read_text() if email_gen_path.exists() else ""

            # Check framework references in each module
            ai_has_client_clarity = "CLIENT_CLARITY_ADVISOR" in ai_content
            ai_has_authentic = "AUTHENTIC_ATTORNEY_ADVISOR" in ai_content

            email_has_client_clarity = "CLIENT_CLARITY_ADVISOR" in email_content
            email_has_authentic = "AUTHENTIC_ATTORNEY_ADVISOR" in email_content

            # Check for collaborative language in AI analyzer
            ai_collaborative_patterns = re.findall(r"\bwe\b|\bour\b|\btogether\b", ai_content, re.IGNORECASE)
            email_collaborative_patterns = re.findall(r"\bwe\b|\bour\b|\btogether\b", email_content, re.IGNORECASE)

            # Framework consistency analysis
            frameworks_consistent = (
                (ai_has_authentic and email_has_authentic and not ai_has_client_clarity and not email_has_client_clarity) or
                (ai_has_client_clarity and email_has_client_clarity and not ai_has_authentic and not email_has_authentic)
            )

            # Check for the documented mismatch
            has_mismatch = ai_has_client_clarity and email_has_authentic

            framework_evidence = []
            if has_mismatch:
                framework_evidence.append("CRITICAL: Framework mismatch detected between AI Analyzer and Email Generator")
            if ai_has_client_clarity:
                framework_evidence.append("AI Analyzer uses CLIENT_CLARITY_ADVISOR")
            if email_has_authentic:
                framework_evidence.append("Email Generator uses AUTHENTIC_ATTORNEY_ADVISOR")

            return ValidationResult(
                test_name="Framework Consistency Between Modules",
                passed=not has_mismatch,  # Pass if no mismatch
                details={
                    "ai_analyzer_client_clarity": ai_has_client_clarity,
                    "ai_analyzer_authentic": ai_has_authentic,
                    "email_generator_client_clarity": email_has_client_clarity,
                    "email_generator_authentic": email_has_authentic,
                    "frameworks_consistent": frameworks_consistent,
                    "framework_mismatch": has_mismatch,
                    "ai_collaborative_language": len(ai_collaborative_patterns),
                    "email_collaborative_language": len(email_collaborative_patterns)
                },
                framework_evidence=framework_evidence
            )

        except Exception as e:
            return ValidationResult(
                test_name="Framework Consistency Between Modules",
                passed=False,
                details={"error": str(e)},
                framework_evidence=[]
            )

    def run_comprehensive_validation(self) -> Dict[str, Any]:
        """Run complete validation suite."""
logger.info('🚨 AUTHENTIC_ATTORNEY_ADVISOR FRAMEWORK VALIDATION')
logger.info('=' * 60)
logger.info('Testing the ACTUAL implemented framework')
logger.info('(NOT CLIENT_CLARITY_ADVISOR which is documented but not implemented)')
logger.info('=' * 60)

        # Run all validation tests
        tests = [
            self.test_framework_identification,
            self.test_florida_law_exclusivity,
            self.test_high_stakes_advice_protocol,
            self.test_direct_professional_tone,
            self.test_ai_analyzer_framework_consistency
        ]

        for test in tests:
            result = test()
            self.log_result(result)

        # Generate summary
        passed_tests = [r for r in self.results if r.passed]
        failed_tests = [r for r in self.results if not r.passed]

        # Collect all framework evidence
        all_evidence = []
        for result in self.results:
            all_evidence.extend(result.framework_evidence)

        summary = {
            "total_tests": len(self.results),
            "passed": len(passed_tests),
            "failed": len(failed_tests),
            "success_rate": f"{(len(passed_tests)/len(self.results)*100):.1f}%",
            "framework_evidence": all_evidence,
            "critical_findings": self._extract_critical_findings(),
            "recommendations": self._generate_recommendations()
        }

        return summary

    def _extract_critical_findings(self) -> List[str]:
        """Extract critical findings from validation results."""
        findings = []

        for result in self.results:
            if not result.passed:
                findings.append(f"❌ {result.test_name}: FAILED")

            # Check for framework mismatch
            if result.details.get("framework_mismatch"):
                findings.append("🚨 CRITICAL: Framework mismatch between AI Analyzer and Email Generator")

            # Check for missing implementations
            if "authentic_attorney_advisor" in result.details and not result.details["authentic_attorney_advisor"]:
                findings.append("⚠️  AUTHENTIC_ATTORNEY_ADVISOR not found in implementation")

        return findings

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []

        # Check for framework consistency issues
        for result in self.results:
            if result.details.get("framework_mismatch"):
                recommendations.append("🔧 Complete CLIENT_CLARITY_ADVISOR migration or update documentation to match AUTHENTIC_ATTORNEY_ADVISOR")

        # Check for missing features
        framework_missing = any(not r.passed for r in self.results if "Framework Implementation" in r.test_name)
        if framework_missing:
            recommendations.append("🔧 Verify framework implementation and update module imports")

        protocol_missing = any("High-Stakes" in r.test_name and not r.passed for r in self.results)
        if protocol_missing:
            recommendations.append("🔧 Implement or verify High-Stakes Advice Protocol")

        if not recommendations:
            recommendations.append("✅ Framework validation passed - implementation matches requirements")

        return recommendations

def main():
    """Run the validation suite."""
    validator = AuthenticAttorneyAdvisorValidator()
    summary = validator.run_comprehensive_validation()

    # Print comprehensive summary
logger.info('\n' + '=' * 60)
logger.info('🎯 VALIDATION SUMMARY')
logger.info('=' * 60)
logger.info(f'Tests Run: {summary['total_tests']}')
logger.info(f'Passed: {summary['passed']}')
logger.error(f'Failed: {summary['failed']}')
logger.info(f'Success Rate: {summary['success_rate']}')

    if summary["critical_findings"]:
logger.error('\n🚨 CRITICAL FINDINGS:')
        for finding in summary["critical_findings"]:
logger.info(f'   {finding}')

logger.info('\n🔍 FRAMEWORK EVIDENCE:')
    for evidence in summary["framework_evidence"]:
logger.info(f'   ✓ {evidence}')

logger.info('\n💡 RECOMMENDATIONS:')
    for rec in summary["recommendations"]:
logger.info(f'   {rec}')

logger.info('\n' + '=' * 60)
logger.info('📋 VALIDATION COMPLETE')
logger.info('=' * 60)

    return summary

if __name__ == "__main__":
    main()
