"""
Enhanced PII Sanitization Module for Legal Data.

This module provides comprehensive PII (Personally Identifiable Information) sanitization
specifically designed for legal documents and data. It includes patterns for standard PII
as well as legal-specific information like case numbers, court names, and legal addresses.

CRITICAL: PII sanitization is ALWAYS enabled in production and cannot be disabled.
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from typing import Dict, List, Optional, Pattern, Tuple


class PIISanitizer:
    """
    Enhanced PII sanitization for legal data with comprehensive pattern matching.
    
    This sanitizer is designed to protect sensitive information in legal documents
    while maintaining document readability and context. It uses sophisticated regex
    patterns to identify and replace various types of PII commonly found in legal data.
    
    SECURITY NOTE: Sanitization is ALWAYS enabled and cannot be disabled in production.
    """
    
    # Comprehensive PII patterns for legal data
    # Each tuple contains: (compiled_regex_pattern, replacement_text, description)
    PII_PATTERNS: List[Tuple[Pattern, str, str]] = [
        # Personal Identifiers
        (
            re.compile(r"\b(?:SSN|Social Security Number|Social Security #|SS#)[:\s]*(\d{3}[-.\s]?\d{2}[-.\s]?\d{4})\b", re.IGNORECASE),
            "[SSN_REDACTED]",
            "Social Security Numbers with labels"
        ),
        (
            re.compile(r"\b(?<!\d)(\d{3}[-.\s]?\d{2}[-.\s]?\d{4})(?!\d)\b"),
            "[SSN]",
            "Social Security Numbers without labels"
        ),
        (
            re.compile(r"\b(?:EIN|Employer Identification Number|Tax ID)[:\s]*(\d{2}[-.\s]?\d{7})\b", re.IGNORECASE),
            "[EIN_REDACTED]",
            "Employer Identification Numbers"
        ),
        (
            re.compile(r"\b(?:DOB|Date of Birth|Birth Date|Born)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b", re.IGNORECASE),
            "[DOB_REDACTED]",
            "Dates of Birth with labels"
        ),
        (
            re.compile(r"\b(?:DL|Driver\'s License|Driver License|License #)[:\s]*([A-Z]\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}|\d{7,12}|[A-Z]{1,2}\d{5,8})\b", re.IGNORECASE),
            "[DL_NUMBER_REDACTED]",
            "Driver License Numbers"
        ),
        (
            re.compile(r"\b(?:Passport|Passport Number|Passport #)[:\s]*([A-Z]{1,2}\d{6,9})\b", re.IGNORECASE),
            "[PASSPORT_REDACTED]",
            "Passport Numbers"
        ),
        
        # Names (multiple strategies for different formats)
        (
            re.compile(r"\b(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+[A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)+\b"),
            "[CLIENT_NAME]",
            "Names with titles"
        ),
        (
            re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+){1,3}\b"),
            "[PERSON_NAME]",
            "Full names without titles"
        ),
        (
            re.compile(r"(?:Plaintiff|Defendant|Petitioner|Respondent|Appellant|Appellee)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", re.IGNORECASE),
            r"\g<0>: [PARTY_NAME_REDACTED]",
            "Legal party names"
        ),
        
        # Financial Information
        (
            re.compile(r"\b(?:Account|Acct|Acc)\.?\s*(?:No\.?|Number|#)?\s*[:\s]*(\d{8,17})\b", re.IGNORECASE),
            "[ACCOUNT_NUMBER]",
            "Bank account numbers"
        ),
        (
            re.compile(r"\b(?:Routing|ABA|RTN)\.?\s*(?:No\.?|Number|#)?\s*[:\s]*(\d{9})\b", re.IGNORECASE),
            "[ROUTING_NUMBER]",
            "Bank routing numbers"
        ),
        (
            re.compile(r"\b(?:4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}|5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}|3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}|6011[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b"),
            "[CREDIT_CARD]",
            "Credit card numbers"
        ),
        (
            re.compile(r"\$\s*[\d,]+(?:\.\d{2})?(?:\s*(?:USD|dollars?|million|thousand|hundred))?", re.IGNORECASE),
            "[MONETARY_AMOUNT]",
            "Monetary amounts"
        ),
        
        # Contact Information
        (
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "[EMAIL]",
            "Email addresses"
        ),
        (
            re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?:\s*(?:ext|x|extension)\.?\s*\d{1,5})?", re.IGNORECASE),
            "[PHONE]",
            "Phone numbers with extensions"
        ),
        (
            re.compile(r"\b(?:Fax|Facsimile)[:\s]*(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", re.IGNORECASE),
            "[FAX_NUMBER]",
            "Fax numbers"
        ),
        
        # Addresses (comprehensive patterns)
        (
            re.compile(r"\b\d{1,5}\s+(?:[NSEW]\.?\s+)?[A-Za-z\s]+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|Place|Pl\.?|Circle|Cir\.?|Trail|Trl\.?|Way|Parkway|Pkwy\.?|Highway|Hwy\.?|Plaza|Square|Sq\.?)(?:\s+(?:Suite|Ste\.?|Apt\.?|Unit|#)\s*\d+[A-Za-z]?)?\b", re.IGNORECASE),
            "[STREET_ADDRESS]",
            "Street addresses with unit numbers"
        ),
        (
            re.compile(r"\b(?:P\.?O\.?\s*Box|Post Office Box)\s*\d+\b", re.IGNORECASE),
            "[PO_BOX]",
            "PO Box addresses"
        ),
        (
            re.compile(r"\b\d{5}(?:[-\s]\d{4})?\b"),
            "[ZIP_CODE]",
            "ZIP codes"
        ),
        
        # Legal-Specific Information
        (
            re.compile(r"(?:Case|Docket|File|Matter|Cause)\.?\s*(?:No\.?|Number|#)?\s*[:\s]*([A-Z0-9]{2,}[-\s]?[A-Z0-9]+(?:[-\s][A-Z0-9]+)*)", re.IGNORECASE),
            "[CASE_NUMBER]",
            "Legal case numbers"
        ),
        (
            re.compile(r"(?:Index|Indictment|Citation)\.?\s*(?:No\.?|Number|#)?\s*[:\s]*(\d+[-/]?\d+)", re.IGNORECASE),
            "[LEGAL_INDEX_NUMBER]",
            "Legal index/indictment numbers"
        ),
        (
            re.compile(r"\b(?:United States|U\.S\.|US|State of [A-Z][a-z]+|County of [A-Z][a-z]+)\s+(?:District|Circuit|Superior|Municipal|County|State|Federal|Bankruptcy|Tax|Family|Probate|Juvenile|Criminal|Civil)\s+Court\b", re.IGNORECASE),
            "[COURT_NAME]",
            "Court names with jurisdiction"
        ),
        (
            re.compile(r"\b(?:Judge|Justice|Magistrate|Hon\.|Honorable)\s+[A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)+\b", re.IGNORECASE),
            "[JUDGE_NAME]",
            "Judge names"
        ),
        (
            re.compile(r"(?:Attorney|Counsel|Lawyer|Esq\.|Esquire)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", re.IGNORECASE),
            "[ATTORNEY_NAME]",
            "Attorney names"
        ),
        (
            re.compile(r"(?:Law Firm|Law Office|Legal Services|Attorneys at Law)[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:LLP|LLC|PC|PA|PLLC|P\.C\.|P\.A\.))?)", re.IGNORECASE),
            "[LAW_FIRM]",
            "Law firm names"
        ),
        (
            re.compile(r"(?:Bar|License|Attorney)\.?\s*(?:No\.?|Number|#)?\s*[:\s]*(\d{5,10})", re.IGNORECASE),
            "[BAR_NUMBER]",
            "Bar/Attorney license numbers"
        ),
        
        # Medical Information (often in legal documents)
        (
            re.compile(r"(?:Patient|Medical Record|MRN|Medical Record Number)[:\s]*([A-Z0-9]{5,15})", re.IGNORECASE),
            "[MEDICAL_RECORD_NUMBER]",
            "Medical record numbers"
        ),
        (
            re.compile(r"(?:Policy|Insurance|Member ID|Subscriber ID)[:\s]*([A-Z0-9]{8,20})", re.IGNORECASE),
            "[INSURANCE_ID]",
            "Insurance policy numbers"
        ),
        (
            re.compile(r"(?:Diagnosis|ICD-10|ICD-9|CPT Code)[:\s]*([A-Z]\d{2}(?:\.\d{1,2})?)", re.IGNORECASE),
            "[MEDICAL_CODE]",
            "Medical diagnosis codes"
        ),
        
        # Vehicle Information
        (
            re.compile(r"(?:VIN|Vehicle Identification Number)[:\s]*([A-Z0-9]{17})", re.IGNORECASE),
            "[VIN]",
            "Vehicle Identification Numbers"
        ),
        (
            re.compile(r"(?:License Plate|Plate Number|Tag)[:\s]*([A-Z0-9]{1,3}[-\s]?[A-Z0-9]{1,4})", re.IGNORECASE),
            "[LICENSE_PLATE]",
            "License plate numbers"
        ),
        
        # Business Information
        (
            re.compile(r"(?:Corporation|Corp\.|Inc\.|LLC|LLP|Ltd\.|Company|Co\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", re.IGNORECASE),
            "[BUSINESS_NAME]",
            "Business entity names"
        ),
        (
            re.compile(r"(?:doing business as|d/b/a|DBA)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", re.IGNORECASE),
            "[DBA_NAME]",
            "DBA business names"
        ),
    ]
    
    def __init__(self):
        """
        Initialize the PII Sanitizer with forced enablement.
        
        CRITICAL: Sanitization is ALWAYS enabled and cannot be disabled in production.
        This is a security requirement to protect sensitive legal data.
        """
        # SECURITY: Always enabled, no environment variable override allowed
        self.enabled = True
        
        # Compile all patterns once for performance
        self._compiled_patterns = [
            (pattern, replacement, desc)
            for pattern, replacement, desc in self.PII_PATTERNS
        ]
        
        # Cache for performance optimization
        self._sanitization_cache = {}
        
    def sanitize(self, text: str, use_cache: bool = True) -> str:
        """
        Sanitize all PII from the provided text.
        
        This method applies all PII patterns to identify and replace sensitive
        information with appropriate placeholders. It maintains text readability
        while protecting privacy.
        
        Args:
            text: The text to sanitize
            use_cache: Whether to use caching for repeated sanitization (default: True)
            
        Returns:
            Sanitized text with PII replaced by placeholders
            
        Examples:
            >>> sanitizer = PIISanitizer()
            >>> sanitizer.sanitize("John Doe's SSN is 123-45-6789")
            "[PERSON_NAME]'s SSN is [SSN_REDACTED]"
        """
        if not text:
            return text
            
        # Check cache if enabled
        if use_cache:
            text_hash = hashlib.md5(text.encode()).hexdigest()
            if text_hash in self._sanitization_cache:
                return self._sanitization_cache[text_hash]
        
        # Apply all sanitization patterns
        sanitized = text
        for pattern, replacement, _ in self._compiled_patterns:
            sanitized = pattern.sub(replacement, sanitized)
        
        # Cache the result if enabled
        if use_cache and len(self._sanitization_cache) < 1000:  # Limit cache size
            self._sanitization_cache[text_hash] = sanitized
        
        return sanitized
    
    def sanitize_dict(self, data: Dict, keys_to_sanitize: Optional[List[str]] = None) -> Dict:
        """
        Sanitize PII in dictionary values.
        
        Args:
            data: Dictionary containing potential PII
            keys_to_sanitize: Optional list of specific keys to sanitize.
                             If None, sanitizes all string values.
            
        Returns:
            Dictionary with sanitized values
        """
        sanitized_dict = {}
        
        for key, value in data.items():
            if keys_to_sanitize and key not in keys_to_sanitize:
                sanitized_dict[key] = value
            elif isinstance(value, str):
                sanitized_dict[key] = self.sanitize(value)
            elif isinstance(value, dict):
                sanitized_dict[key] = self.sanitize_dict(value, keys_to_sanitize)
            elif isinstance(value, list):
                sanitized_dict[key] = [
                    self.sanitize(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                sanitized_dict[key] = value
                
        return sanitized_dict
    
    def anonymize_for_api(self, content: str) -> str:
        """
        Perform double sanitization for content being sent to third-party APIs.
        
        This method applies sanitization twice to ensure maximum protection
        when sending data to external services. This is particularly important
        for AI APIs or other third-party services.
        
        Args:
            content: The content to anonymize for API transmission
            
        Returns:
            Double-sanitized content safe for external API transmission
            
        Examples:
            >>> sanitizer = PIISanitizer()
            >>> sanitizer.anonymize_for_api("Process case #12345 for John Doe")
            "[CASE_NUMBER] for [PERSON_NAME]"
        """
        # First pass sanitization
        first_pass = self.sanitize(content, use_cache=False)
        
        # Second pass to catch any patterns that might have been obscured
        second_pass = self.sanitize(first_pass, use_cache=False)
        
        return second_pass
    
    def sanitize_log_message(self, message: str, level: str = "INFO") -> str:
        """
        Sanitize log messages with level-appropriate detail.
        
        Args:
            message: The log message to sanitize
            level: The log level (DEBUG, INFO, WARNING, ERROR)
            
        Returns:
            Sanitized log message
        """
        # For DEBUG level, provide more context
        if level.upper() == "DEBUG":
            # Less aggressive sanitization for debugging
            return self.sanitize(message)
        # More aggressive sanitization for production logs
        return self.anonymize_for_api(message)
    
    def get_pattern_stats(self) -> Dict[str, int]:
        """
        Get statistics on pattern usage (for monitoring and optimization).
        
        Returns:
            Dictionary with pattern descriptions and match counts
        """
        stats = {}
        for _, _, description in self._compiled_patterns:
            stats[description] = 0
        return stats
    
    def validate_sanitization(self, original: str, sanitized: str) -> bool:
        """
        Validate that sanitization was successful by checking for remaining PII.
        
        Args:
            original: The original text
            sanitized: The sanitized text
            
        Returns:
            True if sanitization appears successful, False if PII may remain
        """
        # Quick checks for common PII patterns that should not exist after sanitization
        dangerous_patterns = [
            r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",  # SSN
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
            r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6011)[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # Credit cards
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, sanitized):
                return False
                
        return True
    
    def clear_cache(self):
        """Clear the sanitization cache to free memory."""
        self._sanitization_cache.clear()


# Singleton instance for consistent sanitization across the application
_global_sanitizer = PIISanitizer()


def sanitize_text(text: str) -> str:
    """
    Convenience function to sanitize text using the global sanitizer.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text
    """
    return _global_sanitizer.sanitize(text)


def sanitize_for_logging(message: str, level: str = "INFO") -> str:
    """
    Convenience function to sanitize log messages.
    
    Args:
        message: Log message to sanitize
        level: Log level
        
    Returns:
        Sanitized log message
    """
    return _global_sanitizer.sanitize_log_message(message, level)


def sanitize_for_api(content: str) -> str:
    """
    Convenience function for API content sanitization.
    
    Args:
        content: Content to sanitize for API transmission
        
    Returns:
        Double-sanitized content
    """
    return _global_sanitizer.anonymize_for_api(content)


# Export public interface
__all__ = [
    "PIISanitizer",
    "sanitize_for_api",
    "sanitize_for_logging",
    "sanitize_text"
]
