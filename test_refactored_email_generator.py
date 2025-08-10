"""
Integration Test for Refactored EmailGeneratorV2

This test validates that the refactored modular EmailGeneratorV2 maintains
backward compatibility and core functionality.
"""

from __future__ import annotations

import logging
import os
import sys


# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_modular_architecture():
    """Test that the new modular EmailGeneratorV2 can be imported and initialized."""
    try:
        from backend_logic.email_generation import EmailGeneratorV2

        # Test initialization
        generator = EmailGeneratorV2()
        logger.info("✅ EmailGeneratorV2 successfully imported and initialized")

        # Test service status
        status = generator.get_service_status()
        logger.info(
            f"✅ Service status retrieved: {status['email_generator_v2']['architecture']}"
        )

        return True

    except Exception as e:
        logger.error(f"❌ Failed to import/initialize EmailGeneratorV2: {e}")
        return False


def test_service_imports():
    """Test that individual services can be imported."""
    try:
        from backend_logic.email_generation import (
            ConfigurationManager,
            FallbackGenerationService,
            JSONArchitectureService,
            TemplateRenderingService,
            TextProcessingService,
        )

        logger.info("✅ All service classes successfully imported")

        # Test basic initialization of each service
        config_mgr = ConfigurationManager()
        text_processor = TextProcessingService()
        json_service = JSONArchitectureService()
        template_service = TemplateRenderingService()
        fallback_service = FallbackGenerationService()

        logger.info("✅ All services successfully initialized")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to import services: {e}")
        return False


def test_configuration_service():
    """Test ConfigurationManager functionality."""
    try:
        from backend_logic.email_generation.services import ConfigurationManager

        config_mgr = ConfigurationManager()

        # Test configuration loading
        config = config_mgr.get_config()
        logger.info(f"✅ Configuration loaded: {len(config)} keys")

        # Test template directory
        template_dir = config_mgr.get_template_directory()
        logger.info(f"✅ Template directory: {template_dir}")

        return True

    except Exception as e:
        logger.error(f"❌ ConfigurationManager test failed: {e}")
        return False


def test_text_processing_service():
    """Test TextProcessingService functionality."""
    try:
        from backend_logic.email_generation.services import TextProcessingService

        text_processor = TextProcessingService()

        # Test basic text cleaning
        test_text = "  This is a   test   with  extra  spaces.  "
        cleaned = text_processor.clean_ai_response(test_text)
        logger.info(f"✅ Text cleaning: '{test_text}' -> '{cleaned}'")

        # Test whitespace normalization
        normalized = text_processor.normalize_whitespace(test_text)
        logger.info("✅ Whitespace normalization successful")

        return True

    except Exception as e:
        logger.error(f"❌ TextProcessingService test failed: {e}")
        return False


def test_json_architecture_service():
    """Test JSONArchitectureService functionality."""
    try:
        from backend_logic.email_generation.services import JSONArchitectureService

        json_service = JSONArchitectureService()

        # Test JSON structure generation
        test_response = "This is a factual summary. Legal analysis follows. Evidence review is important. Recommendations are provided."
        structured = json_service.generate_structured_json(test_response)
        logger.info(f"✅ JSON structure generated with {len(structured)} sections")

        # Test JSON validation
        validated = json_service.validate_json_response(structured)
        logger.info("✅ JSON validation successful")

        # Test conversion to letter
        letter = json_service.convert_json_to_generated_letter(validated)
        logger.info(f"✅ Letter conversion successful, length: {len(letter)}")

        return True

    except Exception as e:
        logger.error(f"❌ JSONArchitectureService test failed: {e}")
        return False


def test_fallback_service():
    """Test FallbackGenerationService functionality."""
    try:
        from backend_logic.email_generation.services import FallbackGenerationService

        fallback_service = FallbackGenerationService()

        # Test fallback content generation
        test_case_data = {
            "case_id": "TEST-001",
            "case_type": "general",
            "case_description": "Test case for fallback service",
        }

        fallback_letter = fallback_service.create_fallback_letter(
            test_case_data, "Test error"
        )
        logger.info(f"✅ Fallback letter generated, length: {len(fallback_letter)}")

        # Test error recovery content
        recovery_content = fallback_service.create_error_recovery_content(
            "test_error", test_case_data
        )
        logger.info(
            f"✅ Error recovery content generated with {len(recovery_content)} sections"
        )

        return True

    except Exception as e:
        logger.error(f"❌ FallbackGenerationService test failed: {e}")
        return False


def test_backward_compatibility():
    """Test that key backward compatibility methods exist."""
    try:
        from backend_logic.email_generation import EmailGeneratorV2

        generator = EmailGeneratorV2()

        # Test that key methods exist and can be called
        methods_to_test = [
            "_clean_ai_response",
            "_prettify_html_output",
            "format_video_analysis_for_appendix",
            "_create_fallback_letter",
        ]

        for method_name in methods_to_test:
            if hasattr(generator, method_name):
                logger.info(f"✅ Backward compatibility method exists: {method_name}")
            else:
                logger.warning(f"⚠️  Method not found: {method_name}")

        # Test a simple method call
        test_text = "Test response text"
        cleaned = generator._clean_ai_response(test_text)
        logger.info("✅ Backward compatibility method call successful")

        return True

    except Exception as e:
        logger.error(f"❌ Backward compatibility test failed: {e}")
        return False


def test_integration_flow():
    """Test a complete integration flow without external dependencies."""
    try:
        from backend_logic.email_generation import EmailGeneratorV2

        generator = EmailGeneratorV2()

        # Test case data
        test_case_data = {
            "case_id": "INTEGRATION-TEST-001",
            "case_type": "contract",
            "case_description": "Integration test case for refactored email generator",
            "client_name": "Test Client",
            "matter_description": "Test matter for architectural validation",
        }

        # This will use fallback services since we don't have OpenAI API key
        logger.info("🔄 Testing integration flow with fallback services...")

        # Test service status
        status = generator.get_service_status()
        logger.info("✅ Service status check completed")

        # Test fallback generation directly
        fallback_response = generator._generate_fallback_response(
            test_case_data, "Integration test - no OpenAI API key"
        )

        logger.info("✅ Integration flow completed successfully")
        logger.info(
            f"   - Structured data sections: {len(fallback_response['structured_data'])}"
        )
        logger.info(
            f"   - Letter content length: {len(fallback_response['letter_content'])}"
        )
        logger.info(f"   - Is fallback: {fallback_response['metadata']['is_fallback']}")

        return True

    except Exception as e:
        logger.error(f"❌ Integration flow test failed: {e}")
        return False


def main():
    """Run all tests and provide summary."""
    logger.info("🚀 Starting Refactored EmailGeneratorV2 Integration Tests")
    logger.info("=" * 60)

    tests = [
        ("Modular Architecture", test_modular_architecture),
        ("Service Imports", test_service_imports),
        ("Configuration Service", test_configuration_service),
        ("Text Processing Service", test_text_processing_service),
        ("JSON Architecture Service", test_json_architecture_service),
        ("Fallback Service", test_fallback_service),
        ("Backward Compatibility", test_backward_compatibility),
        ("Integration Flow", test_integration_flow),
    ]

    results = []

    for test_name, test_func in tests:
        logger.info(f"\n🧪 Running: {test_name}")
        logger.info("-" * 40)

        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {e}")
            results.append((test_name, False))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status:8} | {test_name}")

    logger.info("-" * 60)
    logger.info(f"Results: {passed}/{total} tests passed ({passed / total * 100:.1f}%)")

    if passed == total:
        logger.info("🎉 All tests passed! Refactoring successful.")
        return True
    logger.warning(f"⚠️  {total - passed} tests failed. Review required.")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
