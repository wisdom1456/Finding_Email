"""
Unit tests for template_assembler.py module.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from jinja2 import FileSystemLoader, TemplateNotFound, TemplateSyntaxError

# Import the module under test
from backend.template_assembler import populate_template


class TestPopulateTemplate:
    """Test cases for the populate_template function."""

    @patch("backend.template_assembler.Environment")
    def test_populate_template_basic_functionality(self, mock_env_class):
        """Test basic template population functionality."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<h1>Test Content</h1>"

        content_blocks = {
            "introduction": "Hello World",
            "body": "This is the body",
            "conclusion": "Goodbye",
        }
        template_path = "test_template.html"

        # Act
        result = populate_template(content_blocks, template_path)

        # Assert
        assert result == "<h1>Test Content</h1>"
        mock_env_class.assert_called_once_with(loader=FileSystemLoader("."))
        mock_env.get_template.assert_called_once_with(template_path)
        mock_template.render.assert_called_once_with(content_blocks)

    @patch("backend.template_assembler.Environment")
    def test_populate_template_with_empty_content_blocks(self, mock_env_class):
        """Test populate_template with empty content blocks."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html><body></body></html>"

        content_blocks = {}
        template_path = "empty_template.html"

        # Act
        result = populate_template(content_blocks, template_path)

        # Assert
        assert result == "<html><body></body></html>"
        mock_template.render.assert_called_once_with(content_blocks)

    @patch("backend.template_assembler.Environment")
    def test_populate_template_with_complex_content_blocks(self, mock_env_class):
        """Test populate_template with complex content blocks."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Complex Template Result</html>"

        content_blocks = {
            "client_name": "John Doe",
            "case_number": "CASE-2024-001",
            "introduction": "Dear Mr. Doe,",
            "body": "This letter concerns your case...",
            "conclusion": "Please contact us if you have questions.",
            "signature": "Attorney Name",
            "date": "2024-01-15",
            "attachments": ["Document1.pdf", "Document2.pdf"],
            "legal_disclaimer": "This communication is confidential...",
        }
        template_path = "legal_letter_template.html"

        # Act
        result = populate_template(content_blocks, template_path)

        # Assert
        assert result == "<html>Complex Template Result</html>"
        mock_template.render.assert_called_once_with(content_blocks)

    @patch("backend.template_assembler.Environment")
    def test_populate_template_with_special_characters(self, mock_env_class):
        """Test populate_template with special characters in content."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = (
            "<html>Special chars: ñáéíóú & $5,000</html>"
        )

        content_blocks = {
            "client_name": "José González",
            "amount": "$5,000",
            "description": "Contract with café & restaurant",
        }
        template_path = "template.html"

        # Act
        result = populate_template(content_blocks, template_path)

        # Assert
        assert result == "<html>Special chars: ñáéíóú & $5,000</html>"

    @patch("backend.template_assembler.Environment")
    def test_populate_template_template_not_found(self, mock_env_class):
        """Test populate_template when template file is not found."""
        # Arrange
        mock_env = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.side_effect = TemplateNotFound("template_not_found.html")

        content_blocks = {"test": "content"}
        template_path = "nonexistent_template.html"

        # Act & Assert
        with pytest.raises(TemplateNotFound):
            populate_template(content_blocks, template_path)

    @patch("backend.template_assembler.Environment")
    def test_populate_template_template_syntax_error(self, mock_env_class):
        """Test populate_template when template has syntax errors."""
        # Arrange
        mock_env = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.side_effect = TemplateSyntaxError(
            "Invalid syntax", 1, "template.html"
        )

        content_blocks = {"test": "content"}
        template_path = "bad_syntax_template.html"

        # Act & Assert
        with pytest.raises(TemplateSyntaxError):
            populate_template(content_blocks, template_path)

    @patch("backend.template_assembler.Environment")
    def test_populate_template_render_error(self, mock_env_class):
        """Test populate_template when template rendering fails."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.side_effect = Exception("Rendering failed")

        content_blocks = {"test": "content"}
        template_path = "template.html"

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            populate_template(content_blocks, template_path)
        assert "Rendering failed" in str(exc_info.value)

    @patch("backend.template_assembler.Environment")
    def test_populate_template_different_template_paths(self, mock_env_class):
        """Test populate_template with different template path formats."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Template Result</html>"

        content_blocks = {"test": "content"}

        template_paths = [
            "template.html",
            "templates/template.html",
            "assets/templates/legal_template.html",
            "../templates/shared_template.html",
            "template_with_underscores.html",
            "template-with-dashes.html",
        ]

        # Act & Assert
        for path in template_paths:
            result = populate_template(content_blocks, path)
            assert result == "<html>Template Result</html>"
            mock_env.get_template.assert_called_with(path)

    @patch("backend.template_assembler.Environment")
    def test_populate_template_with_none_values(self, mock_env_class):
        """Test populate_template with None values in content blocks."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Content with None values</html>"

        content_blocks = {
            "introduction": "Hello",
            "body": None,
            "conclusion": "Goodbye",
            "optional_field": None,
        }
        template_path = "template.html"

        # Act
        result = populate_template(content_blocks, template_path)

        # Assert
        assert result == "<html>Content with None values</html>"
        mock_template.render.assert_called_once_with(content_blocks)

    @patch("backend.template_assembler.Environment")
    def test_populate_template_with_nested_content(self, mock_env_class):
        """Test populate_template with nested content structures."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Nested content rendered</html>"

        content_blocks = {
            "client_info": {
                "name": "John Doe",
                "address": "123 Main St",
                "phone": "(555) 123-4567",
            },
            "case_details": {
                "number": "CASE-001",
                "type": "Contract Dispute",
                "status": "Active",
            },
            "documents": [
                {"name": "Contract.pdf", "size": "2MB"},
                {"name": "Invoice.pdf", "size": "1MB"},
            ],
        }
        template_path = "complex_template.html"

        # Act
        result = populate_template(content_blocks, template_path)

        # Assert
        assert result == "<html>Nested content rendered</html>"
        mock_template.render.assert_called_once_with(content_blocks)

    @patch("backend.template_assembler.logging")
    @patch("backend.template_assembler.Environment")
    def test_populate_template_logging(self, mock_env_class, mock_logging):
        """Test that populate_template logs entry and exit."""
        # Arrange
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Test</html>"

        content_blocks = {"test": "content"}
        template_path = "test_template.html"

        # Act
        populate_template(content_blocks, template_path)

        # Assert
        mock_logging.info.assert_any_call(
            f"Entering populate_template with template: {template_path}"
        )
        mock_logging.info.assert_any_call("Exiting populate_template.")

    @patch("backend.template_assembler.logging")
    @patch("backend.template_assembler.Environment")
    def test_populate_template_error_logging(self, mock_env_class, mock_logging):
        """Test that populate_template logs errors appropriately."""
        # Arrange
        mock_env = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.side_effect = Exception("Template error")

        content_blocks = {"test": "content"}
        template_path = "error_template.html"

        # Act & Assert
        with pytest.raises(Exception):
            populate_template(content_blocks, template_path)

        mock_logging.error.assert_called_once()
        error_call_args = mock_logging.error.call_args[0][0]
        assert "Error populating template:" in error_call_args


class TestTemplateAssemblerIntegration:
    """Integration tests for template assembler functionality."""

    def test_populate_template_with_real_template_file(self):
        """Test populate_template with an actual template file."""
        # Create a temporary template file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False
        ) as temp_file:
            template_content = """
            <html>
            <head><title>{{ title }}</title></head>
            <body>
                <h1>{{ introduction }}</h1>
                <p>{{ body }}</p>
                <footer>{{ conclusion }}</footer>
            </body>
            </html>
            """
            temp_file.write(template_content)
            temp_template_path = temp_file.name

        try:
            # Arrange
            content_blocks = {
                "title": "Legal Document",
                "introduction": "Dear Client,",
                "body": "This is the main content of your legal document.",
                "conclusion": "Sincerely, Your Attorney",
            }

            # Since populate_template uses FileSystemLoader with '.',
            # we need to use just the filename
            template_filename = os.path.basename(temp_template_path)

            # Create the template in current directory for the test
            current_dir_template = template_filename
            with open(current_dir_template, "w") as f:
                f.write(template_content)

            try:
                # Act
                result = populate_template(content_blocks, template_filename)

                # Assert
                assert "<title>Legal Document</title>" in result
                assert "<h1>Dear Client,</h1>" in result
                assert "This is the main content" in result
                assert "Sincerely, Your Attorney" in result
                assert "<html>" in result

            finally:
                # Clean up current directory template
                if os.path.exists(current_dir_template):
                    os.unlink(current_dir_template)

        finally:
            # Clean up temporary file
            os.unlink(temp_template_path)

    def test_multiple_template_populations(self):
        """Test multiple template populations with different content."""
        # This test uses mocking since we're testing the unit functionality
        with patch("backend.template_assembler.Environment") as mock_env_class:
            mock_env = Mock()
            mock_template = Mock()
            mock_env_class.return_value = mock_env
            mock_env.get_template.return_value = mock_template

            # Different results for different calls
            mock_template.render.side_effect = [
                "<html>Result 1</html>",
                "<html>Result 2</html>",
                "<html>Result 3</html>",
            ]

            content_sets = [
                {"type": "contract", "content": "Contract details"},
                {"type": "invoice", "content": "Invoice details"},
                {"type": "letter", "content": "Letter content"},
            ]

            results = []
            for content in content_sets:
                result = populate_template(content, "template.html")
                results.append(result)

            # Assert each call produced expected results
            assert results[0] == "<html>Result 1</html>"
            assert results[1] == "<html>Result 2</html>"
            assert results[2] == "<html>Result 3</html>"

            # Verify all calls were made
            assert mock_template.render.call_count == 3


# Pytest fixtures for common test data
@pytest.fixture
def basic_content_blocks():
    """Fixture providing basic content blocks."""
    return {
        "introduction": "Dear valued client,",
        "body": "We are writing to inform you about your case status.",
        "conclusion": "Please contact us if you have any questions.",
    }


@pytest.fixture
def legal_letter_content():
    """Fixture providing legal letter content blocks."""
    return {
        "client_name": "John Doe",
        "client_address": "123 Main Street, Anytown, ST 12345",
        "case_number": "LD-2024-001",
        "date": "January 15, 2024",
        "subject": "Contract Dispute Resolution",
        "salutation": "Dear Mr. Doe:",
        "introduction": "We are writing regarding the contract dispute matter we discussed.",
        "body": """
        After reviewing the contract documents and correspondence, we have identified
        several key issues that support your position. The other party failed to
        meet their obligations under Section 3.2 of the agreement.
        """,
        "next_steps": "We will proceed with formal notice to the other party.",
        "conclusion": "We will keep you informed of all developments in this matter.",
        "closing": "Sincerely,",
        "attorney_name": "Jane Smith, Esq.",
        "firm_name": "Smith & Associates Law Firm",
    }


@pytest.fixture
def complex_case_content():
    """Fixture providing complex case content with nested data."""
    return {
        "case_info": {
            "number": "COMPLEX-2024-001",
            "type": "Multi-Party Litigation",
            "status": "Discovery Phase",
            "priority": "High",
        },
        "parties": [
            {"name": "ABC Corporation", "role": "Plaintiff"},
            {"name": "XYZ Industries", "role": "Defendant"},
            {"name": "123 Services", "role": "Third Party"},
        ],
        "timeline": {
            "filing_date": "2024-01-01",
            "discovery_deadline": "2024-06-01",
            "trial_date": "2024-09-15",
        },
        "documents": [
            {"type": "Complaint", "pages": 25, "date": "2024-01-01"},
            {"type": "Answer", "pages": 15, "date": "2024-02-01"},
            {"type": "Discovery Request", "pages": 10, "date": "2024-03-01"},
        ],
        "financial": {
            "damages_claimed": 500000,
            "legal_fees": 75000,
            "expenses": 15000,
        },
    }


# Tests using fixtures
def test_populate_template_with_basic_fixture(basic_content_blocks):
    """Test populate_template using basic content fixture."""
    with patch("backend.template_assembler.Environment") as mock_env_class:
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Basic Template</html>"

        result = populate_template(basic_content_blocks, "basic_template.html")

        assert result == "<html>Basic Template</html>"
        mock_template.render.assert_called_once_with(basic_content_blocks)


def test_populate_template_with_legal_letter_fixture(legal_letter_content):
    """Test populate_template using legal letter fixture."""
    with patch("backend.template_assembler.Environment") as mock_env_class:
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Legal Letter</html>"

        result = populate_template(legal_letter_content, "legal_template.html")

        assert result == "<html>Legal Letter</html>"
        # Verify the legal content was passed correctly
        call_args = mock_template.render.call_args[0][0]
        assert call_args["client_name"] == "John Doe"
        assert call_args["case_number"] == "LD-2024-001"


def test_populate_template_with_complex_fixture(complex_case_content):
    """Test populate_template using complex case fixture."""
    with patch("backend.template_assembler.Environment") as mock_env_class:
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Complex Case</html>"

        result = populate_template(complex_case_content, "complex_template.html")

        assert result == "<html>Complex Case</html>"
        # Verify nested structure was preserved
        call_args = mock_template.render.call_args[0][0]
        assert call_args["case_info"]["type"] == "Multi-Party Litigation"
        assert len(call_args["parties"]) == 3
        assert call_args["financial"]["damages_claimed"] == 500000


def test_template_paths_validation():
    """Test that different template paths are handled correctly."""
    with patch("backend.template_assembler.Environment") as mock_env_class:
        mock_env = Mock()
        mock_template = Mock()
        mock_env_class.return_value = mock_env
        mock_env.get_template.return_value = mock_template
        mock_template.render.return_value = "<html>Path Test</html>"

        test_paths = [
            "simple.html",
            "templates/nested/deep.html",
            "assets/legal_templates/contract.html",
        ]

        content = {"test": "content"}

        for path in test_paths:
            result = populate_template(content, path)
            assert result == "<html>Path Test</html>"
            mock_env.get_template.assert_called_with(path)


def test_error_handling_comprehensive():
    """Test comprehensive error handling scenarios."""
    content_blocks = {"test": "content"}

    # Test FileSystemLoader creation
    with patch("backend.template_assembler.FileSystemLoader") as mock_loader:
        mock_loader.side_effect = Exception("Loader failed")
        with patch("backend.template_assembler.Environment"):
            with pytest.raises(Exception):
                populate_template(content_blocks, "template.html")
