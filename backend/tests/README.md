# Comprehensive Test Framework

This framework is designed to provide a reusable, configurable, and extensible testing solution for document analysis pipelines. It is capable of handling multiple legal case types and can be adapted to new domains with minimal effort.

## Table of Contents
1. [Overview](#overview)
2. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Directory Structure](#directory-structure)
3. [Running Tests](#running-tests)
4. [Configuration](#configuration)
   - [Anatomy of a Config File](#anatomy-of-a-config-file)
   - [Validation Rules](#validation-rules)
5. [Adding a New Case](#adding-a-new-case)
6. [Adding a New Law Type](#adding-a-new-law-type)
7. [Troubleshooting](#troubleshooting)

---

## 1. Overview

The test framework is orchestrated by the `TestOrchestrator` class, which manages the entire test lifecycle:
- **Configuration Loading**: Reads test parameters from YAML files.
- **Document Handling**: Discovers, categorizes, and prepares test documents.
- **API Interaction**: Sends requests to the document processing API.
- **Validation**: Performs a series of checks on the API response.
- **Artifact Storage**: Saves all test results, including logs, validation reports, and generated files.

## 2. Getting Started

### Prerequisites
- Python 3.8+
- An active virtual environment.
- Required dependencies installed:
  ```bash
  pip install -r requirements.txt
  pip install PyYAML
  ```

### Directory Structure
For each test case, a dedicated directory should be created (e.g., `backend/tests/test_results/devlin/`). This directory must contain:
- `config.yaml`: The main configuration file for the test case.
- `input/`: A directory containing all documents required for the test.
- `reference/`: A directory containing reference materials for comparison (e.g., a reference email).
- `output/`: This directory is created automatically to store test artifacts.

## 3. Running Tests

To run a test, create a Python script that instantiates and runs the `TestOrchestrator`:

```python
# run_single_test.py
from backend.tests.utils.test_framework import TestOrchestrator

def main():
    # Path to the specific test case configuration
    config_path = "backend/tests/test_results/devlin/config.yaml"

    # Initialize and run the test
    orchestrator = TestOrchestrator(config_path)
    orchestrator.run_test()

if __name__ == "__main__":
    main()
```

## 4. Configuration

The framework is configured using YAML files, which are stored in the `backend/tests/templates/` directory and customized for each test case.

### Anatomy of a Config File

```yaml
client_name: "Erik Devlin"
case_type: "Contractor Dispute"
api_url: "http://127.0.0.1:8000/process_documents"

input_dir: "input"
# ... other file handling properties

validation:
  document_intake:
    enabled: true
  email_comparison:
    enabled: true
    reference_file: "reference_email.rtf"
    min_substance_score: 0.75
```

### Validation Rules
The `validation` section is highly customizable. You can enable or disable checks and set specific thresholds. The framework supports validators for:
- `document_intake`: Checks for correct client name, case type, etc.
- `email_comparison`: Compares the generated email against a reference file.
- `ai_analysis`: Ensures that required analytical sections are present.

## 5. Adding a New Case

1. **Create Directory**: Create a new directory for the case (e.g., `backend/tests/test_results/new_case/`).
2. **Add Documents**: Place all test documents in the `input/` subdirectory.
3. **Add Reference Files**: Place any reference materials in the `reference/` subdirectory.
4. **Create Config**: Create a `config.yaml` file by adapting one of the templates from `backend/tests/templates/`. Update the `client_name`, `case_type`, and any other relevant fields.
5. **Create Runner**: Create a test runner script (see [Running Tests](#running-tests)).

## 6. Adding a New Law Type

1. **Create Template**: Create a new configuration template in `backend/tests/templates/` (e.g., `new_law_type_config.yaml`). Define the validation rules and scoring weights that are appropriate for this law type.
2. **Extend Validator (Optional)**: If the new law type requires custom validation logic, you can extend the `TestOrchestrator` with a new `_validate_...` method.

## 7. Troubleshooting

- **`FileNotFoundError` on config**: Ensure the path to `config.yaml` is correct in your test runner script.
- **`No intake form found`**: Check that your `intake_patterns` in `config.yaml` match the naming of your intake form document.
- **Validation Failures**:
  - **`email_comparison`**: Adjust the scoring thresholds in `config.yaml` or update the reference email if the generated output is expected to change.
  - **`document_intake` / `ai_analysis`**: Check the API response to see if the expected fields are present. The issue may be with the API rather than the test framework.
- **Dependency Issues**: Make sure you have installed both `requirements.txt` and `PyYAML`.
