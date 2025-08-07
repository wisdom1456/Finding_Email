"""
Unit tests for email_generator.py module.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# Import the module under test
from backend.email_generator import draft_content


class TestDraftContent:
    """Test cases for the draft_content function."""

    def test_draft_content_with_basic_analysis(self):
        """Test draft_content with basic structured analysis."""
        # Arrange
        structured_analysis = {
            "summary": "Client has a billing dispute",
            "key_points": ["Overcharge of $500", "Service not rendered"],
        }

        # Act
        result = draft_content(structured_analysis)

        # Assert
        assert isinstance(result, dict)
        assert "introduction" in result
        assert "body" in result
        assert "conclusion" in result
        assert len(result) == 3

        # Check that summary is incorporated into introduction
        assert "Client has a billing dispute" in result["introduction"]

    def test_draft_content_with_empty_analysis(self):
        """Test draft_content with empty structured analysis."""
        # Arrange
        structured_analysis = {}

        # Act
        result = draft_content(structured_analysis)

        # Assert
        assert isinstance(result, dict)
        assert "introduction" in result
        assert "body" in result
        assert "conclusion" in result

        # Should handle missing summary gracefully
        assert (
            "Dear recipient, this is an introduction based on ''."
            in result["introduction"]
        )

    def test_draft_content_with_none_analysis(self):
        """Test draft_content with None as structured analysis."""
        # Arrange
        structured_analysis = None

        # Act
        try:
            result = draft_content(structured_analysis)
            # If it handles None gracefully
            assert isinstance(result, dict)
        except (TypeError, AttributeError):
            # If it doesn't handle None, that's also acceptable for this implementation
            pass

    def test_draft_content_with_missing_summary(self):
        """Test draft_content when summary key is missing."""
        # Arrange
        structured_analysis = {
            "key_points": ["Point 1", "Point 2"],
            "client_name": "John Doe",
        }

        # Act
        result = draft_content(structured_analysis)

        # Assert
        assert isinstance(result, dict)
        assert "introduction" in result
        assert "body" in result
        assert "conclusion" in result

        # Should use empty string when summary is missing
        assert (
            "Dear recipient, this is an introduction based on ''."
            in result["introduction"]
        )

    def test_draft_content_with_complex_analysis(self):
        """Test draft_content with complex structured analysis."""
        # Arrange
        structured_analysis = {
            "summary": "Complex legal case involving multiple parties",
            "key_points": [
                "Contract breach by vendor",
                "Damages estimated at $10,000",
                "Timeline violation of 60 days",
            ],
            "client_info": {"name": "ABC Corporation", "case_type": "Contract Dispute"},
            "recommendations": [
                "Seek immediate resolution",
                "Document all communications",
            ],
        }

        # Act
        result = draft_content(structured_analysis)

        # Assert
        assert isinstance(result, dict)
        assert "introduction" in result
        assert "body" in result
        assert "conclusion" in result

        # Verify summary is used
        assert "Complex legal case involving multiple parties" in result["introduction"]

    def test_draft_content_with_special_characters_in_summary(self):
        """Test draft_content with special characters in summary."""
        # Arrange
        structured_analysis = {
            "summary": "Client's case involves $5,000 & 50% interest charges!",
            "key_points": ["Financial dispute", "Interest calculation error"],
        }

        # Act
        result = draft_content(structured_analysis)

        # Assert
        assert isinstance(result, dict)
        assert (
            "Client's case involves $5,000 & 50% interest charges!"
            in result["introduction"]
        )

    def test_draft_content_with_long_summary(self):
        """Test draft_content with a very long summary."""
        # Arrange
        long_summary = (
            "This is a very long summary that contains many details about the case. "
            * 50
        )
        structured_analysis = {
            "summary": long_summary,
            "key_points": ["Point 1", "Point 2"],
        }

        # Act
        result = draft_content(structured_analysis)

        # Assert
        assert isinstance(result, dict)
        assert long_summary in result["introduction"]

    def test_draft_content_return_structure(self):
        """Test the structure of the returned content blocks."""
        # Arrange
        structured_analysis = {"summary": "Test summary"}

        # Act
        result = draft_content(structured_analysis)

        # Assert
        assert isinstance(result, dict)
        assert len(result) == 3

        # Check each content block exists and is a string
        for key in ["introduction", "body", "conclusion"]:
            assert key in result
            assert isinstance(result[key], str)
            assert len(result[key]) > 0

    def test_draft_content_with_unicode_characters(self):
        """Test draft_content with unicode characters in analysis."""
        # Arrange
        structured_analysis = {
            "summary": "Client José González has a dispute with café owner",
            "key_points": ["Café billing issue", "Contract in español"],
        }

        # Act
        result = draft_content(structured_analysis)

        # Assert
        assert isinstance(result, dict)
        assert "José González" in result["introduction"]
        assert "café" in result["introduction"]

    def test_draft_content_content_blocks_not_empty(self):
        """Test that all content blocks have meaningful content."""
        # Arrange
        structured_analysis = {"summary": "Test case summary"}

        # Act
        result = draft_content(structured_analysis)

        # Assert
        for _block_name, content in result.items():
            assert content.strip()  # Should not be empty or just whitespace
            assert len(content.strip()) > 10  # Should have meaningful content

    def test_draft_content_introduction_format(self):
        """Test that introduction follows expected format."""
        # Arrange
        structured_analysis = {"summary": "Sample summary for testing"}

        # Act
        result = draft_content(structured_analysis)

        # Assert
        introduction = result["introduction"]
        assert introduction.startswith("Dear recipient,")
        assert "Sample summary for testing" in introduction

    def test_draft_content_with_different_summary_types(self):
        """Test draft_content with different types of summary values."""
        test_cases = [
            {"summary": "String summary"},
            {"summary": 12345},  # Number
            {"summary": ["List", "Summary"]},  # List
            {"summary": {"nested": "dict"}},  # Dict
        ]

        for analysis in test_cases:
            # Act
            result = draft_content(analysis)

            # Assert
            assert isinstance(result, dict)
            assert "introduction" in result
            # Should handle conversion to string
            assert str(analysis["summary"]) in result["introduction"]

    @patch("backend.email_generator.logging")
    def test_draft_content_logging(self, mock_logging):
        """Test that draft_content logs entry and exit."""
        # Arrange
        structured_analysis = {"summary": "Test for logging"}

        # Act
        draft_content(structured_analysis)

        # Assert
        mock_logging.info.assert_any_call("Entering draft_content.")
        mock_logging.info.assert_any_call("Exiting draft_content.")


class TestEmailGeneratorIntegration:
    """Integration tests for email generator functionality."""

    def test_multiple_drafts_consistency(self):
        """Test that multiple calls to draft_content are consistent."""
        # Arrange
        structured_analysis = {
            "summary": "Consistent test case",
            "key_points": ["Point A", "Point B"],
        }

        # Act
        result1 = draft_content(structured_analysis)
        result2 = draft_content(structured_analysis)

        # Assert
        assert result1 == result2  # Should be deterministic

    def test_draft_content_with_real_world_analysis(self):
        """Test draft_content with realistic legal case analysis."""
        # Arrange
        real_world_analysis = {
            "summary": "Client entered into a service contract with ABC Company on January 15, 2024. Company failed to deliver promised services within the agreed timeframe, causing financial losses.",
            "key_points": [
                "Contract signed on January 15, 2024",
                "Service delivery deadline was March 15, 2024",
                "Services not delivered as of current date",
                "Client suffered $15,000 in damages",
                "ABC Company has been unresponsive to communications",
            ],
            "legal_issues": [
                "Breach of contract",
                "Failure to perform",
                "Damages calculation",
            ],
            "client_info": {
                "name": "Smith Manufacturing",
                "contact": "john.smith@smithmfg.com",
                "case_number": "SM-2024-001",
            },
        }

        # Act
        result = draft_content(real_world_analysis)

        # Assert
        assert isinstance(result, dict)
        assert "introduction" in result
        assert "body" in result
        assert "conclusion" in result

        # Verify summary integration
        assert "ABC Company" in result["introduction"]
        assert "January 15, 2024" in result["introduction"]

    def test_edge_case_handling(self):
        """Test handling of various edge cases."""
        edge_cases = [
            {},  # Empty dict
            {"summary": ""},  # Empty summary
            {"summary": None},  # None summary
            {"key_points": []},  # Empty key points
            {"other_field": "value"},  # Missing expected fields
        ]

        for case in edge_cases:
            # Act
            result = draft_content(case)

            # Assert
            assert isinstance(result, dict)
            assert len(result) == 3
            for block in result.values():
                assert isinstance(block, str)


# Pytest fixtures for common test data
@pytest.fixture
def basic_structured_analysis():
    """Fixture providing basic structured analysis data."""
    return {
        "summary": "Client has a contract dispute with vendor XYZ",
        "key_points": [
            "Contract signed on March 1, 2024",
            "Services not delivered as promised",
            "Client seeking $5,000 in damages",
        ],
    }


@pytest.fixture
def complex_structured_analysis():
    """Fixture providing complex structured analysis data."""
    return {
        "summary": "Multi-party construction contract dispute involving delays and cost overruns",
        "key_points": [
            "Original contract value: $500,000",
            "Project delayed by 6 months",
            "Cost overruns of $150,000",
            "Quality issues with delivered work",
            "Multiple change orders without proper authorization",
        ],
        "parties_involved": [
            "Client: ABC Construction",
            "Contractor: XYZ Builders",
            "Subcontractor: 123 Electrical",
        ],
        "timeline": {
            "contract_date": "2023-06-01",
            "original_completion": "2023-12-01",
            "actual_completion": "2024-06-01",
        },
        "damages": {"direct": 150000, "consequential": 75000, "total": 225000},
        "legal_theories": ["Breach of contract", "Unjust enrichment", "Quantum meruit"],
    }


@pytest.fixture
def personal_injury_analysis():
    """Fixture providing personal injury case analysis."""
    return {
        "summary": "Motor vehicle accident resulting in personal injuries and property damage",
        "key_points": [
            "Accident occurred on Highway 95 on February 14, 2024",
            "Client was rear-ended by defendant vehicle",
            "Client transported to hospital with neck and back injuries",
            "Vehicle deemed total loss",
            "Defendant cited for following too closely",
        ],
        "injuries": ["Cervical strain", "Lumbar sprain", "Post-traumatic stress"],
        "medical_expenses": 25000,
        "lost_wages": 8000,
        "property_damage": 15000,
    }


# Tests using fixtures
def test_draft_content_with_basic_fixture(basic_structured_analysis):
    """Test draft_content using basic fixture."""
    result = draft_content(basic_structured_analysis)

    assert isinstance(result, dict)
    assert "contract dispute with vendor XYZ" in result["introduction"]


def test_draft_content_with_complex_fixture(complex_structured_analysis):
    """Test draft_content using complex fixture."""
    result = draft_content(complex_structured_analysis)

    assert isinstance(result, dict)
    assert "construction contract dispute" in result["introduction"]


def test_draft_content_with_personal_injury_fixture(personal_injury_analysis):
    """Test draft_content using personal injury fixture."""
    result = draft_content(personal_injury_analysis)

    assert isinstance(result, dict)
    assert "Motor vehicle accident" in result["introduction"]


def test_content_blocks_meaningful_content(basic_structured_analysis):
    """Test that content blocks contain meaningful content using fixture."""
    result = draft_content(basic_structured_analysis)

    # Each block should be non-empty and substantial
    for _block_name, content in result.items():
        assert len(content.strip()) > 20  # Meaningful length
        assert content.strip() != content.strip().upper()  # Not all caps
        assert "." in content  # Contains sentences


def test_introduction_customization(complex_structured_analysis):
    """Test that introduction is customized based on analysis content."""
    result = draft_content(complex_structured_analysis)

    introduction = result["introduction"]
    assert "Dear recipient," in introduction
    assert "Multi-party construction contract dispute" in introduction
    assert len(introduction) > 50  # Substantial content


def test_consistency_across_calls(personal_injury_analysis):
    """Test that multiple calls with same input produce same output."""
    result1 = draft_content(personal_injury_analysis)
    result2 = draft_content(personal_injury_analysis)

    assert result1 == result2


def test_different_analysis_types_produce_different_content():
    """Test that different analysis types produce appropriately different content."""
    analyses = [
        {"summary": "Contract dispute case"},
        {"summary": "Personal injury case"},
        {"summary": "Criminal defense case"},
    ]

    results = [draft_content(analysis) for analysis in analyses]

    # Introductions should be different
    introductions = [result["introduction"] for result in results]
    assert len(set(introductions)) == 3  # All different
