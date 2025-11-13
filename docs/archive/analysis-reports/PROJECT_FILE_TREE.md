# Finding Emails Project - File/Folder Tree

This document provides a complete file and folder structure of the Finding Emails project, excluding all items specified in `.gitignore`.

## Root Directory Structure

```
Finding_Emails/
├── .dockerignore
├── .env.example
├── .env.template
├── .gitignore
├── .pre-commit-config.yaml
├── app.py
├── CLEANUP_FILES_TO_REMOVE.md
├── CLEANUP_RESULTS_REPORT.md
├── Dockerfile
├── Findings_Email_Workflow_Review.md
├── index.html
├── Makefile
├── monitoring_dashboard.py
├── pyproject.toml
├── README.md
├── requirements-dev.txt
├── requirements.txt
├── start_app.sh
├── start_servers.sh
├── test_appendix_fix.py
├── test_citation_enhancement.py
├── test_critical_fixes.py
├── assets/
├── backend/
├── backend_logic/
├── components/
├── config/
├── core/
├── cost_sessions/
├── docs/
├── memory-bank/
├── services/
├── test_data/
├── test_results/
├── test-results/
├── tests/
├── utils/
└── validation_output/
```

## Detailed Directory Breakdown

### `/assets/`
```
assets/
└── (directory structure not detailed in current scan)
```

### `/backend/`
```
backend/
├── __init__.py
├── ai_analyzer.py
├── config.py
├── delivery.py
├── document_processor.py
├── email_generator.py
├── quality_validator.py
├── quick_validation_test.py
├── template_assembler.py
├── assets/
│   └── templates/
├── config/
│   ├── README.md
│   └── templates/
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── README.md
│   ├── TESTING_ARCHITECTURE.md
│   └── e2e/
└── utils/
```

### `/backend_logic/`
```
backend_logic/
├── __init__.py
├── ai_analyzer.py
├── async_processor.py
├── audio_processor.py
├── config.py
├── cost_calculator.py
├── cost_estimator.py
├── cost_exporter.py
├── cost_session_manager.py
├── document_processor.py
├── email_generator_backup.py
├── email_generator.py
├── email_generator.py.bak
├── main_processor.py
├── utils.py
├── video_processor.py
├── ai/
├── email_generation/
├── tests/
└── utils/
```

### `/components/`
```
components/
├── __init__.py
├── budget_sheet.py
└── ui_components.py
```

### `/config/`
```
config/
└── auth_config.yaml
```

### `/core/`
```
core/
├── __init__.py
├── ai_analyzer.py
├── document_processor.py
├── email_generator.py
└── main_processor.py
```

### `/cost_sessions/`
```
cost_sessions/
└── (directory for cost tracking sessions)
```

### `/docs/`
```
docs/
├── ARCHITECTURE.md
├── AUTHENTIC_ATTORNEY_IMPLEMENTATION_PLAN.md
├── CITATION_ENHANCEMENT_IMPLEMENTATION.md
├── CLIENT_CLARITY_ADVISOR_IMPLEMENTATION.md
├── COMPREHENSIVE_RISK_ASSESSMENT_REPORT.md
├── COST_TRACKING_TEST_REPORT.md
├── enhanced_file_validation.md
├── FINAL_ARCHITECTURAL_REFINEMENT_PLAN.md
├── FINAL_EFFICIENCY_REPORT.md
├── FINAL_VALIDATION_REPORT.md
├── FORMATTING_LINTING_STANDARDS.md
├── GOOGLE_CLOUD_DEPLOYMENT.md
├── master_schema.md
├── ORCHESTRATOR_EMAIL_GENERATOR_FIX.md
├── PERFORMANCE_VALIDATION_REPORT.md
├── PERFORMANCE.md
├── PROMPT_IMPROVEMENT_PLAN.md
├── refactoring_plan.md
├── RUFF_CLEANUP_PLAN.md
├── SECURITY_AUDIT_REPORT.md
├── SECURITY_IMPROVEMENTS.md
├── SECURITY.md
└── VALIDATION_CHECKLIST.md
```

### `/memory-bank/`
```
memory-bank/
├── activeContext.md
├── client_clarity_advisor_framework.md
├── criminal_video_processing.md
├── debugging_lessons_learned.md
├── optimization_recommendations.md
├── performance_bottleneck_report.md
├── productContext.md
├── progress.md
├── projectbrief.md
├── systemPatterns.md
├── techContext.md
├── vertex_ai_video_analysis.md
├── video_preservation_plan.md
└── archive/
```

### `/services/`
```
services/
├── __init__.py
├── async_processor.py
├── audio_processor.py
├── citation_tracking_service.py
├── config_and_template_loader.py
├── configuration_manager.py
├── content_extraction_service.py
├── content_formatting_service.py
├── content_generation_service.py
├── email_generator_core.py
├── fallback_generation_service.py
├── json_architecture_service.py
├── json_processing_service.py
├── openai_integration_service.py
├── prompt_and_api_service.py
├── shared_utils.py
├── template_rendering_service.py
├── text_processing_service.py
└── video_processor.py
```

### `/test_data/`
```
test_data/
├── Case_Analysis_Amber Bell  Erik Devlin-12.html
├── Devlin_Findings_Email.rtf
├── Findings Letter Template.docx
├── Findings_Clifton Price.eml
├── Findings_Letter_Amber Bell  Erik Devlin-26.html
├── Findings_Miguel Velasco Rachael Taft.eml
├── Intake - Miguel and Rachael.pdf
├── Intake (General) - Alan Ivarson.pdf
├── Intake (General) - Balaji Badam.pdf
├── Intake (General) - Clifton Price.pdf
├── processed_css_fixed_sample.html
├── Badam, Balaji [MetLife]/
├── Devlin, Erik [MetLife]/
├── Price, Clifton [MetLife]/
└── Velasco, Miguel [MetLife]/
```

### `/test_results/`
```
test_results/
└── devlin_manual_run/
```

### `/test-results/`
```
test-results/
├── Case_Analysis_Clifton Price-6.html
├── Document_Appendix_Clifton Price-10.html
├── Findings_Letter_Clifton Price-6.html
└── badam-case-test/
```

### `/tests/`
```
tests/
└── test_startup.py
```

### `/utils/`
```
utils/
├── __init__.py
├── api_optimizer.py
├── async_streamlit.py
├── audit_logger.py
├── auth.py
├── cache_manager.py
├── data_models.py
├── helpers.py
├── logging_config.py
├── metrics.py
├── oauth.py
├── pii_sanitizer.py
├── security.py
├── session_manager.py
├── structured_logger.py
├── tracing.py
├── file_processors/
└── tests/
```

### `/validation_output/`
```
validation_output/
├── amber_bell_erik_devlin_analysis_appendix.html
├── amber_bell_erik_devlin_findings_letter.html
├── balaji_badam_rajya_badam_analysis_appendix.html
├── balaji_badam_rajya_badam_findings_letter.html
├── clifton_price_analysis_appendix.html
├── clifton_price_findings_letter.html
├── document_appendix.html
├── erik_devlin_analysis_appendix.html
├── erik_devlin_findings_letter.html
├── final_prompt.txt
├── findings_letter.html
├── html_output_john_doe_20250808_141623.html
├── miguel_velasco_rachael_taft_analysis_appendix.html
├── miguel_velasco_rachael_taft_findings_letter.html
└── test_appendix_output.html
```

## Excluded Items (per .gitignore)

The following types of files and directories are excluded from this tree:

- **Environment files**: `.env`, `.env.local`, `.env.development`, `.env.production`
- **API Keys/Secrets**: `config/secrets/`, `*.json`, credential files
- **Python cache**: `__pycache__/`, `*.pyc`, `*.pyo`, build artifacts
- **Virtual environments**: `.venv/`, `venv/`, `ENV/`, `env/`
- **Node.js**: `node_modules/`, npm/yarn debug logs
- **Build outputs**: `dist/`, `build/`, `out/`
- **IDE files**: `.vscode/`, `.idea/`, editor swap files
- **OS files**: `.DS_Store`, `Thumbs.db`, system files
- **Logs**: `*.log`, `logs/` directory
- **Database files**: `*.db`, `*.sqlite`
- **Test coverage**: `.coverage`, `.pytest_cache/`, `htmlcov/`
- **Temporary files**: `tmp/`, `temp/`, `*.tmp`, `*.temp`
- **Large media files**: Video files (`.MOV`, `.mp4`, etc.) in test_data
- **Large PDFs**: Specific large PDF files in test_data

## Project Overview

This is a Python-based email generation system for legal findings letters with the following key components:

- **Backend Logic**: Core processing and AI analysis
- **Services**: Modular service architecture
- **Utils**: Shared utilities and helpers
- **Documentation**: Comprehensive project documentation
- **Memory Bank**: Project context and progress tracking
- **Test Data**: Sample cases and templates
- **Validation Output**: Generated email outputs

The project uses Docker for containerization, includes comprehensive testing, and maintains detailed documentation for all components.
