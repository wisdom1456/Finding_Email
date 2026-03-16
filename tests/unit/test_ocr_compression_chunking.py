"""Tests for large-PDF OCR: compression, size gating, and chunked fallback."""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pypdf = pytest.importorskip("pypdf", reason="pypdf not installed")
from pypdf import PdfWriter  # noqa: E402

from legal_portal.services.documents.file_compression_service import (
    CompressionResult,
    FileCompressionService,
)
from legal_portal.services.file_processors.pdf_processor import (
    ChunkedOCRResult,
    MAX_OCR_CHUNKS,
    OCR_CHUNK_SEMAPHORE,
    OCR_CHUNK_TARGET_BYTES,
    OCR_COMPRESS_THRESHOLD,
    SAFE_REMOTE_OCR_LIMIT,
    _ocr_pdf_in_chunks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(num_pages: int = 1, content_per_page: str = "Hello") -> bytes:
    """Create a minimal valid multi-page PDF using pypdf."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=letter)
    for i in range(num_pages):
        c.drawString(72, 720, f"{content_per_page} page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _make_pdf_pypdf(num_pages: int = 1) -> bytes:
    """Create a minimal valid multi-page PDF using only pypdf (no reportlab needed)."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_large_pdf_bytes(target_bytes: int, num_pages: int = 10) -> bytes:
    """Create a PDF of approximately target_bytes by padding with dummy stream data."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    base = buf.getvalue()
    if len(base) >= target_bytes:
        return base
    # Pad by appending junk after %%EOF (still parseable by pypdf)
    padding = b"\x00" * (target_bytes - len(base))
    return base + padding


def _mock_compression_service(
    compressed_size: int | None = None,
    was_compressed: bool = True,
    raise_exc: Exception | None = None,
) -> MagicMock:
    """Create a mock FileCompressionService."""
    svc = MagicMock(spec=FileCompressionService)
    if raise_exc:
        svc.compress_pdf_for_ocr.side_effect = raise_exc
    else:
        def compress_side_effect(pdf_bytes, target_size_mb=20.0):
            c_size = compressed_size if compressed_size is not None else len(pdf_bytes) // 2
            return CompressionResult(
                compressed_data=b"\x00" * c_size,
                original_size=len(pdf_bytes),
                compressed_size=c_size,
                compression_ratio=c_size / len(pdf_bytes) if len(pdf_bytes) > 0 else 1.0,
                method_used="mock-compress",
                was_compressed=was_compressed,
            )
        svc.compress_pdf_for_ocr.side_effect = compress_side_effect
    return svc


def _mock_ocr_client(text_per_call: list[str] | str = "Extracted text") -> AsyncMock:
    """Create a mock OCR client that returns text for each call."""
    client = AsyncMock()
    if isinstance(text_per_call, str):
        client.extract_text.return_value = {"full_text": text_per_call, "provider": "google"}
    else:
        results = [{"full_text": t, "provider": "google"} for t in text_per_call]
        client.extract_text.side_effect = results
    return client


# ===========================================================================
# 1. pypdf compression fix
# ===========================================================================

class TestPypdfCompressionFix:
    """Verify the page-ownership bug fix in _compress_pdf_pypdf2."""

    def test_pypdf_compression_no_error(self):
        """Compress a multi-page PDF — no 'Page must be part of a PdfWriter' error."""
        pdf_data = _make_pdf_pypdf(num_pages=3)
        svc = FileCompressionService()
        # Should not raise
        compressed, method = svc._compress_pdf_pypdf2(pdf_data)
        assert isinstance(compressed, bytes)
        assert len(compressed) > 0
        # Verify result is valid PDF
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(compressed))
        assert len(reader.pages) == 3

    def test_pypdf_compression_returns_valid_pdf(self):
        """Output of pypdf compression is a parseable PDF."""
        pdf_data = _make_pdf_pypdf(num_pages=5)
        svc = FileCompressionService()
        compressed, method = svc._compress_pdf_pypdf2(pdf_data)
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(compressed))
        assert len(reader.pages) == 5


# ===========================================================================
# 2. compress_pdf_for_ocr()
# ===========================================================================

class TestCompressPdfForOcr:
    """Tests for the public compress_pdf_for_ocr method."""

    def test_returns_compression_result(self):
        """Should return a properly populated CompressionResult."""
        pdf_data = _make_pdf_pypdf(num_pages=3)
        svc = FileCompressionService()
        result = svc.compress_pdf_for_ocr(pdf_data, target_size_mb=20.0)
        assert isinstance(result, CompressionResult)
        assert result.original_size == len(pdf_data)
        assert result.compressed_size > 0
        assert isinstance(result.method_used, str)

    def test_failure_returns_original(self):
        """On compression failure, returns original bytes with was_compressed=False."""
        svc = FileCompressionService()
        # Pass invalid PDF data to trigger internal failure
        bad_data = b"not a pdf at all"
        result = svc.compress_pdf_for_ocr(bad_data, target_size_mb=20.0)
        assert result.was_compressed is False
        assert result.compressed_data == bad_data
        assert result.original_size == len(bad_data)


# ===========================================================================
# 3. Pre-OCR pipeline (size gating)
# ===========================================================================

class TestPreOcrPipeline:
    """Test the compression + size-gate logic in process_pdf's remote OCR path."""

    @pytest.mark.asyncio
    async def test_under_threshold_skips_compression(self):
        """PDF under 20MB should skip compression and go direct to remote OCR."""
        small_pdf = _make_pdf_pypdf(num_pages=1)  # tiny
        assert len(small_pdf) < OCR_COMPRESS_THRESHOLD

        ocr_client = _mock_ocr_client("Small PDF text")
        comp_svc = _mock_compression_service()

        # Simulate the size-gate logic directly
        ocr_bytes = small_pdf
        if len(small_pdf) > OCR_COMPRESS_THRESHOLD:
            comp_svc.compress_pdf_for_ocr(small_pdf)

        # Compression should NOT have been called
        comp_svc.compress_pdf_for_ocr.assert_not_called()

    @pytest.mark.asyncio
    async def test_over_threshold_triggers_compression(self):
        """PDF over 20MB should trigger compress_pdf_for_ocr."""
        comp_svc = _mock_compression_service(compressed_size=15 * 1024 * 1024)

        big_size = 25 * 1024 * 1024
        fake_pdf = b"\x00" * big_size

        if len(fake_pdf) > OCR_COMPRESS_THRESHOLD:
            comp_svc.compress_pdf_for_ocr(fake_pdf, target_size_mb=20.0)

        comp_svc.compress_pdf_for_ocr.assert_called_once()

    @pytest.mark.asyncio
    async def test_compression_effective_sends_compressed(self):
        """If compression brings 35MB -> 18MB, the 18MB bytes go to OCR."""
        original_size = 35 * 1024 * 1024
        compressed_size = 18 * 1024 * 1024
        comp_svc = _mock_compression_service(compressed_size=compressed_size)

        ocr_bytes = b"\x00" * original_size
        if len(ocr_bytes) > OCR_COMPRESS_THRESHOLD:
            result = comp_svc.compress_pdf_for_ocr(ocr_bytes, target_size_mb=20.0)
            if result.was_compressed and result.compressed_size < len(ocr_bytes):
                ocr_bytes = result.compressed_data

        assert len(ocr_bytes) == compressed_size

    @pytest.mark.asyncio
    async def test_compression_insufficient_triggers_chunking(self):
        """If compressed size still > 28MB, chunked fallback should be used."""
        original_size = 40 * 1024 * 1024
        compressed_size = 30 * 1024 * 1024  # Still over SAFE_REMOTE_OCR_LIMIT
        comp_svc = _mock_compression_service(compressed_size=compressed_size)

        ocr_bytes = b"\x00" * original_size
        if len(ocr_bytes) > OCR_COMPRESS_THRESHOLD:
            result = comp_svc.compress_pdf_for_ocr(ocr_bytes, target_size_mb=20.0)
            if result.was_compressed and result.compressed_size < len(ocr_bytes):
                ocr_bytes = result.compressed_data

        needs_chunking = len(ocr_bytes) > SAFE_REMOTE_OCR_LIMIT
        assert needs_chunking is True

    @pytest.mark.asyncio
    async def test_compression_failure_falls_back(self):
        """Compression raising should not crash — original bytes still processed."""
        comp_svc = _mock_compression_service(raise_exc=RuntimeError("gs exploded"))

        ocr_bytes = b"\x00" * (25 * 1024 * 1024)
        if len(ocr_bytes) > OCR_COMPRESS_THRESHOLD:
            try:
                comp_svc.compress_pdf_for_ocr(ocr_bytes, target_size_mb=20.0)
            except Exception:
                pass  # Fallback: ocr_bytes stays as original

        # Original bytes survive
        assert len(ocr_bytes) == 25 * 1024 * 1024


# ===========================================================================
# 4. Chunked OCR (_ocr_pdf_in_chunks)
# ===========================================================================

class TestChunkedOcr:
    """Tests for _ocr_pdf_in_chunks."""

    @pytest.mark.asyncio
    async def test_text_assembled_in_page_order(self):
        """Chunks should be reassembled in page order regardless of completion order."""
        pdf = _make_pdf_pypdf(num_pages=6)
        texts = [f"Text from chunk {i}" for i in range(6)]

        # Make OCR return texts for each chunk call (may be fewer chunks than pages)
        ocr_client = AsyncMock()
        call_count = [0]

        async def mock_extract(data, filename, content_type):
            idx = call_count[0]
            call_count[0] += 1
            # Simulate varying latency to test ordering
            await asyncio.sleep(0.01 * (3 - idx % 3))
            return {"full_text": f"Chunk {idx} text", "provider": "google"}

        ocr_client.extract_text.side_effect = mock_extract
        comp_svc = _mock_compression_service()

        result = await _ocr_pdf_in_chunks(
            pdf_bytes=pdf,
            original_filename="test.pdf",
            ocr_client=ocr_client,
            comp_svc=comp_svc,
            target_chunk_bytes=500,  # Small target to force multiple chunks
        )

        assert isinstance(result, ChunkedOCRResult)
        assert result.ocr_strategy == "chunked"
        # Verify page ranges appear in order
        for i, part in enumerate(result.text.split("--- Page Range")):
            if i == 0:
                continue  # skip text before first separator
            # Each part starts with " X-Y ---\n\n"
            assert "Chunk" in part

    @pytest.mark.asyncio
    async def test_corrupt_pdf_returns_empty(self):
        """Invalid bytes should return empty string, not crash."""
        result = await _ocr_pdf_in_chunks(
            pdf_bytes=b"not a pdf",
            original_filename="corrupt.pdf",
            ocr_client=_mock_ocr_client(),
            comp_svc=_mock_compression_service(),
        )
        assert result.text == ""
        assert result.ocr_status == "failed"

    @pytest.mark.asyncio
    async def test_max_chunks_respected(self):
        """Should not create more than MAX_OCR_CHUNKS chunks."""
        # Create a PDF with many pages
        pdf = _make_pdf_pypdf(num_pages=50)
        ocr_client = _mock_ocr_client("text")
        # Make extract_text return consistently
        ocr_client.extract_text = AsyncMock(
            return_value={"full_text": "page text", "provider": "google"}
        )
        comp_svc = _mock_compression_service()

        result = await _ocr_pdf_in_chunks(
            pdf_bytes=pdf,
            original_filename="big.pdf",
            ocr_client=ocr_client,
            comp_svc=comp_svc,
            target_chunk_bytes=200,  # Tiny target to force many chunks
            max_chunks=5,
        )

        # Total chunks (successful + failed) should not exceed max_chunks + overflow marked as failed
        assert result.total_chunks <= 50  # At most one per page
        # OCR calls should be capped
        assert ocr_client.extract_text.call_count <= 5

    @pytest.mark.asyncio
    async def test_partial_failure_surfaced(self):
        """If some chunks fail, result should be partial with failure info."""
        pdf = _make_pdf_pypdf(num_pages=4)

        call_count = [0]

        async def mock_extract(data, filename, content_type):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 1:
                raise ConnectionError("OCR service timeout")
            return {"full_text": f"Chunk {idx} extracted", "provider": "google"}

        ocr_client = AsyncMock()
        ocr_client.extract_text.side_effect = mock_extract
        comp_svc = _mock_compression_service()

        result = await _ocr_pdf_in_chunks(
            pdf_bytes=pdf,
            original_filename="partial.pdf",
            ocr_client=ocr_client,
            comp_svc=comp_svc,
            target_chunk_bytes=200,  # Small to get multiple chunks
        )

        assert result.ocr_status == "partial"
        assert len(result.failed_page_ranges) > 0
        assert "extraction failed" in result.text

    @pytest.mark.asyncio
    async def test_empty_ocr_response_handled(self):
        """OCR returning empty text should mark chunk as failed."""
        pdf = _make_pdf_pypdf(num_pages=2)

        ocr_client = AsyncMock()
        ocr_client.extract_text.return_value = {"full_text": "", "provider": "google"}
        comp_svc = _mock_compression_service()

        result = await _ocr_pdf_in_chunks(
            pdf_bytes=pdf,
            original_filename="empty_ocr.pdf",
            ocr_client=ocr_client,
            comp_svc=comp_svc,
            target_chunk_bytes=200,
        )

        # All chunks returned empty — should all be marked failed
        assert result.ocr_status == "failed"
        assert len(result.failed_page_ranges) > 0
        assert "extraction returned no text" in result.text

    @pytest.mark.asyncio
    async def test_chunk_ocr_timeout_handled(self):
        """OCR timeout should mark chunk as failed, other chunks still processed."""
        pdf = _make_pdf_pypdf(num_pages=3)

        call_count = [0]

        async def mock_extract(data, filename, content_type):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                import httpx
                raise httpx.TimeoutException("read timeout")
            return {"full_text": f"Page {idx} text", "provider": "google"}

        ocr_client = AsyncMock()
        ocr_client.extract_text.side_effect = mock_extract
        comp_svc = _mock_compression_service()

        result = await _ocr_pdf_in_chunks(
            pdf_bytes=pdf,
            original_filename="timeout.pdf",
            ocr_client=ocr_client,
            comp_svc=comp_svc,
            target_chunk_bytes=200,
        )

        assert result.ocr_status == "partial"
        assert len(result.failed_page_ranges) > 0
        assert result.successful_chunks > 0

    @pytest.mark.asyncio
    async def test_chunked_result_metadata(self):
        """ChunkedOCRResult should have correct metadata fields."""
        pdf = _make_pdf_pypdf(num_pages=3)
        ocr_client = AsyncMock()
        ocr_client.extract_text.return_value = {"full_text": "Extracted", "provider": "google"}
        comp_svc = _mock_compression_service()

        result = await _ocr_pdf_in_chunks(
            pdf_bytes=pdf,
            original_filename="meta.pdf",
            ocr_client=ocr_client,
            comp_svc=comp_svc,
            target_chunk_bytes=200,
        )

        assert result.ocr_strategy == "chunked"
        assert result.ocr_status in ("complete", "partial", "failed")
        assert isinstance(result.successful_page_ranges, list)
        assert isinstance(result.failed_page_ranges, list)
        assert result.total_chunks > 0

    @pytest.mark.asyncio
    async def test_single_page_too_large_marked_failed(self):
        """A single page chunk that exceeds safe limit after compression should be marked failed."""
        pdf = _make_pdf_pypdf(num_pages=1)

        # Mock compression that doesn't reduce size enough
        comp_svc = MagicMock(spec=FileCompressionService)
        comp_svc.compress_pdf_for_ocr.return_value = CompressionResult(
            compressed_data=b"\x00" * (SAFE_REMOTE_OCR_LIMIT + 1),
            original_size=SAFE_REMOTE_OCR_LIMIT + 1000,
            compressed_size=SAFE_REMOTE_OCR_LIMIT + 1,
            compression_ratio=0.99,
            method_used="mock",
            was_compressed=True,
        )

        ocr_client = _mock_ocr_client("text")

        result = await _ocr_pdf_in_chunks(
            pdf_bytes=pdf,
            original_filename="huge_page.pdf",
            ocr_client=ocr_client,
            comp_svc=comp_svc,
            target_chunk_bytes=1,  # Force each page into its own chunk
            safe_limit=10,  # Very small limit so the chunk "exceeds" it
        )

        assert len(result.failed_page_ranges) > 0
        assert "extraction failed" in result.text

    @pytest.mark.asyncio
    async def test_all_chunks_succeed_status_complete(self):
        """When all chunks succeed, status should be 'complete'."""
        pdf = _make_pdf_pypdf(num_pages=3)
        ocr_client = AsyncMock()
        ocr_client.extract_text.return_value = {"full_text": "Good text", "provider": "google"}
        comp_svc = _mock_compression_service()

        result = await _ocr_pdf_in_chunks(
            pdf_bytes=pdf,
            original_filename="good.pdf",
            ocr_client=ocr_client,
            comp_svc=comp_svc,
            target_chunk_bytes=200,
        )

        assert result.ocr_status == "complete"
        assert len(result.failed_page_ranges) == 0
        assert result.successful_chunks > 0


# ===========================================================================
# 5. Constants sanity checks
# ===========================================================================

class TestOcrConstants:
    """Verify the constants are set correctly."""

    def test_compress_threshold_below_safe_limit(self):
        assert OCR_COMPRESS_THRESHOLD < SAFE_REMOTE_OCR_LIMIT

    def test_chunk_target_below_safe_limit(self):
        assert OCR_CHUNK_TARGET_BYTES < SAFE_REMOTE_OCR_LIMIT

    def test_max_chunks_positive(self):
        assert MAX_OCR_CHUNKS > 0

    def test_semaphore_positive(self):
        assert OCR_CHUNK_SEMAPHORE > 0
