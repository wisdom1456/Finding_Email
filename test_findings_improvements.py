#!/usr/bin/env python3
"""
Test script to validate the findings letter and video evidence improvements.
Tests all the major changes implemented:
1. Video analysis formatting improvements
2. Video relevance analysis
3. Timeline generation
4. Template restructuring
5. Email template integration
"""

import asyncio
import sys
import os
from typing import Dict, Any, List
from unittest.mock import MagicMock

# Add the project root to Python path
sys.path.insert(0, os.path.abspath('.'))

# Import necessary modules
from backend.utils.data_models import (
    CaseAnalysisResult,
    EnhancedIntakeAnalysis,
    VideoInsight,
    AnalyzedDocument,
    LegalAssessment,
    DemandLetterEvaluation
)
from backend_logic.email_generator import EmailGenerator
from unittest.mock import MagicMock

def create_mock_video_insight() -> VideoInsight:
    """Create a mock video insight for testing."""
    return VideoInsight(
        file_name="security_footage.mp4",
        insights={
            "criminal_analysis": {
                "violations_detected": [
                    {
                        "type": "Property Damage",
                        "description": "Individual seen damaging property with tools",
                        "confidence": 0.85,
                        "timestamp": "00:02:15"
                    },
                    {
                        "type": "Trespassing",
                        "description": "Unauthorized entry onto private property",
                        "confidence": 0.92,
                        "timestamp": "00:01:30"
                    }
                ],
                "evidence_strength": "Strong",
                "legal_implications": [
                    "Clear documentation of property damage",
                    "Video evidence supports trespassing charges",
                    "Timestamps provide chronological evidence"
                ]
            }
        },
        transcript="Person approaches property at 1:30 AM, uses tools to damage fence at 2:15",
        labels=["person", "tools", "fence", "property damage"],
        objects=["fence", "hammer", "individual", "gate"],
        text_annotations=["NO TRESPASSING", "PRIVATE PROPERTY"]
    )

def create_mock_intake_analysis() -> EnhancedIntakeAnalysis:
    """Create a mock intake analysis for testing."""
    return EnhancedIntakeAnalysis(
        client_name="John Smith",
        attorney_name="Attorney Sarah Johnson",
        case_summary="Property damage and trespassing incident at client's residence",
        case_type="Property Damage/Trespassing",
        urgency_level="High",
        client_priorities=["Document property damage", "Pursue criminal charges"],
        desired_outcomes=["Financial compensation", "Criminal prosecution"],
        key_facts=["Security footage captured incident", "Damage estimated at $5,000"],
        parties_involved=[
            {"name": "John Smith", "role": "Property Owner"},
            {"name": "Unknown Suspect", "role": "Alleged Perpetrator"}
        ],
        financial_impact="Property damage estimated at $5,000 plus security costs",
        legal_claims=["Property Damage", "Trespassing", "Criminal Mischief"]
    )

def create_mock_analyzed_document() -> AnalyzedDocument:
    """Create a mock analyzed document for testing."""
    return AnalyzedDocument(
        filename="police_report.pdf",
        document_type="Police Report",
        inferred_title="Police Incident Report - Property Damage Case",
        summary="Police report documenting property damage incident with witness statements",
        key_information="Incident occurred at 123 Main St on January 15, 2024; damage to fence and gate; witness observed suspect with tools",
        relevance_to_case="Primary evidence supporting property damage claims and establishing timeline of events"
    )

def create_mock_case_analysis() -> CaseAnalysisResult:
    """Create a complete mock case analysis for testing."""
    analysis = CaseAnalysisResult()
    analysis.intake_analysis = create_mock_intake_analysis()
    analysis.video_insights = [create_mock_video_insight()]
    analysis.analyzed_documents = [create_mock_analyzed_document()]
    
    # Add legal assessment
    analysis.legal_assessment = LegalAssessment(
        case_type="Property Damage/Trespassing",
        claim_viability="Strong",
        overall_evidence_strength="Strong",
        potential_challenges="Identifying the perpetrator may require additional investigation",
        recommended_actions="File police report, pursue criminal charges, document all damages",
        demand_letter_appropriate=True,
        urgency_assessment="High"
    )
    
    # Add demand letter evaluation
    analysis.demand_letter_evaluation = DemandLetterEvaluation(
        is_appropriate=True,
        reasoning="Clear video evidence and documented damages support demand letter approach",
        potential_outcomes=["Full compensation", "Negotiated settlement"],
        relevant_statutes=["Property Damage Statute", "Trespassing Laws"]
    )
    
    return analysis

def test_video_analysis_formatting():
    """Test the video analysis formatting function."""
    print("🧪 Testing video analysis formatting...")
    
    # Create mock email generator
    mock_client = MagicMock()
    email_generator = EmailGenerator(mock_client)
    
    video_insight = create_mock_video_insight()
    formatted_output = email_generator.format_video_analysis_for_appendix(video_insight)
    
    # Check that output contains expected sections
    expected_sections = [
        "Video Summary",
        "Key Events",
        "Objects/Evidence",
        "Case Relevance"
    ]
    
    found_sections = 0
    for section in expected_sections:
        if section in formatted_output:
            found_sections += 1
    
    # Check that at least some sections are present
    if found_sections == 0:
        print("❌ No expected sections found in formatted output")
        return False
    
    # Check that raw dictionary data is not present
    if "violations_detected" in formatted_output or '{"' in formatted_output:
        print("❌ Raw dictionary data found in formatted output")
        return False
    
    print("✅ Video analysis formatting test passed")
    return True

def test_video_relevance_analysis():
    """Test the video relevance analysis function."""
    print("🧪 Testing video relevance analysis...")
    
    # Create mock email generator
    mock_client = MagicMock()
    email_generator = EmailGenerator(mock_client)
    
    case_analysis = create_mock_case_analysis()
    video_insight = case_analysis.video_insights[0]
    relevance_analysis = email_generator.analyze_video_relevance(video_insight, case_analysis.intake_analysis)
    
    # Check that analysis contains key elements
    expected_keys = [
        "case_connection",
        "evidence_value",
        "legal_impact",
        "corroboration"
    ]
    
    if not isinstance(relevance_analysis, dict):
        print("❌ Relevance analysis should return a dictionary")
        return False
    
    for key in expected_keys:
        if key not in relevance_analysis:
            print(f"❌ Missing key: {key}")
            return False
        if not relevance_analysis[key]:
            print(f"❌ Empty value for key: {key}")
            return False
    
    print("✅ Video relevance analysis test passed")
    return True

def test_timeline_generation():
    """Test the timeline generation function."""
    print("🧪 Testing timeline generation...")
    
    # Create mock email generator
    mock_client = MagicMock()
    email_generator = EmailGenerator(mock_client)
    
    case_analysis = create_mock_case_analysis()
    timeline = email_generator.generate_case_timeline(case_analysis)
    
    # Check that timeline is a list
    if not isinstance(timeline, list):
        print("❌ Timeline should return a list of events")
        return False
    
    # Check that timeline contains events
    if len(timeline) == 0:
        print("❌ Timeline should contain at least some events")
        return False
    
    # Check that events have required structure
    for event in timeline[:3]:  # Check first 3 events
        if not isinstance(event, dict):
            print("❌ Timeline events should be dictionaries")
            return False
        
        required_fields = ['date', 'source', 'event']
        for field in required_fields:
            if field not in event:
                print(f"❌ Timeline event missing field: {field}")
                return False
    
    print("✅ Timeline generation test passed")
    return True

def test_email_template_integration():
    """Test that email generator properly integrates new functions."""
    print("🧪 Testing email template integration...")
    
    # Create mock email generator
    mock_client = MagicMock()
    email_generator = EmailGenerator(mock_client)
    case_analysis = create_mock_case_analysis()
    
    # Test that the new functions are accessible
    try:
        timeline = email_generator.generate_case_timeline(case_analysis)
        video_insight = case_analysis.video_insights[0]
        video_relevance = email_generator.analyze_video_relevance(video_insight, case_analysis.intake_analysis)
        video_formatting = email_generator.format_video_analysis_for_appendix(video_insight)
        
        # Check that all functions return appropriate types
        if not isinstance(timeline, list):
            print("❌ Timeline should return a list")
            return False
        if not isinstance(video_relevance, dict):
            print("❌ Video relevance should return a dict")
            return False
        if not isinstance(video_formatting, str):
            print("❌ Video formatting should return a string")
            return False
            
        print("✅ Email template integration test passed")
        return True
    except Exception as e:
        print(f"❌ Email template integration failed: {e}")
        return False

def test_template_structure():
    """Test that templates have been properly restructured."""
    print("🧪 Testing template structure...")
    
    try:
        # Check findings email template exists and has been updated
        with open("backend/assets/templates/findings_email.jinja2", "r") as f:
            template_content = f.read()
        
        # Check for new Timeline section
        if "Timeline" not in template_content:
            print("❌ Timeline section not found in findings template")
            return False
        
        # Check that Document Review section has been removed/replaced
        if "Document Review" in template_content and "Timeline" not in template_content:
            print("❌ Document Review section still present without Timeline replacement")
            return False
        
        # Check for video relevance integration
        if "analyze_video_relevance" not in template_content:
            print("❌ Video relevance analysis not integrated in template")
            return False
        
        # Check for attorney name in From field
        if "intake_analysis.attorney_name" not in template_content:
            print("❌ Attorney name not used in From field")
            return False
        
        print("✅ Template structure test passed")
        return True
    except FileNotFoundError:
        print("❌ Findings email template not found")
        return False
    except Exception as e:
        print(f"❌ Template structure test failed: {e}")
        return False

def run_all_tests():
    """Run all tests and report results."""
    print("🚀 Starting Findings Letter and Video Evidence Improvements Tests")
    print("=" * 70)
    
    tests = [
        ("Video Analysis Formatting", test_video_analysis_formatting),
        ("Video Relevance Analysis", test_video_relevance_analysis),
        ("Timeline Generation", test_timeline_generation),
        ("Email Template Integration", test_email_template_integration),
        ("Template Structure", test_template_structure)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
    
    print("\n" + "=" * 70)
    print(f"🏁 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The improvements are working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)