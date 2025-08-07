# Pytest Testing Architecture

## 1. Overview

This document outlines the testing architecture for the Legal Document Analysis Portal. The goal is to establish a robust, scalable, and maintainable testing framework using Pytest. This framework will ensure the reliability and quality of the application as it evolves.

The architecture is designed around the current unified Streamlit-Python application, with a clear separation of concerns for different types of tests.

## 2. Directory Structure

A well-organized directory structure is essential for maintainability. We will structure our tests by type (unit, integration, end-to-end) and then by feature or component.

```
backend/tests/
│
├── e2e/
│   ├── test_document_processing_workflow.py
│   └── test_video_analysis_workflow.py
│
├── integration/
│   ├── test_ai_analyzer_integration.py
│   ├── test_email_generator_integration.py
│   └── test_video_processor_gcp.py
│
├── unit/
│   ├── test_ai_analyzer_unit.py
│   ├── test_email_generator_unit.py
│   └── test_document_processor_unit.py
│
├── test_data/
│   ├── documents/
│   │   ├── intake_form.pdf
│   │   └── case_file.docx
│   ├── reference_outputs/
│   │   ├── expected_findings.eml
│   │   └── expected_analysis.txt
│   └── media/
│       └── sample_video.mov
│
├── conftest.py
└── pytest.ini
```

- **`unit/`**: Contains unit tests that test individual functions or classes in isolation. All external dependencies (like AI services, databases, or APIs) will be mocked.
- **`integration/`**: Contains integration tests that verify the interaction between different components of the application. These tests may involve limited, targeted mocking of external services.
- **`e2e/`**: Contains end-to-end tests that simulate a full user workflow, from uploading documents to generating and verifying the final output. These tests should be as close to the real user experience as possible.
- **`test_data/`**: A centralized location for all test-related data, including sample documents, media files, and reference outputs for comparison.

## 3. Configuration

### `pytest.ini`

The `pytest.ini` file will be the central place for configuring Pytest's behavior.

```ini
[pytest]
minversion = 6.0
addopts = -ra -q
testpaths =
    backend/tests/unit
    backend/tests/integration
    backend/tests/e2e
markers =
    unit: Lighweight unit tests
    integration: Tests for component integration
    e2e: Full end-to-end workflow tests
```

- **`testpaths`**: Explicitly defines the directories Pytest should search for tests.
- **`markers`**: Allows us to categorize tests (e.g., `@pytest.mark.e2e`) and run specific categories, which is useful for CI/CD pipelines.

### `conftest.py`

The root `conftest.py` file (`backend/tests/conftest.py`) is ideal for defining fixtures and hooks that are shared across all test files.

- **Shared Fixtures**: Fixtures that provide access to mock services (e.g., a mock OpenAI client) or test data loaders will be defined here.
- **Hooks**: Pytest hooks, if needed, can be implemented here to modify the test collection or execution process.

## 4. Fixtures Strategy

Fixtures are a cornerstone of a good Pytest setup. Our strategy will focus on creating clean, isolated, and reusable test setups.

- **Data Fixtures**: Fixtures will provide test functions with necessary data, like paths to test documents or loaded Pydantic models.
- **Service Fixtures**: We will create fixtures that provide mock instances of external services (e.g., `mock_openai_client`, `mock_gcp_vision_client`). This allows us to control the behavior of these services during tests.
- **State Management**: For tests requiring a populated `st.session_state`, we will use fixtures to set up the session state before the test runs and clean it up afterward.
- **`tmp_path`**: We will heavily utilize Pytest's built-in `tmp_path` fixture for any tests that need to write and read from the filesystem, ensuring no artifacts are left after a test run.

Example fixture in `conftest.py`:
```python
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_openai_client():
    """Provides a mock of the OpenAI client."""
    client = MagicMock()
    # Configure mock responses here
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Mocked AI response."))]
    )
    return client
```

## 5. Mocking and Patching

Mocking is crucial for isolating components and ensuring that our tests are fast and reliable.

- **When to Mock**:
    - **Unit Tests**: All external dependencies (APIs, file system, databases) **must** be mocked.
    - **Integration Tests**: Mocking should be minimal. We might mock a high-level service call (e.g., the final call to an LLM) while testing the interaction of the components leading up to it.
    - **E2E Tests**: Mocking should be avoided as much as possible to ensure the test accurately reflects the real system. However, costly or non-deterministic external services (like LLM providers) can be mocked.
- **How to Mock**: We will use `unittest.mock.patch` (or the `pytest-mock` plugin's `mocker` fixture) to replace objects at runtime. Patching should be as targeted as possible.

```python
# Example of mocking in a unit test
def test_generate_email_content(mocker):
    # Mock the AI call
    mocker.patch(
        'backend.ai_analyzer.call_openai_api',
        return_value="Mocked AI summary."
    )
    # ... rest of the test logic
```

## 6. End-to-End Testing Strategy

Our E2E tests will validate the complete workflow of the application.

- **Simulating Workflows**: Tests will programmatically call the main functions of the Streamlit application to simulate a user uploading files and generating a report.
- **Test Data Management**: Each E2E test case will have its own subdirectory within `backend/tests/e2e/test_scenarios/`, containing the input documents and the reference (expected) output files.
- **Output Comparison**: The core of our E2E strategy is to compare the generated output against a "golden" reference version.
    - For `.txt` and other text-based files, a direct or semantic comparison can be used.
    - For `.eml` files, we can parse the email content and headers to perform assertions.
    - For complex documents, we can use a semantic comparison utility to check for similarity rather than exact matches, making the tests more resilient to minor, acceptable variations in AI-generated content. A utility function `assert_email_similarity` can be created for this.