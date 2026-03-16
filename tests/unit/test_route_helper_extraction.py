"""Tests for PR-A: Route helper extraction.

Verifies that all symbols moved to core.analysis_state and core.signature_detection
are importable from both their new canonical locations and the backward-compatible
re-export in api.routes._analysis_helpers.
"""

from __future__ import annotations


SIGNATURE_DETECTION_SYMBOLS = [
    "_SIGNATURE_TEXT_FALLBACK_PATTERNS",
    "_TEXT_SIGNING_DATE_PATTERNS",
    "_SIGNER_NAME_PATTERNS",
    "_SIGNATURE_INSTRUMENT_HINT_PATTERNS",
    "_SIGNATURE_VERIFICATION_STATUS_ALIASES",
    "_normalize_signature_verification_status",
    "_extract_signature_verification",
    "_apply_signature_verification_override",
    "_normalize_text_signing_date",
    "_infer_signature_detection_from_text",
    "_is_pdf_like_document",
    "_is_signature_inference_candidate",
    "_sample_text_for_state_hash",
    "_extract_signature_instrument_hints",
]

ANALYSIS_STATE_SYMBOLS = [
    "DBColumnsCache",
    "_db_columns_cache",
    "_GAP_ANALYSIS_INPUT_SCHEMA_VERSION",
    "AnalysisCancelledError",
    "_upsert_with_retry",
    "_update_case_with_retry",
    "_analysis_is_cancelled",
    "_cancel_analysis",
    "_update_analysis_progress",
    "_get_user_ai_preferences",
    "_first_non_empty_text",
    "_resolve_letter_identity_context",
    "_resolve_client_name_for_letter",
]


class TestSignatureDetectionCanonicalImports:
    """All signature detection symbols importable from core.signature_detection."""

    def test_all_symbols_importable(self):
        import legal_portal.core.signature_detection as mod

        for name in SIGNATURE_DETECTION_SYMBOLS:
            assert hasattr(mod, name), f"Missing: {name}"

    def test_module_all_matches(self):
        from legal_portal.core.signature_detection import __all__

        assert set(__all__) == set(SIGNATURE_DETECTION_SYMBOLS)


class TestAnalysisStateCanonicalImports:
    """All analysis state symbols importable from core.analysis_state."""

    def test_all_symbols_importable(self):
        import legal_portal.core.analysis_state as mod

        for name in ANALYSIS_STATE_SYMBOLS:
            assert hasattr(mod, name), f"Missing: {name}"

    def test_module_all_matches(self):
        from legal_portal.core.analysis_state import __all__

        assert set(__all__) == set(ANALYSIS_STATE_SYMBOLS)


class TestReExportCompatibility:
    """All moved symbols still importable from api.routes._analysis_helpers."""

    def test_signature_symbols_reexported(self):
        import legal_portal.api.routes._analysis_helpers as mod

        for name in SIGNATURE_DETECTION_SYMBOLS:
            assert hasattr(mod, name), f"Missing re-export: {name}"

    def test_analysis_state_symbols_reexported(self):
        import legal_portal.api.routes._analysis_helpers as mod

        for name in ANALYSIS_STATE_SYMBOLS:
            assert hasattr(mod, name), f"Missing re-export: {name}"

    def test_helpers_all_contains_moved_symbols(self):
        from legal_portal.api.routes._analysis_helpers import __all__

        all_moved = set(SIGNATURE_DETECTION_SYMBOLS + ANALYSIS_STATE_SYMBOLS)
        assert all_moved.issubset(set(__all__)), (
            f"Missing from __all__: {all_moved - set(__all__)}"
        )

    def test_route_only_symbols_still_present(self):
        """Route-specific helpers and models must still exist in _analysis_helpers."""
        from legal_portal.api.routes._analysis_helpers import (
            _ensure_case_access,
            _fetch_latest_analysis_result,
            _new_generation_metrics,
            _emit_generation_metrics,
            _to_sse,
            _quality_report_placeholder,
            AnalysisRequest,
            AnalysisResponse,
            LetterGenerationRequest,
            GapAnalysisRequest,
        )

        assert callable(_ensure_case_access)
        assert callable(_new_generation_metrics)
        assert AnalysisRequest is not None


class TestClassifyDocumentTypeImport:
    """classify_document_type importable from extraction_service (canonical)."""

    def test_importable_from_extraction_service(self):
        from legal_portal.services.documents.extraction_service import classify_document_type

        assert callable(classify_document_type)

    def test_still_importable_from_documents_route(self):
        from legal_portal.api.routes.documents import classify_document_type

        assert callable(classify_document_type)
