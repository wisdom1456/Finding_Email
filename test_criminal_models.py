#!/usr/bin/env python3
"""
Test script to validate the criminal evidence data models implementation.
This script tests the new criminal law data models for proper validation and integration.
"""

from __future__ import annotations

import os
import sys


# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.utils.data_models import (
    CaseAnalysisResult,
    CriminalEvidenceCategory,
    CriminalEvidenceItem,
    CriminalVideoAnalysis,
    EnhancedVideoInsight,
    FileMetadata,
    TimeRange,
    VideoInsight,
)


def test_criminal_evidence_category():
    """Test CriminalEvidenceCategory enum values."""
    print("Testing CriminalEvidenceCategory enum...")

    # Test all 16 categories are available
    categories = [
        CriminalEvidenceCategory.DRIVING_PATTERN_REASON_FOR_STOP,
        CriminalEvidenceCategory.EMERGENCY_LIGHTS_VEHICLE_PULLOVER,
        CriminalEvidenceCategory.INITIAL_ROADSIDE_APPROACH_OBSERVATIONS,
        CriminalEvidenceCategory.PRELIMINARY_QUESTIONING_ADMISSIONS,
        CriminalEvidenceCategory.EXIT_ORDER_PRETEST_OBSERVATIONS,
        CriminalEvidenceCategory.FIELD_SOBRIETY_TESTS,
        CriminalEvidenceCategory.PORTABLE_BREATH_TEST,
        CriminalEvidenceCategory.ARREST_DECISION_HANDCUFFING,
        CriminalEvidenceCategory.MIRANDA_WARNINGS_CUSTODIAL_INTERROGATION,
        CriminalEvidenceCategory.IMPLIED_CONSENT_CHEMICAL_TEST_REQUEST,
        CriminalEvidenceCategory.CHEMICAL_TEST_ADMINISTRATION,
        CriminalEvidenceCategory.TRANSPORT_TO_STATION_JAIL,
        CriminalEvidenceCategory.BOOKING_PROCESSING,
        CriminalEvidenceCategory.RIGHT_TO_COUNSEL_PHONE_CALLS,
        CriminalEvidenceCategory.POST_BOOKING_OBSERVATION_MEDICAL,
        CriminalEvidenceCategory.VEHICLE_TOW_INVENTORY_SEARCH,
    ]

    assert len(categories) == 16, f"Expected 16 categories, got {len(categories)}"
    print(f"✅ All {len(categories)} criminal evidence categories available")
    return True


def test_time_range():
    """Test TimeRange model validation."""
    print("Testing TimeRange model...")

    # Valid time range
    time_range = TimeRange(start_time="02:15", end_time="02:45", confidence=0.85)

    assert time_range.start_time == "02:15"
    assert time_range.end_time == "02:45"
    assert time_range.confidence == 0.85
    print("✅ TimeRange model validation successful")
    return True


def test_criminal_evidence_item():
    """Test CriminalEvidenceItem model validation."""
    print("Testing CriminalEvidenceItem model...")

    time_range = TimeRange(start_time="01:30", end_time="02:00", confidence=0.9)

    evidence_item = CriminalEvidenceItem(
        category=CriminalEvidenceCategory.FIELD_SOBRIETY_TESTS,
        time_range=time_range,
        description="Officer conducts walk-and-turn test on suspect",
        key_observations=[
            "Suspect stumbles on turn",
            "Officer provides unclear instructions",
            "Test conducted on uneven surface",
        ],
        legal_significance="Improper test administration may invalidate results",
        constitutional_issues=[
            "Potential 4th Amendment violation due to improper test conditions"
        ],
        evidence_strength="moderate",
    )

    assert evidence_item.category == CriminalEvidenceCategory.FIELD_SOBRIETY_TESTS
    assert evidence_item.evidence_strength == "moderate"
    assert len(evidence_item.key_observations) == 3
    print("✅ CriminalEvidenceItem model validation successful")
    return True


def test_criminal_video_analysis():
    """Test CriminalVideoAnalysis model."""
    print("Testing CriminalVideoAnalysis model...")

    time_range = TimeRange(start_time="00:30", end_time="01:00", confidence=0.8)
    evidence_item = CriminalEvidenceItem(
        category=CriminalEvidenceCategory.MIRANDA_WARNINGS_CUSTODIAL_INTERROGATION,
        time_range=time_range,
        description="Officer reads Miranda rights to suspect",
        key_observations=[
            "Clear delivery of rights",
            "Suspect acknowledges understanding",
        ],
        legal_significance="Proper Miranda administration protects statements admissibility",
        constitutional_issues=[],
        evidence_strength="strong",
    )

    analysis = CriminalVideoAnalysis(
        evidence_items=[evidence_item],
        timeline_summary="Video shows proper arrest procedures with clear Miranda warnings",
        constitutional_compliance_overview="Generally compliant with constitutional requirements",
        missing_categories=[
            CriminalEvidenceCategory.FIELD_SOBRIETY_TESTS,
            CriminalEvidenceCategory.PORTABLE_BREATH_TEST,
        ],
    )

    assert len(analysis.evidence_items) == 1
    assert len(analysis.missing_categories) == 2
    print("✅ CriminalVideoAnalysis model validation successful")
    return True


def test_enhanced_video_insight():
    """Test EnhancedVideoInsight model with backward compatibility."""
    print("Testing EnhancedVideoInsight model...")

    # Create criminal analysis
    time_range = TimeRange(start_time="00:15", end_time="00:45", confidence=0.95)
    evidence_item = CriminalEvidenceItem(
        category=CriminalEvidenceCategory.ARREST_DECISION_HANDCUFFING,
        time_range=time_range,
        description="Officer places suspect under arrest and applies handcuffs",
        key_observations=[
            "Proper handcuff placement",
            "Officer explains arrest reason",
        ],
        legal_significance="Clear arrest procedure supports probable cause",
        constitutional_issues=[],
        evidence_strength="strong",
    )

    criminal_analysis = CriminalVideoAnalysis(
        evidence_items=[evidence_item],
        timeline_summary="Video shows proper arrest with clear probable cause",
        constitutional_compliance_overview="Arrest procedures comply with constitutional standards",
        missing_categories=[],
    )

    # Test enhanced insight
    enhanced_insight = EnhancedVideoInsight(
        file_name="arrest_video.mp4",
        insights={"general": "Arrest video with constitutional compliance"},
        labels=["arrest", "handcuffs", "miranda"],
        objects=["police_officer", "suspect", "patrol_car"],
        criminal_analysis=criminal_analysis,
        is_criminal_case=True,
        metadata=FileMetadata(filename="arrest_video.mp4", size=1024000),
    )

    assert enhanced_insight.is_criminal_case is True
    assert enhanced_insight.criminal_analysis is not None
    assert len(enhanced_insight.criminal_analysis.evidence_items) == 1
    print("✅ EnhancedVideoInsight model validation successful")

    # Test backward compatibility - regular VideoInsight
    regular_insight = VideoInsight(
        file_name="regular_video.mp4",
        insights={"general": "Regular video analysis"},
        labels=["meeting", "discussion"],
        objects=["table", "chairs", "documents"],
        metadata=FileMetadata(filename="regular_video.mp4", size=512000),
    )

    assert hasattr(regular_insight, "insights")
    assert not hasattr(regular_insight, "is_criminal_case")
    print("✅ Backward compatibility with VideoInsight confirmed")
    return True


def test_case_analysis_result_integration():
    """Test CaseAnalysisResult integration with enhanced video insights."""
    print("Testing CaseAnalysisResult integration...")

    # Create both regular and enhanced video insights
    regular_insight = VideoInsight(
        file_name="regular_video.mp4",
        insights={"type": "general_evidence"},
        labels=["document", "signature"],
        objects=["paper", "pen"],
    )

    time_range = TimeRange(start_time="01:00", end_time="01:30", confidence=0.9)
    evidence_item = CriminalEvidenceItem(
        category=CriminalEvidenceCategory.CHEMICAL_TEST_ADMINISTRATION,
        time_range=time_range,
        description="Breathalyzer test administration",
        key_observations=[
            "Proper 20-minute observation period",
            "Calibrated equipment used",
        ],
        legal_significance="Proper test administration supports reliability",
        constitutional_issues=[],
        evidence_strength="strong",
    )

    criminal_analysis = CriminalVideoAnalysis(
        evidence_items=[evidence_item],
        timeline_summary="Proper chemical test administration",
        constitutional_compliance_overview="Test administration follows proper protocols",
        missing_categories=[],
    )

    enhanced_insight = EnhancedVideoInsight(
        file_name="breathalyzer_test.mp4",
        insights={"type": "chemical_test_evidence"},
        labels=["breathalyzer", "test", "administration"],
        objects=["breathalyzer_machine", "officer", "suspect"],
        criminal_analysis=criminal_analysis,
        is_criminal_case=True,
    )

    # Test CaseAnalysisResult with mixed video insights
    case_result = CaseAnalysisResult(video_insights=[regular_insight, enhanced_insight])

    assert len(case_result.video_insights) == 2
    assert isinstance(case_result.video_insights[0], VideoInsight)
    assert isinstance(case_result.video_insights[1], EnhancedVideoInsight)
    print("✅ CaseAnalysisResult integration with mixed video insights successful")
    return True


def run_all_tests():
    """Run all validation tests."""
    print("🔍 Running Criminal Evidence Data Models Validation Tests\n")

    tests = [
        test_criminal_evidence_category,
        test_time_range,
        test_criminal_evidence_item,
        test_criminal_video_analysis,
        test_enhanced_video_insight,
        test_case_analysis_result_integration,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"❌ {test.__name__} failed")
        except Exception as e:
            failed += 1
            print(f"❌ {test.__name__} failed with exception: {e}")
        print()

    print(f"📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All criminal evidence data models are working correctly!")
        print("✅ Ready for integration with video processor!")
        return True
    print("⚠️  Some tests failed. Please review the implementation.")
    return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
