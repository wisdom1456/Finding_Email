"""Tests for image MIME detection and format conversion helpers.

Verifies:
- MIME type detection from file bytes (magic number detection)
- Fallback to extension-based detection
- HEIC/HEIF conversion to JPEG for Vision API compatibility
"""

from unittest.mock import patch, MagicMock

import pytest


# Standard magic bytes for common image formats
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
HEIC_MAGIC = b"\x00\x00\x00\x1cftyp" + b"heic" + b"\x00" * 100


class TestDetectImageMime:
    """Test _detect_image_mime helper."""

    def test_detect_jpeg_from_bytes(self):
        from legal_portal.api.routes.documents import _detect_image_mime

        result = _detect_image_mime(JPEG_MAGIC, "photo.jpg")
        assert result == "image/jpeg"

    def test_detect_png_from_bytes(self):
        from legal_portal.api.routes.documents import _detect_image_mime

        result = _detect_image_mime(PNG_MAGIC, "screenshot.png")
        assert result == "image/png"

    def test_detect_heic_from_bytes(self):
        """HEIC bytes with .jpg extension should detect as HEIC, not JPEG."""
        from legal_portal.api.routes.documents import _detect_image_mime

        # Mock magic.from_buffer to return image/heic for HEIC bytes
        with patch("legal_portal.api.routes.documents.magic.from_buffer", return_value="image/heic"):
            result = _detect_image_mime(HEIC_MAGIC, "IMG_0001.jpg")
        assert result == "image/heic"

    def test_fallback_to_extension_jpeg(self):
        """Unknown bytes with .jpeg extension falls back to image/jpeg."""
        from legal_portal.api.routes.documents import _detect_image_mime

        with patch("legal_portal.api.routes.documents.magic.from_buffer", return_value="application/octet-stream"):
            result = _detect_image_mime(b"\x00\x00\x00\x00", "file.jpeg")
        assert result == "image/jpeg"

    def test_fallback_to_extension_png(self):
        """Unknown bytes with .png extension falls back to image/png."""
        from legal_portal.api.routes.documents import _detect_image_mime

        with patch("legal_portal.api.routes.documents.magic.from_buffer", return_value="application/octet-stream"):
            result = _detect_image_mime(b"\x00\x00\x00\x00", "file.png")
        assert result == "image/png"

    def test_fallback_to_png_default(self):
        """Unknown bytes with unknown extension defaults to image/png."""
        from legal_portal.api.routes.documents import _detect_image_mime

        with patch("legal_portal.api.routes.documents.magic.from_buffer", return_value="application/octet-stream"):
            result = _detect_image_mime(b"\x00\x00\x00\x00", "file.xyz")
        assert result == "image/png"

    def test_magic_exception_falls_back(self):
        """If magic.from_buffer raises, fall back to extension."""
        from legal_portal.api.routes.documents import _detect_image_mime

        with patch("legal_portal.api.routes.documents.magic.from_buffer", side_effect=Exception("magic error")):
            result = _detect_image_mime(b"\x00", "photo.jpg")
        assert result == "image/jpeg"


class TestEnsureVisionCompatible:
    """Test _ensure_vision_compatible helper."""

    def test_jpeg_passes_through(self):
        from legal_portal.api.routes.documents import _ensure_vision_compatible

        result_bytes, result_mime = _ensure_vision_compatible(JPEG_MAGIC, "image/jpeg")
        assert result_bytes == JPEG_MAGIC
        assert result_mime == "image/jpeg"

    def test_png_passes_through(self):
        from legal_portal.api.routes.documents import _ensure_vision_compatible

        result_bytes, result_mime = _ensure_vision_compatible(PNG_MAGIC, "image/png")
        assert result_bytes == PNG_MAGIC
        assert result_mime == "image/png"

    def test_gif_passes_through(self):
        from legal_portal.api.routes.documents import _ensure_vision_compatible

        result_bytes, result_mime = _ensure_vision_compatible(b"GIF89a", "image/gif")
        assert result_bytes == b"GIF89a"
        assert result_mime == "image/gif"

    def test_webp_passes_through(self):
        from legal_portal.api.routes.documents import _ensure_vision_compatible

        result_bytes, result_mime = _ensure_vision_compatible(b"RIFF", "image/webp")
        assert result_bytes == b"RIFF"
        assert result_mime == "image/webp"

    def test_heic_converted_to_jpeg(self):
        """HEIC bytes should be converted to JPEG."""
        from legal_portal.api.routes.documents import _ensure_vision_compatible

        # Create a mock PIL Image
        mock_image = MagicMock()
        mock_converted = MagicMock()
        mock_image.convert.return_value = mock_converted

        fake_jpeg = b"\xff\xd8\xff\xe0converted"

        def fake_save(buf, format, quality):
            buf.write(fake_jpeg)

        mock_converted.save.side_effect = fake_save

        with patch("PIL.Image.open", return_value=mock_image):
            result_bytes, result_mime = _ensure_vision_compatible(HEIC_MAGIC, "image/heic")

        assert result_bytes == fake_jpeg
        assert result_mime == "image/jpeg"

    def test_conversion_failure_returns_fallback(self):
        """If PIL fails to convert, return original bytes with image/jpeg mime."""
        from legal_portal.api.routes.documents import _ensure_vision_compatible

        with patch("PIL.Image.open", side_effect=Exception("Cannot open HEIC")):
            result_bytes, result_mime = _ensure_vision_compatible(HEIC_MAGIC, "image/heic")

        assert result_bytes == HEIC_MAGIC
        assert result_mime == "image/jpeg"
