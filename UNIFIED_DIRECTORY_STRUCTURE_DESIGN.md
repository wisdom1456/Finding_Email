# Unified Directory Structure Design

## Overview

This document presents a comprehensive production-grade directory structure that consolidates all identified fragmentation issues while following Python packaging best practices and enterprise software organization patterns.

## Current State Problems

### Identified Issues
1. **Code Duplication**: Triple duplication across `backend/`, `backend_logic/`, `core/`
2. **Import Path Inconsistency**: 138+ import references need updates
3. **Configuration Fragmentation**: Multiple config directories and files
4. **Test Structure Chaos**: Tests scattered across multiple directories
5. **Output Directory Inconsistency**: `test_results/`, `test-results/`, `validation_output/`
6. **Memory Bank Disorganization**: Core files missing from root, 37 archived files
7. **Documentation Scatter**: No canonical `/docs/` structure

## Proposed Unified Structure

```
legal-document-portal/
├── README.md
├── app.py                           # Main Streamlit application entry point
├── requirements.txt
├── .gitignore
├── .env.example
├── pyproject.toml                   # Modern Python project configuration
├── ruff.toml                        # Linting and formatting configuration
├── pytest.ini                      # Test configuration
├── Dockerfile
├── docker-compose.yml
│
├── src/                             # Main application source code
│   ├── __init__.py
│   ├── legal_portal/               # Main package namespace
│   │   ├── __init__.py
│   │   ├── core/                   # Core business logic
│   │   │   ├── __init__.py
│   │   │   ├── main_processor.py   # Main processing orchestrator
│   │   │   ├── ai_analyzer.py      # AI analysis coordination
│   │   │   ├── document_processor.py
│   │   │   ├── email_generator.py
│   │   │   ├── audio_processor.py
│   │   │   ├── video_processor.py
│   │   │   ├── citation_tracking_service.py
│   │   │   └── data_models.py      # Pydantic models
│   │   ├── services/               # External service integrations
│   │   │   ├── __init__.py
│   │   │   ├── openai_client.py
│   │   │   ├── json_processing_service.py
│   │   │   └── cost_session_manager.py
│   │   ├── utils/                  # Utility modules
│   │   │   ├── __init__.py
│   │   │   ├── security.py
│   │   │   ├── pii_sanitizer.py
│   │   │   ├── cache_manager.py
│   │   │   ├── api_optimizer.py
│   │   │   ├── logging_config.py
│   │   │   └── helpers.py
│   │   ├── config/                 # Configuration management
│   │   │   ├── __init__.py
│   │   │   ├── settings.py         # Unified Pydantic settings
│   │   │   ├── prompts/            # AI prompts configuration
│   │   │   │   ├── base_prompts.yaml
│   │   │   │   ├── contractor_dispute_config.yaml
│   │   │   │   └── landlord_tenant_config.yaml
│   │   │   └── templates/          # Jinja2 templates
│   │   │       ├── document_appendix.jinja2
│   │   │       └── email_templates/
│   │   └── ui/                     # Streamlit UI components
│   │       ├── __init__.py
│   │       ├── components/
│   │       │   ├── __init__.py
│   │       │   ├── file_upload.py
│   │       │   ├── progress_tracker.py
│   │       │   └── results_display.py
│   │       └── pages/
│   │           ├── __init__.py
│   │           ├── upload_page.py
│   │           └── results_page.py
│
├── tests/                          # Unified test suite
│   ├── __init__.py
│   ├── conftest.py                 # pytest configuration and fixtures
│   ├── unit/                       # Unit tests
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── test_ai_analyzer.py
│   │   │   ├── test_document_processor.py
│   │   │   ├── test_email_generator.py
│   │   │   └── test_main_processor.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── test_openai_client.py
│   │   │   └── test_json_processing_service.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── test_security.py
│   │       ├── test_pii_sanitizer.py
│   │       └── test_cache_manager.py
│   ├── integration/                # Integration tests
│   │   ├── __init__.py
│   │   ├── test_document_pipeline.py
│   │   ├── test_email_generation_pipeline.py
│   │   └── test_citation_enhancement.py
│   ├── e2e/                        # End-to-end tests
│   │   ├── __init__.py
│   │   ├── test_full_workflow.py
│   │   └── test_devlin_workflow.py
│   └── fixtures/                   # Test data and fixtures
│       ├── __init__.py
│       ├── sample_documents/
│       ├── mock_responses/
│       └── test_configs/
│
├── docs/                           # Comprehensive documentation
│   ├── README.md                   # Documentation index
│   ├── architecture/
│   │   ├── overview.md
│   │   ├── component_design.md
│   │   ├── data_flow.md
│   │   └── security_model.md
│   ├── development/
│   │   ├── setup_guide.md
│   │   ├── coding_standards.md
│   │   ├── testing_guide.md
│   │   └── debugging_guide.md
│   ├── deployment/
│   │   ├── local_development.md
│   │   ├── docker_deployment.md
│   │   ├── google_cloud_deployment.md
│   │   └── environment_configuration.md
│   ├── user_guides/
│   │   ├── getting_started.md
│   │   ├── document_processing.md
│   │   └── troubleshooting.md
│   └── api/
│       ├── core_modules.md
│       ├── service_interfaces.md
│       └── configuration_reference.md
│
├── scripts/                        # Utility and maintenance scripts
│   ├── __init__.py
│   ├── setup/
│   │   ├── install_dependencies.py
│   │   ├── configure_environment.py
│   │   └── validate_installation.py
│   ├── maintenance/
│   │   ├── cleanup_cache.py
│   │   ├── backup_data.py
│   │   └── health_check.py
│   ├── development/
│   │   ├── run_tests.py
│   │   ├── format_code.py
│   │   └── lint_check.py
│   └── migration/
│       ├── consolidate_directories.py
│       ├── update_imports.py
│       └── migrate_configs.py
│
├── data/                           # Application data (git-ignored)
│   ├── .gitkeep
│   ├── cache/                      # Application cache
│   ├── uploads/                    # Temporary file uploads
│   ├── outputs/                    # Generated documents
│   │   ├── findings_letters/
│   │   ├── analysis_reports/
│   │   └── appendices/
│   └── logs/                       # Application logs
│       ├── app.log
│       ├── error.log
│       └── audit.log
│
├── .build/                         # Build artifacts (git-ignored)
│   ├── .gitkeep
│   ├── dist/
│   ├── wheels/
│   └── coverage/
│
├── .test/                          # Test artifacts (git-ignored)
│   ├── .gitkeep
│   ├── results/
│   ├── reports/
│   ├── coverage/
│   └── benchmarks/
│
├── memory-bank/                    # Project memory and documentation
│   ├── projectbrief.md            # Core memory bank files
│   ├── productContext.md
│   ├── systemPatterns.md
│   ├── techContext.md
│   ├── activeContext.md
│   ├── progress.md
│   ├── decisionLog.md
│   ├── archive/                    # Historical documentation
│   │   ├── 2025-08-11/
│   │   ├── historical/
│   │   └── superseded/
│   └── specialized/                # Optional specialized docs
│       ├── deploymentGuide.md
│       ├── testingStrategy.md
│       ├── securityCompliance.md
│       └── performanceOptimization.md
│
└── .github/                        # CI/CD and GitHub configuration
    ├── workflows/
    │   ├── ci.yml
    │   ├── gcp-deploy.yml
    │   ├── security-scan.yml
    │   └── docs-deploy.yml
    ├── ISSUE_TEMPLATE/
    ├── PULL_REQUEST_TEMPLATE.md
    └── dependabot.yml
```

## Design Principles

### 1. Modern Python Package Structure
- **src/ layout**: Follows modern Python packaging best practices
- **Namespace packaging**: `legal_portal` as main package namespace
- **Clear module boundaries**: Each module has focused responsibility
- **Proper __init__.py files**: Enable clean imports

### 2. Separation of Concerns
- **src/**: All application source code
- **tests/**: Comprehensive test organization
- **docs/**: All documentation in one place
- **scripts/**: Utility and maintenance scripts
- **data/**: Runtime data (git-ignored)

### 3. Configuration Consolidation
- **Single config module**: `src/legal_portal/config/settings.py`
- **Environment-based**: Pydantic settings with environment overrides
- **Template organization**: Jinja2 templates in logical structure
- **Prompt management**: YAML-based prompt configurations

### 4. Test Organization
- **Three test levels**: unit, integration, e2e
- **Mirror source structure**: Tests mirror src/ organization
- **Shared fixtures**: Common test data and configuration
- **Clear separation**: Different test types in different directories

### 5. Documentation Structure
- **Comprehensive coverage**: Architecture, development, deployment, user guides
- **Logical organization**: By audience and purpose
- **Markdown format**: Consistent documentation format
- **Cross-references**: Linked documentation for easy navigation

## Migration Benefits

### Immediate Benefits
1. **Import Consistency**: All imports follow `from legal_portal.module import class` pattern
2. **Configuration Centralization**: Single source of truth for all settings
3. **Test Organization**: Clear test structure with proper isolation
4. **Documentation Accessibility**: All docs in `/docs/` with clear organization

### Long-term Benefits
1. **Maintainability**: Clear module boundaries and responsibilities
2. **Scalability**: Structure supports growth and additional features
3. **Developer Experience**: Standard Python patterns familiar to developers
4. **Production Readiness**: Enterprise-grade organization suitable for large deployments

## Implementation Strategy

### Phase 1: Core Structure Creation
1. **Create src/ layout** with proper package structure
2. **Move core modules** to `src/legal_portal/core/`
3. **Consolidate configuration** in `src/legal_portal/config/`
4. **Update imports** throughout application

### Phase 2: Test Consolidation
1. **Create unified tests/** structure
2. **Move existing tests** to appropriate subdirectories
3. **Create test fixtures** and shared configuration
4. **Update test imports** and execution

### Phase 3: Documentation Organization
1. **Create docs/** structure with all categories
2. **Migrate existing documentation** to appropriate locations
3. **Create cross-references** and navigation
4. **Update README** with new structure

### Phase 4: Support Infrastructure
1. **Create scripts/** for utilities and maintenance
2. **Organize data/** and build directories
3. **Update CI/CD** for new structure
4. **Validate deployment** processes

## Configuration Management

### Unified Settings Pattern
```python
# src/legal_portal/config/settings.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Application settings
    app_name: str = "Legal Document Portal"
    debug: bool = False
    
    # OpenAI configuration
    openai_api_key: str
    openai_model: str = "gpt-4"
    
    # File processing
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    allowed_extensions: list[str] = [".pdf", ".docx", ".txt"]
    
    # Output directories
    output_dir: str = "data/outputs"
    cache_dir: str = "data/cache"
    log_dir: str = "data/logs"
    
    class Config:
        env_file = ".env"
        env_prefix = "LEGAL_PORTAL_"
```

### Import Pattern Examples
```python
# Clean, consistent imports
from legal_portal.core.main_processor import process_case_documents
from legal_portal.services.openai_client import OpenAIClient
from legal_portal.utils.security import validate_file_upload
from legal_portal.config.settings import get_settings

# Configuration access
settings = get_settings()
client = OpenAIClient(api_key=settings.openai_api_key)
```

## Quality Assurance

### Code Quality Tools
- **Ruff**: Unified linting and formatting
- **mypy**: Type checking
- **pytest**: Test execution
- **coverage**: Test coverage analysis

### CI/CD Integration
- **Automated testing**: All test levels on every PR
- **Code quality checks**: Linting, formatting, type checking
- **Security scanning**: Dependency and code security analysis
- **Documentation deployment**: Automatic docs updates

## File Migration Mapping

### Core Application Files
```bash
# Current → Target
core/ → src/legal_portal/core/
services/ → src/legal_portal/services/
utils/ → src/legal_portal/utils/
config/ → src/legal_portal/config/
```

### Test Files
```bash
# Current → Target
tests/ → tests/unit/
backend/tests/ → tests/unit/ (consolidated)
app/test_*.py → tests/integration/
```

### Documentation
```bash
# Current → Target
*.md → docs/ (organized by category)
memory-bank/ → memory-bank/ (restructured)
```

### Configuration
```bash
# Current → Target
config/*.py → src/legal_portal/config/settings.py
config/*.yaml → src/legal_portal/config/prompts/
```

## Validation Checklist

### Structure Validation
- [ ] All source code under `src/legal_portal/`
- [ ] All tests under `tests/` with proper organization
- [ ] All documentation under `docs/`
- [ ] Configuration consolidated in `config/`

### Import Validation
- [ ] All imports use consistent patterns
- [ ] No circular dependencies
- [ ] Proper package initialization

### Functionality Validation
- [ ] Streamlit app starts successfully
- [ ] All tests pass
- [ ] Configuration loads correctly
- [ ] Documentation builds without errors

## Expected Outcomes

### Code Organization
- **Single package namespace**: `legal_portal`
- **Clear module boundaries**: Each module has focused responsibility
- **Consistent imports**: All follow same pattern
- **No duplication**: Single source of truth for each component

### Development Experience
- **Standard patterns**: Familiar Python package structure
- **Easy navigation**: Clear directory organization
- **Simple testing**: Standard pytest patterns
- **Clear documentation**: Everything in `/docs/`

### Production Readiness
- **Deployable package**: Can be installed as Python package
- **Configuration management**: Environment-based settings
- **Monitoring ready**: Structured logging and metrics
- **Maintenance friendly**: Clear scripts and documentation

This unified structure addresses all identified fragmentation issues while providing a solid foundation for future development and production deployment.