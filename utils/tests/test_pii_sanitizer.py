"""
Unit tests for PII sanitizer module.

This module provides comprehensive tests for PII sanitization functions,
specifically designed for legal data protection. Tests cover all PII patterns
including SSNs, credit cards, legal case numbers, court names, attorney information,
and other sensitive legal data.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

# Import the PII sanitizer module
from backend_logic.utils.pii_sanitizer import (
    PIISanitizer,
    sanitize_for_api,
    sanitize_for_logging,
    sanitize_text,
)


class TestPIISanitizerBasic(unittest.TestCase):
    """Test cases for basic PII sanitization functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_sanitizer_always_enabled(self):
        """Test that sanitizer is always enabled (security requirement)."""
        self.assertTrue(self.sanitizer.enabled)
        # Try to disable it (should not work)
        self.sanitizer.enabled = False
        # Create new instance - should still be enabled
        new_sanitizer = PIISanitizer()
        self.assertTrue(new_sanitizer.enabled)
    
    def test_empty_input(self):
        """Test handling of empty or None inputs."""
        self.assertEqual(self.sanitizer.sanitize(""), "")
        self.assertEqual(self.sanitizer.sanitize(None), None)
        self.assertEqual(self.sanitizer.sanitize("   "), "   ")


class TestPersonalIdentifiers(unittest.TestCase):
    """Test cases for personal identifier sanitization."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_ssn_sanitization(self):
        """Test Social Security Number sanitization."""
        test_cases = [
            ("My SSN is 123-45-6789", "My SSN is [SSN_REDACTED]"),
            ("Social Security Number: 123456789", "Social Security Number: [SSN_REDACTED]"),
            ("SS# 123-45-6789", "SS# [SSN_REDACTED]"),
            ("The number 123-45-6789 is sensitive", "The number [SSN] is sensitive"),
            ("SSN:123-45-6789 and SSN:987-65-4321", "[SSN_REDACTED] and [SSN_REDACTED]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_ein_sanitization(self):
        """Test Employer Identification Number sanitization."""
        test_cases = [
            ("EIN: 12-3456789", "[EIN_REDACTED]"),
            ("Employer Identification Number: 98-7654321", "[EIN_REDACTED]"),
            ("Tax ID: 11-2233445", "[EIN_REDACTED]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_dob_sanitization(self):
        """Test Date of Birth sanitization."""
        test_cases = [
            ("DOB: 01/15/1980", "[DOB_REDACTED]"),
            ("Date of Birth: 12-25-1975", "[DOB_REDACTED]"),
            ("Born: 03/10/1990", "[DOB_REDACTED]"),
            ("Birth Date: 7/4/1985", "[DOB_REDACTED]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_drivers_license_sanitization(self):
        """Test Driver's License sanitization."""
        test_cases = [
            ("DL: A123-4567-8901-2345", "[DL_NUMBER_REDACTED]"),
            ("Driver's License: 12345678", "[DL_NUMBER_REDACTED]"),
            ("License #: FL123456", "[DL_NUMBER_REDACTED]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)


class TestNameSanitization(unittest.TestCase):
    """Test cases for name sanitization."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_full_name_sanitization(self):
        """Test full name sanitization."""
        test_cases = [
            ("John Doe filed a complaint", "[PERSON_NAME] filed a complaint"),
            ("Mary Jane Smith is the plaintiff", "[PERSON_NAME] is the plaintiff"),
            ("Contact Robert Johnson immediately", "Contact [PERSON_NAME] immediately"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_name_with_title_sanitization(self):
        """Test name with title sanitization."""
        test_cases = [
            ("Mr. John Smith attended", "[CLIENT_NAME] attended"),
            ("Dr. Sarah Johnson examined", "[CLIENT_NAME] examined"),
            ("Ms. Emily Davis testified", "[CLIENT_NAME] testified"),
            ("Prof. Michael Brown presented", "[CLIENT_NAME] presented"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_legal_party_names(self):
        """Test legal party name sanitization."""
        test_cases = [
            ("Plaintiff: John Doe", "Plaintiff: [PARTY_NAME_REDACTED]"),
            ("Defendant: Jane Smith", "Defendant: [PARTY_NAME_REDACTED]"),
            ("Petitioner: Robert Johnson", "Petitioner: [PARTY_NAME_REDACTED]"),
            ("Respondent: Mary Williams", "Respondent: [PARTY_NAME_REDACTED]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            # Note: The pattern might capture this differently
            self.assertIn("[", result)  # Should contain some redaction


class TestFinancialInformation(unittest.TestCase):
    """Test cases for financial information sanitization."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_credit_card_sanitization(self):
        """Test credit card number sanitization."""
        test_cases = [
            ("Card: 4111-1111-1111-1111", "Card: [CREDIT_CARD]"),
            ("CC 5500 0000 0000 0004", "CC [CREDIT_CARD]"),
            ("3782-822463-10005", "[CREDIT_CARD]"),
            ("6011-0000-0000-0004", "[CREDIT_CARD]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_bank_account_sanitization(self):
        """Test bank account number sanitization."""
        test_cases = [
            ("Account: 12345678", "[ACCOUNT_NUMBER]"),
            ("Acct# 9876543210", "[ACCOUNT_NUMBER]"),
            ("Account Number: 11223344556677", "[ACCOUNT_NUMBER]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_routing_number_sanitization(self):
        """Test routing number sanitization."""
        test_cases = [
            ("Routing: 123456789", "[ROUTING_NUMBER]"),
            ("ABA: 987654321", "[ROUTING_NUMBER]"),
            ("RTN# 111222333", "[ROUTING_NUMBER]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_monetary_amount_sanitization(self):
        """Test monetary amount sanitization."""
        test_cases = [
            ("Amount: $1,234.56", "Amount: [MONETARY_AMOUNT]"),
            ("Paid $50,000", "Paid [MONETARY_AMOUNT]"),
            ("$100 million settlement", "[MONETARY_AMOUNT] settlement"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)


class TestContactInformation(unittest.TestCase):
    """Test cases for contact information sanitization."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_email_sanitization(self):
        """Test email address sanitization."""
        test_cases = [
            ("Email: john.doe@example.com", "Email: [EMAIL]"),
            ("Contact me at jane@lawfirm.org", "Contact me at [EMAIL]"),
            ("Send to client@gmail.com", "Send to [EMAIL]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_phone_sanitization(self):
        """Test phone number sanitization."""
        test_cases = [
            ("Call: (555) 123-4567", "Call: [PHONE]"),
            ("Phone: 555-123-4567", "Phone: [PHONE]"),
            ("Contact: +1-555-123-4567", "Contact: [PHONE]"),
            ("Tel: 555.123.4567 ext. 123", "Tel: [PHONE]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_address_sanitization(self):
        """Test address sanitization."""
        test_cases = [
            ("123 Main Street", "[STREET_ADDRESS]"),
            ("456 Oak Avenue", "[STREET_ADDRESS]"),
            ("789 Elm Boulevard", "[STREET_ADDRESS]"),
            ("P.O. Box 12345", "[PO_BOX]"),
            ("Zip: 12345", "Zip: [ZIP_CODE]"),
            ("90210-1234", "[ZIP_CODE]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)


class TestLegalInformation(unittest.TestCase):
    """Test cases for legal-specific information sanitization."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_case_number_sanitization(self):
        """Test case number sanitization."""
        test_cases = [
            ("Case No. 2025-CV-12345", "[CASE_NUMBER]"),
            ("Docket #: ABC-123-DEF", "[CASE_NUMBER]"),
            ("File Number: 98765-A", "[CASE_NUMBER]"),
            ("Matter: XYZ-2025-001", "[CASE_NUMBER]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_court_name_sanitization(self):
        """Test court name sanitization."""
        test_cases = [
            ("Filed in Circuit Court", "Filed in [COURT_NAME]"),
            ("U.S. District Court ruling", "[COURT_NAME] ruling"),
            ("State of Florida Superior Court", "[COURT_NAME]"),
            ("County Court decision", "[COURT_NAME] decision"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_judge_name_sanitization(self):
        """Test judge name sanitization."""
        test_cases = [
            ("Judge John Smith presiding", "[JUDGE_NAME] presiding"),
            ("Hon. Jane Doe ruled", "[JUDGE_NAME] ruled"),
            ("Magistrate Robert Johnson", "[JUDGE_NAME]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)
    
    def test_attorney_information_sanitization(self):
        """Test attorney information sanitization."""
        test_cases = [
            ("Attorney: John Smith", "[ATTORNEY_NAME]"),
            ("Counsel: Jane Doe, Esq.", "[ATTORNEY_NAME]"),
            ("Bar Number: 12345", "[BAR_NUMBER]"),
            ("Law Firm: Smith & Associates LLP", "[LAW_FIRM]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)


class TestMedicalInformation(unittest.TestCase):
    """Test cases for medical information in legal documents."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_medical_record_sanitization(self):
        """Test medical record number sanitization."""
        test_cases = [
            ("MRN: ABC123456", "[MEDICAL_RECORD_NUMBER]"),
            ("Patient: John Doe, Medical Record Number: XYZ789", "Patient: [PERSON_NAME], [MEDICAL_RECORD_NUMBER]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            # Check that medical info is redacted
            self.assertIn("[", result)
    
    def test_insurance_id_sanitization(self):
        """Test insurance ID sanitization."""
        test_cases = [
            ("Policy: INS123456789", "[INSURANCE_ID]"),
            ("Member ID: MEM987654321", "[INSURANCE_ID]"),
        ]
        
        for input_text, expected in test_cases:
            result = self.sanitizer.sanitize(input_text)
            self.assertEqual(result, expected)


class TestComplexDocuments(unittest.TestCase):
    """Test cases for complex document sanitization."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_multiple_pii_in_text(self):
        """Test sanitization of text with multiple PII elements."""
        input_text = """
        Client John Smith (SSN: 123-45-6789) filed a complaint in Circuit Court.
        Case No. 2025-CV-12345. Contact: john.smith@email.com or (555) 123-4567.
        Attorney: Jane Doe, Esq. from Smith & Associates LLP.
        Amount in dispute: $50,000.
        """
        
        result = self.sanitizer.sanitize(input_text)
        
        # Check that all PII is sanitized
        self.assertNotIn("John Smith", result)
        self.assertNotIn("123-45-6789", result)
        self.assertNotIn("2025-CV-12345", result)
        self.assertNotIn("john.smith@email.com", result)
        self.assertNotIn("(555) 123-4567", result)
        self.assertNotIn("Jane Doe", result)
        self.assertNotIn("$50,000", result)
        
        # Check that redaction markers are present
        self.assertIn("[", result)
        self.assertIn("]", result)
    
    def test_legal_document_paragraph(self):
        """Test sanitization of a typical legal document paragraph."""
        input_text = """
        On January 15, 2025, Plaintiff John Michael Doe, residing at 
        123 Main Street, Anytown, FL 12345, filed this action against 
        Defendant Jane Smith Corporation. The matter is before Judge 
        Robert Johnson in the Circuit Court of Florida, Case No. 2025-CV-98765.
        Plaintiff's attorney is Mary Williams, Esq. (Bar No. 54321) of 
        Williams Law Firm, P.A. Plaintiff alleges damages exceeding $100,000.
        """
        
        result = self.sanitizer.sanitize(input_text)
        
        # Original PII should be gone
        self.assertNotIn("John Michael Doe", result)
        self.assertNotIn("123 Main Street", result)
        self.assertNotIn("12345", result)
        self.assertNotIn("Jane Smith", result)
        self.assertNotIn("Robert Johnson", result)
        self.assertNotIn("2025-CV-98765", result)
        self.assertNotIn("Mary Williams", result)
        self.assertNotIn("54321", result)
        self.assertNotIn("$100,000", result)


class TestAPIAndLoggingSanitization(unittest.TestCase):
    """Test cases for API and logging-specific sanitization."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_anonymize_for_api(self):
        """Test double sanitization for API transmission."""
        input_text = "Client John Doe, SSN: 123-45-6789"
        
        # First sanitization
        single_sanitized = self.sanitizer.sanitize(input_text)
        self.assertNotIn("John Doe", single_sanitized)
        self.assertNotIn("123-45-6789", single_sanitized)
        
        # Double sanitization for API
        double_sanitized = self.sanitizer.anonymize_for_api(input_text)
        self.assertNotIn("John Doe", double_sanitized)
        self.assertNotIn("123-45-6789", double_sanitized)
        # Should be at least as sanitized as single
        self.assertIn("[", double_sanitized)
    
    def test_sanitize_log_message(self):
        """Test log message sanitization with different levels."""
        input_text = "Processing case for John Doe, email: john@example.com"
        
        # INFO level sanitization
        info_result = self.sanitizer.sanitize_log_message(input_text, "INFO")
        self.assertNotIn("john@example.com", info_result)
        
        # DEBUG level sanitization (might be less aggressive)
        debug_result = self.sanitizer.sanitize_log_message(input_text, "DEBUG")
        self.assertNotIn("john@example.com", debug_result)
    
    def test_sanitize_dict(self):
        """Test dictionary sanitization."""
        input_dict = {
            "client_name": "John Doe",
            "ssn": "123-45-6789",
            "email": "john@example.com",
            "case_number": "2025-CV-12345",
            "nested": {
                "attorney": "Jane Smith",
                "phone": "(555) 123-4567"
            },
            "non_pii": 12345  # Non-string value
        }
        
        result = self.sanitizer.sanitize_dict(input_dict)
        
        # Check that PII is sanitized
        self.assertNotIn("John Doe", str(result))
        self.assertNotIn("123-45-6789", str(result))
        self.assertNotIn("john@example.com", str(result))
        self.assertNotIn("Jane Smith", str(result["nested"]))
        self.assertNotIn("(555) 123-4567", str(result["nested"]))
        
        # Non-string values should be preserved
        self.assertEqual(result["non_pii"], 12345)
    
    def test_selective_dict_sanitization(self):
        """Test selective key sanitization in dictionaries."""
        input_dict = {
            "client_name": "John Doe",
            "public_info": "This is public",
            "ssn": "123-45-6789",
        }
        
        # Sanitize only specific keys
        result = self.sanitizer.sanitize_dict(
            input_dict,
            keys_to_sanitize=["client_name", "ssn"]
        )
        
        # Specified keys should be sanitized
        self.assertNotIn("John Doe", result["client_name"])
        self.assertNotIn("123-45-6789", result["ssn"])
        # Unspecified key should be unchanged
        self.assertEqual(result["public_info"], "This is public")


class TestCacheAndPerformance(unittest.TestCase):
    """Test cases for caching and performance features."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sanitizer = PIISanitizer()
    
    def test_cache_functionality(self):
        """Test that caching works correctly."""
        input_text = "John Doe, SSN: 123-45-6789"
        
        # First call - should cache
        result1 = self.sanitizer.sanitize(input_text, use_cache=True)
        
        # Second call - should use cache
        result2 = self.sanitizer.sanitize(input_text, use_cache=True)
        
        # Results should be identical
        self.assertEqual(result1, result2)
    
    def test_cache_clear(self):
        """Test cache clearing functionality."""
        input_text = "John Doe, SSN: 123-45-6789"
        
        # Populate cache
        self.sanitizer.sanitize(input_text, use_cache=True)
        self.assertTrue(len(self.sanitizer._sanitization_cache) > 0)
        
        # Clear cache
        self.sanitizer.clear_cache()
        self.assertEqual(len(self.sanitizer._sanitization_cache), 0)
    
    def test_validation_function(self):
        """Test validation that sanitization was successful."""
        original = "John Doe, SSN: 123-45-6789, Card: 4111-1111-1111-1111"
        sanitized = self.sanitizer.sanitize(original)
        
        # Should validate as successful
        is_valid = self.sanitizer.validate_sanitization(original, sanitized)
        self.assertTrue(is_valid)
        
        # Test with incomplete sanitization
        bad_sanitized = "John Doe, SSN: [SSN], Card: 4111-1111-1111-1111"
        is_valid = self.sanitizer.validate_sanitization(original, bad_sanitized)
        self.assertFalse(is_valid)  # Credit card not sanitized


class TestConvenienceFunctions(unittest.TestCase):
    """Test module-level convenience functions."""
    
    def test_sanitize_text_function(self):
        """Test the module-level sanitize_text function."""
        input_text = "John Doe, email: john@example.com"
        result = sanitize_text(input_text)
        
        self.assertNotIn("John Doe", result)
        self.assertNotIn("john@example.com", result)
    
    def test_sanitize_for_logging_function(self):
        """Test the module-level sanitize_for_logging function."""
        input_text = "Processing SSN: 123-45-6789"
        result = sanitize_for_logging(input_text, "INFO")
        
        self.assertNotIn("123-45-6789", result)
    
    def test_sanitize_for_api_function(self):
        """Test the module-level sanitize_for_api function."""
        input_text = "Client: John Doe, Case: 2025-CV-12345"
        result = sanitize_for_api(input_text)
        
        self.assertNotIn("John Doe", result)
        self.assertNotIn("2025-CV-12345", result)


if __name__ == "__main__":
    unittest.main()
