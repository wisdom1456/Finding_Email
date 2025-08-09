#!/usr/bin/env python3

"""
Debug script to examine the actual content that's failing normalization.
"""
from __future__ import annotations

import os
import sys


sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import re

from bs4 import BeautifulSoup
from openai import OpenAI

from backend.utils.data_models import (
    CaseAnalysisResult,
    EnhancedIntakeAnalysis,
    LegalAssessment,
)
from backend_logic.email_generator import EmailGeneratorV2


def count_normalization_issues(html_content):
    """Count normalization issues like the validation harness does."""
    if not html_content:
        return 0, 0, 0
    
    # Parse HTML and extract text
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text()
    
    # Count duplicate sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentence_counts = {}
    for sentence in sentences:
        clean_sentence = re.sub(r"\s+", " ", sentence.strip().lower())
        if len(clean_sentence) > 10:  # Only count meaningful sentences
            sentence_counts[clean_sentence] = sentence_counts.get(clean_sentence, 0) + 1
    
    duplicate_sentences = sum(1 for count in sentence_counts.values() if count > 1)
    
    # Count long sentences (>15 words)
    long_sentences = 0
    for sentence in sentences:
        words = sentence.split()
        if len(words) > 15:
            long_sentences += 1
    
    # Count repeated 3-word phrases
    words = re.findall(r"\b\w+\b", text.lower())
    phrase_counts = {}
    for i in range(len(words) - 2):
        phrase = " ".join(words[i:i+3])
        phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
    
    repeated_phrases = sum(1 for count in phrase_counts.values() if count > 2)
    
    return duplicate_sentences, long_sentences, repeated_phrases, sentences, phrase_counts

def analyze_long_sentences(sentences):
    """Analyze which sentences are too long."""
    print("\n🔍 LONG SENTENCES ANALYSIS:")
    print("=" * 60)
    long_sentences = []
    for i, sentence in enumerate(sentences):
        words = sentence.split()
        if len(words) > 15:
            long_sentences.append((i, len(words), sentence.strip()))
    
    print(f"Found {len(long_sentences)} sentences with >15 words:")
    for i, (sent_num, word_count, sentence) in enumerate(long_sentences[:10]):  # Show first 10
        print(f"\n{i+1}. ({word_count} words): {sentence[:100]}...")
    
    return long_sentences

def analyze_repeated_phrases(phrase_counts):
    """Analyze which phrases are repeated too much."""
    print("\n🔍 REPEATED PHRASES ANALYSIS:")
    print("=" * 60)
    repeated = [(phrase, count) for phrase, count in phrase_counts.items() if count > 2]
    repeated.sort(key=lambda x: x[1], reverse=True)
    
    print(f"Found {len(repeated)} phrases repeated >2 times:")
    for i, (phrase, count) in enumerate(repeated[:15]):  # Show top 15
        print(f"{i+1}. '{phrase}' appears {count} times")
    
    return repeated

# Create a test case
print("🧪 Analyzing actual generated content for normalization issues...")

client = OpenAI()
generator = EmailGeneratorV2(client)

# Create a realistic test case
intake = EnhancedIntakeAnalysis(
    client_name="Jane Smith",
    attorney_name="John Attorney",
    case_summary="Civil rights violation case involving police misconduct",
    case_type="Civil Rights Violation",
    urgency_level="High",
    financial_impact="Potential damages for civil rights violations estimated at $50,000-$100,000",
    key_facts=["Police stop without probable cause", "Excessive force used", "Video evidence available"],
    legal_claims=["42 USC 1983 civil rights violation", "Excessive force under Fourth Amendment"]
)

legal_assessment = LegalAssessment(
    case_type="Civil Rights Violation",
    claim_viability="Strong",
    overall_evidence_strength="Substantial video and witness evidence",
    potential_challenges="Qualified immunity defense, burden of proof issues",
    recommended_actions="File federal civil rights lawsuit, preserve all evidence, document injuries",
    demand_letter_appropriate="No - immediate litigation recommended",
    urgency_assessment="High - statute of limitations concerns"
)

analysis = CaseAnalysisResult(
    intake_analysis=intake,
    legal_assessment=legal_assessment,
    analyzed_documents=[],
    transcripted_media=[],
    video_insights=[]
)

print("📧 Generating email...")
try:
    result = generator.generate_email_and_analysis_docs(analysis)
    html_content = result["main_letter"]
    
    print("✅ Email generated successfully")
    print(f"📏 Content length: {len(html_content)} characters")
    
    # Analyze normalization issues
    print("\n🔬 NORMALIZATION ANALYSIS:")
    print("=" * 60)
    
    duplicates, long_count, repeated_count, sentences, phrase_counts = count_normalization_issues(html_content)
    
    print("📊 SUMMARY:")
    print(f"  - Duplicate sentences: {duplicates}")
    print(f"  - Long sentences (>15 words): {long_count}")
    print(f"  - Repeated 3-word phrases (>2 times): {repeated_count}")
    print(f"  - Total sentences: {len(sentences)}")
    print(f"  - Total unique 3-word phrases: {len(phrase_counts)}")
    
    # Analyze the problematic content
    long_sentences = analyze_long_sentences(sentences)
    repeated_phrases = analyze_repeated_phrases(phrase_counts)
    
    # Save detailed analysis
    with open("normalization_analysis.txt", "w") as f:
        f.write("DETAILED NORMALIZATION ANALYSIS\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Duplicate sentences: {duplicates}\n")
        f.write(f"Long sentences: {long_count}\n")
        f.write(f"Repeated phrases: {repeated_count}\n\n")
        
        f.write("LONG SENTENCES:\n")
        f.write("-" * 30 + "\n")
        for i, (sent_num, word_count, sentence) in enumerate(long_sentences):
            f.write(f"{i+1}. ({word_count} words): {sentence}\n\n")
        
        f.write("\nREPEATED PHRASES:\n")
        f.write("-" * 30 + "\n")
        for phrase, count in repeated_phrases:
            f.write(f"'{phrase}' appears {count} times\n")
        
        f.write("\n\nFULL HTML CONTENT:\n")
        f.write("=" * 50 + "\n")
        f.write(html_content)
    
    print("\n📄 Detailed analysis saved to: normalization_analysis.txt")
    
    # Show a sample of the problematic content
    print("\n📝 SAMPLE CONTENT (first 500 chars):")
    print("=" * 60)
    plain_text = BeautifulSoup(html_content, "html.parser").get_text()
    print(plain_text[:500] + "...")

except Exception as e:
    print(f"❌ Error generating email: {e}")
    import traceback
    traceback.print_exc()
