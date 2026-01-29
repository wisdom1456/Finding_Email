# Active Context

*Date: 2026-01-02*

## 1. Current Focus: Enhanced Document Analysis Extraction (OPTIMIZED)

**MAJOR OPTIMIZATION (Oct 2, 2025)**: Enhanced document analysis to extract comprehensive structured detail, eliminating need for full content in downstream prompts.

### What Changed
1. **Data Model**: Enhanced `AnalyzedDocument` with rich extraction fields:
   - `detailed_findings`: 500-800 word comprehensive analysis
   - `key_facts`: Array of 10-20 specific factual statements
   - `evidence_points`: Array of evidentiary items
   - `parties_mentioned`: Structured party data with roles and context
   - `amounts_and_dates`: Financial and temporal data extraction
   - `legal_issues_identified`: Legal implications from document
   - `summary`: Expanded to 250-400 words (was 100-150)

2. **AI Analyzer Prompt Optimization**:
   - **REMOVED DUPLICATION**: Eliminated redundant client priorities, outcomes, case type fields (lines 235-239)
   - **Single Context Source**: Now uses only `ctx.model_dump_json()` - no duplicate fields
   - **Enhanced Extraction Instructions**: AI now extracts 5-10x more structured detail per document
   - **Token Efficiency**: Reduced prompt size while increasing extraction quality

3. **Architecture Benefits**:
   - Full document content sent once (during analysis)
   - Rich structured data extracted and preserved
   - Downstream prompts use detailed extractions, not full content
   - No token overflow issues
   - More accurate and comprehensive analysis

### Previous Token Issue (RESOLVED)
- **Root Cause**: Extracting only 100-150 word summaries from full documents was insufficient
- **Duplication Issue**: Sending intake context fields twice in document analysis prompt
- **Solution**: Extract comprehensive detail during analysis; use structured data in later phases
- **Result**: Better quality analysis with more efficient token usage

### Benefits
- ✅ **Accuracy**: Email generation can verify facts against source documents (when explicitly requested)
- ✅ **Citations**: Can quote exact passages from original documents (via `analyzed_documents_with_content` property)
- ✅ **Transparency**: Full audit trail of what AI analyzed
- ✅ **Debugging**: Can compare AI summaries against original text
- ✅ **Token Efficiency**: Default prompts don't include full documents (prevents overflow)

### Technical Details
- Memory overhead: Acceptable for typical case loads (5-20 documents)
- Token optimization: Original content excluded from **all** prompts by default (final assessment + email generation)
- Access pattern: Full documents available via `analysis.analyzed_documents_with_content` property when needed
- Two-tier system: Lightweight by default, full access when explicitly requested
- Documentation: Complete architecture in `docs/FULL_DOCUMENT_CONTENT_ARCHITECTURE.md`

### Letter Generation Prompt Optimization (Oct 2, 2025)
**CRITICAL SCALABILITY FIX**: Further optimized letter generation prompts to handle 40+ document cases.

**Problem Identified**:
- 5-6 document case = 3,160 lines in final_prompt.txt
- 40 document projection = 11,500+ lines, 80,000-120,000 tokens (would exceed limits)

**Solution Implemented** (`json_processing_service.py` lines 154-167):
Excluded verbose/redundant fields from letter generation prompt:
- ❌ `detailed_findings` (500-800 words, redundant with summary)
- ❌ `evidence_points` (duplicates key_facts)
- ❌ `key_points`, `citations`, `metadata` (mostly empty/technical)
- ✅ Kept: `summary`, `key_facts`, `parties_mentioned`, `amounts_and_dates`, `legal_issues_identified`, `timeline_events`

**Impact**:
- 60% reduction in prompt size per document
- 40 doc case: 11,500 → 5,600 lines, 40,000-50,000 tokens (within limits)
- Quality maintained: All essential facts, dates, parties, legal issues preserved
- Full data still accessible via `analyzed_documents_with_content` if needed

**Documentation**: `docs/PROMPT_SIZE_OPTIMIZATION.md`

## 2. Automatic Output File Cleanup (Oct 2, 2025)

Implemented intelligent output file management with 24-hour automatic cleanup to prevent disk space accumulation:

### Architecture
- **Two-Tier Storage**: Session memory (immediate) + Cache storage (24h TTL)
- **Smart Caching**: Generated documents cached via `DocumentCache` with automatic expiration
- **Diagnostic Preservation**: Optional retention of debug files in `validation_output/`
- **Configurable Cleanup**: Environment-based control via `USE_CACHE_FOR_OUTPUTS`, `OUTPUT_RETENTION_HOURS`, `DEBUG_MODE`

### Implementation Details
- **Cache Manager Enhanced**: Added `cache_generated_document()` and `cleanup_validation_output()` functions
- **Configuration**: New settings in `config/default.py` for output behavior control
- **Main Processor**: Modified `save_output_files()` to use cache; added startup cleanup routine
- **Default Behavior**: Production mode enables 24-hour auto-cleanup; debug mode preserves all files

### Benefits
- ✅ No disk space accumulation from old output files
- ✅ Downloads available during active sessions (via session state)
- ✅ Automatic cleanup on startup (configurable retention period)
- ✅ Debug mode for troubleshooting (preserves diagnostic files)

### Documentation
- Complete guide: `docs/OUTPUT_FILE_MANAGEMENT.md`
- Configuration examples for production, debug, and development modes
- API usage examples and troubleshooting guide

## 3. CSV File Support Added

CSV file support has been fully integrated into the legal document processing system:
1.  **Security Layer**: Added `.csv` to allowed extensions and MIME types (`text/csv`, `application/csv`) in `security.py`
2.  **Data Models**: Added `CSV` file type to `FileType` enum in `data_models.py`
3.  **UI Integration**: Updated file uploader in `ui_components.py` to accept CSV files
4.  **Enhanced Validation**: Added comprehensive CSV validation in `enhanced_file_validator.py` including encoding detection, row/column validation, and structure checking
5.  **CSV Processor**: Created `csv_processor.py` to parse CSV files and convert to structured text format with headers, data rows, and metadata
6.  **Processor Registration**: Registered CSV processor in file processors mapping for both `text/csv` and `application/csv` MIME types

## 4. New Mexico Legal Corpus Added (Dec 2025)

Successfully implemented Phase 1 of the New Mexico multi-state support plan:
1.  **New Corpus Directory**: Created `new_mexico_legal_corpus/` directory.
2.  **Statute Integration**: Moved and renamed `nm_statutes_full.jsonl` to `new_mexico_legal_corpus/statutes.jsonl`.
3.  **Alias Integration**: Moved and renamed `nm_statute_aliases_full.jsonl` to `new_mexico_legal_corpus/statute_aliases.jsonl`.
4.  **Rule Integration**: Moved and renamed `nm_rules_full.jsonl` to `new_mexico_legal_corpus/nm_rules.jsonl`.
5.  **Documentation**: Created `new_mexico_legal_corpus/README.md` documenting the corpus structure and coverage (Consumer Protection, Landlord-Tenant, Construction Defects).

## 2. Recent Changes & Key Decisions

*   **GPT-5.2 Migration (Jan 2026)**: Migrated all AI services from GPT-4o to GPT-5.2 and GPT-5-mini
    *   **Primary Model**: `gpt-5.2` for complex legal analysis, letter generation, multi-stage analysis
    *   **Cost-Optimized**: `gpt-5-mini` for document summaries, chat, simpler tasks
    *   **New Parameters**: `reasoning_effort` (none/low/medium/high/xhigh), `verbosity` (low/medium/high), `max_output_tokens`
    *   **Implementation**: Using `extra_body` in Chat Completions API for SDK compatibility
    *   **Files Updated**: `openai_client.py`, `multi_stage_analyzer.py`, `case_chat_service.py`, `demand_letter_service.py`, `main_processor.py`, `json_processing_service.py`

*   **New Mexico Corpus Integration (Dec 2025)**: Completed the first phase of adding New Mexico support by establishing a structured legal corpus mirroring the Florida structure.

*   **CSV File Support (Oct 2, 2025)**: Comprehensive CSV file support added throughout the system
    *   **File Processing**: CSV files are now validated, processed, and converted to structured text format
    *   **Validation**: Includes encoding detection (UTF-8, Latin-1, CP1252), row/column consistency checks, and CSV parsing validation
    *   **Security**: Full integration with existing security validation infrastructure including magic number detection
    *   **User Experience**: CSV files can be uploaded alongside other document types in the case folder
*   **Case Analysis Restructure (Oct 2, 2025)**: Completely restructured `utils.py` case analysis generation to focus on case analysis rather than document analysis
    *   **Case-Centric Sections**: Now includes Key Facts, Parties Involved, Legal Issues Identified, Financial Impact, Client Priorities, Desired Outcomes
    *   **Enhanced Legal Assessment Display**: Shows claim viability, evidence strength, potential challenges (with warning styling), recommended actions, and urgency assessment
    *   **Recommendations Section**: Added Final Analysis with recommendations and next steps when available
    *   **Document Reference**: Documents now shown as brief count with reference to separate Document Appendix, eliminating document-by-document summaries from case analysis
    *   **Professional Styling**: Added colored boxes (green for assessments, red for warnings), list items with border accents, party boxes for clear information hierarchy
*   **Full-Width Display Fix**: Updated `app/components/ui_components.py` to use `width=None` parameter and CSS `max-width: 100%; width: 100%` for proper rendering of findings email in results tab
*   **Intake Document Inclusion**: Modified `src/legal_portal/services/main_processor.py` to include intake form as first document in appendix with special "Primary Document" designation and blue border styling
*   **Document Appendix Template Created**: Built comprehensive `document_appendix.jinja2` template with professional styling, timeline support, and proper document categorization (intake vs case documents)
*   **Visual Hierarchy**: Implemented badge system (intake form, case document, video) and color coding to improve document navigation

## 3. Pending Decisions & Open Questions

*   **CI/CD Pipeline Strategy**: What is the desired CI/CD workflow? (e.g., GitHub Actions, GitLab CI, etc.). Key steps to define include automated testing, linting, building, and deployment triggers.
*   **Test Coverage Threshold**: What is the target code coverage percentage for the `legal_portal` package?
*   **Feature Prioritization**: What are the first new features to be built on top of the consolidated platform?
*   **Production Deployment**: Consider deployment to Google Cloud Platform or other cloud services for live production access.

## 4. Data Propagation Verification (Oct 2, 2025)

*   **Status**: ✅ ENHANCED - Data is correctly propagated through all AI prompting phases with full document content retention
*   **Analysis Document**: `DATA_PROPAGATION_ANALYSIS.md` updated with complete verification and enhancement details
*   **Key Findings**:
    *   Phase 1 (Document Processing): All files properly extracted and categorized with full text content
    *   Phase 2 (Intake Analysis): Complete intake form content sent to AI, structured data extracted
    *   Phase 3 (Case Document Analysis): **CRITICAL** - Each document receives full intake context AND full original content is preserved in AnalyzedDocument
    *   Phase 4 (Final Assessment): Complete case analysis from all phases included in prompt (original_content excluded for efficiency)
    *   Phase 5 (Email Generation): Master prompt receives complete case data **including full original document content** for accurate citations
*   **Verification Evidence**:
    *   `main_processor.py:699` - Intake analysis explicitly passed to document analysis
    *   `ai_analyzer.py:232-239` - Client priorities and intake context injected into every document prompt
    *   `ai_analyzer.py:935` - Original document content attached to AnalyzedDocument
    *   `ai_analyzer.py:701` - Original content strategically excluded from final assessment prompt
    *   `json_processing_service.py:188-190` - analyzed_documents_with_content property provides full access
    *   Diagnostic files in `validation_output/` capture data at each stage
*   **No Data Loss**: Each phase successfully passes complete context to the next phase, now including full original document text

## 5. Recent Improvements (Oct 2, 2025)

*   **Enhanced Document Analysis Context**: Added document metadata (file type, size) to analysis prompts for better disambiguation
*   **Timeline Events Capture**: Added `timeline_events` field to `AnalyzedDocument` model to capture chronological events from each document
*   **Improved Prompt Schema**: Updated document analysis prompt to include metadata section and timeline events extraction
*   **Benefits**: Better context for AI analysis, improved timeline generation in appendix, enhanced document disambiguation
*   **Timeline Fix**: Fixed timeline_events access bug in appendix generation - now properly displays dates and descriptions instead of "Unknown" and "Event recorded"

## 6. Key Insights

*   **Git Repository Success**: Application successfully pushed to GitHub repository (https://github.com/wisdom1456/Finding_Email.git) with comprehensive commit history and clean main branch
*   **Markdown Intermediate Format**: Using Markdown as an intermediate format provides significantly better control over final HTML output than asking AI to generate HTML directly
*   **Post-Processing Reliability**: The new two-step process (Markdown generation + HTML conversion) is more reliable and produces cleaner, more consistent results
*   **Content Generation Improvements**: The separation of content generation and formatting concerns improves maintainability and allows for easier HTML structure modifications
*   **Unified Architecture**: The consolidated architecture significantly simplifies dependency management and reduces cognitive overhead for developers
*   **Centralized Configuration**: Management through `src/legal_portal/config` has eliminated major sources of errors from the previous fragmented system
*   **Pre-commit Hooks**: Ruff-based code quality enforcement is working correctly and maintaining code standards automatically
