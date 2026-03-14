"""Tests for the centralized exception hierarchy."""

from legal_portal.core.exceptions import (
    AnalysisPipelineError,
    AppError,
    AuthorizationError,
    ExternalServiceError,
    NotFoundError,
    TransientDatabaseError,
    ValidationError,
)


class TestAppError:
    def test_default_status_code(self):
        err = AppError("something broke")
        assert err.status_code == 500

    def test_default_error_code(self):
        err = AppError("something broke")
        assert err.error_code == "INTERNAL_ERROR"

    def test_message_stored(self):
        err = AppError("something broke")
        assert err.message == "something broke"
        assert str(err) == "something broke"

    def test_context_defaults_to_empty(self):
        err = AppError("x")
        assert err.context == {}

    def test_context_stored(self):
        err = AppError("x", context={"doc_id": "123"})
        assert err.context == {"doc_id": "123"}

    def test_error_code_override(self):
        err = AppError("x", error_code="CUSTOM")
        assert err.error_code == "CUSTOM"

    def test_to_log_dict(self):
        err = AppError("oops", context={"k": "v"}, error_code="MY_CODE")
        d = err.to_log_dict()
        assert d["error_type"] == "AppError"
        assert d["error_code"] == "MY_CODE"
        assert d["error_message"] == "oops"
        assert d["context"] == {"k": "v"}

    def test_is_exception(self):
        assert issubclass(AppError, Exception)


class TestSubclasses:
    def test_validation_error(self):
        err = ValidationError("bad input")
        assert err.status_code == 422
        assert err.error_code == "VALIDATION_ERROR"
        assert isinstance(err, AppError)

    def test_authorization_error(self):
        err = AuthorizationError("forbidden")
        assert err.status_code == 403
        assert err.error_code == "AUTHORIZATION_ERROR"
        assert isinstance(err, AppError)

    def test_not_found_error(self):
        err = NotFoundError("missing")
        assert err.status_code == 404
        assert err.error_code == "NOT_FOUND"
        assert isinstance(err, AppError)

    def test_external_service_error(self):
        err = ExternalServiceError("upstream down")
        assert err.status_code == 502
        assert err.error_code == "EXTERNAL_SERVICE_ERROR"
        assert isinstance(err, AppError)

    def test_transient_database_error(self):
        err = TransientDatabaseError("timeout")
        assert err.status_code == 503
        assert err.error_code == "TRANSIENT_DATABASE_ERROR"
        assert isinstance(err, AppError)

    def test_analysis_pipeline_error(self):
        err = AnalysisPipelineError("pipeline failed")
        assert err.status_code == 500
        assert err.error_code == "ANALYSIS_PIPELINE_ERROR"
        assert isinstance(err, AppError)

    def test_subclass_inherits_to_log_dict(self):
        err = NotFoundError("gone", context={"id": "42"})
        d = err.to_log_dict()
        assert d["error_type"] == "NotFoundError"
        assert d["error_code"] == "NOT_FOUND"

    def test_subclass_error_code_override(self):
        err = ValidationError("bad", error_code="CUSTOM_VALIDATION")
        assert err.error_code == "CUSTOM_VALIDATION"
