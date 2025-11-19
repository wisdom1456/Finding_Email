# Legal Portal Test Suite

This test suite "freezes" the current behavior of the Legal Document Analysis Portal before refactoring to FastAPI/Svelte. All tests use mocks for external dependencies to ensure fast, deterministic execution.

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and mocks
├── integration/
│   └── test_workflows.py         # End-to-end workflow tests (7 tests)
└── unit/
    ├── test_cost_calculator.py    # Cost calculation tests (4 tests)
    ├── test_statute_validation.py # Statute validation tests (5 tests)
    ├── test_corpus_coverage.py    # Corpus coverage tests (5 tests)
    └── test_document_processor.py # Document processing tests (5 tests)
```

**Total: ~26 tests across 5 test modules**

## Running Tests

Run all tests:
```bash
pytest tests/
```

Run with verbose output:
```bash
pytest tests/ -v
```

Run specific test file:
```bash
pytest tests/integration/test_workflows.py
```

Run specific test:
```bash
pytest tests/integration/test_workflows.py::test_full_document_processing_workflow
```

## Mock Strategy

All external dependencies are mocked to ensure:
- **No network calls** - OpenAI/Anthropic APIs are never called
- **Deterministic results** - Same output every run
- **Fast execution** - Tests complete in < 30 seconds

### Mocked Components

1. **OpenAI Client** (`mock_openai_client` fixture)
   - Returns deterministic JSON responses based on prompt content
   - Includes realistic token usage data for cost tracking

2. **Florida Legal Corpus** (`mock_corpus_data` fixture)
   - Small corpus with 5 known statutes (501.204, 83.56, 702.01, 558.004, 627.70131)
   - Includes aliases and rules for testing normalization

3. **File Processors** (`mock_file_processors` fixture)
   - Returns fake extracted text for PDF, DOCX, TXT, and image files
   - No actual file I/O operations

4. **Streamlit Context** (`mock_streamlit_context` fixture)
   - Global autouse fixture prevents RuntimeErrors
   - Mocks `st.session_state`, `st.error`, `st.warning`, etc.

## Test Coverage

### Integration Tests (`tests/integration/test_workflows.py`)

1. **`test_full_document_processing_workflow`**
   - Tests complete workflow from intake to findings letter
   - Validates `ProcessingResult` structure and key fields
   - Asserts presence of client name and statute citations

2. **`test_api_contract_serialization`**
   - Freezes the exact JSON shape for future frontend API
   - Validates all required keys and data types
   - Ensures no Pydantic internal fields leak out

3. **`test_workflow_graceful_failure`**
   - Ensures refactors don't break error bubbling
   - Validates that exceptions are caught and returned in `errors` list

4. **`test_letter_generation_contains_required_elements`**
   - Validates generated letter contains client name, attorney name, matter reference
   - Asserts at least one statute citation is present
   - Checks HTML structure

5. **`test_corpus_coverage_warnings_appear_in_result`**
   - Tests that unsupported practice areas generate warnings
   - Validates warnings appear in `ProcessingResult.warnings`

6. **`test_cost_tracking_aggregates_correctly`**
   - Validates cost tracking structure
   - Tests aggregation of service costs

7. **`test_statute_validation_catches_hallucinations`**
   - Tests that fake/nonexistent statutes are caught
   - Validates unverified citations list

### Unit Tests

#### Cost Calculator (`test_cost_calculator.py`)
- Exact cost calculations with deterministic inputs
- Tests for document analysis, audio, and video processing
- Aggregation of multiple service costs

#### Statute Validation (`test_statute_validation.py`)
- Verification of known statutes from corpus
- Detection of fake/nonexistent statutes
- Citation format normalization
- HTML citation extraction

#### Corpus Coverage (`test_corpus_coverage.py`)
- Identification of covered practice areas (landlord-tenant, consumer protection)
- Detection of unsupported areas (federal, criminal)
- Confidence scoring for unknown cases
- Structure validation

#### Document Processor (`test_document_processor.py`)
- Text document processing
- Intake vs case document classification
- Metadata population
- Prompt construction with context integration

## What Each Test "Freezes"

### Workflow Behavior
- Document processing returns `ProcessingResult` with specific structure
- Letter generation includes required elements (client name, citations, sections)
- Errors are handled gracefully and returned in `errors` list
- Warnings appear in `warnings` list for unsupported cases

### API Contract
- `ProcessingResult` serializes to JSON with exact key structure
- Data types are preserved (float for costs, list for errors)
- No internal Pydantic fields exposed

### Business Logic
- Cost calculations use exact pricing rates
- Statute validation correctly identifies verified vs unverified citations
- Corpus coverage correctly flags supported vs unsupported practice areas
- Document classification logic (intake vs case document)

## Dependencies

Required test dependencies (in `requirements-dev.txt`):
- `pytest>=7.4.0`
- `pytest-asyncio>=0.21.0`
- `pytest-mock>=3.12.0`

## Notes

- All tests are designed to run **without network access**
- Tests use **deterministic mocks** - same input always produces same output
- **No real files** are created or modified during test execution
- Tests are **fast** - complete suite runs in < 30 seconds

## Troubleshooting

### Import Errors
If you see import errors, ensure you're running from the project root:
```bash
cd /path/to/Finding_Emails
pytest tests/
```

### Async Test Warnings
If you see async warnings, ensure `pytest-asyncio` is installed and configured:
```bash
pip install pytest-asyncio
```

### Streamlit Context Errors
The `mock_streamlit_context` fixture should prevent these. If you see `RuntimeError: No SessionContext`, check that the fixture is being applied (it's autouse, so it should be automatic).

