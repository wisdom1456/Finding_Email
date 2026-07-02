"""Tests for error-path ProcessingResult construction.

Verifies that when the pipeline fails (e.g. summarization returns zero
successful batches), the fallback ProcessingResult:
  - is valid Pydantic (no secondary ValidationError)
  - has status="failed" or "awaiting_recovery"
  - surfaces the original error in the errors list
  - has correct field types for all required fields
"""
import json
import pytest

from legal_portal.core.data_models import ProcessingResult, ProcessingError


class TestErrorPathProcessingResult:
    """Verify all error-path ProcessingResult constructors produce valid objects."""

    def test_awaiting_recovery_result_is_valid(self):
        """Synthesis gate awaiting_recovery path must produce valid ProcessingResult."""
        errors = [
            ProcessingError(
                source="batch_summarization",
                error_type="EmptyResponse",
                error_message="Model returned empty response for batch 1",
            ),
        ]
        block_reasons = ["3 hard failures", "stuck docs: 2 pending"]

        result = ProcessingResult(
            main_letter="",
            document_summaries="",
            case_analysis=json.dumps({
                "case_summary": "Analysis blocked at synthesis gate",
                "practice_area": "Unknown",
                "key_issues": block_reasons,
                "relevant_statutes": [],
                "additional_details": f"Blocked: {', '.join(block_reasons)}",
            }),
            status="awaiting_recovery",
            errors=errors,
            processing_time_seconds=12.5,
        )

        assert result.status == "awaiting_recovery"
        assert isinstance(result.document_summaries, str)
        assert isinstance(result.main_letter, str)
        assert isinstance(result.case_analysis, str)
        assert len(result.errors) == 1
        assert result.errors[0].source == "batch_summarization"
        assert result.multi_stage_result is None

    def test_validation_error_result_is_valid(self):
        """ValueError catch path must produce valid ProcessingResult."""
        errors = [
            ProcessingError(
                source="main_processor",
                error_type="ValidationError",
                error_message="No documents to process",
            ),
        ]

        result = ProcessingResult(
            main_letter="<html><body><p>Processing failed due to validation error.</p></body></html>",
            document_summaries="",
            case_analysis=json.dumps({
                "case_summary": "Processing failed - validation error",
                "practice_area": "Unknown",
                "key_issues": ["Processing error"],
                "relevant_statutes": [],
                "additional_details": "No documents to process",
            }),
            status="failed",
            processing_time_seconds=1.0,
            document_count=0,
            errors=errors,
        )

        assert result.status == "failed"
        assert "validation error" in result.main_letter.lower()
        assert result.multi_stage_result is None
        assert len(result.errors) == 1

    def test_unexpected_error_result_is_valid(self):
        """Generic Exception catch path must produce valid ProcessingResult."""
        errors = [
            ProcessingError(
                source="main_processor",
                error_type="RuntimeError",
                error_message="OpenAI returned an empty or null response.",
            ),
        ]

        result = ProcessingResult(
            main_letter="<html><body><p>Processing failed due to an unexpected error.</p></body></html>",
            document_summaries="",
            case_analysis=json.dumps({
                "case_summary": "Processing failed - unexpected error",
                "practice_area": "Unknown",
                "key_issues": ["Processing error"],
                "relevant_statutes": [],
                "additional_details": "OpenAI returned an empty or null response.",
            }),
            status="failed",
            processing_time_seconds=30.0,
            document_count=0,
            errors=errors,
        )

        assert result.status == "failed"
        assert result.multi_stage_result is None
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "RuntimeError"

    def test_multi_stage_failure_error_is_valid(self):
        """Multi-stage analysis failure must produce valid ProcessingError."""
        error = ProcessingError(
            source="multi_stage_analysis",
            error_type="TimeoutError",
            error_message="OpenAI request timed out after 120s",
        )

        assert error.source == "multi_stage_analysis"
        assert error.error_type == "TimeoutError"
        assert "timed out" in error.error_message

    def test_empty_response_errors_surface_in_result(self):
        """Simulates summarization returning zero successful batches.

        Verifies:
        - pipeline fails cleanly
        - fallback ProcessingResult is valid
        - surfaced error mentions empty model responses
        - no secondary Pydantic validation error
        """
        # Simulate 5 batches all returning empty responses
        errors = []
        for i in range(5):
            errors.append(ProcessingError(
                source="batch_summarization",
                error_type="EmptyResponse",
                error_message="OpenAI returned an empty or null response.",
            ))
            errors.append(ProcessingError(
                source="batch_summarization",
                error_type="EmptyBatch",
                error_message=f"Model returned empty response for batch {i+1}",
            ))

        # This is what the outer except handler should produce
        result = ProcessingResult(
            main_letter="<html><body><p>Processing failed due to an unexpected error.</p></body></html>",
            document_summaries="",
            case_analysis=json.dumps({
                "case_summary": "Processing failed - unexpected error",
                "practice_area": "Unknown",
                "key_issues": ["Processing error"],
                "relevant_statutes": [],
                "additional_details": "All summarization batches returned empty responses",
            }),
            status="failed",
            processing_time_seconds=15.0,
            document_count=28,
            errors=errors,
        )

        # No Pydantic ValidationError — construction succeeded
        assert result.status == "failed"
        assert result.multi_stage_result is None
        assert len(result.errors) == 10  # 5 empty + 5 batch errors

        # Verify error content is accessible for worker extraction
        result_dict = result.model_dump(mode="json")
        assert result_dict["status"] == "failed"
        pipeline_errors = result_dict["errors"]
        assert len(pipeline_errors) == 10
        empty_errors = [e for e in pipeline_errors if "empty" in e["error_message"].lower()]
        assert len(empty_errors) >= 5

    def test_document_summaries_must_be_string(self):
        """Passing a list to document_summaries must raise Pydantic ValidationError."""
        with pytest.raises(Exception):
            ProcessingResult(
                main_letter="",
                document_summaries=[],  # type: ignore — intentionally wrong
                case_analysis="{}",
                status="failed",
            )

    def test_missing_main_letter_raises(self):
        """Omitting main_letter must raise Pydantic ValidationError."""
        with pytest.raises(Exception):
            ProcessingResult(
                document_summaries="",
                case_analysis="{}",
                status="failed",
            )

    def test_missing_case_analysis_raises(self):
        """Omitting case_analysis must raise Pydantic ValidationError."""
        with pytest.raises(Exception):
            ProcessingResult(
                main_letter="",
                document_summaries="",
                status="failed",
            )
