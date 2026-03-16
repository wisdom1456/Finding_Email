# Analysis.py Migration Checklist - Test Coverage Summary

## Complete Function Inventory and Test Coverage

### Primary API Endpoint Functions (21 functions)

| # | Function Name | Test Files | Test Count | Coverage Type | Status |
|---|---|---|---|---|---|
| 1 | `start_analysis` | test_analysis.py | 3 tests | Direct API | COVERED |
| 2 | `cancel_analysis` | test_service_role_resilience.py | 1 test | Direct API | COVERED |
| 3 | `cancel_case_analysis` | None found | 0 tests | - | NOT COVERED |
| 4 | `get_analysis_status` | test_analysis.py | 1 test | Direct API | COVERED |
| 5 | `get_analysis_results` | test_analysis.py, test_analysis_results_pending.py | 5 tests | Direct API + Unit | COVERED |
| 6 | `save_streaming_analysis` | test_save_streaming_analysis.py | 11 tests | Direct API + Unit | COVERED |
| 7 | `get_streaming_result` | None found | 0 tests | - | NOT COVERED |
| 8 | `generate_letter` | test_generate_letter_formatting.py | 1 test | Direct API | COVERED |
| 9 | `stream_findings_letter` | test_letter_stream_integration.py | 4 tests | Direct API | COVERED |
| 10 | `generate_recommendation_letter` | None found | 0 tests | - | NOT COVERED |
| 11 | `stream_recommendation_letter` | None found | 0 tests | - | NOT COVERED |
| 12 | `calculate_demand_amount` | None found | 0 tests | - | NOT COVERED |
| 13 | `stream_chat_response` | None found | 0 tests | - | NOT COVERED |
| 14 | `case_chat` | None found | 0 tests | - | NOT COVERED |
| 15 | `analyze_gaps_on_demand` | None found | 0 tests | - | NOT COVERED |
| 16 | `resolve_gaps_and_refresh` | None found | 0 tests | - | NOT COVERED |
| 17 | `analyze_gaps_streaming` | None found | 0 tests | - | NOT COVERED |
| 18 | `process_case_background` | None found | 0 tests | - | NOT COVERED |
| 19 | `stream_case_analysis` | None found | 0 tests | - | NOT COVERED |
| 20 | `get_document_status` | test_documents.py | 1 test | Direct API | COVERED |
| 21 | `get_analysis_state` | None found | 0 tests | - | NOT COVERED |

**Summary: 7 functions with test coverage, 14 functions with no direct tests**

### Helper Functions with Test Coverage

| Helper Function | Test Files | Test Count | Test Functions |
|---|---|---|---|
| `_extract_deferred_documents` | test_deferred_extraction.py, test_eml_attachment_upload.py | 5 tests | test_deferred_pdf_gets_extracted, test_deferred_eml_gets_extracted, test_deferred_extraction_handles_failure, test_dedup_called_for_eml_docs, test_pdf_attachment_uploaded_as_new_document |
| `_dedup_email_threads` | test_email_thread_dedup.py | 4 tests | test_thread_keeps_longest_reply, test_exact_duplicates_flagged, test_different_threads_not_deduped, test_no_eml_docs_is_noop |
| `_resolve_letter_identity_context` | test_letter_identity_resolution.py | 2 tests | test_resolve_letter_identity_uses_profile_when_artifacts_missing, test_resolve_letter_identity_honors_override_precedence |
| `_build_gap_analysis_batches` | test_map_reduce_gap_analysis.py | 1+ tests | Various batch model tests (indirect) |

### Other Functions with Some Coverage

| Function | Test Files | Notes |
|---|---|---|
| `_fetch_gap_intake_content` | test_analysis_results_pending.py | 4 unit tests for intake payload handling |
| `_infer_signature_detection_from_text` | test_gap_resolution_helpers.py | 2 tests |
| `_derive_signature_detection_for_gap_doc` | test_gap_resolution_helpers.py | 4 tests |
| `_build_signature_evidence` | test_gap_resolution_helpers.py | 2 tests |
| `_build_case_document_state_hash` | test_gap_resolution_helpers.py | 1 test |
| `_build_gap_analysis_input_hash` | test_gap_resolution_helpers.py | 2 tests |
| `_build_gap_resolution_hash` | test_gap_resolution_helpers.py | 1 test |
| `_build_resolution_context` | test_gap_resolution_helpers.py | 1 test |
| `_build_supporting_document_hash` | test_gap_resolution_helpers.py | 2 tests |

## Test File Summary

### API Tests (Direct endpoint testing)
- **test_analysis.py**: 14 tests covering start_analysis, get_analysis_status, get_analysis_results, generate_findings_letter
- **test_analysis_results_pending.py**: 8 tests (3 for get_analysis_results pending logic, 4 for _fetch_gap_intake_content, 1 class)
- **test_letter_stream_integration.py**: 4 tests for stream_findings_letter with comprehensive event/budget testing
- **test_generate_letter_formatting.py**: 1 test for generate_letter HTML formatting
- **test_save_streaming_analysis.py**: 11 tests for save_streaming_analysis with schema validation
- **test_documents.py**: Document upload/verification tests, 1 for get_document_status
- **test_service_role_resilience.py**: 1 test for cancel_analysis resilience

### Unit Tests (Helper function testing)
- **test_deferred_extraction.py**: 5 tests for _extract_deferred_documents
- **test_email_thread_dedup.py**: 4 tests for _dedup_email_threads
- **test_letter_identity_resolution.py**: 2 tests for _resolve_letter_identity_context
- **test_gap_resolution_helpers.py**: 14 tests for gap analysis helpers
- **test_map_reduce_gap_analysis.py**: Gap analysis model and batching tests

## Migration Risks (No Test Coverage)

HIGH PRIORITY (14 uncovered endpoint functions):
1. `cancel_case_analysis` - Cancellation variant
2. `get_streaming_result` - Streaming result retrieval
3. `generate_recommendation_letter` - Recommendation letter generation
4. `stream_recommendation_letter` - Recommendation letter streaming
5. `calculate_demand_amount` - Financial calculation
6. `stream_chat_response` - Chat interface
7. `case_chat` - Chat endpoint
8. `analyze_gaps_on_demand` - On-demand gap analysis
9. `resolve_gaps_and_refresh` - Gap resolution workflow
10. `analyze_gaps_streaming` - Streaming gap analysis
11. `process_case_background` - Background processing
12. `stream_case_analysis` - Case analysis streaming
13. `retry_failed_documents` - Document retry logic
14. `skip_failed_documents` - Document skip logic
15. `get_analysis_state` - State retrieval

## Recommended Phased Rollout

### Phase 1: Already Covered (Safe to Deploy)
- start_analysis
- get_analysis_status
- get_analysis_results
- save_streaming_analysis
- generate_letter (basic)
- stream_findings_letter
- Helper functions for deferred extraction, dedup, identity resolution

### Phase 2: Needs Unit Tests
- cancel_analysis variants
- Streaming result retrieval
- gap analysis functions
- chat endpoints

### Phase 3: Integration Testing
- Recommend letter generation
- Demand amount calculation
- Full workflow streaming tests
