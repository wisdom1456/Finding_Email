# Project Cleanup Plan - Legal Document Analysis Portal

## Overview
This document outlines the cleanup strategy to reduce technical debt, organize documentation, and improve project maintainability.

## Files to Archive (Move to `docs/archive/`)

### Implementation Summaries & Session Notes (52 files)
These are historical development notes that should be archived for reference:

- ALL_FIXES_SUMMARY.md
- BACKEND_CONSOLIDATION_SUMMARY.md
- BEFORE_AFTER_COMPARISON.md
- CACHE_FIX_SUMMARY.md
- CACHE_INTEGRATION_COMPLETE.md
- CANONICAL_DOCUMENTATION_STRUCTURE_PLAN.md
- CITATION_REMOVAL_IMPLEMENTATION.md
- CITED_LETTER_TAB_IMPLEMENTATION.md
- CLEANUP_FILES_TO_REMOVE.md
- CLEANUP_RESULTS_REPORT.md
- CLEAN_FILENAME_CITATIONS_IMPLEMENTATION.md
- CLIENT_FRIENDLY_LETTER_IMPROVEMENTS_SUMMARY.md
- CONCRETE_REFACTOR_PLAN.md
- CONFIGURATION_CONSOLIDATION_PLAN.md
- CURRENT_FILE_TREE.md
- DATA_PROPAGATION_ANALYSIS.md
- DOCUMENT_ANALYSIS_OPTIMIZATION.md
- DUPLICATE_AND_OVERLAP_AUDIT_REPORT.md
- Findings_Email_Workflow_Review.md
- GPT4O_SWITCH_AND_INTAKE_ONLY_IMPLEMENTATION.md
- GPT4O_VISION_API_FIX.md
- GPT4O_VISION_HOTFIX_LOGGING.md
- GPT4O_VISION_MIGRATION.md
- GPT_MODEL_ANALYSIS_AND_RECOMMENDATIONS.md
- HOTFIX_QUALITY_VALIDATOR_JSON_SERIALIZATION.md
- IMAGE_BATCH_PROCESSING_IMPLEMENTATION.md
- IMPLEMENTATION_COMPLETE.md
- IMPLEMENTATION_STATUS_DATA_QUALITY_LETTER_CLEANUP.md
- IMPLEMENTATION_SUMMARY.md
- MEMORY_BANK_CONSOLIDATION_ANALYSIS.md
- MEMORY_BANK_CONSOLIDATION_PLAN.md
- OPTION_A_FINAL_IMPLEMENTATION.md
- OPTION_A_IMPLEMENTATION_SUMMARY.md
- OUTPUT_DIRECTORY_CONSOLIDATION_ANALYSIS.md
- PHASE1_AUTO_REFRESH_IMPLEMENTATION.md
- PHASE1_HOTFIX.md
- PHASE1_HOTFIX2.md
- PHASE1_HOTFIX3_UI_STATUS_DETECTION.md
- PHASE1_HOTFIX4_THREAD_SAFE_QUEUE.md
- PHASE1_IMPLEMENTATION_SUMMARY.md
- PHASE1_TESTING_GUIDE.md
- PHASE1_UI_FEEDBACK_IMPROVEMENTS.md
- PROJECT_FILE_TREE.md
- SESSION_SUMMARY_2025-11-04_DATA_QUALITY_IMPROVEMENTS.md
- SIMPLIFICATION_IMPLEMENTATION.md
- STRUCTURED_JSON_IMPLEMENTATION_SUMMARY.md
- TESTING_BATCH_PROCESSING.md
- TESTING_GUIDE_DATA_QUALITY_IMPROVEMENTS.md
- TESTING_GUIDE_STRUCTURED_JSON.md
- TESTING_INSTRUCTIONS.md
- TEST_RESTRUCTURE_PLAN.md
- UNIFIED_DIRECTORY_STRUCTURE_DESIGN.md
- backend_consolidation_plan.md
- documentation_similarity_map.md
- duplication_and_overlap_report.md
- refactor_and_moves_plan.md

## Files to Keep in Root (Active Documentation)

### Essential Documentation
- README.md - Main project documentation
- DEPLOYMENT_GUIDE.md - Active deployment instructions
- ENV_SETUP_GUIDE.md - Environment setup guide
- QUICK_ENV_SETUP.md - Quick setup reference
- QUICK_START.md - Quick start guide
- GITHUB_AUTH_SETUP.md - GitHub authentication setup

## Scripts to Consolidate

### Keep These Scripts
- `scripts/start_local_dev.sh` - Primary local startup for backend + frontend
- `run_app.py` - Python entry point for FastAPI backend

### Archive or Remove
- `run_app.sh` - Outdated (references incorrect path: app/main.py)
- `start_servers.sh` - May be obsolete if backend removed
- `consolidate.sh` - One-time use script
- `force_cleanup.sh` - One-time use script
- `post_consolidation_fix.sh` - One-time use script
- `cleanup.sh` - Redundant with this cleanup
- `configure_env.sh` - Functionality should be in documentation
- `deploy.sh` - Move to scripts/ directory if still needed
- `setup_and_deploy.sh` - Move to scripts/ directory if still needed

## Log Files to Remove
- build.log
- frontend_live.log
- session_audit.log
- ruff_lint_report.txt
- ruff_final_report.txt
- ruff_lint_report_latest.txt

## Build Artifacts to Verify
- dist/ - Should be in .gitignore, verify if needed
- node_modules/ - Should be in .gitignore
- `=2.4.0` - Seems like a corrupted file, remove

## Directories to Organize

### Archive Directories
- cost_sessions/ - Move to docs/archive/ or output/archive/
- debug_output/ - Move to output/debug/
- validation_output/ - Move to output/validation/

## Actions

1. **Create Archive Structure**
   ```
   docs/archive/
   ├── implementation-notes/
   ├── testing-guides/
   └── analysis-reports/
   ```

2. **Move Files** - Move implementation summaries to appropriate archive folders

3. **Remove Obsolete Items** - Remove log files and temporary build artifacts

4. **Update .gitignore** - Ensure build artifacts and logs are ignored

5. **Consolidate Documentation** - Create master guides from the essential docs

6. **Code Quality** - Run linter and fix issues

## Result
After cleanup, the root directory will contain:
- README.md (comprehensive)
- Essential setup guides (consolidated)
- requirements.txt
- pyproject.toml
- Core configuration files
- Primary startup script
- Standard project directories (src/, tests/, docs/, scripts/)
