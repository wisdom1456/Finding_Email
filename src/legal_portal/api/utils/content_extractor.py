"""Document processing utilities for downloading and extracting text from files."""

import io
from typing import Optional, Tuple

import requests

from legal_portal.services.file_compression_service import get_compression_service
from legal_portal.utils.compression_utils import format_file_size
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# Conditional imports for PDF extraction
# Try pypdf first (lightweight, works on Vercel), then fitz (PyMuPDF, better quality)
PYPDF_AVAILABLE = False
FITZ_AVAILABLE = False

try:
    from pypdf import PdfReader

    PYPDF_AVAILABLE = True
    logger.debug("pypdf available for PDF extraction")
except ImportError:
    logger.debug("pypdf not available")

try:
    import fitz  # PyMuPDF

    FITZ_AVAILABLE = True
    logger.debug("PyMuPDF (fitz) available for PDF extraction")
except ImportError:
    logger.debug("PyMuPDF (fitz) not available")

# Conditional import for DOCX
DOCX_AVAILABLE = False
try:
    from docx import Document

    DOCX_AVAILABLE = True
    logger.debug("python-docx available for DOCX extraction")
except ImportError:
    logger.debug("python-docx not available")


class DocumentProcessor:
    """Handles document download and text extraction."""

    @staticmethod
    def download_file(url: str, access_token: str) -> Tuple[bytes, str]:
        """Download a file from a URL with authentication.

        Args:
        ----
            url: URL to download from
            access_token: OAuth access token for authentication

        Returns:
        -------
            Tuple of (file_content, content_type)

        Raises:
        ------
            Exception: If download fails

        """
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "application/octet-stream")
        return response.content, content_type

    @staticmethod
    def extract_text_from_pdf(file_content: bytes) -> str:
        """Extract text from PDF file.

        Uses pypdf (lightweight) or falls back to PyMuPDF (fitz) if available.

        Args:
        ----
            file_content: PDF file bytes

        Returns:
        -------
            Extracted text

        """
        # Try PyMuPDF first (better quality extraction) if available
        if FITZ_AVAILABLE:
            try:
                pdf_document = fitz.open(stream=file_content, filetype="pdf")
                text_parts = []
                for page_num in range(pdf_document.page_count):
                    page = pdf_document[page_num]
                    text_parts.append(page.get_text())
                pdf_document.close()
                return "\n\n".join(text_parts)
            except Exception as e:
                logger.warning(f"PyMuPDF extraction failed, trying pypdf: {e}")

        # Fall back to pypdf (lightweight, works on Vercel)
        if PYPDF_AVAILABLE:
            try:
                reader = PdfReader(io.BytesIO(file_content))
                text_parts = []
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                return "\n\n".join(text_parts)
            except Exception as e:
                raise Exception(f"Failed to extract text from PDF with pypdf: {str(e)}") from e

        # No PDF library available
        raise Exception("No PDF extraction library available (install pypdf or PyMuPDF)")

    @staticmethod
    def extract_text_from_docx(file_content: bytes) -> str:
        """Extract text from DOCX file.

        Args:
        ----
            file_content: DOCX file bytes

        Returns:
        -------
            Extracted text

        """
        if not DOCX_AVAILABLE:
            raise Exception("python-docx not available for DOCX extraction")

        try:
            doc = Document(io.BytesIO(file_content))
            text_parts = [paragraph.text for paragraph in doc.paragraphs]
            return "\n".join(text_parts)
        except Exception as e:
            raise Exception(f"Failed to extract text from DOCX: {str(e)}") from e

    @staticmethod
    def extract_text_from_txt(file_content: bytes) -> str:
        """Extract text from plain text file.

        Args:
        ----
            file_content: Text file bytes

        Returns:
        -------
            Extracted text

        """
        try:
            # Try UTF-8 first, fall back to latin-1
            try:
                return file_content.decode("utf-8")
            except UnicodeDecodeError:
                return file_content.decode("latin-1", errors="replace")
        except Exception as e:
            raise Exception(f"Failed to extract text from TXT: {str(e)}") from e

    @classmethod
    def extract_text(cls, file_content: bytes, content_type: str, filename: str = "") -> Optional[str]:
        """Extract text from file based on content type.

        Args:
        ----
            file_content: File bytes
            content_type: MIME type of the file
            filename: Original filename (used for extension fallback)

        Returns:
        -------
            Extracted text or None if extraction not supported

        """
        # Normalize content type
        content_type = content_type.lower().split(";")[0].strip()

        # Check file extension as fallback
        extension = ""
        if filename and "." in filename:
            extension = filename.split(".")[-1].lower()

        # PDF
        if content_type == "application/pdf" or extension == "pdf":
            if not PYPDF_AVAILABLE and not FITZ_AVAILABLE:
                logger.warning(f"No PDF library available to extract text from {filename}")
                return None
            return cls.extract_text_from_pdf(file_content)

        # DOCX
        elif (
            content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or extension == "docx"
        ):
            if not DOCX_AVAILABLE:
                logger.warning(f"python-docx not available to extract text from {filename}")
                return None
            return cls.extract_text_from_docx(file_content)

        # Plain text
        elif content_type.startswith("text/") or extension in ["txt", "text", "log", "md"]:
            return cls.extract_text_from_txt(file_content)

        # Unsupported type
        else:
            return None

    @classmethod
    def download_and_extract(
        cls, url: str, access_token: str, filename: str = "", compress: bool = True
    ) -> Tuple[bytes, str, Optional[str], Optional[dict]]:
        """Download file, optionally compress it, and extract text in one operation.

        Args:
        ----
            url: URL to download from
            access_token: OAuth access token
            filename: Original filename for type detection
            compress: Whether to attempt compression for large files (default: True)

        Returns:
        -------
            Tuple of (file_content, content_type, extracted_text, compression_metadata)
            compression_metadata includes: {
                "compressed": bool,
                "original_size": int,
                "compressed_size": int,
                "compression_ratio": float,
                "method": str
            }

        Raises:
        ------
            Exception: If download fails

        """
        # Download file
        file_content, content_type = cls.download_file(url, access_token)
        original_size = len(file_content)

        # Log download
        logger.info(f"Downloaded file: {filename} ({format_file_size(original_size)})")

        # Initialize compression metadata
        compression_metadata = {
            "compressed": False,
            "original_size": original_size,
            "compressed_size": original_size,
            "compression_ratio": 1.0,
            "method": "none",
        }

        # Attempt compression if enabled and file is large enough
        if compress:
            try:
                compression_service = get_compression_service()
                compression_result = compression_service.compress_file(file_content, filename, content_type)

                # Update file content if compressed
                if compression_result.was_compressed:
                    file_content = compression_result.compressed_data
                    logger.info(
                        f"Compression applied: {format_file_size(original_size)} → "
                        f"{format_file_size(compression_result.compressed_size)} "
                        f"({compression_result.method_used})"
                    )

                # Update compression metadata
                compression_metadata = {
                    "compressed": compression_result.was_compressed,
                    "original_size": compression_result.original_size,
                    "compressed_size": compression_result.compressed_size,
                    "compression_ratio": compression_result.compression_ratio,
                    "method": compression_result.method_used,
                }

            except Exception as e:
                logger.warning(f"Compression attempt failed for {filename}: {e}")
                # Continue with uncompressed file

        # Extract text (may return None for unsupported types)
        # Note: Extract from the potentially compressed file
        try:
            extracted_text = cls.extract_text(file_content, content_type, filename)
        except Exception as e:
            logger.warning(f"Text extraction failed for {filename}: {e}")
            extracted_text = None

        return file_content, content_type, extracted_text, compression_metadata
