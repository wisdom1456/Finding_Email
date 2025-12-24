from __future__ import annotations

import mimetypes
import os
import time

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.utils.logging_config import get_module_logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = get_module_logger(__name__)

# Conditional imports for PDF extraction
# Try PyMuPDF first (better quality), then pypdf (lightweight, works on Vercel)
FITZ_AVAILABLE = False
PYPDF_AVAILABLE = False

try:
    import fitz  # PyMuPDF

    FITZ_AVAILABLE = True
    logger.debug("PyMuPDF (fitz) available for PDF extraction")
except ImportError:
    logger.debug("PyMuPDF (fitz) not available")

try:
    from pypdf import PdfReader

    PYPDF_AVAILABLE = True
    logger.debug("pypdf available for PDF extraction")
except ImportError:
    logger.debug("pypdf not available")


def _wait_for_file_ready(file_path: str, max_wait_seconds: float = 2.0) -> bool:
    """Wait for file to be fully written and accessible.

    Args:
    ----
        file_path: Path to file to check
        max_wait_seconds: Maximum time to wait in seconds

    Returns:
    -------
        True if file is ready, False if timeout

    """
    start_time = time.time()
    last_size = -1
    stable_count = 0

    while time.time() - start_time < max_wait_seconds:
        try:
            if not os.path.exists(file_path):
                time.sleep(0.1)
                continue

            # Check if file size is stable (not being written)
            current_size = os.path.getsize(file_path)
            if current_size == last_size and current_size > 0:
                stable_count += 1
                if stable_count >= 2:  # Stable for 2 checks (0.2 seconds)
                    return True
            else:
                stable_count = 0

            last_size = current_size
            time.sleep(0.1)
        except (IOError, OSError):
            time.sleep(0.1)
            continue

    return os.path.exists(file_path)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=1.0),
    retry=retry_if_exception_type((IOError, OSError, FileNotFoundError)),
    reraise=True,
)
def _open_pdf_with_fitz_retry(file_path: str):
    """Open PDF with retry logic for filesystem sync issues using PyMuPDF."""
    if not FITZ_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) not available")

    # First ensure file is ready
    if not _wait_for_file_ready(file_path, max_wait_seconds=2.0):
        raise FileNotFoundError(f"File not ready after waiting: {file_path}")

    return fitz.open(file_path)


def _extract_text_with_fitz(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF (fitz)."""
    text_parts = []
    with _open_pdf_with_fitz_retry(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "".join(text_parts)


def _extract_text_with_pypdf(file_path: str) -> str:
    """Extract text from PDF using pypdf (lightweight)."""
    if not PYPDF_AVAILABLE:
        raise ImportError("pypdf not available")

    # First ensure file is ready
    if not _wait_for_file_ready(file_path, max_wait_seconds=2.0):
        raise FileNotFoundError(f"File not ready after waiting: {file_path}")

    text_parts = []
    with open(file_path, "rb") as f:
        reader = PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def detect_pdf_corruption(file_path: str) -> tuple[bool, str]:
    """Detect if PDF is corrupt and provide reason.

    Args:
    ----
        file_path: Path to PDF file to check

    Returns:
    -------
        Tuple of (is_valid, reason_message)

    """
    if not os.path.exists(file_path):
        return False, "File not found"

    file_size = os.path.getsize(file_path)
    if file_size < 100:
        return False, f"File too small ({file_size} bytes)"

    # Check PDF header
    try:
        with open(file_path, "rb") as f:
            header = f.read(5)
            if header != b"%PDF-":
                return False, "Invalid PDF header"
    except Exception as e:
        return False, f"Cannot read file: {str(e)}"

    # Try opening with available library
    if FITZ_AVAILABLE:
        try:
            with fitz.open(file_path) as doc:
                if doc.page_count == 0:
                    return False, "No pages found"
                return True, "Valid PDF"
        except Exception as e:
            return False, f"Cannot open: {str(e)}"
    elif PYPDF_AVAILABLE:
        try:
            with open(file_path, "rb") as f:
                reader = PdfReader(f)
                if len(reader.pages) == 0:
                    return False, "No pages found"
                return True, "Valid PDF"
        except Exception as e:
            return False, f"Cannot open: {str(e)}"
    else:
        return False, "No PDF library available"


async def process_pdf(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """Process a PDF file by extracting its text content.

    Uses PyMuPDF (fitz) if available, falls back to pypdf (lightweight).

    Args:
    ----
        file_path: Path to the PDF file
        document_type: Type classification for the document
        original_filename: Original name of the file

    Returns:
    -------
        ProcessedDocument with extracted text content

    """
    logger.debug(f"Processing PDF: {original_filename}")

    text_content = ""
    file_size = 0

    # Pre-validate file exists and has reasonable size
    if not os.path.exists(file_path):
        logger.error(f"PDF file not found: {file_path}")
        text_content = f"Error: PDF file not found - {original_filename}"
    else:
        file_size = os.path.getsize(file_path)

        # Reject suspiciously small PDFs (< 100 bytes likely corrupt)
        if file_size < 100:
            logger.warning(f"Suspiciously small PDF ({file_size} bytes): {original_filename}")
            text_content = f"Error: PDF file too small to be valid ({file_size} bytes)"
        else:
            # Try PyMuPDF first (better quality extraction)
            if FITZ_AVAILABLE:
                try:
                    text_content = _extract_text_with_fitz(file_path)
                    logger.info(f"✅ Successfully extracted text from {original_filename} using PyMuPDF")
                except Exception as e:
                    logger.warning(f"PyMuPDF extraction failed for {original_filename}: {e}")
                    text_content = ""

            # Fall back to pypdf if PyMuPDF failed or unavailable
            if not text_content and PYPDF_AVAILABLE:
                try:
                    text_content = _extract_text_with_pypdf(file_path)
                    logger.info(f"✅ Successfully extracted text from {original_filename} using pypdf")
                except Exception as e:
                    error_msg = str(e)
                    if "Stream has ended unexpectedly" in error_msg:
                        logger.error(f"PDF stream truncated for {original_filename}: {error_msg}")
                        text_content = (
                            f"Error: PDF file appears to be truncated or corrupted - {original_filename}"
                        )
                    else:
                        logger.error(f"pypdf extraction failed for {original_filename}: {e}")
                        text_content = f"Error extracting text from {original_filename}: {error_msg}"

            # No library available or both failed
            if not text_content:
                if not FITZ_AVAILABLE and not PYPDF_AVAILABLE:
                    logger.error(f"No PDF library available to extract text from {original_filename}")
                    text_content = f"Error: No PDF extraction library available for {original_filename}"
                elif not text_content.startswith("Error"):
                    # Extraction returned empty string (possibly scanned PDF)
                    logger.warning(f"No text extracted from {original_filename} (possibly scanned/image PDF)")
                    text_content = (
                        f"[No text content extracted from {original_filename} - may be a scanned/image PDF]"
                    )

    content_type, _ = mimetypes.guess_type(file_path)

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(file_name=original_filename, file_type=FileType.PDF, file_size=file_size)

    if text_content.startswith("Error") or text_content.startswith("[No text"):
        logger.warning(f"⚠️ Created fallback metadata for {original_filename}, size: {file_size}")
    else:
        logger.info(f"✅ Created FileMetadata for {original_filename}, size: {file_size}")

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.PDF,
        metadata=file_metadata,
    )
