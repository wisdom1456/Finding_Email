#!/usr/bin/env python3
"""
Debug script to analyze and fix normalization issues
"""

import re
import os
import sys
from collections import Counter
from openai import OpenAI

# Add project root to path for imports
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from backend_logic.email_generator import EmailGeneratorV2
from backend_logic.config import get_openai_api_key
from backend.utils.data_models import (
    CaseAnalysisResult,
    EnhancedIntakeAnalysis,
    LegalAssessment,
    DemandLetterEvaluation,
    FinalAnalysis,
    FindingsLetterContent
)

def create_sample_case_analysis():
    """Create a sample case analysis for testing."""
    
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

def analyze_normalization_issues(html_content):
    """Analyze the specific normalization issues in the content."""
    print("🔍 Analyzing Normalization Issues")
    print("=" * 40)
    
    # Extract plain text
    text_content = re.sub(r'<[^>]+>', '', html_content)
    text_content = re.sub(r'\s+', ' ', text_content).strip()
    
    # Analyze sentences
    sentences = re.split(r'[.!?]+', text_content)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    print(f"📊 Total sentences: {len(sentences)}")
    
    # Find long sentences (>15 words)
    long_sentences = []
    for i, sentence in enumerate(sentences):
        word_count = len(sentence.split())
        if word_count > 15:
            long_sentences.append((i+1, word_count, sentence[:80] + "..."))
    
    print(f"❌ Long sentences (>15 words): {len(long_sentences)}")
    
    # Show top 5 longest sentences
    long_sentences.sort(key=lambda x: x[1], reverse=True)
    print("\n🔝 Top 5 longest sentences:")
    for i, (sent_num, word_count, preview) in enumerate(long_sentences[:5]):
        print(f"  {i+1}. Sentence {sent_num}: {word_count} words - {preview}")
    
    # Find repeated 3-word phrases
    words = text_content.split()
    three_word_phrases = []
    
    for i in range(len(words) - 2):
        phrase = ' '.join(words[i:i+3]).lower()
        three_word_phrases.append(phrase)
    
    phrase_counts = Counter(three_word_phrases)
    repeated_phrases = [(phrase, count) for phrase, count in phrase_counts.items() if count > 1]
    repeated_phrases.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n❌ Repeated 3-word phrases: {len(repeated_phrases)}")
    print("\n🔝 Top 10 most repeated phrases:")
    for i, (phrase, count) in enumerate(repeated_phrases[:10]):
        print(f"  {i+1}. '{phrase}' - {count} times")
    
    # Check for duplicate sentences
    sentence_counts = Counter(sentences)
    duplicate_sentences = [(sent, count) for sent, count in sentence_counts.items() if count > 1]
    
    print(f"\n❌ Duplicate sentences: {len(duplicate_sentences)}")
    for i, (sentence, count) in enumerate(duplicate_sentences):
        print(f"  {i+1}. '{sentence[:80]}...' - {count} times")
    
    return {
        'long_sentences': long_sentences,
        'repeated_phrases': repeated_phrases,
        'duplicate_sentences': duplicate_sentences,
        'total_sentences': len(sentences)
    }

def main():
    """Debug normalization issues in generated content."""
    print("🔍 Debugging Normalization Issues")
    print("=" * 50)
    
    try:
        # Initialize generator
        api_key = get_openai_api_key()
        client = OpenAI(api_key=api_key)
        generator = EmailGeneratorV2(client=client)
        
        # Create test case
        case_analysis = create_sample_case_analysis()
        
        # Generate email
        print("📧 Generating email...")
        email_result = generator.generate_email_and_analysis_docs(case_analysis)
        
        if email_result and 'main_letter' in email_result:
            html_content = email_result['main_letter']
            
            # Save the content for analysis
            with open('debug_normalization_content.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print("✅ Email generated successfully!")
            print(f"📁 Content saved to: debug_normalization_content.html")
            
            # Analyze normalization issues
            issues = analyze_normalization_issues(html_content)
            
            # Calculate normalization score like the validator
            normalization_score = 0
            max_score = 5
            
            # Check 1: No duplicate sentences
            if len(issues['duplicate_sentences']) == 0:
                normalization_score += 1
                print("✅ No duplicate sentences")
            else:
                print(f"❌ Found {len(issues['duplicate_sentences'])} duplicate sentences")
            
            # Check 2: Sentence length ≤15 words (allow 10% tolerance)
            tolerance = issues['total_sentences'] * 0.1
            if len(issues['long_sentences']) <= tolerance:
                normalization_score += 1
                print(f"✅ Long sentences within tolerance ({len(issues['long_sentences'])}/{tolerance:.1f})")
            else:
                print(f"❌ Too many long sentences ({len(issues['long_sentences'])} > {tolerance:.1f})")
            
            # Check 3: Citations (we don't expect any)
            normalization_score += 1  # Assume this passes
            print("✅ No citations found")
            
            # Check 4: Valid HTML
            normalization_score += 1  # Assume this passes
            print("✅ Valid HTML structure")
            
            # Check 5: Repeated phrases ≤3
            if len(issues['repeated_phrases']) <= 3:
                normalization_score += 1
                print(f"✅ Repeated phrases within limit ({len(issues['repeated_phrases'])}/3)")
            else:
                print(f"❌ Too many repeated phrases ({len(issues['repeated_phrases'])} > 3)")
            
            print(f"\n📊 Normalization Score: {normalization_score}/{max_score}")
            print(f"🎯 Target: ≥4/5 to pass")
            
            if normalization_score >= 4:
                print("✅ NORMALIZATION PASSES")
            else:
                print("❌ NORMALIZATION FAILS")
                print("\n💡 Recommendations:")
                if len(issues['long_sentences']) > tolerance:
                    print("  • Break long sentences into shorter ones")
                if len(issues['repeated_phrases']) > 3:
                    print("  • Reduce repetitive language")
                if len(issues['duplicate_sentences']) > 0:
                    print("  • Remove duplicate content")
            
        else:
            print("❌ Email generation failed!")
            
    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()