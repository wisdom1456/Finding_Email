"""Security module for file upload validation and protection.

This module provides comprehensive security functions for handling file uploads,
including path traversal prevention, file size enforcement, content type validation,
and secure filename sanitization.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

# Try to import streamlit, but make it optional
# Streamlit is only needed for Streamlit apps, not FastAPI backend
try:
    import streamlit as st

    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False
    st = None  # type: ignore

# Try to import python-magic, but make it optional
# python-magic requires libmagic which may not be available in serverless environments
try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

# Maximum file size: 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# Magic number signatures for file type detection when python-magic is unavailable
# Format: {extension: [(signature_bytes, offset, mime_type)]}
# offset is the byte position where the signature starts (usually 0)
MAGIC_SIGNATURES = {
    ".pdf": [(b"%PDF", 0, "application/pdf")],
    ".png": [(b"\x89PNG\r\n\x1a\n", 0, "image/png")],
    ".jpg": [
        (b"\xff\xd8\xff\xe0", 0, "image/jpeg"),  # JFIF
        (b"\xff\xd8\xff\xe1", 0, "image/jpeg"),  # Exif
        (b"\xff\xd8\xff\xdb", 0, "image/jpeg"),  # Raw JPEG
    ],
    ".jpeg": [
        (b"\xff\xd8\xff\xe0", 0, "image/jpeg"),
        (b"\xff\xd8\xff\xe1", 0, "image/jpeg"),
        (b"\xff\xd8\xff\xdb", 0, "image/jpeg"),
    ],
    ".docx": [(b"PK\x03\x04", 0, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")],
    ".doc": [(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0, "application/msword")],
    # Note: .txt, .csv, .eml don't have reliable magic numbers - they are text-based
}

# Allowed file extensions (whitelist)
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".rtf",
    ".eml",
    ".jpg",
    ".jpeg",
    ".png",
    ".csv",
}

# Allowed MIME types (whitelist)
ALLOWED_MIME_TYPES = {
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "application/rtf",
    "text/rtf",
    "text/csv",
    "application/csv",
    # Email files
    "message/rfc822",
    # Images
    "image/jpeg",
    "image/png",
}

# MIME type to extension mapping for validation
MIME_EXTENSION_MAP = {
    "application/pdf": [".pdf"],
    "application/msword": [".doc"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "text/plain": [".txt", ".eml"],  # .eml files may be detected as text/plain
    "application/rtf": [".rtf"],
    "text/rtf": [".rtf"],
    "text/csv": [".csv"],
    "application/csv": [".csv"],
    "message/rfc822": [".eml"],  # Standard MIME type for .eml files
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
}


def secure_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks and ensure safe storage.

    This function:
    - Removes any directory path components to prevent traversal
    - Removes dangerous characters that could be interpreted by the OS
    - Prevents hidden files (starting with dots)
    - Adds a unique timestamp hash to prevent filename collisions
    - Preserves the file extension for proper content type handling

    Args:
    ----
        filename: The original filename from the upload

    Returns:
    -------
        A sanitized, safe filename with timestamp hash

    Examples:
    --------
        >>> secure_filename("../../../etc/passwd")
        'passwd_a1b2c3d4'
        >>> secure_filename("dangerous<script>.pdf")
        'dangerous_script_e5f6g7h8.pdf'

    """
    if not filename:
        # Generate a random filename if none provided
        timestamp_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        return f"unnamed_{timestamp_hash}"

    # Remove any directory path components (prevent path traversal)
    basename = os.path.basename(filename)

    # Split name and extension
    name, ext = os.path.splitext(basename)

    # Remove any non-alphanumeric characters except dots, dashes, underscores
    # This prevents command injection and special character issues
    cleaned_name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)

    # Remove leading dots (hidden files) and trailing dots/spaces
    cleaned_name = cleaned_name.lstrip(".").rstrip(". ")

    # Ensure filename is not empty after cleaning
    if not cleaned_name:
        cleaned_name = "file"

    # Limit filename length to prevent filesystem issues
    if len(cleaned_name) > 100:
        cleaned_name = cleaned_name[:100]

    # Add timestamp hash to prevent collisions
    timestamp_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

    # Reconstruct filename with sanitized components
    return f"{cleaned_name}_{timestamp_hash}{ext.lower()}"


def validate_file_size(file_data: bytes, max_size: int = MAX_FILE_SIZE) -> None:
    """Enforce file size limits to prevent resource exhaustion attacks.

    Args:
    ----
        file_data: The file content as bytes
        max_size: Maximum allowed file size in bytes (default: 100MB)

    Raises:
    ------
        ValueError: If file size exceeds the maximum allowed size

    Examples:
    --------
        >>> validate_file_size(b"small file content")  # OK
        >>> validate_file_size(b"x" * (101 * 1024 * 1024))  # Raises ValueError

    """
    file_size = len(file_data)

    if file_size > max_size:
        # Format sizes for readable error message
        file_size_mb = file_size / (1024 * 1024)
        max_size_mb = max_size / (1024 * 1024)
        raise ValueError(
            f"File size ({file_size_mb:.2f}MB) exceeds maximum allowed size ({max_size_mb:.2f}MB). "
            f"Please upload a smaller file."
        )

    # Also check for empty files
    if file_size == 0:
        raise ValueError("Empty files are not allowed. Please upload a valid file.")


def validate_file_content(file_data: bytes, filename: str) -> Tuple[str, str]:
    """Validate file content matches claimed type using magic number detection.

    This prevents file type spoofing attacks where malicious files are disguised
    with safe extensions. Uses python-magic to detect actual content type.

    Args:
    ----
        file_data: The file content as bytes
        filename: The claimed filename with extension

    Returns:
    -------
        Tuple of (detected_mime_type, file_extension)

    Raises:
    ------
        ValueError: If file content type is not allowed or doesn't match extension

    Examples:
    --------
        >>> validate_file_content(pdf_bytes, "document.pdf")  # OK
        >>> validate_file_content(exe_bytes, "malware.pdf")  # Raises ValueError

    """
    # Extract the file extension
    ext = Path(filename).suffix.lower()

    # Check if extension is in allowed list
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File extension '{ext}' is not allowed. "
            f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Detect actual content type using magic numbers
    if HAS_MAGIC:
        try:
            mime_type = magic.from_buffer(file_data, mime=True)
        except Exception as e:
            raise ValueError(f"Unable to determine file content type: {e!s}") from e
    else:
        # Fallback: Use built-in magic number detection for binary files
        # This provides defense-in-depth when python-magic (libmagic) is unavailable
        mime_type = None

        # Check magic signatures for known binary file types
        if ext in MAGIC_SIGNATURES:
            for signature, offset, expected_mime in MAGIC_SIGNATURES[ext]:
                if len(file_data) > offset + len(signature):
                    if file_data[offset : offset + len(signature)] == signature:
                        mime_type = expected_mime
                        break

            # If extension requires a signature but none matched, reject the file
            if mime_type is None:
                raise ValueError(
                    f"File content does not match expected format for '{ext}'. "
                    f"The file may be corrupted or disguised as a different type."
                )
        else:
            # For text-based formats (txt, csv, eml), use mimetypes.guess_type
            # These don't have reliable magic numbers
            guessed_type, _ = mimetypes.guess_type(filename)
            if guessed_type:
                mime_type = guessed_type
            else:
                # Last resort: map extension to common MIME types
                ext_to_mime = {
                    ".pdf": "application/pdf",
                    ".doc": "application/msword",
                    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".txt": "text/plain",
                    ".csv": "text/csv",
                    ".eml": "message/rfc822",
                    ".rtf": "application/rtf",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                }
                mime_type = ext_to_mime.get(ext, "application/octet-stream")

    # Check if detected MIME type is allowed
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"File content type '{mime_type}' is not allowed. "
            f"The file may be corrupted or disguised as a different type."
        )

    # Verify that the extension matches the detected content type
    expected_extensions = MIME_EXTENSION_MAP.get(mime_type, [])
    if ext not in expected_extensions:
        raise ValueError(
            f"File extension '{ext}' does not match detected content type '{mime_type}'. "
            f"Expected extensions for this content type: {', '.join(expected_extensions)}"
        )

    return mime_type, ext


def validate_total_upload_size(total_size: int, max_total: int = MAX_FILE_SIZE) -> None:
    """Validate total upload size for batch uploads.

    Args:
    ----
        total_size: Total size of all uploaded files in bytes
        max_total: Maximum allowed total size (default: 100MB)

    Raises:
    ------
        ValueError: If total size exceeds limit

    """
    if total_size > max_total:
        total_mb = total_size / (1024 * 1024)
        max_mb = max_total / (1024 * 1024)
        raise ValueError(
            f"Total upload size ({total_mb:.2f}MB) exceeds maximum allowed ({max_mb:.2f}MB). "
            f"Please reduce the number or size of files."
        )


def create_secure_temp_file(file_data: bytes, filename: str) -> str:
    """Create a secure temporary file with validated content.

    Args:
    ----
        file_data: The file content as bytes
        filename: The original filename (will be sanitized)

    Returns:
    -------
        Path to the secure temporary file

    Raises:
    ------
        ValueError: If any security validation fails
        OSError: If unable to create temporary file

    """
    # Perform all security validations
    validate_file_size(file_data)
    secure_name = secure_filename(filename)
    mime_type, ext = validate_file_content(file_data, secure_name)

    # Create secure temporary file
    # Use NamedTemporaryFile with delete=False to persist for processing
    try:
        with tempfile.NamedTemporaryFile(delete=False, prefix="secure_", suffix=ext, mode="wb") as tmp_file:
            tmp_file.write(file_data)
            tmp_path = tmp_file.name

        # Set restrictive permissions (owner read/write only)
        os.chmod(tmp_path, 0o600)

        return tmp_path

    except OSError as e:
        raise OSError(f"Failed to create secure temporary file: {e!s}") from e


def validate_file_path(file_path: str, base_dir: str) -> bool:
    """Validate that a file path is within the allowed base directory.

    Prevents directory traversal attacks by ensuring the resolved path
    is within the expected directory.

    Args:
    ----
        file_path: The file path to validate
        base_dir: The allowed base directory

    Returns:
    -------
        True if path is valid and safe, False otherwise

    Examples:
    --------
        >>> validate_file_path("/app/uploads/file.pdf", "/app/uploads")  # True
        >>> validate_file_path("/app/uploads/../../../etc/passwd", "/app/uploads")  # False

    """
    try:
        # Resolve to absolute paths
        base = Path(base_dir).resolve()
        file = Path(file_path).resolve()

        # Check if file path is within base directory
        # This prevents traversal attacks like ../../../etc/passwd
        return file.is_relative_to(base)
    except (ValueError, OSError):
        return False


def sanitize_path_component(component: str) -> str:
    """Sanitize a single path component for safe directory/file creation.

    Args:
    ----
        component: A directory or file name component

    Returns:
    -------
        Sanitized component safe for filesystem use

    """
    # Remove any path separators
    component = component.replace("/", "_").replace("\\", "_")

    # Remove dangerous characters
    component = re.sub(r"[^a-zA-Z0-9._-]", "_", component)

    # Remove leading/trailing dots and spaces
    component = component.strip(". ")

    # Ensure not empty
    if not component:
        component = "unnamed"

    return component


def get_safe_upload_path(base_dir: str, filename: str, subfolder: Optional[str] = None) -> str:
    """Generate a safe upload path with all security validations.

    Args:
    ----
        base_dir: Base upload directory
        filename: Original filename (will be sanitized)
        subfolder: Optional subfolder within base_dir (will be sanitized)

    Returns:
    -------
        Safe, validated file path for upload

    Raises:
    ------
        ValueError: If resulting path would be outside base directory

    """
    # Sanitize filename
    safe_filename = secure_filename(filename)

    # Build path components
    path_components = [base_dir]

    # Add sanitized subfolder if provided
    if subfolder:
        safe_subfolder = sanitize_path_component(subfolder)
        path_components.append(safe_subfolder)

    path_components.append(safe_filename)

    # Join path components
    upload_path = os.path.join(*path_components)

    # Validate the resulting path
    if not validate_file_path(upload_path, base_dir):
        raise ValueError("Invalid upload path detected. Possible path traversal attempt.")

    return upload_path


def sanitize_text_for_db(text: Optional[str]) -> Optional[str]:
    """Sanitize text for PostgreSQL storage by removing problematic characters.
    
    PostgreSQL text columns cannot store NULL characters (\\u0000).
    This function removes them and other control characters that can cause issues.
    
    Args:
        text: The text to sanitize
        
    Returns:
        Sanitized text safe for PostgreSQL, or None if input was None

    """
    if text is None:
        return None

    # Remove NULL characters (\\u0000) - PostgreSQL cannot store these
    sanitized = text.replace('\x00', '')

    # Optionally remove other problematic control characters (except newline, tab, carriage return)
    # This regex removes control chars U+0001-U+0008, U+000B-U+000C, U+000E-U+001F
    sanitized = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f]', '', sanitized)

    return sanitized


# Export public interface
__all__ = [
    "ALLOWED_EXTENSIONS",
    "ALLOWED_MIME_TYPES",
    "MAX_FILE_SIZE",
    "create_secure_temp_file",
    "get_safe_upload_path",
    "sanitize_path_component",
    "sanitize_text_for_db",
    "secure_filename",
    "validate_file_content",
    "validate_file_path",
    "validate_file_size",
    "validate_total_upload_size",
]
