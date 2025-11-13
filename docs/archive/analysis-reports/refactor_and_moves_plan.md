# Refactor and Moves Plan

## 1. Introduction

This document provides a comprehensive, step-by-step plan for refactoring the "Finding Emails" repository from its current duplicated and fragmented state into a clean, production-grade project. It synthesizes the findings from the `DUPLICATE_AND_OVERLAP_AUDIT_REPORT.md` and the `TEST_RESTRUCTURE_PLAN.md` into a single, executable strategy.

The core goal is to establish a single source of truth for all code, configuration, tests, and documentation, thereby improving maintainability, reducing complexity, and preparing the project for future development.

## 2. Canonical Directory Structure

The final, refactored project will adhere to the following directory structure:

```
finding-emails/
├── .github/              # CI/CD workflows
├── .test_results/        # Git-ignored test artifacts
├── app.py                # Main Streamlit application
├── config/
│   ├── default.py        # Pydantic settings loading
│   └── universal.yaml    # Universal configuration values
├── core/
│   ├── ai_analyzer.py
│   ├── document_processor.py
│   └── email_generator.py
├── docs/                 # All project documentation
├── memory-bank/
│   ├── activeContext.md
│   ├── productContext.md
│   ├── projectbrief.md
│   ├── progress.md
│   └── systemPatterns.md
├── services/
│   └── email_service.py  # High-level service abstractions
├── tests/
│   ├── e2e/
│   ├── integration/
│   └── unit/
└── utils/
    ├── file_processors/
    └── security.py
```

## 3. Execution Plan: Git Operations

The following `git` commands will be executed to achieve the target structure. This sequence is designed to be run from the repository root.

**Phase 1: Consolidate Core Logic**

*   **Goal**: Move the canonical logic from `core/` to the new top-level directories and remove all duplicated and legacy code.

```bash
# Move canonical core logic to its final destination
git mv core/ai_analyzer.py core/
git mv core/document_processor.py core/
git mv core/email_generator.py core/

# Remove all other legacy and duplicate logic directories
git rm -r backend/
git rm -r backend_backup/
git rm -r backend_logic_backup/
git rm -r services/services # extra nested services dir

# The primary services directory will be used for high-level service abstractions
# (Create if it doesn't exist, or clean it out if it does)
mkdir -p services
# git rm -r services/* # Uncomment if services dir contains old files
touch services/__init__.py
```

**Phase 2: Unify Configuration**

*   **Goal**: Consolidate all configuration into the `config/` directory and remove legacy config files.

```bash
# Move the canonical Pydantic settings
git mv config/settings.py config/default.py

# Move the universal YAML config and remove the convoluted path
git mv backend/config/templates/universal_legal_config.yaml config/universal.yaml

# Remove old config directories
git rm -r backend/config/
git rm -r backend_backup/config/
```

**Phase 3: Restructure Tests**

*   **Goal**: Implement the `TEST_RESTRUCTURE_PLAN.md`.

```bash
# Create the new test structure
mkdir -p tests/e2e tests/integration tests/unit/core tests/unit/utils

# Move and merge tests
git mv backend_backup/tests/unit/test_ai_analyzer.py tests/unit/core/test_ai_analyzer.py
git mv backend_backup/tests/unit/test_document_processor.py tests/unit/core/test_document_processor.py
git mv backend_backup/tests/unit/test_email_generator.py tests/unit/core/test_email_generator.py
git mv utils/tests/test_pii_sanitizer.py tests/unit/utils/test_pii_sanititizer.py
git mv utils/tests/test_security.py tests/unit/utils/test_security.py
git mv backend_backup/tests/e2e/test_devlin_workflow.py tests/integration/test_email_generation_pipeline.py

# Remove old test directories
git rm -r tests/ # a few loose files here
git rm -r backend/tests/
git rm -r backend_backup/tests/
git rm -r utils/tests/
```

**Phase 4: Clean Up Output Directories**

*   **Goal**: Standardize artifact and output locations.

```bash
# Remove old output directories
git rm -r test_results/
git rm -r test-results/
git rm -r validation_output/

# Create the new git-ignored directory
mkdir .test_results
echo "*" > .test_results/.gitignore
```

## 4. Post-Refactor Verification

After executing the `git` commands, the following steps must be taken:

1.  **Update Imports**: Run a global search-and-replace to update all Python import paths to reflect the new structure.
2.  **Run Tests**: Execute the full test suite from the root directory to confirm that all tests pass.
3.  **Run Streamlit App**: Launch the `app.py` to ensure the application runs without errors.
4.  **Update `.gitignore`**: Add `.test_results/` and `cost_sessions/` to the main `.gitignore` file.