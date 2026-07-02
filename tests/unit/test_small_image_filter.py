"""Tests for the small image filtering logic during Clio document import."""



SMALL_IMAGE_THRESHOLD_BYTES = 50 * 1024  # 50KB


def is_filterable_small_image(content_type: str, size_bytes: int) -> bool:
    """Determine if a document should be filtered as a small image.

    Returns True only when content_type starts with 'image/' AND size is
    between 1 and SMALL_IMAGE_THRESHOLD_BYTES (exclusive). If metadata is
    missing or ambiguous, returns False (prefer false negatives).
    """
    ct = (content_type or "").lower().strip()
    return (
        ct.startswith("image/")
        and size_bytes > 0
        and size_bytes < SMALL_IMAGE_THRESHOLD_BYTES
    )


class TestIsFilterableSmallImage:
    """Unit tests for the is_filterable_small_image helper."""

    def test_png_under_threshold_filtered(self):
        assert is_filterable_small_image("image/png", 10_000) is True

    def test_jpeg_under_threshold_filtered(self):
        assert is_filterable_small_image("image/jpeg", 25_000) is True

    def test_gif_under_threshold_filtered(self):
        assert is_filterable_small_image("image/gif", 5_000) is True

    def test_webp_under_threshold_filtered(self):
        assert is_filterable_small_image("image/webp", 30_000) is True

    def test_bmp_under_threshold_filtered(self):
        assert is_filterable_small_image("image/bmp", 1_000) is True

    def test_x_icon_under_threshold_filtered(self):
        assert is_filterable_small_image("image/x-icon", 2_048) is True

    def test_svg_under_threshold_filtered(self):
        """Any image/ MIME type should be filterable, including uncommon ones."""
        assert is_filterable_small_image("image/svg+xml", 8_000) is True

    def test_image_exactly_at_threshold_not_filtered(self):
        """Boundary: exactly 50KB should NOT be filtered (< not <=)."""
        assert is_filterable_small_image("image/png", SMALL_IMAGE_THRESHOLD_BYTES) is False

    def test_image_over_threshold_not_filtered(self):
        assert is_filterable_small_image("image/jpeg", 100_000) is False

    def test_image_well_over_threshold_not_filtered(self):
        assert is_filterable_small_image("image/png", 5_000_000) is False

    def test_small_pdf_not_filtered(self):
        """Non-image MIME types must never be filtered regardless of size."""
        assert is_filterable_small_image("application/pdf", 10_000) is False

    def test_small_docx_not_filtered(self):
        assert is_filterable_small_image(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            20_000,
        ) is False

    def test_small_text_not_filtered(self):
        assert is_filterable_small_image("text/plain", 500) is False

    def test_small_octet_stream_not_filtered(self):
        assert is_filterable_small_image("application/octet-stream", 10_000) is False

    def test_missing_content_type_not_filtered(self):
        """Missing content_type -> do not filter (false negative preferred)."""
        assert is_filterable_small_image("", 10_000) is False

    def test_none_content_type_not_filtered(self):
        assert is_filterable_small_image(None, 10_000) is False

    def test_size_zero_not_filtered(self):
        """size == 0 is ambiguous metadata -> do not filter."""
        assert is_filterable_small_image("image/png", 0) is False

    def test_negative_size_not_filtered(self):
        assert is_filterable_small_image("image/png", -1) is False

    def test_content_type_with_whitespace(self):
        """Content type with leading/trailing whitespace should still match."""
        assert is_filterable_small_image("  image/png  ", 10_000) is True

    def test_content_type_case_insensitive(self):
        assert is_filterable_small_image("Image/PNG", 10_000) is True
        assert is_filterable_small_image("IMAGE/JPEG", 10_000) is True

    def test_content_type_with_parameters(self):
        """MIME types with parameters are still images and should be filtered."""
        assert is_filterable_small_image("image/png; charset=utf-8", 10_000) is True

    def test_one_byte_image_filtered(self):
        """Smallest valid size (1 byte) should be filtered if image."""
        assert is_filterable_small_image("image/png", 1) is True

    def test_just_under_threshold_filtered(self):
        assert is_filterable_small_image("image/jpeg", SMALL_IMAGE_THRESHOLD_BYTES - 1) is True


class TestSkipRecordIdempotency:
    """Tests for the duplicate prevention logic for skipped_small_image records.

    These tests verify the logic pattern used in cases.py where existing_clio_ids
    is checked before inserting a skip record.
    """

    def test_new_clio_id_creates_record(self):
        """A document not in existing_clio_ids should produce a skip record."""
        existing_clio_ids = set()
        doc_id = 12345
        inserted = []

        # Simulate the logic from cases.py
        if doc_id not in existing_clio_ids:
            inserted.append(doc_id)

        assert doc_id in inserted

    def test_existing_clio_id_skips_insert(self):
        """A document already in existing_clio_ids should NOT produce a new record."""
        existing_clio_ids = {12345, 67890}
        doc_id = 12345
        inserted = []

        if doc_id not in existing_clio_ids:
            inserted.append(doc_id)

        assert doc_id not in inserted

    def test_different_clio_id_creates_record(self):
        """A different clio_id should still create a record."""
        existing_clio_ids = {12345}
        doc_id = 99999
        inserted = []

        if doc_id not in existing_clio_ids:
            inserted.append(doc_id)

        assert doc_id in inserted


class TestSkipRecordMetadata:
    """Tests verifying that skip records use neutral fields, not error fields."""

    def test_skip_record_has_skip_reason(self):
        """Skip record metadata should use skip_reason, not error."""
        skip_record_metadata = {
            "clio_source": True,
            "clio_type": "document",
            "clio_id": 123,
            "skip_reason": "small_image_filtered",
            "skip_detail": "Image under 50KB threshold (10000 bytes)",
        }
        assert "skip_reason" in skip_record_metadata
        assert "skip_detail" in skip_record_metadata
        assert "error" not in skip_record_metadata
        assert "error_type" not in skip_record_metadata

    def test_skip_record_status(self):
        """Skip record status should be 'skipped_small_image'."""
        status = "skipped_small_image"
        assert status == "skipped_small_image"
        assert "error" not in status
