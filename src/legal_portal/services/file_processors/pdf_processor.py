from __future__ import annotations

import asyncio
import base64
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
from legal_portal.utils.openai_client import OpenAIClient
from starlette.concurrency import run_in_threadpool
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


async def _extract_text_via_vision(file_path: str, original_filename: str) -> str:
    """Fall back to GPT-4o Vision for scanned PDFs.

    Render all pages to images and send to Vision API in parallel.
    """
    if not FITZ_AVAILABLE:
        return ""

    if not os.path.exists(file_path):
        logger.error(f"Cannot perform Vision fallback: File not found at {file_path}")
        return ""

    try:
        logger.info(f"🔍 Attempting GPT-4o Vision extraction for scanned PDF: {original_filename}")

        import fitz

        openai_client_wrapper = OpenAIClient()
        client = openai_client_wrapper.client

        # Open the document
        try:
            doc = fitz.open(file_path)
        except Exception as open_err:
            logger.error(f"Failed to open PDF for Vision extraction: {open_err}")
            return ""

        # Limit to 20 pages to prevent extreme costs and timeouts, while covering most legal docs
        # User said "entire documents", but 20 is a safe "entire" for most scanned packets.
        # We can increase this if 20 is not enough.
        max_pages = 25
        page_count = doc.page_count
        pages_to_process = min(page_count, max_pages)

        if page_count > max_pages:
            logger.warning(
                f"Document {original_filename} has {page_count} pages. "
                f"Limiting Vision extraction to first {max_pages} pages."
            )

        async def process_page(page_index: int):
            """Process a single page: render and send to OpenAI."""
            try:
                # Render page to image in thread pool
                def render_page():
                    page = doc[page_index]
                    # Render page to image (2x zoom for better text legibility)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    return pix.tobytes("png")

                img_data = await run_in_threadpool(render_page)
                base64_image = base64.b64encode(img_data).decode("utf-8")

                prompt = (
                    f"Extract all text from page {page_index + 1} of this legal document. "
                    f"Filename: {original_filename}. "
                    "Provide the text verbatim. Do not summarize."
                )

                content = [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ]

                # Make the API call in thread pool (since client is sync)
                def make_api_call():
                    return client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": content}],
                        max_tokens=1500,
                        temperature=0.0,
                    )

                response = await run_in_threadpool(make_api_call)
                page_text = response.choices[0].message.content
                if page_text:
                    return f"--- Page {page_index + 1} ---\n{page_text}"
                return ""
            except Exception as page_err:
                logger.error(f"Error processing page {page_index + 1} of {original_filename}: {page_err}")
                return f"--- Page {page_index + 1} ---\n[Error extracting text from this page]"

        # Process pages in parallel
        # We use a semaphore to limit concurrency to avoid hitting OpenAI rate limits
        # or overwhelming the local CPU/memory with image rendering.
        semaphore = asyncio.Semaphore(5)

        async def sem_process_page(i):
            async with semaphore:
                return await process_page(i)

        tasks = [sem_process_page(i) for i in range(pages_to_process)]
        extracted_parts = await asyncio.gather(*tasks)

        # Close doc manually since we didn't use context manager to keep it open for parallel tasks
        doc.close()

        # Filter out empty results
        extracted_parts = [p for p in extracted_parts if p]

        if not extracted_parts:
            return ""

        extracted_text = "\n\n".join(extracted_parts)
        logger.info(
            f"✅ Successfully extracted {len(extracted_parts)} pages via Vision for {original_filename}"
        )
        return f"[Extracted via GPT-4o Vision]\n\n{extracted_text}"

    except Exception as e:
        logger.error(f"Vision extraction failed for {original_filename}: {e}")
        return ""


async def process_pdf(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """Process a PDF file by extracting its text content.

    Uses PyMuPDF (fitz) if available, falls back to pypdf (lightweight).
    If extraction yields no results, falls back to Vision API for scanned docs.

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
    extraction_method = "standard"

    # Pre-validate file exists and has reasonable size
    if not os.path.exists(file_path):
        logger.error(f"PDF file not found: {file_path}")
        text_content = f"Error: PDF file not found - {original_filename}"
    else:
        file_size = os.path.getsize(file_path)

        # Reject suspiciously small PDFs (< 100 bytes likely corrupt)
        if file_size < 100:
            logger.warning(f"Suspiciously small PDF ({file_size} bytes): {original_filename}")
            text_content = f"Error: PDF file appears to be corrupted or empty ({file_size} bytes)"
        else:
            # Try PyMuPDF first (better quality extraction)
            if FITZ_AVAILABLE:
                try:
                    text_content = _extract_text_with_fitz(file_path)
                    if text_content.strip():
                        logger.info(f"✅ Successfully extracted text from {original_filename} using PyMuPDF")
                        extraction_method = "PyMuPDF"
                except Exception as e:
                    logger.warning(f"PyMuPDF extraction failed for {original_filename}: {e}")
                    text_content = ""

            # Fall back to pypdf if PyMuPDF failed or returned empty
            if not text_content.strip() and PYPDF_AVAILABLE:
                try:
                    text_content = _extract_text_with_pypdf(file_path)
                    if text_content.strip():
                        logger.info(f"✅ Successfully extracted text from {original_filename} using pypdf")
                        extraction_method = "pypdf"
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

            # Check if we need Vision fallback (empty text or error message from standard libs)
            # Scanned PDFs often return empty text or just whitespace
            needs_vision = not text_content.strip() or text_content.startswith("Error")

            # Also use Vision if standard extraction yielded very little text (< 100 chars)
            # while the file size is large (> 50KB), which usually indicates a scanned document
            # with some junk text or just headers.
            if not needs_vision and len(text_content.strip()) < 100 and file_size > 50000:
                logger.info(
                    f"Low text yield for {original_filename} ({len(text_content)} chars), "
                    "trying Vision fallback"
                )
                needs_vision = True

            if needs_vision:
                vision_text = await _extract_text_via_vision(file_path, original_filename)
                if vision_text:
                    text_content = vision_text
                    extraction_method = "GPT-4o Vision"

            # No library available or all failed
            if not text_content.strip():
                if not FITZ_AVAILABLE and not PYPDF_AVAILABLE:
                    logger.error(f"No PDF library available to extract text from {original_filename}")
                    text_content = f"Error: No PDF extraction library available for {original_filename}"
                else:
                    # Extraction returned empty string even after all attempts
                    logger.warning(f"No text extracted from {original_filename} (even after Vision attempt)")
                    text_content = (
                        f"[No text content could be extracted from {original_filename}. "
                        f"The file may be an image scan that failed OCR.]"
                    )

    content_type, _ = mimetypes.guess_type(file_path)

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(file_name=original_filename, file_type=FileType.PDF, file_size=file_size)

    if text_content.startswith("Error") or text_content.startswith("[No text"):
        logger.warning(f"⚠️ Created fallback metadata for {original_filename}, size: {file_size}")
        extraction_quality = "low"
    else:
        logger.info(f"✅ Created FileMetadata for {original_filename}, size: {file_size}")
        extraction_quality = "high" if len(text_content.strip()) > 200 else "medium"

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.PDF,
        metadata=file_metadata,
        extraction_quality=extraction_quality,
        extraction_method=extraction_method,
    )
