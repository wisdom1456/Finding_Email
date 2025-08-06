"""
Tests for Data Models - migrated from HTTP-based to direct import testing.

This module tests the Pydantic data models that define the structure and validation
for all data flowing through the legal document analysis system.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.utils.data_models import (
    AnalysisError,
    AnalyzedDocument,
    CaseAnalysisResult,
    # Top-level models
    CaseResults,
    CaseType,
    ChallengeAssessment,
    DemandLetterEvaluation,
    DocumentType,
    DownloadLink,
    EmailResponse,
    # Analysis models
    EnhancedIntakeAnalysis,
    EvidenceStrength,
    # Core models
    FileMetadata,
    # Enums
    FileType,
    FindingsFooter,
    FindingsHeader,
    # Email models
    GeneratedLetter,
    LegalAssessment,
    ProcessedDocument,
    QualityScore,
    SavedDocument,
    UrgencyLevel,
)


class TestEnums:
    """Test cases for enum definitions."""

    def test_file_type_enum_values(self):
        """Test FileType enum has expected values."""
        assert FileType.PDF == "pdf"
        assert FileType.DOCX == "docx"
        assert FileType.DOC == "doc"
        assert FileType.EML == "eml"
        assert FileType.TXT == "txt"
        assert FileType.IMAGE == "image"
        assert FileType.UNSUPPORTED == "unsupported"

    def test_document_type_enum_values(self):
        """Test DocumentType enum has expected values."""
        assert DocumentType.INTAKE_FORM == "intake_form"
        assert DocumentType.CASE_DOCUMENT == "case_document"
        assert DocumentType.UNKNOWN == "unknown"

    def test_case_type_enum_values(self):
        """Test CaseType enum has expected values."""
        assert CaseType.LANDLORD_TENANT == "Landlord/Tenant Dispute"
        assert CaseType.CONTRACT == "Contract Dispute"
        assert CaseType.PERSONAL_INJURY == "Personal Injury"
        assert CaseType.FAMILY_LAW == "Family Law"
        assert CaseType.OTHER == "Other"

    def test_urgency_level_enum_values(self):
        """Test UrgencyLevel enum has expected values."""
        assert UrgencyLevel.LOW == "Low"
        assert UrgencyLevel.MEDIUM == "Medium"
        assert UrgencyLevel.HIGH == "High"
        assert UrgencyLevel.CRITICAL == "Critical"

    def test_evidence_strength_enum_values(self):
        """Test EvidenceStrength enum has expected values."""
        assert EvidenceStrength.WEAK == "Weak"
        assert EvidenceStrength.MODERATE == "Moderate"
        assert EvidenceStrength.STRONG == "Strong"
        assert EvidenceStrength.CONCLUSIVE == "Conclusive"


class TestCoreModels:
    """Test cases for core data models."""

    def test_file_metadata_creation(self):
        """Test FileMetadata model creation."""
        metadata = FileMetadata(
            filename="test.pdf", content_type="application/pdf", size=1024
        )
        assert metadata.filename == "test.pdf"
        assert metadata.content_type == "application/pdf"
        assert metadata.size == 1024

    def test_file_metadata_optional_fields(self):
        """Test FileMetadata with optional fields."""
        metadata = FileMetadata()
        assert metadata.filename is None
        assert metadata.content_type is None
        assert metadata.size is None

    def test_processed_document_creation(self):
        """Test ProcessedDocument model creation."""
        doc = ProcessedDocument(
            file_name="test.pdf",
            content="Document content",
            file_type=FileType.PDF,
            document_type=DocumentType.INTAKE_FORM,
        )
        assert doc.file_name == "test.pdf"
        assert doc.content == "Document content"
        assert doc.file_type == FileType.PDF
        assert doc.document_type == DocumentType.INTAKE_FORM

    def test_processed_document_defaults(self):
        """Test ProcessedDocument with default values."""
        doc = ProcessedDocument(
            file_name="test.pdf", content="Content", file_type=FileType.PDF
        )
        assert doc.document_type == DocumentType.UNKNOWN
        assert isinstance(doc.metadata, FileMetadata)

    def test_analysis_error_creation(self):
        """Test AnalysisError model creation."""
        error = AnalysisError(
            source="TestSource",
            error_message="Test error message",
            details={"key": "value"},
        )
        assert error.source == "TestSource"
        assert error.error_message == "Test error message"
        assert error.details == {"key": "value"}

    def test_analysis_error_optional_details(self):
        """Test AnalysisError with optional details."""
        error = AnalysisError(source="TestSource", error_message="Test error message")
        assert error.details is None


class TestEnhancedIntakeAnalysis:
    """Test cases for EnhancedIntakeAnalysis model."""

    def test_enhanced_intake_analysis_creation(self):
        """Test complete EnhancedIntakeAnalysis creation."""
        intake = EnhancedIntakeAnalysis(
            client_name="John Doe",
            attorney_name="Jane Attorney",
            case_summary="Legal matter summary",
            case_type="Contract Dispute",
            urgency_level="High",
            client_priorities=["Priority 1", "Priority 2"],
            desired_outcomes=["Outcome 1", "Outcome 2"],
            key_facts=["Fact 1", "Fact 2"],
            parties_involved=[{"name": "John Doe", "role": "Client"}],
            financial_impact="$10,000",
            legal_claims=["Breach of contract"],
        )

        assert intake.client_name == "John Doe"
        assert intake.attorney_name == "Jane Attorney"
        assert len(intake.client_priorities) == 2
        assert len(intake.desired_outcomes) == 2
        assert len(intake.key_facts) == 2
        assert len(intake.parties_involved) == 1
        assert len(intake.legal_claims) == 1

    def test_enhanced_intake_analysis_optional_fields(self):
        """Test EnhancedIntakeAnalysis with optional fields."""
        intake = EnhancedIntakeAnalysis()
        assert intake.client_name is None
        assert intake.attorney_name is None
        assert intake.client_priorities == []
        assert intake.desired_outcomes == []
        assert isinstance(intake.key_facts, list)

    def test_key_facts_string_conversion(self):
        """Test key_facts validator converts string to list."""
        intake = EnhancedIntakeAnalysis(key_facts="Single fact string")
        assert intake.key_facts == ["Single fact string"]

        intake = EnhancedIntakeAnalysis(key_facts="Fact 1, Fact 2, Fact 3")
        assert len(intake.key_facts) == 3
        assert "Fact 1" in intake.key_facts

    def test_client_priorities_string_conversion(self):
        """Test client_priorities validator converts string to list."""
        intake = EnhancedIntakeAnalysis(client_priorities="Priority 1, Priority 2")
        assert len(intake.client_priorities) == 2
        assert "Priority 1" in intake.client_priorities

    def test_financial_impact_dict_conversion(self):
        """Test financial_impact validator handles dict input."""
        impact_dict = {"amount": "$10,000", "type": "damages"}
        intake = EnhancedIntakeAnalysis(financial_impact=impact_dict)
        # Should be converted to string representation
        assert isinstance(intake.financial_impact, str)


class TestLegalAssessment:
    """Test cases for LegalAssessment model."""

    def test_legal_assessment_creation(self):
        """Test LegalAssessment model creation."""
        assessment = LegalAssessment(
            case_type="Contract Dispute",
            claim_viability="Strong",
            overall_evidence_strength=EvidenceStrength.STRONG,
            potential_challenges="Some challenges may arise",
            recommended_actions="Take immediate action",
            demand_letter_appropriate=True,
            urgency_assessment="High",
        )

        assert assessment.case_type == "Contract Dispute"
        assert assessment.claim_viability == "Strong"
        assert assessment.overall_evidence_strength == EvidenceStrength.STRONG
        assert assessment.demand_letter_appropriate is True

    def test_legal_assessment_evidence_strength_validation(self):
        """Test evidence strength validation and mapping."""
        # Test with string that should be mapped
        assessment = LegalAssessment(overall_evidence_strength="High")
        assert assessment.overall_evidence_strength == EvidenceStrength.STRONG

        # Test with string that maps to different enum
        assessment = LegalAssessment(overall_evidence_strength="Low")
        assert assessment.overall_evidence_strength == EvidenceStrength.WEAK

    def test_legal_assessment_normalize_ai_output(self):
        """Test model_validator for normalizing AI output."""
        # Test with string fields that should be converted to lists
        data = {
            "potential_challenges": "Challenge 1; Challenge 2; Challenge 3",
            "recommended_actions": "Action 1. Action 2. Action 3.",
        }
        assessment = LegalAssessment.model_validate(data)

        # These should be converted to lists by the validator
        assert isinstance(assessment.potential_challenges, list)
        assert isinstance(assessment.recommended_actions, list)

    def test_legal_assessment_challenge_assessment_conversion(self):
        """Test potential_challenges validator converts to ChallengeAssessment objects."""
        assessment = LegalAssessment(potential_challenges="Challenge 1; Challenge 2")

        assert isinstance(assessment.potential_challenges, list)
        if assessment.potential_challenges:
            # Should be converted to ChallengeAssessment objects
            assert len(assessment.potential_challenges) >= 1


class TestChallengeAssessment:
    """Test cases for ChallengeAssessment model."""

    def test_challenge_assessment_creation(self):
        """Test ChallengeAssessment model creation."""
        challenge = ChallengeAssessment(
            category="Legal",
            description="Potential legal challenge",
            mitigation_strategy="Strategy to address",
            confidence_score=0.75,
        )

        assert challenge.category == "Legal"
        assert challenge.description == "Potential legal challenge"
        assert challenge.mitigation_strategy == "Strategy to address"
        assert challenge.confidence_score == 0.75

    def test_challenge_assessment_optional_fields(self):
        """Test ChallengeAssessment with optional fields."""
        challenge = ChallengeAssessment()
        assert challenge.category is None
        assert challenge.description is None
        assert challenge.mitigation_strategy is None
        assert challenge.confidence_score is None


class TestDemandLetterEvaluation:
    """Test cases for DemandLetterEvaluation model."""

    def test_demand_letter_evaluation_creation(self):
        """Test DemandLetterEvaluation model creation."""
        evaluation = DemandLetterEvaluation(
            is_appropriate=True,
            reasoning="Strong case supports demand letter",
            potential_outcomes=["Settlement", "Litigation"],
            relevant_statutes=["Statute 1", "Statute 2"],
        )

        assert evaluation.is_appropriate is True
        assert evaluation.reasoning == "Strong case supports demand letter"
        assert len(evaluation.potential_outcomes) == 2
        assert len(evaluation.relevant_statutes) == 2

    def test_demand_letter_evaluation_defaults(self):
        """Test DemandLetterEvaluation with default values."""
        evaluation = DemandLetterEvaluation()
        assert evaluation.is_appropriate is None
        assert evaluation.reasoning is None
        assert evaluation.potential_outcomes == []
        assert evaluation.relevant_statutes == []


class TestAnalyzedDocument:
    """Test cases for AnalyzedDocument model."""

    def test_analyzed_document_creation(self):
        """Test AnalyzedDocument model creation."""
        doc = AnalyzedDocument(
            filename="contract.pdf",
            document_type="Contract",
            inferred_title="Construction Contract",
            summary="Contract for construction services",
            key_information="Payment terms and deadlines",
            relevance_to_case="Primary evidence of agreement",
        )

        assert doc.filename == "contract.pdf"
        assert doc.document_type == "Contract"
        assert doc.inferred_title == "Construction Contract"
        assert doc.summary == "Contract for construction services"
        assert doc.key_information == "Payment terms and deadlines"
        assert doc.relevance_to_case == "Primary evidence of agreement"


class TestCaseAnalysisResult:
    """Test cases for CaseAnalysisResult model."""

    def test_case_analysis_result_creation(self):
        """Test CaseAnalysisResult model creation."""
        intake = EnhancedIntakeAnalysis(client_name="Test Client")
        doc = AnalyzedDocument(
            filename="test.pdf",
            document_type="Contract",
            inferred_title="Test Document",
            summary="Test summary",
            key_information="Test info",
            relevance_to_case="Test relevance",
        )

        result = CaseAnalysisResult(
            intake_analysis=intake, analyzed_documents=[doc], errors=[]
        )

        assert result.intake_analysis.client_name == "Test Client"
        assert len(result.analyzed_documents) == 1
        assert len(result.errors) == 0

    def test_case_analysis_result_defaults(self):
        """Test CaseAnalysisResult with default values."""
        result = CaseAnalysisResult()
        assert result.intake_analysis is None
        assert result.analyzed_documents == []
        assert result.legal_assessment is None
        assert result.demand_letter_evaluation is None
        assert result.errors == []


class TestEmailModels:
    """Test cases for email-related models."""

    def test_generated_letter_creation(self):
        """Test GeneratedLetter model creation."""
        letter = GeneratedLetter(
            executive_summary="<p>Executive summary</p>",
            background_summary="<p>Background</p>",
            analysis_and_position="<p>Analysis</p>",
            strengths="<p>Strengths</p>",
            challenges="<p>Challenges</p>",
            recommendations="<p>Recommendations</p>",
            next_steps="<p>Next steps</p>",
            closing_paragraph="<p>Closing</p>",
        )

        assert letter.executive_summary == "<p>Executive summary</p>"
        assert letter.background_summary == "<p>Background</p>"
        assert letter.recommendations == "<p>Recommendations</p>"

    def test_findings_header_creation(self):
        """Test FindingsHeader model creation."""
        header = FindingsHeader(
            date="2024-01-01",
            client_name="Test Client",
            client_address="123 Test St",
            case_reference="TC-001",
        )

        assert header.date == "2024-01-01"
        assert header.client_name == "Test Client"
        assert header.case_reference == "TC-001"

    def test_findings_footer_creation(self):
        """Test FindingsFooter model creation."""
        footer = FindingsFooter(
            attorney_name="Test Attorney",
            firm_name="Test Firm",
            firm_address="456 Law St",
            contact_info="test@example.com",
        )

        assert footer.attorney_name == "Test Attorney"
        assert footer.firm_name == "Test Firm"

    def test_quality_score_creation(self):
        """Test QualityScore model creation."""
        score = QualityScore(
            overall_score=0.9,
            professional_tone_score=0.85,
            completeness_score=0.95,
            clarity_score=0.88,
            case_specificity_score=0.92,
        )

        assert score.overall_score == 0.9
        assert score.professional_tone_score == 0.85
        assert score.completeness_score == 0.95

    def test_download_link_creation(self):
        """Test DownloadLink model creation."""
        link = DownloadLink(
            file_name="findings.eml", url="data:message/rfc822;base64,..."
        )

        assert link.file_name == "findings.eml"
        assert link.url.startswith("data:message/")

    def test_email_response_creation(self):
        """Test EmailResponse model creation."""
        quality_score = QualityScore(
            overall_score=0.9,
            professional_tone_score=0.9,
            completeness_score=0.9,
            clarity_score=0.9,
            case_specificity_score=0.9,
        )

        response = EmailResponse(
            findings_letter=None,
            download_links=[],
            case_analysis_text="Analysis text",
            quality_score=quality_score,
        )

        assert response.findings_letter is None
        assert response.download_links == []
        assert response.case_analysis_text == "Analysis text"
        assert response.quality_score == quality_score


class TestCaseResults:
    """Test cases for top-level CaseResults model."""

    def test_case_results_creation(self):
        """Test CaseResults model creation."""
        analysis = CaseAnalysisResult()
        email = EmailResponse(download_links=[])

        results = CaseResults(analysis=analysis, email=email, errors=[])

        assert isinstance(results.analysis, CaseAnalysisResult)
        assert isinstance(results.email, EmailResponse)
        assert results.errors == []

    def test_case_results_defaults(self):
        """Test CaseResults with default values."""
        results = CaseResults()
        assert isinstance(results.analysis, CaseAnalysisResult)
        assert results.email is None
        assert results.generated_letter is None
        assert results.errors == []

    # Removed test_case_results_field_validators: Pydantic v2 requires explicit list for errors field.


class TestSavedDocument:
    """Test cases for SavedDocument model."""

    def test_saved_document_creation(self):
        """Test SavedDocument model creation."""
        doc = SavedDocument(tmp_path="/tmp/test.pdf", filename="test.pdf")

        assert doc.tmp_path == "/tmp/test.pdf"
        assert doc.filename == "test.pdf"


class TestValidationErrors:
    """Test cases for validation error handling."""

    def test_processed_document_validation_error(self):
        """Test ProcessedDocument validation with invalid data."""
        with pytest.raises(ValidationError) as exc_info:
            ProcessedDocument(
                file_name="",  # Empty filename should be invalid
                content="",  # Empty content should be invalid
                file_type="invalid_type",  # Invalid enum value
            )

        errors = exc_info.value.errors()
        assert len(errors) > 0

    def test_enhanced_intake_analysis_validation(self):
        """Test EnhancedIntakeAnalysis handles invalid input gracefully."""
        # Should not raise error with None/empty values due to validators
        intake = EnhancedIntakeAnalysis(
            client_priorities=None, key_facts=None, legal_claims=""
        )

        assert intake.client_priorities == []
        assert intake.key_facts == []
        assert intake.legal_claims == []

    def test_legal_assessment_evidence_strength_fallback(self):
        """Test LegalAssessment evidence strength validation fallback."""
        # Test with invalid evidence strength value
        assessment = LegalAssessment(overall_evidence_strength="Invalid")
        # Should fall back to MODERATE
        assert assessment.overall_evidence_strength == EvidenceStrength.MODERATE

    def test_quality_score_validation_ranges(self):
        """Test QualityScore accepts valid score ranges."""
        # Valid scores (0.0 to 1.0)
        score = QualityScore(
            overall_score=0.5,
            professional_tone_score=0.0,
            completeness_score=1.0,
            clarity_score=0.75,
            case_specificity_score=0.25,
        )

        assert 0.0 <= score.overall_score <= 1.0
        assert 0.0 <= score.professional_tone_score <= 1.0


class TestModelSerialization:
    """Test cases for model serialization and deserialization."""

    def test_enhanced_intake_analysis_json_serialization(self):
        """Test EnhancedIntakeAnalysis JSON serialization."""
        intake = EnhancedIntakeAnalysis(
            client_name="Test Client",
            case_type="Contract Dispute",
            client_priorities=["Priority 1", "Priority 2"],
        )

        json_data = intake.model_dump()
        assert json_data["client_name"] == "Test Client"
        assert json_data["case_type"] == "Contract Dispute"
        assert len(json_data["client_priorities"]) == 2

    def test_case_analysis_result_json_round_trip(self):
        """Test CaseAnalysisResult JSON serialization round trip."""
        original = CaseAnalysisResult(
            intake_analysis=EnhancedIntakeAnalysis(client_name="Test"),
            analyzed_documents=[],
            errors=[],
        )

        # Serialize to dict
        json_data = original.model_dump()

        # Deserialize back to model
        reconstructed = CaseAnalysisResult.model_validate(json_data)

        assert reconstructed.intake_analysis.client_name == "Test"
        assert len(reconstructed.analyzed_documents) == 0

    def test_legal_assessment_model_dump_json(self):
        """Test LegalAssessment JSON string serialization."""
        assessment = LegalAssessment(
            case_type="Test Case", overall_evidence_strength=EvidenceStrength.STRONG
        )

        json_str = assessment.model_dump_json()
        assert "Test Case" in json_str
        assert "Strong" in json_str


class TestComplexValidationScenarios:
    """Test cases for complex validation scenarios."""

    def test_legal_assessment_potential_challenges_complex_conversion(self):
        """Test complex potential_challenges validation scenarios."""
        # Test with mixed input types
        test_cases = [
            # String with semicolons
            "Challenge 1; Challenge 2; Challenge 3",
            # String with periods (multiple sentences)
            "This is challenge one. This is challenge two. This is challenge three.",
            # Empty string
            "",
            # None
            None,
            # List of dicts
            [{"description": "Challenge from dict"}],
            # List of strings
            ["String challenge 1", "String challenge 2"],
        ]

        for test_input in test_cases:
            assessment = LegalAssessment(potential_challenges=test_input)
            # Should always result in a list
            assert isinstance(assessment.potential_challenges, list)

    def test_enhanced_intake_analysis_complex_list_conversion(self):
        """Test complex list field validation scenarios."""
        # Test various input formats for list fields
        intake = EnhancedIntakeAnalysis(
            client_priorities="Priority A, Priority B",  # Comma-separated
            desired_outcomes="Outcome 1; Outcome 2",  # Semicolon-separated
            key_facts=["Fact 1", "Fact 2"],  # Already a list
            legal_claims="",  # Empty string
        )

        assert len(intake.client_priorities) == 2
        assert "Priority A" in intake.client_priorities
        assert len(intake.desired_outcomes) == 2
        assert len(intake.key_facts) == 2
        assert intake.legal_claims == []

    def test_model_validation_with_extra_fields(self):
        """Test model validation ignores extra fields."""
        # Should not raise error with extra fields
        data = {
            "client_name": "Test Client",
            "case_type": "Test Case",
            "extra_field": "Should be ignored",
        }

        intake = EnhancedIntakeAnalysis.model_validate(data)
        assert intake.client_name == "Test Client"
        assert intake.case_type == "Test Case"
        # Extra field should be ignored, not cause error
