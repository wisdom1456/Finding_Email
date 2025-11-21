"""Document processing utilities for downloading and extracting text from files.
"""

import io
from typing import Optional, Tuple

import fitz  # PyMuPDF
import requests
from docx import Document


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

        Args:
        ----
            file_content: PDF file bytes

        Returns:
        -------
            Extracted text
        """
        try:
            # Open PDF from bytes
            pdf_document = fitz.open(stream=file_content, filetype="pdf")

            text_parts = []
            for page_num in range(pdf_document.page_count):
                page = pdf_document[page_num]
                text_parts.append(page.get_text())

            pdf_document.close()
            return "\n\n".join(text_parts)
        except Exception as e:
            raise Exception(f"Failed to extract text from PDF: {str(e)}")

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
        try:
            doc = Document(io.BytesIO(file_content))
            text_parts = [paragraph.text for paragraph in doc.paragraphs]
            return "\n".join(text_parts)
        except Exception as e:
            raise Exception(f"Failed to extract text from DOCX: {str(e)}")

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
            raise Exception(f"Failed to extract text from TXT: {str(e)}")

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
            return cls.extract_text_from_pdf(file_content)

        # DOCX
        elif (
            content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or extension == "docx"
        ):
            return cls.extract_text_from_docx(file_content)

        # Plain text
        elif content_type.startswith("text/") or extension in ["txt", "text", "log", "md"]:
            return cls.extract_text_from_txt(file_content)

        # Unsupported type
        else:
            return None

    @classmethod
    def download_and_extract(
        cls, url: str, access_token: str, filename: str = ""
    ) -> Tuple[bytes, str, Optional[str]]:
        """Download file and extract text in one operation.

        Args:
        ----
            url: URL to download from
            access_token: OAuth access token
            filename: Original filename for type detection

        Returns:
        -------
            Tuple of (file_content, content_type, extracted_text)

        Raises:
        ------
            Exception: If download fails
        """
        # Download file
        file_content, content_type = cls.download_file(url, access_token)

        # Extract text (may return None for unsupported types)
        try:
            extracted_text = cls.extract_text(file_content, content_type, filename)
        except Exception as e:
            print(f"Warning: Text extraction failed: {e}")
            extracted_text = None

        return file_content, content_type, extracted_text
