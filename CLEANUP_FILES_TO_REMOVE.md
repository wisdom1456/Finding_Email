# Dead Code and FastAPI Artifacts Cleanup - Files to Remove

## Summary
This document lists all files identified for removal as part of the cleanup effort.
Total files to remove: 100+
Estimated lines to remove: 5,350+

## Debug Scripts (11 files in root)
```bash
debug_actual_json_structure.py
debug_actual_normalization_content.py
debug_analysis_state.py
debug_email_generator_test.py
debug_json_output.py
debug_normalization_issues.py
debug_pipeline_fix_validation.py
debug_template_context_real.py
debug_template_context.py
debug_template_rendering.py
debug_validation_output.py
```

## Normalization Fix Scripts (3 files)
```bash
advanced_normalization_fix.py
enhanced_normalization_fix.py
fix_normalization_post_processor.py
```

## Test Scripts in Root (50+ files)
```bash
test_analyzed_document_fix.py
test_authentic_attorney_advisor_validation.py
test_budget_core_integration.py
test_budget_integration.py
test_constructor_fix.py
test_cost_performance.py
test_criminal_models.py
test_criminal_video_integration.py
test_criminal_video_processor.py
test_css_corruption_debug.py
test_css_corruption_direct.py
test_css_fix_direct.py
test_css_fix_validation.py
test_deadline_bolding.py
test_email_generator_enhancement.py
test_email_generator_enhancements.py
test_email_generator_refactor.py
test_enhanced_validation.py
test_error_handling_validation.py
test_findings_improvements.py
test_framework_devlin.py
test_framework_discrepancy_validation.py
test_html_structure_improvement.py
test_html_validation.py
test_json_parsing_fixed.py
test_json_parsing_simple.py
test_json_parsing.py
test_logging_config.py
test_logging.py
test_main_processor.py
test_next_steps_validation.py
test_normalization_effectiveness.py
test_normalization_pipeline.py
test_performance_validation.py
test_polish_and_sanitize_integration.py
test_post_processing.py
test_prompt_injection.py
test_readability_regeneration.py
test_refactored_architecture.py
test_refactored_email_generator.py
test_regex_replace_fix.py
test_sanitize_pass_integration.py
test_section_validation_integration.py
test_simple_verification.py
test_simplification_feature.py
test_strengths_weaknesses_validation.py
test_template_compatibility.py
test_template_fix_validation.py
test_template_fix_verification.py
test_template_rendering.py
test_template_validation_fix.py
test_video_formatting.py
test_video_google_api.py
test_word_count_trimming.py
validation_test_harness.py
```

## Generated Output Files (11 files)
```bash
debug_normalization_content_fixed.html
debug_normalization_content.html
debug_template_output.html
debug_validation_analysis_output.html
debug_validation_email_output.html
debug_raw_json_structure.json
debug_raw_output.html
test_appendix.html
test_main_letter.html
normalization_analysis.txt
validation_report.txt
```

## Analyzer Scripts and Results (10 files)
```bash
# Analyzer scripts
dead_code_analyzer.py
import_analyzer.py
parallelization_analyzer.py
redundant_logic_analyzer.py
replace_print_statements.py

# Results
bandit_report.json
dead_code_analysis_results.json
import_analysis_results.json
parallelization_analysis_results.json
performance_test_results.json
redundant_logic_analysis_results.json
```

## Documentation/Report Files (5 files)
```bash
CODE_PATH_EFFICIENCY_ANALYSIS_REPORT.md
FRAMEWORK_VALIDATION_REPORT.md
STRUCTURED_LOGGING_IMPLEMENTATION.md
testing_strategy.md
workflow_overview.md
```

## Railway Deployment Configs (2 files)
```bash
railway.toml
railway.toml.full
```

## FastAPI Test Files (2 files)
```bash
backend/tests/test_main.py
backend/tests/simple_test.py
```

## Files to Fix (not remove)
```bash
backend_logic/async_processor.py  # Remove FastAPI import, replace with standard exception
```

## IMPORTANT NOTES:
1. The backend/ directory MUST BE KEPT (except the two FastAPI test files) as it contains utils used throughout the system
2. backend_logic/ directory MUST BE KEPT as it contains active business logic
3. All files listed above have been verified to have NO dependencies from active code
4. Total estimated lines to remove: 5,350+