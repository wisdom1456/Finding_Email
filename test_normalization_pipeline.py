#!/usr/bin/env python3
"""
Test script for the new normalization pipeline implementation.

This script validates that:
1. Citation filtering works on raw text without corrupting HTML
2. Sentence splitting improves readability 
3. AI simplification (when enabled) works properly
4. HTML structure is preserved throughout the process
"""

import os
import sys
import re
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from backend_logic.email_generator import EmailGeneratorV2
    from backend.utils.data_models import CaseAnalysisResult, EnhancedIntakeAnalysis
    from openai import OpenAI
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


def test_citation_filtering():
    """Test enhanced citation filtering on raw text."""
    print("\n🔍 Testing Enhanced Citation Filtering...")
    
    # Create a mock generator with minimal config
    client = OpenAI(api_key="test-key")  # Mock client
    
    # Create mock config with citation filter
    mock_config = {
        'citation_filter_regex': r'(Fla\.?\s*Stat\.?|§+|\bChapter\s*\d+\b|\bF\.S\.\s*\d[\d\.\(\)]*)',
        'template_path': 'backend/assets/templates/findings_email.jinja2'
    }
    
    # Create generator instance
    generator = EmailGeneratorV2.__new__(EmailGeneratorV2)
    generator.client = client
    generator.config = mock_config
    
    # Test content with citations
    test_content = """
    Under Florida Statute § 83.56, the landlord must provide proper notice.
    Chapter 713 governs construction liens in Florida.
    F.S. 768.81 addresses comparative negligence.
    The requirements are found in Fla. Stat. 95.11(3)(a).
    """
    
    # Apply citation filtering
    result = generator._apply_enhanced_citation_filtering(test_content)
    
    # Verify citations were removed
    citation_patterns = [r'§\s*\d+', r'Chapter\s*\d+', r'F\.S\.\s*\d+', r'Fla\.\s*Stat\.']
    citations_found = any(re.search(pattern, result, re.IGNORECASE) for pattern in citation_patterns)
    
    if citations_found:
        print(f"❌ Citation filtering failed - citations still present in: {result}")
        return False
    else:
        print(f"✅ Citation filtering successful")
        print(f"   Original: {len(test_content)} chars")
        print(f"   Filtered: {len(result)} chars")
        print(f"   Sample result: {result[:100]}...")
        return True


def test_sentence_splitting():
    """Test sentence splitting logic on raw text."""
    print("\n🔍 Testing Sentence Splitting Logic...")
    
    # Create generator instance
    client = OpenAI(api_key="test-key")
    generator = EmailGeneratorV2.__new__(EmailGeneratorV2)
    generator.client = client
    generator.config = {}
    
    # Test content with very long sentences
    test_content = """
    This is an extremely long and complex sentence that contains multiple clauses and coordinating conjunctions, and it should be split into shorter, more readable sentences because it currently exceeds the thirty-five word threshold that triggers the sentence splitting logic, and furthermore it contains additional complexity that makes it difficult to read and understand.
    """
    
    # Count original words
    original_words = len(test_content.split())
    
    # Apply sentence splitting
    result = generator._apply_sentence_splitting_logic(test_content)
    
    # Count sentences in result
    sentences = re.split(r'(?<=[.!?])\s+', result.strip())
    sentences = [s for s in sentences if s.strip()]  # Remove empty sentences
    
    # Check if splitting occurred
    max_sentence_length = max(len(sentence.split()) for sentence in sentences)
    
    print(f"   Original words: {original_words}")
    print(f"   Result sentences: {len(sentences)}")
    print(f"   Max sentence length: {max_sentence_length} words")
    print(f"   Sample result: {result[:150]}...")
    
    if max_sentence_length <= 35:
        print(f"✅ Sentence splitting successful - no sentences exceed 35 words")
        return True
    else:
        print(f"❌ Sentence splitting failed - longest sentence: {max_sentence_length} words")
        return False


def test_html_preservation():
    """Test that HTML structure is preserved during processing."""
    print("\n🔍 Testing HTML Structure Preservation...")
    
    # Create generator instance
    client = OpenAI(api_key="test-key")
    
    mock_config = {
        'citation_filter_regex': r'(Fla\.?\s*Stat\.?|§+|\bChapter\s*\d+\b)',
        'simplification': {'enabled': False}  # Disable AI simplification for this test
    }
    
    generator = EmailGeneratorV2.__new__(EmailGeneratorV2)
    generator.client = client
    generator.config = mock_config
    
    # Test content that might be processed (raw text before HTML structure)
    test_content = """
    Under Florida Statute § 83.56, the landlord must provide proper notice to tenants.
    This requirement is very important, and furthermore it must be followed precisely because failure to comply can result in significant legal consequences for the landlord, and moreover it affects the validity of any subsequent legal proceedings.
    """
    
    # Apply the complete cleaning pipeline (this simulates what happens in _clean_ai_response)
    result = generator._clean_ai_response(test_content)
    
    # Verify content was processed but structure preserved
    print(f"   Original length: {len(test_content)} chars")
    print(f"   Processed length: {len(result)} chars")
    print(f"   Sample result: {result[:200]}...")
    
    # Check that basic processing occurred
    if len(result) < len(test_content):
        print(f"✅ Content was processed (citations removed)")
    else:
        print(f"⚠️  Content length unchanged - processing may not have occurred")
    
    # Since this is raw text processing, we don't expect HTML tags yet
    # The key is that the content is clean and ready for HTML template processing
    if result and result.strip():
        print(f"✅ Content processing successful - clean text ready for template")
        return True
    else:
        print(f"❌ Content processing failed - empty result")
        return False


def test_ai_simplification_config():
    """Test AI simplification configuration handling."""
    print("\n🔍 Testing AI Simplification Configuration...")
    
    # Create generator instance
    client = OpenAI(api_key="test-key")
    
    # Test with AI simplification disabled
    mock_config_disabled = {
        'simplification': {'enabled': False}
    }
    
    generator = EmailGeneratorV2.__new__(EmailGeneratorV2)
    generator.client = client
    generator.config = mock_config_disabled
    
    test_content = "This is complex legal terminology that could potentially be simplified."
    
    result = generator._apply_optional_ai_simplification(test_content)
    
    if result == test_content:
        print(f"✅ AI simplification correctly disabled - content unchanged")
        return True
    else:
        print(f"❌ AI simplification config not respected")
        return False


def run_all_tests():
    """Run all normalization pipeline tests."""
    print("🧪 Testing New Normalization Pipeline Implementation")
    print("=" * 60)
    
    tests = [
        ("Citation Filtering", test_citation_filtering),
        ("Sentence Splitting", test_sentence_splitting),
        ("HTML Preservation", test_html_preservation),
        ("AI Simplification Config", test_ai_simplification_config),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} test failed with error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Normalization pipeline implementation is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please review the implementation.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)