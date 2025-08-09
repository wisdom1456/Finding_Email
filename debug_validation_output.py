#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


sys.path.append(os.path.join(os.path.dirname(__file__), "backend_logic"))

from bs4 import BeautifulSoup
from config import get_openai_api_key
from email_generator import EmailGeneratorV2
from openai import OpenAI

# Add the validation harness imports to create a proper test case
from backend.utils.data_models import (
    AnalyzedDocument,
    CaseAnalysisResult,
    DemandLetterEvaluation,
    EnhancedIntakeAnalysis,
    FinalAnalysis,
    FindingsLetterContent,
    LegalAssessment,
)


def create_sample_case_analysis() -> CaseAnalysisResult:
    """Create a comprehensive sample case analysis for testing."""
    
    # Enhanced intake analysis
    intake = EnhancedIntakeAnalysis(
        client_name="Jane Smith",
        attorney_name="John Attorney",
        case_summary="Comprehensive Complex Civil Rights case involving complex legal claims with multiple procedural requirements and substantive evidence analysis.",
        case_type="Civil Rights Violation",
        urgency_level="High",
        client_priorities=[
            "Seek monetary compensation for damages",
            "Ensure accountability for violations",
            "Prevent future incidents"
        ],
        desired_outcomes=[
            "Settlement of $150,000 or more",
            "Public acknowledgment of wrongdoing",
            "Policy changes to prevent recurrence"
        ],
        key_facts=[
            "Incident occurred on March 15, 2024 at defendant's premises",
            "Multiple witnesses observed the violation",
            "Security footage captured the entire incident",
            "Medical documentation supports injury claims",
            "Defendant has history of similar violations"
        ],
        parties_involved=[],
        financial_impact="Significant medical expenses and lost wages totaling approximately $75,000",
        legal_claims=[
            "42 U.S.C. § 1983 Civil Rights Violation",
            "Florida Civil Rights Act Violation",
            "Negligence and Gross Negligence",
            "Intentional Infliction of Emotional Distress"
        ]
    )
    
    # Create findings letter content
    findings_content = FindingsLetterContent(
        factual_summary="This Complex Civil Rights case presents compelling evidence of civil rights violations occurring on March 15, 2024. Our comprehensive review of incident reports, witness statements, and medical documentation reveals a clear pattern of misconduct resulting in significant physical and emotional damages. The evidence strongly supports multiple claims under both federal and Florida state law.",
        legal_analysis="Under 42 U.S.C. § 1983 and the Florida Civil Rights Act, defendants actions constitute clear violations of established constitutional and statutory protections. The evidence meets all elements for civil rights claims, negligence, and intentional tort actions. Florida courts have consistently awarded substantial damages in similar cases with comparable evidence.",
        strengths_of_case="Exceptional case strength derives from multiple independent witnesses, comprehensive documentation, clear liability chain, and substantial documented damages. Security footage provides uncontestable evidence, while medical records establish both immediate and long-term impacts requiring ongoing treatment and accommodation.",
        challenges_and_risks="Primary challenges include potential statute of limitations defenses and possible sovereign immunity claims. However, the continuing violation doctrine and clear constitutional violations significantly mitigate these concerns. Settlement negotiations may face initial resistance requiring strategic pressure.",
        recommended_next_steps="Immediate action required including comprehensive demand letter filing within 14 days, witness statement collection by August 30, 2024, and federal court preparation by September 15, 2024. Client consultation scheduled to discuss settlement parameters and litigation strategy.",
        demand_letter_analysis="Demand letter strategy is highly appropriate given case strength and evidence quality. Conservative settlement range of $125,000-$200,000 reflects documented damages and comparable case outcomes. Strong negotiating position supports aggressive initial demands with structured settlement discussions."
    )
    
    return CaseAnalysisResult(
        intake_analysis=intake,
        analyzed_documents=[],  # Simplified for debugging
        legal_assessment=LegalAssessment(
            case_type="Federal Civil Rights with State Law Claims",
            claim_viability="Strong viability",
            overall_evidence_strength="Excellent",
            potential_challenges="Statute limitations",
            recommended_actions="File demand letter",
            demand_letter_appropriate="Yes",
            urgency_assessment="High priority"
        ),
        demand_letter_evaluation=DemandLetterEvaluation(
            is_appropriate="Yes",
            reasoning="Strong evidence",
            potential_outcomes=["Settlement $125k-$200k"],
            relevant_statutes=["42 U.S.C. § 1983"]
        ),
        final_analysis=FinalAnalysis(
            case_summary="Strong civil rights case",
            recommendations="Proceed with demand letter",
            next_steps=["File demand letter within 14 days"]
        ),
        findings_letter_content=findings_content
    )

def main():
    print("🔍 Debug Validation Output - Checking Template Rendering")
    print("="*60)
    
    # Initialize OpenAI client like validation harness does
    try:
        api_key = get_openai_api_key()
        client = OpenAI(api_key=api_key)
        generator = EmailGeneratorV2(client=client)
        print("✅ EmailGeneratorV2 initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize EmailGeneratorV2: {e}")
        return
    
    # Create case analysis like validation harness
    case_analysis = create_sample_case_analysis()
    
    print("🧪 Testing case: Complex Civil Rights Case")
    
    # Generate email using same method as validation harness
    email_result = generator.generate_email_and_analysis_docs(case_analysis)
    
    if not email_result:
        print("❌ Email generation returned None")
        return
    
    # EmailGeneratorV2 returns dict with 'main_letter' and 'appendix' keys
    generated_email = email_result["main_letter"] if isinstance(email_result, dict) else email_result
    analysis_doc = email_result.get("appendix", "") if isinstance(email_result, dict) else ""
    
    print(f"\n📄 Generated Email Length: {len(generated_email)} characters")
    print(f"📄 Analysis Doc Length: {len(analysis_doc)} characters")
    
    # Extract sections like validation harness does
    soup = BeautifulSoup(generated_email, "html.parser")
    
    # Look for H2 and H3 tags
    h2_sections = soup.find_all("h2")
    h3_sections = soup.find_all("h3")
    
    print("\n🔍 Section Analysis:")
    print(f"   H2 sections found: {len(h2_sections)}")
    print(f"   H3 sections found: {len(h3_sections)}")
    print(f"   Total sections: {len(h2_sections) + len(h3_sections)}")
    
    if h2_sections:
        print("\n📋 H2 Section Titles:")
        for i, h2 in enumerate(h2_sections, 1):
            print(f"   {i}. '{h2.get_text().strip()}'")
    
    if h3_sections:
        print("\n📋 H3 Section Titles:")
        for i, h3 in enumerate(h3_sections, 1):
            print(f"   {i}. '{h3.get_text().strip()}'")
    
    # Look for section-title divs (legacy format)
    section_divs = soup.find_all("div", class_="section-title")
    if section_divs:
        print(f"\n⚠️  Found {len(section_divs)} legacy section-title divs:")
        for i, div in enumerate(section_divs, 1):
            print(f"   {i}. '{div.get_text().strip()}'")
    
    # Save output for inspection
    with open("debug_validation_email_output.html", "w") as f:
        f.write(generated_email)
    
    with open("debug_validation_analysis_output.html", "w") as f:
        f.write(analysis_doc)
    
    print("\n💾 Saved outputs:")
    print("   Email: debug_validation_email_output.html")
    print("   Analysis: debug_validation_analysis_output.html")
    
    # Show first 500 chars for quick inspection
    print("\n📝 Email Preview (first 500 chars):")
    print(generated_email[:500])
    print("...")

if __name__ == "__main__":
    main()
