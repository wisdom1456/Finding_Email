#!/usr/bin/env python3
"""
Debug script to examine the actual JSON structure being generated
"""
from __future__ import annotations

import json
import os
import sys

from openai import OpenAI


# Add project root to path for imports
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from backend.utils.data_models import (
    AnalyzedDocument,
    CaseAnalysisResult,
    DemandLetterEvaluation,
    EnhancedIntakeAnalysis,
    FinalAnalysis,
    FindingsLetterContent,
    LegalAssessment,
)
from backend_logic.config import get_openai_api_key
from backend_logic.email_generator import EmailGeneratorV2


def create_sample_case_analysis():
    """Create a sample case analysis for testing."""
    
    # Enhanced intake analysis
    intake = EnhancedIntakeAnalysis(
        client_name="Jane Smith",
        attorney_name="John Attorney",
        case_summary="Civil rights violation case with strong evidence",
        case_type="Civil Rights Violation",
        urgency_level="High",
        client_priorities=["Seek monetary compensation", "Ensure accountability"],
        desired_outcomes=["Settlement of $150,000 or more", "Policy changes"],
        key_facts=[
            "Incident occurred on March 15, 2024",
            "Multiple witnesses observed the violation",
            "Security footage captured the incident"
        ],
        parties_involved=[],
        financial_impact="Medical expenses and lost wages totaling $75,000",
        legal_claims=[
            "42 U.S.C. § 1983 Civil Rights Violation",
            "Florida Civil Rights Act Violation"
        ]
    )
    
    # Create findings letter content
    findings_content = FindingsLetterContent(
        factual_summary="This civil rights case presents compelling evidence of violations occurring on March 15, 2024. Our comprehensive review reveals a clear pattern of misconduct resulting in significant damages.",
        legal_analysis="Under 42 U.S.C. § 1983 and the Florida Civil Rights Act, defendant's actions constitute clear violations of established constitutional protections. The evidence meets all elements for civil rights claims.",
        strengths_of_case="Exceptional case strength derives from multiple independent witnesses, comprehensive documentation, and clear liability chain with substantial documented damages.",
        challenges_and_risks="Primary challenges include potential statute of limitations defenses and possible sovereign immunity claims. However, continuing violation doctrine mitigates these concerns.",
        recommended_next_steps="Immediate action required including demand letter filing within 14 days, witness statement collection by August 30, 2024, and federal court preparation by September 15, 2024.",
        demand_letter_analysis="Demand letter strategy is highly appropriate given case strength. Conservative settlement range of $125,000-$200,000 reflects documented damages."
    )
    
    return CaseAnalysisResult(
        intake_analysis=intake,
        analyzed_documents=[],
        legal_assessment=LegalAssessment(
            case_type="Federal Civil Rights",
            claim_viability="Strong viability",
            overall_evidence_strength="Excellent",
            potential_challenges="Statute of limitations",
            recommended_actions="File demand letter immediately",
            demand_letter_appropriate="Yes",
            urgency_assessment="High priority"
        ),
        demand_letter_evaluation=DemandLetterEvaluation(
            is_appropriate="Yes",
            reasoning="Strong evidence supports demand",
            potential_outcomes=["Settlement $125k-$200k"],
            relevant_statutes=["42 U.S.C. § 1983"]
        ),
        final_analysis=FinalAnalysis(
            case_summary="Strong civil rights case with comprehensive evidence",
            recommendations="Proceed with demand letter immediately",
            next_steps=[
                "File demand letter within 14 days",
                "Gather witness statements by August 30, 2024",
                "Prepare federal court by September 15, 2024"
            ]
        ),
        findings_letter_content=findings_content
    )

def main():
    """Debug the actual JSON structure being generated."""
    print("🔍 Debugging Actual JSON Structure Generation")
    print("=" * 50)
    
    try:
        # Initialize generator
        api_key = get_openai_api_key()
        client = OpenAI(api_key=api_key)
        generator = EmailGeneratorV2(client=client)
        
        # Create test case
        case_analysis = create_sample_case_analysis()
        
        # Generate just the JSON without template rendering
        print("📊 Generating JSON data...")
        json_data = generator._generate_structured_json(case_analysis)
        
        if json_data:
            print("✅ JSON generation successful!")
            print(f"📄 JSON Keys: {list(json_data.keys())}")
            
            # Save raw JSON for inspection
            with open("debug_raw_json_structure.json", "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            print("📁 Raw JSON saved to: debug_raw_json_structure.json")
            
            # Check for specific fields the template expects
            print("\n🔍 Checking Template-Expected Fields:")
            
            # Check generated_letter fields
            if "generated_letter" in json_data:
                gl = json_data["generated_letter"]
                print(f"  ✅ generated_letter present with keys: {list(gl.keys())}")
                print(f"  📝 background_summary present: {'background_summary' in gl}")
                print(f"  📝 analysis_and_position present: {'analysis_and_position' in gl}")
                if "background_summary" in gl:
                    print(f"  📏 background_summary length: {len(str(gl['background_summary']))}")
                if "analysis_and_position" in gl:
                    print(f"  📏 analysis_and_position length: {len(str(gl['analysis_and_position']))}")
            else:
                print("  ❌ generated_letter missing!")
            
            # Check bridges
            if "bridges" in json_data:
                bridges = json_data["bridges"]
                print(f"  ✅ bridges present with keys: {list(bridges.keys())}")
            else:
                print("  ❌ bridges missing!")
            
            # Check claims
            if "claims" in json_data:
                claims = json_data["claims"]
                print(f"  ✅ claims present, count: {len(claims) if isinstance(claims, list) else 'not a list'}")
            else:
                print("  ❌ claims missing!")
            
            # Check next_steps
            if "next_steps" in json_data:
                ns = json_data["next_steps"]
                print(f"  ✅ next_steps present with keys: {list(ns.keys()) if isinstance(ns, dict) else 'not a dict'}")
            else:
                print("  ❌ next_steps missing!")
            
        else:
            print("❌ JSON generation failed!")
            
    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
