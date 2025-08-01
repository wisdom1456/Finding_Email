# Test Case Migration Guide

This guide provides instructions for migrating existing test cases (Badam, Price, Velasco) to the new reusable test framework.

## Overview
The new framework uses a standardized directory structure and YAML configuration files to manage test cases. Migration involves reorganizing files and creating a `config.yaml` for each case.

## Migration Steps

### 1. Create Case Directory
For each test case, create a dedicated directory in `backend/tests/test_results/`:
- `backend/tests/test_results/badam/`
- `backend/tests/test_results/price/`
- `backend/tests/test_results/velasco/`

### 2. Organize Files
Inside each case directory, create the following subdirectories:
- `input/`: Move all source documents into this folder.
- `reference/`: Place any reference files for comparison here (e.g., `reference_email.rtf`).

### 3. Create `config.yaml`
Create a `config.yaml` file in the root of each case directory. Use the appropriate template from `backend/tests/templates/` as a starting point.

**Example for a Landlord-Tenant Case (e.g., Badam):**
```yaml
# backend/tests/test_results/badam/config.yaml
client_name: "Balaji Badam"
case_type: "Landlord-Tenant"
api_url: "http://127.0.0.1:8000/api/v1/analysis/full-pipeline"

# --- File Handling ---
input_dir: "input"
output_dir: "output"
reference_dir: "reference"
supported_extensions: [".pdf", ".docx", ".txt", ".eml"]
intake_patterns: ["intake"]

# --- Validation Rules ---
validation:
  document_intake:
    enabled: true
  email_comparison:
    enabled: true
    reference_file: "reference_email.rtf"
    min_substance_score: 0.7
```

### 4. Create a Test Runner
Create a test runner script for each migrated case. This script will instantiate and run the `TestOrchestrator`.

**Example for the Badam Case:**
```python
# backend/tests/test_badam_migrated.py
import pytest
from backend.tests.utils.test_framework import TestOrchestrator

@pytest.mark.framework
def test_badam_case_migrated():
    config_path = "backend/tests/test_results/badam/config.yaml"
    orchestrator = TestOrchestrator(config_path)
    orchestrator.run_test()

if __name__ == "__main__":
    pytest.main([__file__])
```

## Conclusion
By following these steps, you can migrate all existing test cases to the new framework, ensuring that they are standardized, configurable, and easy to maintain.
