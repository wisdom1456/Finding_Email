from __future__ import annotations

import mimetypes
import os
import time

import fitz  # PyMuPDF
from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.utils.logging_config import get_module_logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = get_module_logger(__name__)


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
def _open_pdf_with_retry(file_path: str):
    """Open PDF with retry logic for filesystem sync issues."""
    # First ensure file is ready
    if not _wait_for_file_ready(file_path, max_wait_seconds=2.0):
        raise FileNotFoundError(f"File not ready after waiting: {file_path}")

    return fitz.open(file_path)


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

    # Try opening
    try:
        with fitz.open(file_path) as doc:
            if doc.page_count == 0:
                return False, "No pages found"
            return True, "Valid PDF"
    except Exception as e:
        return False, f"Cannot open: {str(e)}"


async def process_pdf(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """Process a PDF file by extracting its text content using PyMuPDF from a given path."""
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
            try:
                with _open_pdf_with_retry(file_path) as doc:
                    for page in doc:
                        text_content += page.get_text()
                logger.info(f"✅ Successfully extracted text from {original_filename}")
            except Exception as e:
                logger.error(f"Error processing PDF {original_filename}: {e}")
                text_content = f"Error extracting text from {original_filename}: {str(e)}"

    content_type, _ = mimetypes.guess_type(file_path)

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(file_name=original_filename, file_type=FileType.PDF, file_size=file_size)

    if text_content.startswith("Error"):
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
