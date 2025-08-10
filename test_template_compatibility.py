#!/usr/bin/env python3
"""
Comprehensive test suite for validating findings letter template and AI prompt improvements.

This test validates:
1. Template loading and rendering functionality
2. AI prompt compatibility with new template structure
3. Video analysis formatting improvements
4. Data model compatibility with template expectations
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add the project root to Python path
sys.path.insert(0, ".")


def test_template_loading():
    """Test 1: Template Loading and Basic Rendering"""
logger.info('🔍 TEST 1: Template Loading and Basic Rendering')

    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        # Find project root and template directory
        project_root = os.getcwd()
        template_dir = os.path.join(project_root, "backend", "assets", "templates")

logger.info(f'   📂 Template directory: {template_dir}')
logger.info(f'   📂 Directory exists: {os.path.exists(template_dir)}')

        if not os.path.exists(template_dir):
logger.info('   ❌ Template directory not found')
            return False

        # List available templates
        available_files = os.listdir(template_dir)
logger.info(f'   📄 Available templates: {available_files}')

        # Check required templates exist
        required_templates = ["findings_email.jinja2", "document_appendix.jinja2"]
        missing_templates = [t for t in required_templates if t not in available_files]

        if missing_templates:
logger.info(f'   ❌ Missing required templates: {missing_templates}')
            return False

        # Initialize Jinja2 environment
        jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Test loading main template
        try:
            jinja_env.get_template("findings_email.jinja2")
logger.info('   ✅ Main template (findings_email.jinja2) loaded successfully')
        except Exception as e:
logger.error(f'   ❌ Failed to load main template: {e}')
            return False

        # Test loading appendix template
        try:
            jinja_env.get_template("document_appendix.jinja2")
logger.info('   ✅ Appendix template (document_appendix.jinja2) loaded successfully')
                "   ✅ Appendix template (document_appendix.jinja2) loaded successfully"
            )
        except Exception as e:
logger.error(f'   ❌ Failed to load appendix template: {e}')
            return False

logger.info('   🎉 Template loading test PASSED')
        return True

    except Exception as e:
logger.error(f'   ❌ Template loading test FAILED: {e}')
        return False


def test_data_model_compatibility():
    """Test 2: Data Model Compatibility with Template Structure"""
logger.info('\n🔍 TEST 2: Data Model Compatibility')

    try:
        from backend.utils.data_models import (
            CaseAnalysisResult,
            CriminalEvidenceCategory,
            CriminalEvidenceItem,
            CriminalVideoAnalysis,
            EnhancedIntakeAnalysis,
            EnhancedVideoInsight,
            GeneratedLetter,
            TimeRange,
        )

        # Test GeneratedLetter model structure
logger.info('   📋 Testing GeneratedLetter model...')

        test_generated_letter = GeneratedLetter(
            executive_summary="<p>Test executive summary</p>",
            background_summary="<p>Test background summary</p>",
            analysis_and_position="<p>Test key legal concerns</p>",  # This should map to template
            media_summary="<p>Test media summary</p>",
            video_analysis_appendix="<p>Test video appendix</p>",
            strengths="<ul><li>Test strength 1</li><li>Test strength 2</li></ul>",
            challenges="<ul><li>Test challenge 1</li><li>Test challenge 2</li></ul>",
            recommendations="<ul><li>Test recommendation 1</li><li>Test recommendation 2</li></ul>",
            next_steps="<ul><li>Test next step 1</li><li>Test next step 2</li></ul>",
            closing_paragraph="<p>Test closing paragraph</p>",
        )
logger.info('   ✅ GeneratedLetter model created successfully')
logger.info(f'   📊 Fields: {list(test_generated_letter.model_fields.keys())}')

        # Test Enhanced Video Insight with Criminal Analysis
logger.info('   📋 Testing Enhanced Video Insight with Criminal Analysis...')

        test_time_range = TimeRange(
            start_time="00:45", end_time="01:30", confidence=0.85
        )

        test_evidence_item = CriminalEvidenceItem(
            category=CriminalEvidenceCategory.FIELD_SOBRIETY_TESTS,
            time_range=test_time_range,
            description="Officer conducts standardized field sobriety tests",
            key_observations=[
                "Subject sways during one-leg stand",
                "Officer provides clear instructions",
            ],
            legal_significance="Field sobriety test results may be challenged based on administration",
            constitutional_issues=["No Miranda warnings given during testing"],
            evidence_strength="moderate",
        )

        test_criminal_analysis = CriminalVideoAnalysis(
            evidence_items=[test_evidence_item],
            timeline_summary="Traffic stop initiated at 00:15, field sobriety tests conducted 00:45-01:30",
            constitutional_compliance_overview="Potential 4th Amendment issues identified during search",
            missing_categories=[
                CriminalEvidenceCategory.MIRANDA_WARNINGS_CUSTODIAL_INTERROGATION
            ],
        )

        test_enhanced_video = EnhancedVideoInsight(
            file_name="test_video.mov",
            insights={"analysis": "test analysis"},
            transcript="Test transcript content",
            labels=["traffic stop", "police"],
            objects=["police car", "suspect vehicle"],
            text_annotations=["POLICE", "LICENSE PLATE"],
            duration=120.5,
            confidence=0.9,
            is_criminal_case=True,
            criminal_analysis=test_criminal_analysis,
        )
logger.info('   ✅ Enhanced Video Insight with Criminal Analysis created successfully')
            "   ✅ Enhanced Video Insight with Criminal Analysis created successfully"
        )

        # Test CaseAnalysisResult with all components
logger.info('   📋 Testing CaseAnalysisResult integration...')

        test_intake = EnhancedIntakeAnalysis(
            client_name="Test Client",
            attorney_name="Test Attorney",
            case_summary="Test case summary",
            case_type="Criminal Defense",
            urgency_level="High",
        )

        test_analysis = CaseAnalysisResult(
            intake_analysis=test_intake, video_insights=[test_enhanced_video]
        )
logger.info('   ✅ CaseAnalysisResult with video insights created successfully')

logger.info('   🎉 Data model compatibility test PASSED')
        return True, test_generated_letter, test_analysis

    except Exception as e:
logger.error(f'   ❌ Data model compatibility test FAILED: {e}')
        import traceback

        traceback.print_exc()
        return False, None, None


def test_template_rendering(generated_letter, analysis):
    """Test 3: Template Rendering with Real Data"""
logger.info('\n🔍 TEST 3: Template Rendering with Real Data')

    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        # Set up Jinja2 environment
        project_root = os.getcwd()
        template_dir = os.path.join(project_root, "backend", "assets", "templates")
        jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Prepare template context
        template_context = {
            "analysis": analysis,
            "generated_letter": generated_letter,
            "current_date": datetime.now().strftime("%B %d, %Y"),
        }

        # Test main template rendering
logger.info('   🎨 Testing main template rendering...')
        main_template = jinja_env.get_template("findings_email.jinja2")

        try:
            main_html = main_template.render(
                results=template_context, current_date=template_context["current_date"]
            )
logger.info(f'   ✅ Main template rendered successfully ({len(main_html)} characters)')
                f"   ✅ Main template rendered successfully ({len(main_html)} characters)"
            )

            # Check for key sections in rendered output
            expected_sections = [
                "1. Background Summary",
                "2. Key Legal Concerns",
                "3. Strengths of Your Case",
                "4. Potential Challenges",
                "5. Recommendations",
                "6. Next Steps",
            ]

            missing_sections = []
            for section in expected_sections:
                if section not in main_html:
                    missing_sections.append(section)

            if missing_sections:
logger.info(f'   ⚠️  Missing sections in rendered output: {missing_sections}')
            else:
logger.info('   ✅ All expected sections found in rendered output')

        except Exception as e:
logger.error(f'   ❌ Main template rendering failed: {e}')
            return False

        # Test appendix template rendering
logger.info('   🎨 Testing appendix template rendering...')
        appendix_template = jinja_env.get_template("document_appendix.jinja2")

        try:
            appendix_html = appendix_template.render(
                results=template_context, current_date=template_context["current_date"]
            )
logger.info(f'   ✅ Appendix template rendered successfully ({len(appendix_html)} characters)')
                f"   ✅ Appendix template rendered successfully ({len(appendix_html)} characters)"
            )

            # Check for criminal video analysis sections
            if "Criminal Law Evidence Analysis" in appendix_html:
logger.info('   ✅ Criminal video analysis section found')
            else:
logger.info('   ⚠️  Criminal video analysis section not found')

            # Check for enhanced formatting elements
            formatting_elements = [
                "Timestamped Evidence Categories",
                "Timeline Summary",
                "Constitutional Compliance Overview",
            ]

            found_elements = []
            for element in formatting_elements:
                if element in appendix_html:
                    found_elements.append(element)

logger.info(f'   📊 Enhanced formatting elements found: {found_elements}')

        except Exception as e:
logger.error(f'   ❌ Appendix template rendering failed: {e}')
            return False

logger.info('   🎉 Template rendering test PASSED')
        return True

    except Exception as e:
logger.error(f'   ❌ Template rendering test FAILED: {e}')
        import traceback

        traceback.print_exc()
        return False


def test_ai_method_compatibility():
    """Test 4: AI Method Compatibility"""
logger.info('\n🔍 TEST 4: AI Method Compatibility')

    try:
        # Test that all required AI generation methods exist
logger.debug('   🔍 Checking EmailGenerator method signatures...')

        from openai import OpenAI

        from backend_logic.email_generator import EmailGenerator

        # Create a mock EmailGenerator instance
        # Note: This requires a valid OpenAI client, but we're just testing method existence
        try:
            # Use a dummy API key for testing - we won't make actual API calls
            test_client = OpenAI(api_key="dummy-key-for-testing")
            EmailGenerator(test_client)
logger.info('   ✅ EmailGenerator instantiated successfully')
        except Exception as e:
logger.info(f'   ⚠️  Could not instantiate EmailGenerator (expected in test): {e}')

        # Check that all required methods exist
        required_methods = [
            "_generate_legal_concerns",  # New method for "Key Legal Concerns" section
            "_generate_background_summary",
            "_generate_strengths",
            "_generate_challenges",
            "_generate_recommendations",
            "_generate_next_steps",
            "_generate_closing_paragraph",
        ]

        method_check_results = {}
        for method_name in required_methods:
            if hasattr(EmailGenerator, method_name):
                method_check_results[method_name] = "✅ EXISTS"
            else:
                method_check_results[method_name] = "❌ MISSING"

logger.info('   📋 Method existence check:')
        for method, status in method_check_results.items():
logger.info(f'      {method}: {status}')

        missing_methods = [
            method
            for method, status in method_check_results.items()
            if "MISSING" in status
        ]
        if missing_methods:
logger.info(f'   ❌ Missing required methods: {missing_methods}')
            return False
logger.info('   ✅ All required AI generation methods exist')

logger.info('   🎉 AI method compatibility test PASSED')
        return True

    except Exception as e:
logger.error(f'   ❌ AI method compatibility test FAILED: {e}')
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all compatibility tests"""
logger.info('🧪 FINDINGS LETTER TEMPLATE & AI PROMPT COMPATIBILITY TESTS')
logger.info('=' * 70)

    test_results = {}

    # Test 1: Template Loading
    test_results["template_loading"] = test_template_loading()

    # Test 2: Data Model Compatibility
    success, generated_letter, analysis = test_data_model_compatibility()
    test_results["data_model_compatibility"] = success

    # Test 3: Template Rendering (only if previous tests passed)
    if success and generated_letter and analysis:
        test_results["template_rendering"] = test_template_rendering(
            generated_letter, analysis
        )
    else:
        test_results["template_rendering"] = False
logger.error('\n⏭️  Skipping template rendering test due to previous failures')

    # Test 4: AI Method Compatibility
    test_results["ai_method_compatibility"] = test_ai_method_compatibility()

    # Summary
logger.info('\n📊 TEST SUMMARY')
logger.info('=' * 50)

    total_tests = len(test_results)
    passed_tests = sum(1 for result in test_results.values() if result)

    for test_name, result in test_results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
logger.info(f'   {test_name}: {status}')

logger.info(f'\n🎯 OVERALL RESULT: {passed_tests}/{total_tests} tests passed')

    if passed_tests == total_tests:
logger.info('🎉 ALL TESTS PASSED - Template and AI prompt improvements are compatible!')
            "🎉 ALL TESTS PASSED - Template and AI prompt improvements are compatible!"
        )
        return True
logger.error('⚠️  SOME TESTS FAILED - Issues detected that need attention')
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
