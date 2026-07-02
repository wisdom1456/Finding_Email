from __future__ import annotations

import asyncio
import base64
import io
import mimetypes
import os
import re
import time
from dataclasses import dataclass, field

from starlette.concurrency import run_in_threadpool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.utils.google_vision_client import GoogleVisionClient
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.metrics import MetricsCollector
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)

# --- OCR size constants ---
OCR_COMPRESS_THRESHOLD = 20 * 1024 * 1024    # 20MB — trigger compression early
SAFE_REMOTE_OCR_LIMIT = 28 * 1024 * 1024     # 28MB — safe transport ceiling
MAX_OCR_CHUNKS = 20                            # cap total chunks per document
OCR_CHUNK_SEMAPHORE = 3                        # max concurrent chunk OCR requests
OCR_CHUNK_TARGET_BYTES = 20 * 1024 * 1024     # target chunk size


@dataclass
class ChunkedOCRResult:
    """Result of chunked OCR extraction."""

    text: str
    ocr_status: str          # "complete" | "partial" | "failed"
    ocr_strategy: str        # "chunked"
    successful_page_ranges: list[str] = field(default_factory=list)
    failed_page_ranges: list[str] = field(default_factory=list)
    total_chunks: int = 0
    successful_chunks: int = 0


async def _ocr_pdf_in_chunks(
    pdf_bytes: bytes,
    original_filename: str,
    ocr_client,
    comp_svc,
    target_chunk_bytes: int = OCR_CHUNK_TARGET_BYTES,
    safe_limit: int = SAFE_REMOTE_OCR_LIMIT,
    max_chunks: int = MAX_OCR_CHUNKS,
    concurrency: int = OCR_CHUNK_SEMAPHORE,
) -> ChunkedOCRResult:
    """Split a large PDF into size-aware chunks and OCR each via the remote service."""
    from pypdf import PdfReader, PdfWriter

    # --- Parse PDF ---
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        logger.error(f"[OCR:CHUNK:PDF_CORRUPT] {original_filename}: cannot parse PDF for chunking ({e})")
        return ChunkedOCRResult(text="", ocr_status="failed", ocr_strategy="chunked")

    total_pages = len(pdf_reader.pages)
    if total_pages == 0:
        return ChunkedOCRResult(text="", ocr_status="failed", ocr_strategy="chunked")

    # --- Build size-aware chunks ---
    def _build_chunks(target: int) -> list[tuple[bytes, str]]:
        """Build PDF chunks, each targeting `target` bytes. Returns [(chunk_bytes, page_range_str), ...]."""
        chunks: list[tuple[bytes, str]] = []
        writer = PdfWriter()
        chunk_start = 0

        for i, page in enumerate(pdf_reader.pages):
            writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            current_size = len(buf.getvalue())

            is_last_page = (i == total_pages - 1)
            if current_size >= target or is_last_page:
                chunk_bytes = buf.getvalue()
                page_range = f"{chunk_start + 1}-{i + 1}"
                chunks.append((chunk_bytes, page_range))
                writer = PdfWriter()
                chunk_start = i + 1

        return chunks

    chunks = _build_chunks(target_chunk_bytes)

    # Handle MAX_OCR_CHUNKS overflow
    if len(chunks) > max_chunks:
        logger.warning(
            f"[OCR:CHUNK:CAP_EXCEEDED] {original_filename}: {len(chunks)} chunks needed, "
            f"cap is {max_chunks}, attempting rebuild with larger target"
        )
        MetricsCollector.record_counter("ocr.chunk_cap_exceeded")
        # Rebuild with larger target
        larger_target = safe_limit - 2 * 1024 * 1024  # SAFE_REMOTE_OCR_LIMIT - 2MB
        chunks = _build_chunks(larger_target)

        if len(chunks) > max_chunks:
            # Trim to cap and mark remaining as failed
            overflow_ranges = [pr for _, pr in chunks[max_chunks:]]
            remaining_pages = sum(
                int(pr.split("-")[1]) - int(pr.split("-")[0]) + 1 for pr in overflow_ranges
            )
            logger.error(
                f"[OCR:CHUNK:CAP_EXCEEDED] {original_filename}: still {len(chunks)} chunks after rebuild, "
                f"cap is {max_chunks}, {remaining_pages} pages not extracted"
            )
            failed_overflow = overflow_ranges
            chunks = chunks[:max_chunks]
        else:
            failed_overflow = []
    else:
        failed_overflow = []

    num_chunks = len(chunks)
    logger.info(
        f"[OCR:CHUNK] {original_filename}: splitting {total_pages} pages into "
        f"{num_chunks} chunks (target {target_chunk_bytes / (1024*1024):.0f}MB each)"
    )
    MetricsCollector.record_counter("ocr.chunk_fallback_used")
    MetricsCollector.record_gauge("ocr.chunks_created", num_chunks)

    # --- OCR each chunk with concurrency control ---
    semaphore = asyncio.Semaphore(concurrency)

    async def ocr_chunk(chunk_index: int, chunk_bytes: bytes, page_range_str: str) -> tuple[int, str, bool]:
        """Returns (chunk_index, text, success)."""
        async with semaphore:
            # Size check — compress individual chunk if needed
            if len(chunk_bytes) > safe_limit:
                try:
                    comp_result = comp_svc.compress_pdf_for_ocr(
                        chunk_bytes, target_size_mb=safe_limit / (1024 * 1024)
                    )
                    if comp_result.was_compressed and comp_result.compressed_size <= safe_limit:
                        chunk_bytes = comp_result.compressed_data
                    else:
                        logger.error(
                            f"[OCR:CHUNK:TOO_LARGE] {original_filename} pages {page_range_str}: "
                            f"{len(chunk_bytes) / (1024*1024):.1f}MB even after compression"
                        )
                        MetricsCollector.record_counter("ocr.chunk_too_large")
                        return (chunk_index, f"[Pages {page_range_str}: extraction failed — chunk too large for OCR]", False)
                except Exception as e:
                    logger.error(
                        f"[OCR:CHUNK:TOO_LARGE] {original_filename} pages {page_range_str}: "
                        f"compression error: {e}"
                    )
                    MetricsCollector.record_counter("ocr.chunk_too_large")
                    return (chunk_index, f"[Pages {page_range_str}: extraction failed — chunk too large for OCR]", False)

            try:
                result = await ocr_client.extract_text(
                    chunk_bytes, f"{original_filename}_chunk{chunk_index}.pdf", "application/pdf"
                )
                chunk_text = result.get("full_text", "") if isinstance(result, dict) else ""
                if not chunk_text or not chunk_text.strip():
                    logger.warning(
                        f"[OCR:CHUNK:EMPTY] {original_filename} pages {page_range_str}: OCR returned empty text"
                    )
                    MetricsCollector.record_counter("ocr.chunk_empty")
                    return (chunk_index, f"[Pages {page_range_str}: extraction returned no text]", False)
                return (chunk_index, chunk_text, True)
            except Exception as e:
                logger.error(
                    f"[OCR:CHUNK:FAILED] {original_filename} pages {page_range_str}: {type(e).__name__}: {e}"
                )
                MetricsCollector.record_counter("ocr.chunk_ocr_failed")
                return (chunk_index, f"[Pages {page_range_str}: extraction failed — {type(e).__name__}]", False)

    tasks = [
        ocr_chunk(i, chunk_bytes, page_range)
        for i, (chunk_bytes, page_range) in enumerate(chunks)
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # --- Reassemble in page order ---
    successful_ranges: list[str] = []
    failed_ranges: list[str] = list(failed_overflow)
    ordered_texts: list[tuple[int, str, str]] = []  # (index, text, page_range)

    for i, raw in enumerate(raw_results):
        page_range = chunks[i][1]
        if isinstance(raw, Exception):
            logger.error(f"[OCR:CHUNK:FAILED] {original_filename} pages {page_range}: {raw}")
            MetricsCollector.record_counter("ocr.chunk_ocr_failed")
            ordered_texts.append((i, f"[Pages {page_range}: extraction failed — {type(raw).__name__}]", page_range))
            failed_ranges.append(page_range)
        else:
            chunk_index, text, success = raw
            ordered_texts.append((chunk_index, text, page_range))
            if success:
                successful_ranges.append(page_range)
            else:
                failed_ranges.append(page_range)

    ordered_texts.sort(key=lambda x: x[0])

    # Build final text with separators
    parts = []
    for _, text, page_range in ordered_texts:
        parts.append(f"\n\n--- Page Range {page_range} ---\n\n")
        parts.append(text)
    assembled_text = "".join(parts).strip()

    successful_count = len(successful_ranges)
    total_count = num_chunks + len(failed_overflow)

    if successful_count == 0:
        status = "failed"
    elif failed_ranges:
        status = "partial"
    else:
        status = "complete"

    if status == "complete":
        logger.info(
            f"[OCR:CHUNK:COMPLETE] {original_filename}: {len(assembled_text)} chars "
            f"from {successful_count}/{total_count} chunks"
        )
    elif status == "partial":
        logger.warning(
            f"[OCR:CHUNK:PARTIAL] {original_filename}: {len(failed_ranges)} chunks failed, "
            f"pages {', '.join(failed_ranges)} not extracted"
        )

    return ChunkedOCRResult(
        text=assembled_text,
        ocr_status=status,
        ocr_strategy="chunked",
        successful_page_ranges=successful_ranges,
        failed_page_ranges=failed_ranges,
        total_chunks=total_count,
        successful_chunks=successful_count,
    )


async def _ocr_with_fallback(
    img_data: bytes,
    page_index: int,
    original_filename: str,
    google_client: GoogleVisionClient,
) -> str:
    """Try Google Vision OCR with automatic fallback to GPT-4o Vision.

    Args:
    ----
        img_data: Image bytes (PNG)
        page_index: 0-based page index
        original_filename: Original filename for logging
        google_client: Google Vision client instance

    Returns:
    -------
        Extracted text or empty string on failure

    """
    # Try Google Vision first
    try:
        def do_ocr():
            return google_client.extract_text_from_image(img_data)

        page_text = await asyncio.wait_for(
            run_in_threadpool(do_ocr),
            timeout=30.0,
        )
        logger.debug(f"Google Vision returned for page {page_index + 1}")
        return page_text

    except ValueError as size_err:
        # Image too large for Google Vision - fall back to GPT-4o Vision
        logger.warning(f"Page {page_index + 1}: {size_err}. Falling back to GPT-4o Vision.")

        try:
            openai_client = OpenAIClient()
            client = openai_client.client

            base64_image = base64.b64encode(img_data).decode("utf-8")
            prompt = (
                f"Extract ALL text from page {page_index + 1} of this legal document image. "
                f"Filename: {original_filename}. "
                "This is a scanned document that needs OCR text extraction. "
                "Maintain the logical structure and layout. Provide the text verbatim."
            )

            def gpt4o_ocr():
                return client.chat.completions.create(
                    model="gpt-5.5",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}},
                        ]
                    }],
                    max_completion_tokens=4000,
                    reasoning_effort="none",
                    temperature=0.0,
                )

            response = await asyncio.wait_for(run_in_threadpool(gpt4o_ocr), timeout=60.0)
            page_text = response.choices[0].message.content
            logger.info(f"GPT-4o Vision fallback succeeded for page {page_index + 1}")
            return page_text

        except Exception as gpt_err:
            logger.error(f"GPT-4o Vision fallback also failed for page {page_index + 1}: {gpt_err}")
            return ""

    except asyncio.TimeoutError:
        logger.error(f"Google Vision API timeout on page {page_index + 1} of {original_filename}")
        return ""

    except Exception as e:
        logger.error(f"OCR failed for page {page_index + 1}: {e}")
        return ""


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


SIGNATURE_TEXT_PATTERNS = [
    ("Counterpart signature page", re.compile(r"\bcounterpart\s+signature\s+page\b", re.IGNORECASE)),
    ("Signed by marker", re.compile(r"\bsigned\s+by\b", re.IGNORECASE)),
    ("Electronic signature marker", re.compile(r"\belectronically\s+signed\b", re.IGNORECASE)),
    ("DocuSign envelope marker", re.compile(r"\bdocusign\s+envelope\s+id\b", re.IGNORECASE)),
    ("Signature label", re.compile(r"\bsignature\s*[:_]", re.IGNORECASE)),
]


def _normalize_pdf_signing_date(raw_date: str | None) -> str | None:
    """Normalize PDF signing date (D:YYYYMMDDHHMMSS-07'00') to ISO 8601."""
    if not raw_date:
        return None

    cleaned = raw_date.strip()
    if cleaned.startswith("D:"):
        cleaned = cleaned[2:]

    match = re.match(
        r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})"
        r"(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})?"
        r"(?:(?P<tz_sign>[+\-Z])(?P<tz_hour>\d{2})'? ?(?P<tz_min>\d{2})'?)?$",
        cleaned,
    )
    if not match:
        return raw_date

    year = match.group("year")
    month = match.group("month")
    day = match.group("day")
    hour = match.group("hour")
    minute = match.group("minute")
    second = match.group("second") or "00"
    tz_sign = match.group("tz_sign")
    tz_hour = match.group("tz_hour")
    tz_min = match.group("tz_min")

    if tz_sign and tz_sign != "Z" and tz_hour and tz_min:
        tz = f"{tz_sign}{tz_hour}:{tz_min}"
    elif tz_sign == "Z":
        tz = "Z"
    else:
        tz = ""

    return f"{year}-{month}-{day}T{hour}:{minute}:{second}{tz}"


def _extract_text_signature_markers(text: str) -> list[str]:
    """Extract textual indicators that a document is signed."""
    if not text:
        return []

    markers = []
    for label, pattern in SIGNATURE_TEXT_PATTERNS:
        if pattern.search(text):
            markers.append(label)
    return markers


def _extract_signer_names(decoded_pdf: str, extracted_text: str) -> list[str]:
    """Best-effort extraction of signer names from PDF metadata/text."""
    names: list[str] = []

    metadata_name_patterns = [
        re.compile(r"/Name\s*\(([^)]+)\)"),
        re.compile(r"/T\s*\(([^)]+)\)"),
    ]
    for pattern in metadata_name_patterns:
        for match in pattern.findall(decoded_pdf):
            candidate = re.sub(r"\s+", " ", match).strip()
            if candidate and 2 <= len(candidate) <= 80:
                names.append(candidate)

    text_name_patterns = [
        re.compile(r"(?im)^\s*signed\s+by\s*[:\-]\s*([A-Z][A-Za-z ,.'-]{2,80})\s*$"),
        re.compile(r"(?im)^\s*signature\s*[:\-]\s*([A-Z][A-Za-z ,.'-]{2,80})\s*$"),
    ]
    for pattern in text_name_patterns:
        for match in pattern.findall(extracted_text or ""):
            candidate = re.sub(r"\s+", " ", match).strip()
            if candidate and 2 <= len(candidate) <= 80:
                names.append(candidate)

    # Deduplicate while preserving order
    deduped: list[str] = []
    seen = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
        if len(deduped) >= 5:
            break

    return deduped


def _detect_pdf_signature(pdf_bytes: bytes, extracted_text: str) -> dict:
    """Detect digital/text signature indicators from PDF bytes and extracted text."""
    decoded_pdf = ""
    if pdf_bytes:
        decoded_pdf = pdf_bytes.decode("latin-1", errors="ignore")

    indicators: list[str] = []

    has_type_sig = b"/Type/Sig" in pdf_bytes if pdf_bytes else False
    has_byte_range = b"/ByteRange" in pdf_bytes if pdf_bytes else False
    has_sub_filter = b"/SubFilter" in pdf_bytes if pdf_bytes else False
    has_sig_flags = b"/SigFlags" in pdf_bytes if pdf_bytes else False

    if has_type_sig:
        indicators.append("PDF signature dictionary present")
    if has_byte_range:
        indicators.append("Signature ByteRange present")
    if has_sub_filter:
        indicators.append("Signature SubFilter present")
    if has_sig_flags:
        indicators.append("AcroForm signature flags present")

    # Detect e-sign provider hints in either metadata bytes or extracted text
    if "docusign" in decoded_pdf.lower() or "docusign" in (extracted_text or "").lower():
        indicators.append("DocuSign marker present")

    has_digital_signature = has_type_sig or (has_byte_range and has_sub_filter)

    text_markers = _extract_text_signature_markers(extracted_text or "")
    indicators.extend(text_markers)
    has_signature_markers = len(text_markers) > 0

    raw_signing_date = None
    for pattern in (
        re.compile(r"/M\s*\((D:[^)]+)\)"),
        re.compile(r"/SigningTime\s*\((D:[^)]+)\)"),
    ):
        match = pattern.search(decoded_pdf)
        if match:
            raw_signing_date = match.group(1).strip()
            break
    signing_date = _normalize_pdf_signing_date(raw_signing_date)

    signer_names = _extract_signer_names(decoded_pdf, extracted_text or "")

    if has_digital_signature:
        status = "signed"
        confidence = "high"
    elif has_signature_markers:
        status = "signed"
        confidence = "medium" if len(text_markers) >= 2 else "low"
    elif pdf_bytes or (extracted_text and extracted_text.strip()):
        status = "not_detected"
        confidence = "none"
    else:
        status = "unknown"
        confidence = "none"

    # Deduplicate indicator list while preserving order
    deduped_indicators: list[str] = []
    seen = set()
    for indicator in indicators:
        key = indicator.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped_indicators.append(indicator)

    return {
        "status": status,
        "confidence": confidence,
        "has_digital_signature": has_digital_signature,
        "has_signature_markers": has_signature_markers,
        "signature_marker_count": len(text_markers),
        "signing_date": signing_date,
        "signing_date_raw": raw_signing_date,
        "signer_names": signer_names,
        "indicators": deduped_indicators[:10],
    }


def _is_likely_plain_text(data: bytes) -> tuple[bool, str]:
    """Detect if bytes are likely plain text rather than binary data.

    Used to handle .pdf files that are actually plain text (e.g., exported notes from Clio).

    Args:
    ----
        data: Raw bytes to analyze

    Returns:
    -------
        Tuple of (is_text: bool, decoded_text: str if is_text else "")

    """
    if not data or len(data) < 10:
        return False, ""

    # Try UTF-8 decode first
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError:
        # Try latin-1 as fallback (it can decode any byte sequence)
        try:
            decoded = data.decode("latin-1")
        except Exception:
            return False, ""

    # Heuristic: Check if content looks like text
    # - High ratio of printable characters (letters, digits, punctuation, whitespace)
    # - Very few null bytes (binary files often have many)
    # - Contains common text patterns

    # Count null bytes - binary files typically have many
    null_count = data.count(b"\x00")
    if null_count > len(data) * 0.01:  # More than 1% null bytes = likely binary
        return False, ""

    # Count printable characters
    printable_count = sum(1 for c in decoded if c.isprintable() or c in "\n\r\t")
    printable_ratio = printable_count / len(decoded) if decoded else 0

    # Text should be at least 85% printable characters
    if printable_ratio < 0.85:
        return False, ""

    # Additional check: content should look "texty" somewhere near the beginning.
    # Important: some Clio exports start with lots of leading newlines/whitespace,
    # so we scan a larger prefix and don't require letters in the first 500 chars.
    sample = decoded[:10_000]
    if not sample.strip():
        return False, ""

    # Treat HTML/XML as text (common for error pages or exported notes)
    if sample.lstrip().startswith("<"):
        return True, decoded

    has_alnum = any(c.isalnum() for c in sample)
    has_whitespace = any(c.isspace() for c in sample)

    if has_alnum and has_whitespace:
        return True, decoded

    # Some valid plain-text can be dense (e.g., CSV-ish or IDs). If it's mostly printable,
    # has at least some alnum, and no null bytes, treat as text.
    if has_alnum:
        return True, decoded

    return False, ""


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
                logger.info(f"Published OCR start progress for {original_filename}")
            except Exception as prog_err:
                logger.warning(f"Failed to publish initial OCR progress: {prog_err}")

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

                        # Optimization: cap zoom and use JPEG to keep images under 30MB
                        # Google Vision has 40MB limit
                        rect = page.rect
                        width, height = rect.width, rect.height

                        MAX_DIMENSION = 4000  # Cap at 4000px to prevent huge images

                        # Adjust zoom based on page size
                        if width > 2000 or height > 2000:
                            zoom = 1.0  # Very large pages (plats, surveys)
                            logger.info(f"Very large page ({width:.0f}x{height:.0f}), using 1.0x zoom")
                        elif width > 1200 or height > 1200:
                            zoom = 1.5  # Large pages
                        else:
                            zoom = 2.0  # Normal pages

                        # Further cap if still too large
                        estimated_dim = max(width * zoom, height * zoom)
                        if estimated_dim > MAX_DIMENSION:
                            zoom = MAX_DIMENSION / max(width, height)
                            logger.info(f"Capping zoom to {zoom:.2f}x for {MAX_DIMENSION}px limit")

                        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                        # JPEG is 5-10x smaller than PNG, quality 85 is good for OCR
                        img_bytes = pix.tobytes("jpeg", jpg_quality=85)
                        logger.debug(f"Rendered: {pix.width}x{pix.height}px, {len(img_bytes)/1024:.0f}KB")
                        return img_bytes

                    try:
                        img_data = await asyncio.wait_for(
                            run_in_threadpool(render_page),
                            timeout=30.0,
                        )
                        logger.debug(f"Page {page_index + 1} rendered, size: {len(img_data)} bytes")
                    except asyncio.TimeoutError:
                        logger.error(f"Rendering timeout on page {page_index + 1} of {original_filename}")
                        completed_pages[0] += 1
                        return ""
                    except Exception as render_err:
                        logger.error(
                            f"Rendering error on page {page_index + 1} "
                            f"of {original_filename}: {render_err}"
                        )
                        completed_pages[0] += 1
                        return ""

                    # Send to Google Vision with automatic fallback to GPT-4o for oversized images
                    logger.debug(f"Sending page {page_index + 1} to OCR (Google Vision with fallback)")
                    page_text = await _ocr_with_fallback(
                        img_data, page_index, original_filename, google_client
                    )

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

    # Validate credentials before proceeding (with timeout protection)
    try:
        valid, validation_msg = await asyncio.wait_for(
            run_in_threadpool(google_client.validate_credentials),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"Credential validation timed out for {original_filename}")
        return ""

    if not valid:
        logger.error(f"Google Vision credentials invalid: {validation_msg}")
        logger.error("Falling back to GPT-4o Vision. Check your service account key.")
        return ""

    try:
        logger.info(f"🔍 Starting Google Cloud Vision OCR for: {original_filename}")
        logger.info(f"[TRACE] About to open PDF bytes ({len(pdf_bytes)} bytes) for: {original_filename}")

        import fitz

        # Open from memory stream instead of file path
        try:

            def open_pdf():
                logger.debug(f"[TRACE] Inside open_pdf thread for: {original_filename}")
                return fitz.open(stream=pdf_bytes, filetype="pdf")

            logger.info(f"[TRACE] Calling fitz.open with 15s timeout for: {original_filename}")
            doc = await asyncio.wait_for(
                run_in_threadpool(open_pdf),
                timeout=15.0,
            )
            logger.info(f"[TRACE] fitz.open completed for: {original_filename}")
        except asyncio.TimeoutError:
            logger.error(f"Timeout opening PDF bytes for {original_filename} (15s limit)")
            return ""
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
                logger.info(f"Published OCR start progress for {original_filename}")
            except Exception as prog_err:
                logger.warning(f"Failed to publish initial OCR progress: {prog_err}")

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

                        # Optimization: cap zoom and use JPEG to keep images under 30MB
                        # Google Vision has 40MB limit
                        rect = page.rect
                        width, height = rect.width, rect.height

                        MAX_DIMENSION = 4000  # Cap at 4000px to prevent huge images

                        # Adjust zoom based on page size
                        if width > 2000 or height > 2000:
                            zoom = 1.0  # Very large pages (plats, surveys)
                            logger.info(f"Very large page ({width:.0f}x{height:.0f}), using 1.0x zoom")
                        elif width > 1200 or height > 1200:
                            zoom = 1.5  # Large pages
                        else:
                            zoom = 2.0  # Normal pages

                        # Further cap if still too large
                        estimated_dim = max(width * zoom, height * zoom)
                        if estimated_dim > MAX_DIMENSION:
                            zoom = MAX_DIMENSION / max(width, height)
                            logger.info(f"Capping zoom to {zoom:.2f}x for {MAX_DIMENSION}px limit")

                        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                        # JPEG is 5-10x smaller than PNG, quality 85 is good for OCR
                        img_bytes = pix.tobytes("jpeg", jpg_quality=85)
                        logger.debug(f"Rendered: {pix.width}x{pix.height}px, {len(img_bytes)/1024:.0f}KB")
                        return img_bytes

                    try:
                        img_data = await asyncio.wait_for(
                            run_in_threadpool(render_page),
                            timeout=30.0,
                        )
                        logger.debug(f"Page {page_index + 1} rendered, size: {len(img_data)} bytes")
                    except asyncio.TimeoutError:
                        logger.error(f"Rendering timeout on page {page_index + 1} of {original_filename}")
                        completed_pages[0] += 1
                        return ""
                    except Exception as render_err:
                        logger.error(
                            f"Rendering error on page {page_index + 1} "
                            f"of {original_filename}: {render_err}"
                        )
                        completed_pages[0] += 1
                        return ""

                    # Send to Google Vision with automatic fallback to GPT-4o for oversized images
                    logger.debug(f"Sending page {page_index + 1} to OCR (Google Vision with fallback)")
                    page_text = await _ocr_with_fallback(
                        img_data, page_index, original_filename, google_client
                    )

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

            def open_pdf_file():
                return fitz.open(file_path)

            doc = await asyncio.wait_for(
                run_in_threadpool(open_pdf_file),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout opening PDF file at {file_path} (15s limit)")
            return ""
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

                    # Optimization: check page size and cap zoom for large pages
                    rect = page.rect
                    width, height = rect.width, rect.height

                    zoom = 2.0  # Default zoom for good text legibility
                    if width > 3000 or height > 3000:
                        zoom = 1.0
                        logger.info(f"GPT-4o Vision (file): Very large page ({width:.0f}x{height:.0f}), using 1.0x zoom")
                    elif width > 1500 or height > 1500:
                        zoom = 1.5
                        logger.info(f"GPT-4o Vision (file): Large page ({width:.0f}x{height:.0f}), using 1.5x zoom")

                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                    return pix.tobytes("png")

                img_data = await run_in_threadpool(render_page)
                logger.info(f"GPT-4o Vision (file): Page {page_index + 1} image size: {len(img_data)} bytes")

                base64_image = base64.b64encode(img_data).decode("utf-8")

                prompt = (
                    f"Extract ALL text from page {page_index + 1} of this legal document image. "
                    f"Filename: {original_filename}. "
                    "This is a scanned document that needs OCR text extraction. "
                    "Maintain the logical structure and layout. "
                    "If there are tables, preserve the row/column relationship "
                    "using markdown or clear spacing. "
                    "Provide the text verbatim including all numbers, dates, and names. Do not summarize."
                )

                content = [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high"  # Request high detail for OCR accuracy
                        },
                    },
                ]

                # Make the API call in thread pool (since client is sync)
                def make_api_call():
                    return client.chat.completions.create(
                        model="gpt-5.5",
                        messages=[{"role": "user", "content": content}],
                        max_completion_tokens=4000,  # Increased for dense documents
                        reasoning_effort="none",
                        temperature=0.0,
                    )

                try:
                    logger.debug(f"Sending page {page_index + 1} to OpenAI Vision API")
                    response = await asyncio.wait_for(
                        run_in_threadpool(make_api_call),
                        timeout=60.0,  # OpenAI can be slower than Google
                    )
                    page_text = response.choices[0].message.content
                    logger.info(f"GPT-4o Vision (file): OpenAI returned for page {page_index + 1}: {len(page_text) if page_text else 0} chars")
                except asyncio.TimeoutError:
                    logger.error(f"OpenAI Vision API timeout on page {page_index + 1} of {original_filename}")
                    completed_pages[0] += 1
                    return f"--- Page {page_index + 1} ---\n[Extraction timed out]"
                except Exception as api_err:
                    logger.error(f"OpenAI Vision API error on page {page_index + 1}: {api_err}")
                    completed_pages[0] += 1
                    return f"--- Page {page_index + 1} ---\n[API Error: {api_err}]"

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

            def open_pdf_vision():
                return fitz.open(stream=pdf_bytes, filetype="pdf")

            doc = await asyncio.wait_for(
                run_in_threadpool(open_pdf_vision),
                timeout=15.0,
            )
            logger.debug(f"Opened PDF from memory for Vision: {original_filename} ({len(pdf_bytes)} bytes)")
        except asyncio.TimeoutError:
            logger.error(f"Timeout opening PDF bytes for Vision: {original_filename} (15s limit)")
            return ""
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

                    # Optimization: check page size and cap zoom for large pages
                    # to avoid memory issues and excessively large images
                    rect = page.rect
                    width, height = rect.width, rect.height

                    zoom = 2.0  # Default zoom for good text legibility
                    if width > 3000 or height > 3000:
                        zoom = 1.0
                        logger.info(f"GPT-4o Vision (bytes): Very large page ({width:.0f}x{height:.0f}), using 1.0x zoom")
                    elif width > 1500 or height > 1500:
                        zoom = 1.5
                        logger.info(f"GPT-4o Vision (bytes): Large page ({width:.0f}x{height:.0f}), using 1.5x zoom")

                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                    img_bytes = pix.tobytes("png")
                    logger.debug(f"GPT-4o Vision (bytes): Rendered page {page_index + 1}: {len(img_bytes)} bytes, {pix.width}x{pix.height}px")
                    return img_bytes

                img_data = await run_in_threadpool(render_page)

                # Log image size for debugging Vision API issues
                logger.info(f"GPT-4o Vision (bytes): Page {page_index + 1} image size: {len(img_data)} bytes")

                base64_image = base64.b64encode(img_data).decode("utf-8")

                # Log base64 size (should be ~1.37x raw size)
                logger.debug(f"GPT-4o Vision (bytes): Page {page_index + 1} base64 size: {len(base64_image)} chars")

                prompt = (
                    f"Extract ALL text from page {page_index + 1} of this legal document image. "
                    f"Filename: {original_filename}. "
                    "This is a scanned document that needs OCR text extraction. "
                    "Maintain the logical structure and layout. "
                    "If there are tables, preserve the row/column relationship "
                    "using markdown or clear spacing. "
                    "Provide the text verbatim including all numbers, dates, and names. Do not summarize."
                )

                content = [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high"  # Request high detail for OCR accuracy
                        },
                    },
                ]

                # Make the API call in thread pool (since client is sync)
                def make_api_call():
                    return client.chat.completions.create(
                        model="gpt-5.5",
                        messages=[{"role": "user", "content": content}],
                        max_completion_tokens=4000,  # Increased for dense documents
                        reasoning_effort="none",
                        temperature=0.0,
                    )

                try:
                    logger.debug(f"Sending page {page_index + 1} to OpenAI Vision API")
                    response = await asyncio.wait_for(
                        run_in_threadpool(make_api_call),
                        timeout=60.0,  # OpenAI can be slower than Google
                    )
                    page_text = response.choices[0].message.content
                    logger.info(f"GPT-4o Vision (bytes): OpenAI returned for page {page_index + 1}: {len(page_text) if page_text else 0} chars")
                except asyncio.TimeoutError:
                    logger.error(f"OpenAI Vision API timeout on page {page_index + 1} of {original_filename}")
                    completed_pages[0] += 1
                    return f"--- Page {page_index + 1} ---\n[Extraction timed out]"
                except Exception as api_err:
                    logger.error(f"OpenAI Vision API error on page {page_index + 1}: {api_err}")
                    completed_pages[0] += 1
                    return f"--- Page {page_index + 1} ---\n[API Error: {api_err}]"

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
    raw_pdf_bytes = b""
    page_count = 0
    ocr_provider = None
    extraction_error = None
    signature_detection = None

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
            raw_pdf_bytes = pdf_bytes
            file_size = len(pdf_bytes)
            logger.debug(f"Read {file_size} bytes from {original_filename} into memory")

            # Validate PDF header - must start with %PDF-
            # This catches cases where Supabase returned an error response instead of file content
            if not pdf_bytes.startswith(b"%PDF-"):
                # Check if this is actually plain text saved with .pdf extension
                # (common with Clio exported notes/communications)
                is_text, decoded_text = _is_likely_plain_text(pdf_bytes)

                if is_text and decoded_text.strip():
                    logger.info(
                        f"Detected plain text in .pdf file: {original_filename} "
                        f"({len(decoded_text)} chars). Using text_fallback extraction."
                    )
                    text_content = decoded_text
                    extraction_method = "text_fallback"
                    pdf_bytes = None  # Skip PDF extraction - we already have the text
                else:
                    # Not a valid PDF and not recognizable text
                    header8 = pdf_bytes[:8]
                    reason = None
                    if header8.startswith(b"PK\x03\x04"):
                        reason = "looks like a ZIP/DOCX (PK\\x03\\x04)"
                    elif header8.startswith(b"\xFF\xD8\xFF"):
                        reason = "looks like a JPEG (FF D8 FF)"
                    elif header8.startswith(b"\x89PNG\r\n\x1a\n"):
                        reason = "looks like a PNG"
                    elif pdf_bytes.lstrip().startswith(b"<"):
                        reason = "looks like HTML/XML"

                    first_bytes = pdf_bytes[:100].decode("utf-8", errors="replace")
                    logger.error(
                        f"Invalid PDF content for {original_filename}: "
                        f"Expected PDF header, got: {first_bytes[:50]}..."
                    )
                    reason_text = f" ({reason})" if reason else ""
                    text_content = (
                        f"Error: Downloaded content is not a valid PDF{reason_text} - {original_filename}"
                    )
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
                    # Get page count using PyMuPDF if available
                    # Use a timeout to prevent hangs on problematic PDFs
                    def open_and_count():
                        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                            return doc.page_count

                    try:
                        page_count = await asyncio.wait_for(
                            run_in_threadpool(open_and_count),
                            timeout=15.0,
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout opening PDF for page count: {original_filename}")
                        extraction_error = "Timeout opening PDF"
                        text_content = f"Error: PDF file timed out during processing - {original_filename}"
                    else:
                        # Also wrap text extraction in timeout
                        try:
                            text_content = await asyncio.wait_for(
                                run_in_threadpool(
                                    _extract_text_with_fitz_bytes, pdf_bytes, original_filename
                                ),
                                timeout=30.0,
                            )
                        except asyncio.TimeoutError:
                            logger.error(f"Timeout extracting text from PDF: {original_filename}")
                            extraction_error = "Timeout extracting text"
                            text_content = ""
                        if text_content.strip():
                            logger.info(
                                f"✅ Successfully extracted text from {original_filename} using PyMuPDF"
                            )
                            extraction_method = "PyMuPDF"
                except Exception as e:
                    logger.warning(f"PyMuPDF extraction failed for {original_filename}: {e}")
                    extraction_error = f"PyMuPDF error: {e}"
                    text_content = ""

            # Fall back to pypdf if PyMuPDF failed or returned empty - using bytes stream
            if not text_content.strip() and PYPDF_AVAILABLE:
                try:
                    # Update page count if not already set
                    if page_count == 0:
                        import io

                        from pypdf import PdfReader

                        def get_pypdf_page_count():
                            reader = PdfReader(io.BytesIO(pdf_bytes))
                            return len(reader.pages)

                        try:
                            page_count = await asyncio.wait_for(
                                run_in_threadpool(get_pypdf_page_count),
                                timeout=15.0,
                            )
                        except asyncio.TimeoutError:
                            logger.error(f"Timeout reading PDF with pypdf: {original_filename}")
                            page_count = 0

                    try:
                        text_content = await asyncio.wait_for(
                            run_in_threadpool(_extract_text_with_pypdf_bytes, pdf_bytes, original_filename),
                            timeout=30.0,
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout extracting text with pypdf: {original_filename}")
                        text_content = ""
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
                        extraction_error = f"pypdf error: {e}"
                        text_content = f"Error extracting text from {original_filename}: {error_msg}"

            # Check if we need Vision fallback (empty text or error message from standard libs)
            # Scanned PDFs often return empty text or just whitespace
            needs_vision = not text_content.strip() or text_content.startswith("Error")

            # More robust heuristic for scanned/image-heavy detection:
            # Trigger OCR if:
            # 1. Total text is very low (< 200 chars total) AND file is large (> 50KB)
            # 2. Average text per page is suspiciously low (< 50 chars/page)
            # AND file is large enough to contain images
            avg_text_per_page = len(text_content.strip()) / max(1, page_count)
            is_low_yield = len(text_content.strip()) < 200 or avg_text_per_page < 50
            is_large_enough = file_size > (25000 * max(1, page_count))  # ~25KB per page is typical for images

            if not needs_vision and is_low_yield and is_large_enough:
                logger.info(
                    f"Low text yield for {original_filename} ({len(text_content)} total chars, "
                    f"{avg_text_per_page:.1f} per page). Size: {file_size} bytes. "
                    "Likely scanned or image-heavy - trying Vision fallback."
                )
                needs_vision = True

            if needs_vision:
                from legal_portal.config.default import get_settings
                _settings = get_settings()

                if _settings.ocr_remote_enabled:
                    # Route OCR to Cloud Run service (Google Vision only)
                    # with pre-OCR compression + size gate + chunked fallback
                    try:
                        from legal_portal.utils.ocr_service_client import (
                            get_ocr_client, OCRConfigError,
                        )
                        from legal_portal.services.documents.file_compression_service import get_compression_service
                        ocr_client = get_ocr_client()
                        comp_svc = get_compression_service()
                        import mimetypes as _mt
                        content_type, _ = _mt.guess_type(original_filename)
                        content_type = content_type or "application/pdf"

                        # --- Pre-OCR compression + size gate ---
                        ocr_bytes = pdf_bytes
                        ocr_strategy = "direct"
                        size_mb = len(pdf_bytes) / (1024 * 1024)

                        MetricsCollector.record_gauge("ocr.original_bytes", len(pdf_bytes))

                        if len(pdf_bytes) > OCR_COMPRESS_THRESHOLD:
                            MetricsCollector.record_counter("ocr.compression_attempted")
                            try:
                                comp_result = comp_svc.compress_pdf_for_ocr(pdf_bytes, target_size_mb=20.0)
                                MetricsCollector.record_gauge("ocr.compressed_bytes", comp_result.compressed_size)
                                if comp_result.was_compressed and comp_result.compressed_size < len(pdf_bytes):
                                    logger.info(
                                        f"[OCR:COMPRESS] {original_filename}: {size_mb:.1f}MB -> "
                                        f"{comp_result.compressed_size / (1024*1024):.1f}MB ({comp_result.method_used})"
                                    )
                                    MetricsCollector.record_counter("ocr.compression_succeeded")
                                    ocr_bytes = comp_result.compressed_data
                                    ocr_strategy = "compressed"
                                else:
                                    logger.info(
                                        f"[OCR:COMPRESS] {original_filename}: compression did not reduce size"
                                    )
                            except Exception as e:
                                logger.warning(f"[OCR:COMPRESS:FAILED] {original_filename}: {e}")
                                MetricsCollector.record_counter("ocr.compression_failed")
                        else:
                            logger.info(
                                f"[OCR:DIRECT] {original_filename}: {size_mb:.1f}MB — under threshold, sending directly"
                            )
                            MetricsCollector.record_gauge("ocr.compressed_bytes", 0)

                        if len(ocr_bytes) <= SAFE_REMOTE_OCR_LIMIT:
                            # Direct send (original or compressed)
                            if ocr_strategy == "compressed":
                                logger.info(f"[OCR:COMPRESS:OK] {original_filename}: under limit after compression, sending to remote OCR")
                            result = await ocr_client.extract_text(
                                ocr_bytes, original_filename, content_type
                            )
                            text_content = result["full_text"]
                            extraction_method = f"cloud_run_ocr ({result['provider']})"
                            ocr_provider = result["provider"]
                            logger.info(
                                f"Remote OCR completed for {original_filename}",
                                extra={
                                    "trace_id": result.get("trace_id"),
                                    "provider": result["provider"],
                                    "page_count": result.get("page_count"),
                                    "latency_ms": result.get("latency_ms"),
                                },
                            )
                        else:
                            # Chunked OCR fallback
                            logger.info(
                                f"[OCR:COMPRESS:INSUFFICIENT] {original_filename}: still "
                                f"{len(ocr_bytes) / (1024*1024):.1f}MB, entering chunk fallback"
                            )
                            MetricsCollector.record_counter("ocr.compression_insufficient")
                            chunked = await _ocr_pdf_in_chunks(
                                pdf_bytes=pdf_bytes,
                                original_filename=original_filename,
                                ocr_client=ocr_client,
                                comp_svc=comp_svc,
                            )
                            text_content = chunked.text
                            extraction_method = f"cloud_run_ocr_chunked ({chunked.ocr_status})"
                            ocr_provider = "Google"

                    except OCRConfigError as e:
                        # Missing OCR_SERVICE_TOKEN/URL — config error, not transient.
                        # Always fall back to local OCR regardless of ocr_remote_required.
                        logger.warning(f"OCR remote misconfigured ({e}), falling back to local OCR for {original_filename}")
                        vision_text = await _extract_text_via_google_ocr_bytes(
                            pdf_bytes, original_filename, progress_callback
                        )
                        if vision_text:
                            text_content = vision_text
                            extraction_method = "Google Cloud Vision"
                            ocr_provider = "Google"
                        else:
                            vision_text = await _extract_text_via_vision_bytes(
                                pdf_bytes, original_filename, progress_callback
                            )
                            if vision_text:
                                text_content = vision_text
                                extraction_method = "GPT-4o Vision"
                                ocr_provider = "OpenAI"
                    except Exception as e:
                        logger.error(f"Remote OCR failed for {original_filename}: {e}")
                        # Always fall back to local OCR on remote failure —
                        # ocr_remote_required only controls whether we *prefer* remote,
                        # not whether a server 500 should block extraction entirely.
                        logger.warning(f"Falling back to local OCR for {original_filename}")
                        vision_text = await _extract_text_via_google_ocr_bytes(
                            pdf_bytes, original_filename, progress_callback
                        )
                        if vision_text:
                            text_content = vision_text
                            extraction_method = "Google Cloud Vision"
                            ocr_provider = "Google"
                        else:
                            vision_text = await _extract_text_via_vision_bytes(
                                pdf_bytes, original_filename, progress_callback
                            )
                            if vision_text:
                                text_content = vision_text
                                extraction_method = "GPT-4o Vision"
                                ocr_provider = "OpenAI"
                else:
                    # Local OCR path (OCR_REMOTE_ENABLED=false)
                    # Try Google Cloud Vision first (faster and cheaper) - using bytes
                    vision_text = await _extract_text_via_google_ocr_bytes(
                        pdf_bytes, original_filename, progress_callback
                    )
                    if vision_text:
                        text_content = vision_text
                        extraction_method = "Google Cloud Vision"
                        ocr_provider = "Google"
                    else:
                        # Fall back to GPT-4o Vision if Google Vision unavailable or failed
                        vision_text = await _extract_text_via_vision_bytes(
                            pdf_bytes, original_filename, progress_callback
                        )
                        if vision_text:
                            text_content = vision_text
                            extraction_method = "GPT-4o Vision"
                            ocr_provider = "OpenAI"

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

    signature_detection = _detect_pdf_signature(
        pdf_bytes=raw_pdf_bytes,
        extracted_text=text_content if not text_content.startswith("Error") else "",
    )
    if signature_detection.get("status") == "signed":
        logger.info(
            f"✅ Signature detected in {original_filename} | "
            f"digital={signature_detection.get('has_digital_signature')} "
            f"markers={signature_detection.get('signature_marker_count')} "
            f"confidence={signature_detection.get('confidence')}"
        )

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.PDF,
        metadata=file_metadata,
        extraction_quality=extraction_quality,
        extraction_method=extraction_method,
        page_count=page_count,
        ocr_provider=ocr_provider,
        extraction_error=extraction_error,
        signature_detection=signature_detection,
    )
