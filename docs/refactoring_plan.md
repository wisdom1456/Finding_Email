# Email Generator Refactoring Plan

## Objective
Refactor `backend_logic/email_generator.py` to improve maintainability, reduce complexity, and clearly separate concerns. The goal is to break down the monolithic class into smaller, focused modules.

## Current State
The `EmailGeneratorV2` class in `backend_logic/email_generator.py` is currently responsible for:
- Configuration loading and template management
- AI prompt building and OpenAI API interaction
- JSON generation, cleaning, and validation
- HTML/text processing, sanitization, and formatting
- Content extraction and fallback generation
- Core email generation orchestration

## Proposed Modular Structure

### 1. `email_generator_core.py` (New)
- **Responsibility:** Orchestrates the overall email generation process.
- **Key Classes/Methods:**
    - `EmailGeneratorV2` (renamed to `EmailGeneratorCore` or similar, or keep `EmailGeneratorV2` as the main entry point)
    - `generate_email_with_debug`
    - `generate_email_and_analysis_docs`
    - `generate_findings` (legacy compatibility)
    - `_validate_input_analysis`
    - `_get_validation_summary`
    - `_create_comprehensive_structure_plan`
    - `_generate_all_sections_with_tracking`
    - `_section_header_to_key`
    - `_map_sections_to_template_fields`
    - `_validate_generated_letter`
    - `_validate_all_fields`
    - `_create_fallback_letter`
    - `_generate_fallback_documents`

### 2. `prompt_and_api_service.py` (New)
- **Responsibility:** Handles all interactions with the OpenAI API, including prompt building and response handling.
- **Key Classes/Methods:**
    - `PromptAndApiService`
    - `_build_enhanced_prompt`
    - `_make_openai_request`

### 3. `json_processing_service.py` (New)
- **Responsibility:** Manages JSON generation, cleaning, and validation against the master schema.
- **Key Classes/Methods:**
    - `JsonProcessingService`
    - `_generate_structured_json`
    - `_clean_json_response`
    - `_validate_json_response`
    - `_get_default_value_for_key`
    - `_validate_case_metadata`
    - `_validate_bridges_structure`
    - `_validate_generated_letter_structure`
    - `_validate_claims_structure`
    - `_validate_next_steps_structure`
    - `_convert_json_to_generated_letter`
    - `_format_next_steps_from_json`

### 4. `content_formatting_service.py` (New)
- **Responsibility:** Applies all HTML/text processing, sanitization, and formatting rules. This will be a large module and might need further breakdown later.
- **Key Classes/Methods:**
    - `ContentFormattingService`
    - `_count_p_tags`
    - `_detect_corruption_patterns`
    - `_strip_html_tags`
    - `_trim_html_content_by_word_count`
    - `_trim_element_at_sentence_boundary`
    - `_fallback_word_trim`
    - `_apply_word_count_trimming`
    - `_apply_enhanced_sanitization`
    - `_apply_deadline_formatting`
    - `_clean_ai_response`
    - `_format_legal_analysis`
    - `_format_recommendations`
    - `_format_subsections`
    - `_strip_citations`
    - `_format_bullet_points`
    - `_clean_section_numbering`
    - `_ensure_proper_whitespace`
    - `_trim_wordiness`
    - `_apply_enhanced_citation_filtering`
    - `_apply_sentence_splitting_logic`
    - `_apply_optional_ai_simplification`
    - `_sanitize_output_grammar`
    - `_ensure_html_structure`
    - `_normalize_spacing`
    - `_prettify_html_output`
    - `_apply_readability_gate`
    - `_apply_normalization_fixes`
    - `_check_and_prevent_duplicate_disclaimer`
    - `log_simplification_step`
    - `_apply_comprehensive_simplification`
    - `_apply_aggressive_readability_fixes`
    - `_aggressively_improve_text_readability`
    - `_split_long_sentence_aggressively`
    - `_replace_complex_vocabulary`
    - `_check_text_coherence`
    - `_replace_redundant_patterns`
    - `_convert_passive_to_active`
    - `_apply_final_simplification_pass`
    - `_simplify_sentence_structure`
    - `_apply_fallback_simplification`
    - `_ultra_simplify_text`
    - `_split_sentence_intelligently`
    - `_validate_sentence_fragment`

### 5. `content_extraction_service.py` (New)
- **Responsibility:** Extracts relevant information from `CaseAnalysisResult` for prompt building and fallback content.
- **Key Classes/Methods:**
    - `ContentExtractionService`
    - `_extract_key_facts`
    - `_identify_emphasis_items`
    - `_extract_legal_issues`
    - `_extract_media_evidence_points`
    - `_extract_case_assessment_points`
    - `_extract_recommendations`
    - `_ensure_analysis_completeness`
    - `_generate_video_analysis_appendix`
    - `_extract_case_specific_details`
    - `_generate_fallback_factual_summary`
    - `_generate_fallback_legal_analysis`
    - `_generate_fallback_next_steps`
    - `_generate_fallback_media_summary`
    - `_generate_fallback_strengths`
    - `_generate_fallback_challenges`
    - `_generate_fallback_section_content`
    - `format_video_analysis_for_appendix`

### 6. `config_and_template_loader.py` (New)
- **Responsibility:** Handles loading configuration and managing Jinja2 templates.
- **Key Classes/Methods:**
    - `ConfigAndTemplateLoader`
    - `_load_configuration`
    - `_find_template_directory`

## Migration Strategy
1.  Create new Python files for each proposed module under `backend_logic/email_generation/services/`.
2.  Move the identified methods into their respective new classes.
3.  Update the `EmailGeneratorV2` class to import and utilize instances of these new service classes.
4.  Adjust method calls within `EmailGeneratorV2` to delegate to the appropriate service methods.
5.  Ensure all necessary imports are added to the new files and removed from `email_generator.py` where no longer needed.
6.  **Crucially, re-apply the original task's requirements:** Remove or comment out all code related to AI-driven simplification, readability scoring, word count validation/truncation, HTML sanitization/cleaning, CSS formatting/prettifying, `AdvancedNormalizationProcessor`, and post-processor guard validation. This will be done as part of the code migration, ensuring these functionalities are not carried over to the new modules or are explicitly removed from the core orchestration.