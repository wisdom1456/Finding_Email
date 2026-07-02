"""Tests for image compression: resize, PNG-to-JPEG conversion, and hard cap enforcement."""

from __future__ import annotations

import io
import os
import time

from PIL import Image

from legal_portal.services.documents.file_compression_service import FileCompressionService


def _make_png(width: int, height: int, color: tuple = (0, 128, 255)) -> bytes:
    """Create a synthetic PNG image with random noise so it has realistic file size."""
    # Random pixel data creates a realistically-sized PNG (solid colors compress to nothing)
    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_rgba_png(width: int, height: int) -> bytes:
    """Create a synthetic RGBA PNG image with noise."""
    img = Image.frombytes("RGBA", (width, height), os.urandom(width * height * 4))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestImageCompression:
    """Tests for _compress_image with resize and format conversion."""

    def setup_method(self):
        self.service = FileCompressionService(
            max_image_dimension=3000,
            png_to_jpeg_threshold_mb=0.01,  # Very low threshold so test PNGs trigger conversion
            image_hard_cap_mb=5.0,
        )

    def test_large_png_converted_to_jpeg(self):
        """Large PNGs should be converted to JPEG."""
        png_data = _make_png(2000, 1500)
        result_data, method = self.service._compress_image(png_data, "image/png")

        assert "jpeg" in method
        assert "converted" in method
        # Verify it's actually JPEG by reading the header
        img = Image.open(io.BytesIO(result_data))
        assert img.format == "JPEG"

    def test_oversized_dimensions_resized(self):
        """Images exceeding max_image_dimension should be resized."""
        png_data = _make_png(5000, 4000)
        service = FileCompressionService(
            max_image_dimension=3000,
            png_to_jpeg_threshold_mb=0.01,
            image_hard_cap_mb=5.0,
        )
        result_data, method = service._compress_image(png_data, "image/png")

        assert "resized" in method
        img = Image.open(io.BytesIO(result_data))
        assert max(img.size) <= 3000

    def test_small_png_stays_png(self):
        """Small PNGs below threshold should stay as PNG."""
        png_data = _make_png(200, 200)
        service = FileCompressionService(
            max_image_dimension=3000,
            png_to_jpeg_threshold_mb=50.0,  # Very high threshold
            image_hard_cap_mb=5.0,
        )
        result_data, method = service._compress_image(png_data, "image/png")

        # Should stay PNG (either compressed or skipped)
        assert "converted" not in method

    def test_jpeg_stays_jpeg(self):
        """JPEG images should remain JPEG."""
        img = Image.new("RGB", (1000, 800), (100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        jpeg_data = buf.getvalue()

        result_data, method = self.service._compress_image(jpeg_data, "image/jpeg")
        assert "jpeg" in method
        assert "converted" not in method

    def test_rgba_transparency_handled(self):
        """RGBA images converted to JPEG should have white background."""
        rgba_data = _make_rgba_png(2000, 1500)
        result_data, method = self.service._compress_image(rgba_data, "image/png")

        img = Image.open(io.BytesIO(result_data))
        assert img.mode == "RGB"

    def test_compression_faster_than_10_seconds(self):
        """Compression of a large image should complete in under 10 seconds."""
        # 4000x3000 solid color PNG
        png_data = _make_png(4000, 3000)
        start = time.monotonic()
        result_data, method = self.service._compress_image(png_data, "image/png")
        elapsed = time.monotonic() - start

        assert elapsed < 10.0, f"Compression took {elapsed:.1f}s, expected < 10s"

    def test_output_smaller_than_original(self):
        """Compressed output should be smaller than the original large PNG."""
        png_data = _make_png(4000, 3000)
        result_data, method = self.service._compress_image(png_data, "image/png")

        assert len(result_data) < len(png_data)

    def test_should_compress_image_lower_threshold(self):
        """Images should use a lower compression threshold (3MB)."""
        # 4MB should trigger compression for images
        assert self.service.should_compress(4 * 1024 * 1024, "image/png") is True
        # 2MB should not
        assert self.service.should_compress(2 * 1024 * 1024, "image/png") is False
        # 4MB PDF should NOT trigger (below 10MB default)
        assert self.service.should_compress(4 * 1024 * 1024, "application/pdf") is False
        # Without content_type, uses default threshold
        assert self.service.should_compress(4 * 1024 * 1024) is False

    def test_exif_orientation_applied(self):
        """EXIF orientation should be applied before stripping metadata."""
        from PIL.ExifTags import Base as ExifBase

        # Use noisy image so JPEG compression actually reduces size
        img = Image.frombytes("RGB", (800, 400), os.urandom(800 * 400 * 3))
        exif = img.getexif()
        exif[ExifBase.Orientation] = 6  # 90 degrees CW
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=98, exif=exif.tobytes())
        jpeg_data = buf.getvalue()

        service = FileCompressionService(
            max_image_dimension=3000,
            png_to_jpeg_threshold_mb=50.0,
            image_hard_cap_mb=5.0,
        )
        result_data, method = service._compress_image(jpeg_data, "image/jpeg")

        # After orientation is applied, 800x400 rotated 90° becomes 400x800
        result_img = Image.open(io.BytesIO(result_data))
        assert result_img.size == (400, 800)

    def test_palette_mode_png_handled(self):
        """P-mode (palette) PNGs should be handled correctly when converted."""
        # Create a noisy RGB image, then convert to palette mode
        img = Image.frombytes("RGB", (2000, 1500), os.urandom(2000 * 1500 * 3))
        img = img.convert("P")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        p_data = buf.getvalue()

        result_data, method = self.service._compress_image(p_data, "image/png")
        # Should not raise an error
        result_img = Image.open(io.BytesIO(result_data))
        # If converted to JPEG, mode should be RGB; if stayed PNG (skipped), could be P
        if "converted" in method or "jpeg" in method:
            assert result_img.mode == "RGB"
