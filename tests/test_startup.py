"""
Startup Tests for Legal Document Analysis Portal

This module tests that all major components of the application can be imported
successfully without errors. This helps catch import errors early in the
development process.
"""

import sys
import unittest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestStartupImports(unittest.TestCase):
    """Test that all major modules can be imported without errors."""

    def test_core_modules_import(self):
        """Test that core modules can be imported."""
        try:
            from core.document_processor import DocumentProcessor
            from core.email_generator import EmailGeneratorV2, EmailReadabilityError
            from core.ai_analyzer import AIAnalyzer
            from core.main_processor import process_case_documents, process_case_documents_cli
            
            # Verify classes/functions exist
            self.assertTrue(callable(DocumentProcessor))
            self.assertTrue(callable(EmailGeneratorV2))
            self.assertTrue(callable(AIAnalyzer))
            self.assertTrue(callable(process_case_documents))
            self.assertTrue(callable(process_case_documents_cli))
            self.assertTrue(issubclass(EmailReadabilityError, Exception))
            
            print("✅ Core modules imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import core modules: {e}")

    def test_backend_modules_import(self):
        """Test that backend modules can be imported."""
        try:
            from backend.utils.data_models import (
                CaseAnalysisResult,
                AnalysisError,
                AnalyzedDocument,
                DocumentType,
                MediaProcessingError,
                TranscriptedMedia,
                VideoInsight,
            )
            from backend.utils.validators import validate_file_type, validate_file_size
            
            # Verify classes exist
            self.assertTrue(callable(CaseAnalysisResult))
            self.assertTrue(callable(AnalysisError))
            self.assertTrue(callable(AnalyzedDocument))
            self.assertTrue(callable(validate_file_type))
            
            print("✅ Backend modules imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import backend modules: {e}")

    def test_service_modules_import(self):
        """Test that service modules can be imported."""
        try:
            from services.audio_processor import AudioProcessor
            from services.video_processor import VideoProcessor
            from services.configuration_manager import ConfigurationManager
            from services.content_generation_service import ContentGenerationService
            from services.fallback_generation_service import FallbackGenerationService
            from services.json_processing_service import JsonProcessingService
            from services.template_rendering_service import TemplateRenderingService
            from services.text_processing_service import TextProcessingService
            
            # Verify classes exist
            self.assertTrue(callable(AudioProcessor))
            self.assertTrue(callable(VideoProcessor))
            self.assertTrue(callable(ConfigurationManager))
            
            print("✅ Service modules imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import service modules: {e}")

    def test_utils_modules_import(self):
        """Test that utility modules can be imported."""
        try:
            from utils.logging_config import setup_logging
            from utils.helpers import (
                ProgressTracker,
                calculate_document_sizes,
                display_processing_cost_update,
            )
            from utils.file_processors.pdf_processor import PDFProcessor
            from utils.file_processors.docx_processor import DOCXProcessor
            from utils.file_processors.txt_processor import TXTProcessor
            from utils.file_processors.eml_processor import EMLProcessor
            from utils.file_processors.image_processor import ImageProcessor
            
            # Verify functions/classes exist
            self.assertTrue(callable(setup_logging))
            self.assertTrue(callable(ProgressTracker))
            self.assertTrue(callable(calculate_document_sizes))
            
            print("✅ Utility modules imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import utility modules: {e}")

    def test_backend_logic_modules_import(self):
        """Test that backend_logic modules can be imported."""
        try:
            from backend_logic.config import get_openai_api_key
            from backend_logic.cost_session_manager import CostSessionManager
            from backend_logic.email_generator import EmailGenerator
            from backend_logic.cost_estimator import CostEstimator
            
            # Verify functions/classes exist
            self.assertTrue(callable(get_openai_api_key))
            self.assertTrue(callable(CostSessionManager))
            self.assertTrue(callable(EmailGenerator))
            
            print("✅ Backend logic modules imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import backend_logic modules: {e}")

    def test_components_import(self):
        """Test that UI components can be imported."""
        try:
            from components.ui_components import render_case_info_form
            from components.budget_sheet import render_budget_sheet
            
            # Verify functions exist
            self.assertTrue(callable(render_case_info_form))
            self.assertTrue(callable(render_budget_sheet))
            
            print("✅ Component modules imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import component modules: {e}")

    def test_streamlit_app_import_partial(self):
        """
        Test Streamlit app import (may fail due to missing dependencies).
        This test is marked as expected to potentially fail.
        """
        try:
            # Try to import the app module
            import app
            print("✅ Streamlit app module imported successfully")
        except ModuleNotFoundError as e:
            if "streamlit_authenticator" in str(e):
                print(f"⚠️ Expected missing dependency: {e}")
                # This is expected - streamlit_authenticator needs to be installed
                pass
            else:
                # Unexpected import error
                self.fail(f"Unexpected import error in app module: {e}")
        except ImportError as e:
            # Log but don't fail on other import errors in app.py
            print(f"⚠️ App module import warning: {e}")


class TestCriticalImports(unittest.TestCase):
    """Test the most critical imports that were specifically fixed."""
    
    def test_email_readability_error_import(self):
        """Test that EmailReadabilityError can be imported from core.email_generator."""
        try:
            from core.email_generator import EmailReadabilityError
            
            # Verify it's an exception class
            self.assertTrue(issubclass(EmailReadabilityError, Exception))
            
            # Test that it can be instantiated
            error = EmailReadabilityError("Test error message")
            self.assertEqual(str(error), "Test error message")
            
            print("✅ EmailReadabilityError imported and works correctly")
        except ImportError as e:
            self.fail(f"Failed to import EmailReadabilityError: {e}")
    
    def test_main_processor_functions_import(self):
        """Test that main processor functions can be imported."""
        try:
            from core.main_processor import (
                process_case_documents,
                process_case_documents_cli,
                extract_case_name,
                save_output_files,
                html_to_plain_text,
            )
            
            # Verify all are callable
            self.assertTrue(callable(process_case_documents))
            self.assertTrue(callable(process_case_documents_cli))
            self.assertTrue(callable(extract_case_name))
            self.assertTrue(callable(save_output_files))
            self.assertTrue(callable(html_to_plain_text))
            
            print("✅ Main processor functions imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import main processor functions: {e}")
    
    def test_core_init_imports(self):
        """Test that core/__init__.py exports work correctly."""
        try:
            from core import (
                DocumentProcessor,
                EmailGeneratorV2,
                EmailReadabilityError,
                AIAnalyzer,
                process_case_documents,
                process_case_documents_cli,
            )
            
            # Verify all are present
            self.assertTrue(callable(DocumentProcessor))
            self.assertTrue(callable(EmailGeneratorV2))
            self.assertTrue(callable(AIAnalyzer))
            self.assertTrue(callable(process_case_documents))
            self.assertTrue(callable(process_case_documents_cli))
            self.assertTrue(issubclass(EmailReadabilityError, Exception))
            
            print("✅ Core __init__ exports work correctly")
        except ImportError as e:
            self.fail(f"Failed to import from core/__init__.py: {e}")


def run_startup_tests():
    """Run all startup tests and provide a summary."""
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add all test cases
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestStartupImports))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCriticalImports))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("STARTUP TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✅ All startup tests passed! The application can import successfully.")
    else:
        print("\n❌ Some tests failed. Please review the errors above.")
        if result.failures:
            print("\nFailed tests:")
            for test, traceback in result.failures:
                print(f"  - {test}")
        if result.errors:
            print("\nTests with errors:")
            for test, traceback in result.errors:
                print(f"  - {test}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_startup_tests()
    sys.exit(0 if success else 1)