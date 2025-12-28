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
from legal_portal.utils.google_vision_client import GoogleVisionClient
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


# ============================================================================
# BYTES-BASED EXTRACTION FUNCTIONS
# These avoid filesystem race conditions in Vercel serverless by working
# directly with bytes in memory instead of file paths.
# ============================================================================


def _extract_text_with_fitz_bytes(pdf_bytes: bytes, original_filename: str) -> str:
    """Extract text from PDF bytes using PyMuPDF (fitz).

    Args:
    ----
        pdf_bytes: PDF file content as bytes
        original_filename: Original filename for logging

    Returns:
    -------
        Extracted text content

    """
    if not FITZ_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) not available")

    import fitz

    text_parts = []
    # Open from memory stream instead of file path
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "".join(text_parts)


def _extract_text_with_pypdf_bytes(pdf_bytes: bytes, original_filename: str) -> str:
    """Extract text from PDF bytes using pypdf (lightweight).

    Args:
    ----
        pdf_bytes: PDF file content as bytes
        original_filename: Original filename for logging

    Returns:
    -------
        Extracted text content

    """
    if not PYPDF_AVAILABLE:
        raise ImportError("pypdf not available")

    import io

    text_parts = []
    # Read from BytesIO stream instead of file
    reader = PdfReader(io.BytesIO(pdf_bytes))
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


async def _extract_text_via_google_ocr(
    file_path: str,
    original_filename: str,
    progress_callback=None,
) -> str:
    """Extract text from scanned PDF using Google Cloud Vision OCR.

    Much faster and cheaper than GPT-4o Vision (~$1.50/1000 pages vs ~$15-30).

    Args:
    ----
        file_path: Path to the PDF file
        original_filename: Original filename for logging
        progress_callback: Optional callback for granular progress updates

    Returns:
    -------
        Extracted text or empty string on failure

    """
    if not FITZ_AVAILABLE:
        logger.warning("PyMuPDF not available for PDF rendering")
        return ""

    # Check if Google Vision is available
    logger.debug("Getting Google Vision client instance...")
    google_client = GoogleVisionClient.get_instance()

    if not google_client.is_available:
        logger.warning(
            "Google Vision client not available. "
            "Check GOOGLE_APPLICATION_CREDENTIALS_JSON env var is set correctly."
        )
        return ""

    logger.info("Google Vision client is available, validating credentials...")

    # Validate credentials before proceeding
    valid, validation_msg = google_client.validate_credentials()
    if not valid:
        logger.error(f"Google Vision credentials invalid: {validation_msg}")
        logger.error("Falling back to GPT-4o Vision. Check your service account key.")
        return ""

    if not os.path.exists(file_path):
        logger.error(f"Cannot perform Google OCR: File not found at {file_path}")
        return ""

    try:
        logger.info(f"🔍 Starting Google Cloud Vision OCR for: {original_filename}")

        import fitz

        # Open the document
        try:
            doc = fitz.open(file_path)
        except Exception as open_err:
            logger.error(f"Failed to open PDF for Google OCR: {open_err}")
            return ""

        # Process all pages (Google Vision is fast enough)
        max_pages = 50  # Higher limit since Google Vision is faster
        page_count = doc.page_count
        pages_to_process = min(page_count, max_pages)

        if page_count > max_pages:
            logger.warning(
                f"Document {original_filename} has {page_count} pages. "
                f"Limiting OCR to first {max_pages} pages."
            )

        # Send initial progress update
        if progress_callback:
            try:
                await progress_callback(
                    f"OCR: Starting Google Vision for {original_filename} ({pages_to_process} pages)",
                    "google_ocr_start",
                )
            except Exception:
                pass

        extracted_parts = []
        completed_pages = [0]

        # Process pages with high concurrency (Google Vision handles it well)
        semaphore = asyncio.Semaphore(15)

        async def process_page(page_index: int) -> str:
            """Render page and extract text via Google Vision."""
            async with semaphore:
                try:
                    # Render page to image
                    logger.debug(f"Rendering page {page_index + 1} of {original_filename}")

                    def render_page():
                        page = doc[page_index]
                        # 2x zoom for better OCR accuracy
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        return pix.tobytes("png")

                    img_data = await run_in_threadpool(render_page)
                    logger.debug(f"Page {page_index + 1} rendered, size: {len(img_data)} bytes")

                    # Send to Google Vision (in thread pool since it's sync)
                    # Add timeout to prevent hanging on auth issues
                    def do_ocr():
                        return google_client.extract_text_from_image(img_data)

                    try:
                        logger.debug(f"Sending page {page_index + 1} to Google Vision API")
                        page_text = await asyncio.wait_for(
                            run_in_threadpool(do_ocr),
                            timeout=30.0,
                        )
                        logger.debug(f"Google Vision returned for page {page_index + 1}")
                    except asyncio.TimeoutError:
                        logger.error(
                            f"Google Vision API timeout on page {page_index + 1} of {original_filename} "
                            "(30s limit). Check credentials or network."
                        )
                        completed_pages[0] += 1
                        return ""

                    # Update progress
                    completed_pages[0] += 1
                    if progress_callback:
                        try:
                            msg = (
                                f"OCR: Page {completed_pages[0]}/{pages_to_process} "
                                f"of {original_filename}"
                            )
                            await progress_callback(msg, f"page_{page_index + 1}")
                        except Exception:
                            pass

                    if page_text and page_text.strip():
                        return f"--- Page {page_index + 1} ---\n{page_text.strip()}"
                    return ""

                except Exception as page_err:
                    logger.error(
                        f"Google OCR error on page {page_index + 1} of {original_filename}: {page_err}"
                    )
                    completed_pages[0] += 1
                    return ""

        # Process all pages in parallel
        tasks = [process_page(i) for i in range(pages_to_process)]
        results = await asyncio.gather(*tasks)

        # Close doc
        doc.close()

        # Filter and combine results
        extracted_parts = [r for r in results if r]

        if not extracted_parts:
            logger.warning(f"Google OCR returned no text for {original_filename}")
            return ""

        extracted_text = "\n\n".join(extracted_parts)
        logger.info(f"✅ Google Vision OCR extracted {len(extracted_parts)} pages from {original_filename}")
        return f"[Extracted via Google Cloud Vision OCR]\n\n{extracted_text}"

    except Exception as e:
        logger.error(f"Google Vision OCR failed for {original_filename}: {e}")
        return ""


async def _extract_text_via_google_ocr_bytes(
    pdf_bytes: bytes,
    original_filename: str,
    progress_callback=None,
) -> str:
    """Extract text from PDF bytes using Google Cloud Vision OCR.

    BYTES-BASED VERSION: Works directly with PDF bytes to avoid filesystem issues.

    Args:
    ----
        pdf_bytes: PDF file content as bytes
        original_filename: Original filename for logging
        progress_callback: Optional callback for granular progress updates

    Returns:
    -------
        Extracted text or empty string on failure

    """
    if not FITZ_AVAILABLE:
        logger.warning("PyMuPDF not available for PDF rendering")
        return ""

    # Check if Google Vision is available
    logger.debug("Getting Google Vision client instance...")
    google_client = GoogleVisionClient.get_instance()

    if not google_client.is_available:
        logger.warning(
            "Google Vision client not available. "
            "Check GOOGLE_APPLICATION_CREDENTIALS_JSON env var is set correctly."
        )
        return ""

    logger.info("Google Vision client is available, validating credentials...")

    # Validate credentials before proceeding
    valid, validation_msg = google_client.validate_credentials()
    if not valid:
        logger.error(f"Google Vision credentials invalid: {validation_msg}")
        logger.error("Falling back to GPT-4o Vision. Check your service account key.")
        return ""

    try:
        logger.info(f"🔍 Starting Google Cloud Vision OCR for: {original_filename}")

        import fitz

        # Open from memory stream instead of file path
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            logger.debug(f"Opened PDF from memory: {original_filename} ({len(pdf_bytes)} bytes)")
        except Exception as open_err:
            # Log bytes info for debugging invalid content
            header = pdf_bytes[:20] if pdf_bytes else b""
            logger.error(
                f"Failed to open PDF bytes for Google OCR: {open_err}. "
                f"Size: {len(pdf_bytes) if pdf_bytes else 0} bytes, Header: {header!r}"
            )
            return ""

        # Process all pages (Google Vision is fast enough)
        max_pages = 50  # Higher limit since Google Vision is faster
        page_count = doc.page_count
        pages_to_process = min(page_count, max_pages)

        if page_count > max_pages:
            logger.warning(
                f"Document {original_filename} has {page_count} pages. "
                f"Limiting OCR to first {max_pages} pages."
            )

        # Send initial progress update
        if progress_callback:
            try:
                await progress_callback(
                    f"OCR: Starting Google Vision for {original_filename} ({pages_to_process} pages)",
                    "google_ocr_start",
                )
            except Exception:
                pass

        extracted_parts = []
        completed_pages = [0]

        # Process pages with high concurrency (Google Vision handles it well)
        semaphore = asyncio.Semaphore(15)

        async def process_page(page_index: int) -> str:
            """Render page and extract text via Google Vision."""
            async with semaphore:
                try:
                    # Render page to image
                    logger.debug(f"Rendering page {page_index + 1} of {original_filename}")

                    def render_page():
                        page = doc[page_index]
                        # 2x zoom for better OCR accuracy
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        return pix.tobytes("png")

                    img_data = await run_in_threadpool(render_page)
                    logger.debug(f"Page {page_index + 1} rendered, size: {len(img_data)} bytes")

                    # Send to Google Vision (in thread pool since it's sync)
                    # Add timeout to prevent hanging on auth issues
                    def do_ocr():
                        return google_client.extract_text_from_image(img_data)

                    try:
                        logger.debug(f"Sending page {page_index + 1} to Google Vision API")
                        page_text = await asyncio.wait_for(
                            run_in_threadpool(do_ocr),
                            timeout=30.0,
                        )
                        logger.debug(f"Google Vision returned for page {page_index + 1}")
                    except asyncio.TimeoutError:
                        logger.error(
                            f"Google Vision API timeout on page {page_index + 1} of {original_filename} "
                            "(30s limit). Check credentials or network."
                        )
                        completed_pages[0] += 1
                        return ""

                    # Update progress
                    completed_pages[0] += 1
                    if progress_callback:
                        try:
                            msg = (
                                f"OCR: Page {completed_pages[0]}/{pages_to_process} "
                                f"of {original_filename}"
                            )
                            await progress_callback(msg, f"page_{page_index + 1}")
                        except Exception:
                            pass

                    if page_text and page_text.strip():
                        return f"--- Page {page_index + 1} ---\n{page_text.strip()}"
                    return ""

                except Exception as page_err:
                    logger.error(
                        f"Google OCR error on page {page_index + 1} of {original_filename}: {page_err}"
                    )
                    completed_pages[0] += 1
                    return ""

        # Process all pages in parallel
        tasks = [process_page(i) for i in range(pages_to_process)]
        results = await asyncio.gather(*tasks)

        # Close doc
        doc.close()

        # Filter and combine results
        extracted_parts = [r for r in results if r]

        if not extracted_parts:
            logger.warning(f"Google OCR returned no text for {original_filename}")
            return ""

        extracted_text = "\n\n".join(extracted_parts)
        logger.info(f"✅ Google Vision OCR extracted {len(extracted_parts)} pages from {original_filename}")
        return f"[Extracted via Google Cloud Vision OCR]\n\n{extracted_text}"

    except Exception as e:
        logger.error(f"Google Vision OCR failed for {original_filename}: {e}")
        return ""


async def _extract_text_via_vision(
    file_path: str,
    original_filename: str,
    progress_callback=None,
) -> str:
    """Fall back to GPT-4o Vision for scanned PDFs.

    Render all pages to images and send to Vision API in parallel.
    NOTE: This is now a secondary fallback after Google Cloud Vision.

    Args:
    ----
        file_path: Path to the PDF file
        original_filename: Original filename for logging
        progress_callback: Optional callback for granular progress updates

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

        # Limit to 25 pages to prevent extreme costs and timeouts
        max_pages = 25
        page_count = doc.page_count
        pages_to_process = min(page_count, max_pages)

        if page_count > max_pages:
            logger.warning(
                f"Document {original_filename} has {page_count} pages. "
                f"Limiting Vision extraction to first {max_pages} pages."
            )

        # Track completed pages for progress reporting
        completed_pages = [0]  # Use list for mutable in nested async

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

                # Update progress after successful page extraction
                completed_pages[0] += 1
                if progress_callback:
                    try:
                        msg = (
                            f"OCR: Extracted page {completed_pages[0]}/{pages_to_process} "
                            f"from {original_filename}"
                        )
                        await progress_callback(msg, f"page_{page_index + 1}")
                    except Exception:
                        pass  # Don't let progress callback errors stop extraction

                if page_text:
                    return f"--- Page {page_index + 1} ---\n{page_text}"
                return ""
            except Exception as page_err:
                logger.error(f"Error processing page {page_index + 1} of {original_filename}: {page_err}")
                completed_pages[0] += 1  # Still count as processed even if failed
                return f"--- Page {page_index + 1} ---\n[Error extracting text from this page]"

        # Process pages in parallel with increased concurrency (10 instead of 5)
        # This speeds up large documents while staying within OpenAI rate limits
        semaphore = asyncio.Semaphore(10)

        async def sem_process_page(i):
            async with semaphore:
                return await process_page(i)

        # Send initial progress update
        if progress_callback:
            try:
                await progress_callback(
                    f"OCR: Starting Vision extraction for {original_filename} ({pages_to_process} pages)",
                    "vision_start",
                )
            except Exception:
                pass

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


async def _extract_text_via_vision_bytes(
    pdf_bytes: bytes,
    original_filename: str,
    progress_callback=None,
) -> str:
    """Fall back to GPT-4o Vision for scanned PDFs.

    BYTES-BASED VERSION: Works directly with PDF bytes to avoid filesystem issues.

    Args:
    ----
        pdf_bytes: PDF file content as bytes
        original_filename: Original filename for logging
        progress_callback: Optional callback for granular progress updates

    """
    if not FITZ_AVAILABLE:
        return ""

    try:
        logger.info(f"🔍 Attempting GPT-4o Vision extraction for scanned PDF: {original_filename}")

        import fitz

        openai_client_wrapper = OpenAIClient()
        client = openai_client_wrapper.client

        # Open from memory stream instead of file path
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            logger.debug(f"Opened PDF from memory for Vision: {original_filename} ({len(pdf_bytes)} bytes)")
        except Exception as open_err:
            # Log bytes info for debugging invalid content
            header = pdf_bytes[:20] if pdf_bytes else b""
            logger.error(
                f"Failed to open PDF bytes for Vision extraction: {open_err}. "
                f"Size: {len(pdf_bytes) if pdf_bytes else 0} bytes, Header: {header!r}"
            )
            return ""

        # Limit to 25 pages to prevent extreme costs and timeouts
        max_pages = 25
        page_count = doc.page_count
        pages_to_process = min(page_count, max_pages)

        if page_count > max_pages:
            logger.warning(
                f"Document {original_filename} has {page_count} pages. "
                f"Limiting Vision extraction to first {max_pages} pages."
            )

        # Track completed pages for progress reporting
        completed_pages = [0]  # Use list for mutable in nested async

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

                # Update progress after successful page extraction
                completed_pages[0] += 1
                if progress_callback:
                    try:
                        msg = (
                            f"OCR: Extracted page {completed_pages[0]}/{pages_to_process} "
                            f"from {original_filename}"
                        )
                        await progress_callback(msg, f"page_{page_index + 1}")
                    except Exception:
                        pass  # Don't let progress callback errors stop extraction

                if page_text:
                    return f"--- Page {page_index + 1} ---\n{page_text}"
                return ""
            except Exception as page_err:
                logger.error(f"Error processing page {page_index + 1} of {original_filename}: {page_err}")
                completed_pages[0] += 1  # Still count as processed even if failed
                return f"--- Page {page_index + 1} ---\n[Error extracting text from this page]"

        # Process pages in parallel with increased concurrency (10 instead of 5)
        # This speeds up large documents while staying within OpenAI rate limits
        semaphore = asyncio.Semaphore(10)

        async def sem_process_page(i):
            async with semaphore:
                return await process_page(i)

        # Send initial progress update
        if progress_callback:
            try:
                await progress_callback(
                    f"OCR: Starting Vision extraction for {original_filename} ({pages_to_process} pages)",
                    "vision_start",
                )
            except Exception:
                pass

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
    file_path: str,
    document_type: DocumentType,
    original_filename: str,
    progress_callback=None,
) -> ProcessedDocument:
    """Process a PDF file by extracting its text content.

    Uses PyMuPDF (fitz) if available, falls back to pypdf (lightweight).
    If extraction yields no results, falls back to Vision API for scanned docs.

    IMPORTANT: Reads file into memory ONCE to avoid Vercel serverless filesystem
    race conditions where files may not be fully synced to disk.

    Args:
    ----
        file_path: Path to the PDF file
        document_type: Type classification for the document
        original_filename: Original name of the file
        progress_callback: Optional callback for granular progress updates

    Returns:
    -------
        ProcessedDocument with extracted text content

    """
    logger.debug(f"Processing PDF: {original_filename}")

    text_content = ""
    file_size = 0
    extraction_method = "standard"
    pdf_bytes = None

    # Pre-validate file exists and read into memory ONCE
    # This avoids race conditions in Vercel serverless where files may not be fully synced
    if not os.path.exists(file_path):
        logger.error(f"PDF file not found: {file_path}")
        text_content = f"Error: PDF file not found - {original_filename}"
    else:
        try:
            # Read file into memory once - eliminates filesystem race conditions
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()
            file_size = len(pdf_bytes)
            logger.debug(f"Read {file_size} bytes from {original_filename} into memory")

            # Validate PDF header - must start with %PDF-
            # This catches cases where Supabase returned an error response instead of file content
            if not pdf_bytes.startswith(b"%PDF-"):
                first_bytes = pdf_bytes[:100].decode("utf-8", errors="replace")
                logger.error(
                    f"Invalid PDF content for {original_filename}: "
                    f"Expected PDF header, got: {first_bytes[:50]}..."
                )
                text_content = f"Error: Downloaded content is not a valid PDF - {original_filename}"
                pdf_bytes = None  # Prevent further processing

        except Exception as read_err:
            logger.error(f"Failed to read PDF into memory: {original_filename}: {read_err}")
            text_content = f"Error: Failed to read PDF file - {original_filename}"
            file_size = 0

    if pdf_bytes:
        # Reject suspiciously small PDFs (< 100 bytes likely corrupt)
        if file_size < 100:
            logger.warning(f"Suspiciously small PDF ({file_size} bytes): {original_filename}")
            text_content = f"Error: PDF file appears to be corrupted or empty ({file_size} bytes)"
        else:
            # Try PyMuPDF first (better quality extraction) - using bytes stream
            if FITZ_AVAILABLE:
                try:
                    text_content = _extract_text_with_fitz_bytes(pdf_bytes, original_filename)
                    if text_content.strip():
                        logger.info(f"✅ Successfully extracted text from {original_filename} using PyMuPDF")
                        extraction_method = "PyMuPDF"
                except Exception as e:
                    logger.warning(f"PyMuPDF extraction failed for {original_filename}: {e}")
                    text_content = ""

            # Fall back to pypdf if PyMuPDF failed or returned empty - using bytes stream
            if not text_content.strip() and PYPDF_AVAILABLE:
                try:
                    text_content = _extract_text_with_pypdf_bytes(pdf_bytes, original_filename)
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
                # Try Google Cloud Vision first (faster and cheaper) - using bytes
                vision_text = await _extract_text_via_google_ocr_bytes(
                    pdf_bytes, original_filename, progress_callback
                )
                if vision_text:
                    text_content = vision_text
                    extraction_method = "Google Cloud Vision"
                else:
                    # Fall back to GPT-4o Vision if Google Vision unavailable or failed
                    vision_text = await _extract_text_via_vision_bytes(
                        pdf_bytes, original_filename, progress_callback
                    )
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
