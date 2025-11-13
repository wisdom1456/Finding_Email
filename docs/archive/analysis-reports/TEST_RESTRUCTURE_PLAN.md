# Test Restructure Plan with Unified Tests/ Hierarchy

## Overview

This document provides a comprehensive plan for restructuring the test suite to align with the unified `src/legal_portal/` package structure. This plan builds on the concrete refactor plan but focuses specifically on test organization, categorization, and migration strategy.

## Current Test Landscape Analysis

### 1.1 Existing Test Structure

```
tests/
├── __init__.py
├── main_test.py                     # Unit test for main function
├── test_appendix_fix.py            # Integration test for template rendering
├── test_citation_enhancement.py    # Integration test for citation system
├── test_critical_fixes.py          # Integration test for critical fixes
├── test_new_architecture.py        # Unit test for app architecture
├── e2e/                           # Empty directory
├── integration/                   # Empty directory
└── unit/                          # Empty directory
```

### 1.2 Legacy Test Directories (To Be Consolidated)

Based on duplication analysis, these test directories contain duplicated or legacy tests:

```
backend/tests/                     # Legacy backend tests
backend_backup/tests/              # Complete backup copy
backend_logic_backup/tests/        # Backup copy
utils/tests/                       # Utility-specific tests
```

### 1.3 Test Classification

| Test File | Current Type | Target Category | New Location | Rationale |
|-----------|-------------|-----------------|---------------|-----------|
| `main_test.py` | Unit | Unit | `tests/unit/app/` | Tests single function |
| `test_new_architecture.py` | Unit | Unit | `tests/unit/app/` | Tests app components |
| `test_citation_enhancement.py` | Integration | Integration | `tests/integration/` | Tests service interaction |
| `test_appendix_fix.py` | Integration | Integration | `tests/integration/` | Tests template rendering |
| `test_critical_fixes.py` | Integration | Integration | `tests/integration/` | Tests system fixes |

## 2. Target Test Structure Design

### 2.1 Unified Test Hierarchy

```
tests/
├── __init__.py                    # Test package initialization
├── conftest.py                   # Shared pytest configuration
├── pytest.ini                   # Pytest settings (updated)
├── requirements.txt              # Test-specific dependencies
│
├── unit/                         # Unit tests (individual components)
│   ├── __init__.py
│   ├── app/                      # App-level unit tests
│   │   ├── __init__.py
│   │   ├── test_main.py          # Main function tests
│   │   └── test_components.py    # UI component tests
│   ├── core/                     # Core module unit tests
│   │   ├── __init__.py
│   │   ├── test_ai_analyzer.py
│   │   ├── test_document_processor.py
│   │   ├── test_email_generator.py
│   │   ├── test_main_processor.py
│   │   └── test_video_processor.py
│   ├── services/                 # Service unit tests
│   │   ├── __init__.py
│   │   ├── test_content_extraction.py
│   │   ├── test_content_generation.py
│   │   └── test_citation_tracking.py
│   ├── utils/                    # Utility unit tests
│   │   ├── __init__.py
│   │   ├── test_cache_manager.py
│   │   ├── test_pii_sanitizer.py
│   │   ├── test_security.py
│   │   └── test_validators.py
│   └── config/                   # Configuration unit tests
│       ├── __init__.py
│       └── test_settings.py
│
├── integration/                  # Integration tests (service interactions)
│   ├── __init__.py
│   ├── test_citation_enhancement.py    # Citation system integration
│   ├── test_template_rendering.py      # Template rendering integration
│   ├── test_document_workflow.py       # Document processing workflow
│   ├── test_email_generation.py        # Email generation workflow
│   ├── test_critical_fixes.py          # System fix validation
│   └── test_cost_tracking.py           # Cost tracking integration
│
├── e2e/                          # End-to-end tests (full workflows)
│   ├── __init__.py
│   ├── test_complete_workflow.py       # Full document analysis workflow
│   ├── test_streamlit_app.py           # Streamlit app end-to-end
│   └── test_findings_generation.py     # Complete findings letter generation
│
├── fixtures/                     # Test data and fixtures
│   ├── __init__.py
│   ├── sample_documents/         # Sample test documents
│   │   ├── test_contract.pdf
│   │   ├── test_email.pdf
│   │   └── test_intake.pdf
│   ├── mock_responses/           # Mock API responses
│   │   ├── openai_responses.json
│   │   └── vertex_responses.json
│   ├── test_configs/             # Test configuration files
│   │   ├── test_settings.yaml
│   │   └── test_prompts.yaml
│   └── expected_outputs/         # Expected test outputs
│       ├── sample_findings.html
│       └── sample_citations.json
│
└── performance/                  # Performance and benchmark tests
    ├── __init__.py
    ├── test_document_processing_speed.py
    ├── test_memory_usage.py
    └── benchmarks/
        └── processing_benchmarks.py
```

## 3. Test Migration Strategy

### 3.1 Phase 1: Prepare New Structure

```bash
# Create new test directory structure
mkdir -p tests/{unit,integration,e2e,fixtures,performance}
mkdir -p tests/unit/{app,core,services,utils,config}
mkdir -p tests/fixtures/{sample_documents,mock_responses,test_configs,expected_outputs}
mkdir -p tests/performance/benchmarks

# Create __init__.py files
find tests -type d -exec touch {}/__init__.py \;
```

### 3.2 Phase 2: Migrate Existing Tests

```bash
# Move and rename existing tests
git mv tests/main_test.py tests/unit/app/test_main.py
git mv tests/test_new_architecture.py tests/unit/app/test_components.py
git mv tests/test_citation_enhancement.py tests/integration/
git mv tests/test_appendix_fix.py tests/integration/test_template_rendering.py
git mv tests/test_critical_fixes.py tests/integration/

# Clean up root-level test files (after migration)
# Remove any remaining test files at root level after verification
```

### 3.3 Phase 3: Update Import Paths in Tests

All test files need updated import paths to match the new `src/legal_portal/` structure:

```python
# OLD imports (to be updated)
from core.main_processor import process_case_documents
from core.citation_tracking_service import CitationTrackingService
from config.default import get_settings

# NEW imports (after refactor)
from legal_portal.core.main_processor import process_case_documents
from legal_portal.core.citation_tracking_service import CitationTrackingService
from legal_portal.config.settings import get_settings
```

### 3.4 Phase 4: Create Missing Test Files

Based on the codebase analysis, create unit tests for core modules:

```bash
# Core module tests
touch tests/unit/core/test_ai_analyzer.py
touch tests/unit/core/test_document_processor.py
touch tests/unit/core/test_email_generator.py
touch tests/unit/core/test_main_processor.py
touch tests/unit/core/test_video_processor.py

# Service tests
touch tests/unit/services/test_content_extraction.py
touch tests/unit/services/test_content_generation.py
touch tests/unit/services/test_citation_tracking.py

# Utility tests
touch tests/unit/utils/test_cache_manager.py
touch tests/unit/utils/test_pii_sanitizer.py
touch tests/unit/utils/test_security.py
touch tests/unit/utils/test_validators.py

# Configuration tests
touch tests/unit/config/test_settings.py

# E2E tests
touch tests/e2e/test_complete_workflow.py
touch tests/e2e/test_streamlit_app.py
touch tests/e2e/test_findings_generation.py
```

## 4. Test Configuration Updates

### 4.1 Enhanced pytest.ini

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
pythonpath = src
addopts = 
    --verbose
    --tb=short
    --strict-markers
    --disable-warnings
    --durations=10
    --cov=legal_portal
    --cov-report=html:coverage_html
    --cov-report=term-missing
    --cov-fail-under=70
markers =
    unit: Unit tests for individual components
    integration: Integration tests for service interactions
    e2e: End-to-end tests for complete workflows
    slow: Tests that take longer than 1 second
    external: Tests that require external services
    smoke: Quick smoke tests for basic functionality
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

### 4.2 conftest.py for Shared Fixtures

```python
"""
Shared pytest fixtures and configuration
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing"""
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content="Mock response"))]
    )
    return mock_client

@pytest.fixture
def sample_case_analysis():
    """Sample case analysis data for testing"""
    return {
        "client_name": "John Doe",
        "case_type": "Contract Dispute",
        "analyzed_documents": [],
        "case_timeline": []
    }

@pytest.fixture
def test_settings():
    """Test configuration settings"""
    from legal_portal.config.settings import Settings
    return Settings(
        openai_api_key="test-key",
        environment="test",
        log_level="DEBUG"
    )

@pytest.fixture(scope="session")
def test_data_dir():
    """Path to test data directory"""
    return Path(__file__).parent / "fixtures"
```

### 4.3 Test Dependencies (requirements.txt)

```txt
# Core testing framework
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
pytest-asyncio>=0.21.0

# Test utilities
factory-boy>=3.3.0
faker>=19.0.0
responses>=0.23.0

# Performance testing
pytest-benchmark>=4.0.0
memory-profiler>=0.61.0

# Coverage and reporting
coverage>=7.3.0
pytest-html>=3.2.0
```

## 5. Test Categories and Guidelines

### 5.1 Unit Test Guidelines

**Purpose**: Test individual functions/classes in isolation
**Characteristics**:
- Fast execution (< 100ms per test)
- No external dependencies
- Extensive mocking of dependencies
- High code coverage target (>90%)

**Example Structure**:
```python
def test_email_generator_creates_valid_email():
    """Test that email generator creates properly formatted email"""
    # Arrange
    generator = EmailGenerator(mock_settings)
    case_data = create_mock_case_data()
    
    # Act
    result = generator.generate_findings_email(case_data)
    
    # Assert
    assert result.subject is not None
    assert "findings" in result.body.lower()
    assert result.recipient == case_data.client_email
```

### 5.2 Integration Test Guidelines

**Purpose**: Test interactions between services/modules
**Characteristics**:
- Moderate execution time (< 5s per test)
- May use real configurations
- Tests service boundaries
- Validates data flow between components

**Example Structure**:
```python
def test_citation_tracking_integration():
    """Test complete citation tracking workflow"""
    # Arrange
    citation_service = CitationTrackingService()
    document_processor = DocumentProcessor()
    
    # Act
    processed_doc = document_processor.process(sample_document)
    citations = citation_service.extract_citations(processed_doc)
    
    # Assert
    assert len(citations) > 0
    assert all(c.source_document for c in citations)
```

### 5.3 E2E Test Guidelines

**Purpose**: Test complete user workflows
**Characteristics**:
- Slower execution (< 30s per test)
- May use external services (with caution)
- Tests full application stack
- Validates user scenarios

**Example Structure**:
```python
def test_complete_findings_workflow():
    """Test complete findings letter generation workflow"""
    # Arrange
    test_files = get_test_document_files()
    
    # Act
    result = process_case_documents(test_files)
    
    # Assert
    assert result.success
    assert result.findings_letter is not None
    assert result.appendix is not None
    assert len(result.citations) > 0
```

## 6. Legacy Test Consolidation

### 6.1 Test Duplication Resolution

Based on the duplication analysis, consolidate duplicate tests:

```bash
# Remove duplicate test files from legacy directories
git rm -rf backend/tests/
git rm -rf backend_backup/tests/
git rm -rf backend_logic_backup/tests/

# Merge unique tests from utils/tests/ if any exist
if [ -d "utils/tests" ]; then
    find utils/tests -name "test_*.py" -exec git mv {} tests/unit/utils/ \;
    git rm -rf utils/tests/
fi
```

### 6.2 Test Data Consolidation

```bash
# Consolidate test data from legacy directories
mkdir -p tests/fixtures/legacy_data

# Move any unique test data from legacy locations
find backend*/tests -name "*.json" -o -name "*.yaml" -o -name "*.txt" | \
    xargs -I {} git mv {} tests/fixtures/legacy_data/ 2>/dev/null || true
```

## 7. Test Execution Strategy

### 7.1 Test Running Commands

```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit           # Unit tests only
pytest -m integration    # Integration tests only
pytest -m e2e            # E2E tests only
pytest -m "not slow"     # Skip slow tests

# Run tests with coverage
pytest --cov=legal_portal --cov-report=html

# Run performance tests
pytest tests/performance/ --benchmark-only
```

### 7.2 CI/CD Integration

```yaml
# GitHub Actions test matrix
test_matrix:
  test_type:
    - unit
    - integration
    - e2e
  python_version:
    - "3.11"
    - "3.12"

steps:
  - name: Run Unit Tests
    run: pytest -m unit --cov=legal_portal
  
  - name: Run Integration Tests
    run: pytest -m integration
  
  - name: Run E2E Tests (on main branch only)
    if: github.ref == 'refs/heads/main'
    run: pytest -m e2e
```

## 8. Validation Procedures

### 8.1 Pre-Migration Validation

```bash
# Count existing tests
echo "Current test count:"
find tests -name "test_*.py" | wc -l

# Run existing tests to establish baseline
pytest tests/ --tb=no -q
```

### 8.2 Post-Migration Validation

```bash
# Verify all tests are discovered
pytest --collect-only | grep "test session starts"

# Verify no import errors
pytest --tb=no -q

# Verify test categorization
pytest -m unit --collect-only
pytest -m integration --collect-only
pytest -m e2e --collect-only

# Run smoke tests
pytest -m smoke --tb=no
```

### 8.3 Test Coverage Validation

```bash
# Generate coverage report
pytest --cov=legal_portal --cov-report=term-missing

# Verify minimum coverage thresholds
pytest --cov=legal_portal --cov-fail-under=70
```

## 9. Rollback Procedures

If test migration causes issues:

```bash
# Rollback to pre-migration state
git checkout HEAD~1 -- tests/

# Or restore from backup tag
git checkout backup-pre-refactor-v2 -- tests/
```

## 10. Success Criteria

### 10.1 Structural Success Criteria

- [ ] All tests organized into unit/integration/e2e categories
- [ ] No duplicate test files across directories
- [ ] All tests use updated import paths (legal_portal.*)
- [ ] Test discovery works for all categories
- [ ] No legacy test directories remain

### 10.2 Functional Success Criteria

- [ ] All existing tests pass after migration
- [ ] Test coverage maintained or improved (>70%)
- [ ] Test execution time reasonable (<5min for full suite)
- [ ] CI/CD pipeline updated for new structure
- [ ] Documentation updated with new test organization

### 10.3 Quality Success Criteria

- [ ] Clear test categorization and naming
- [ ] Comprehensive conftest.py with useful fixtures
- [ ] Test data properly organized in fixtures/
- [ ] Performance tests identified and isolated
- [ ] Proper test markers applied consistently

## 11. Future Test Development Guidelines

### 11.1 Test Creation Standards

When adding new tests:

1. **Determine Category**: Unit/Integration/E2E based on scope
2. **Follow Naming**: `test_[module]_[function]_[scenario].py`
3. **Use Fixtures**: Leverage shared fixtures from conftest.py
4. **Add Markers**: Apply appropriate pytest markers
5. **Update Coverage**: Ensure new code has test coverage

### 11.2 Test Maintenance Standards

1. **Regular Review**: Monthly review of test structure
2. **Performance Monitoring**: Track test execution times
3. **Coverage Monitoring**: Maintain coverage above 70%
4. **Fixture Updates**: Keep shared fixtures current
5. **Documentation**: Update test documentation with changes

This test restructure plan provides a comprehensive migration strategy that aligns with the unified package structure while establishing clear testing standards and procedures for future development.