"""
Unified Testing Framework for Legal Document Analysis Portal

This testing framework has been migrated from the backend/tests/ HTTP-based tests
to directly import and test the backend_logic modules without HTTP overhead.

Test Structure:
- test_document_processor.py: Tests for document processing logic
- test_ai_analyzer.py: Tests for AI analysis services  
- test_email_generator.py: Tests for email generation
- test_quality_validator.py: Tests for quality validation
- conftest.py: Shared fixtures and configuration
- test_data/: Preserved sample data and test cases
"""