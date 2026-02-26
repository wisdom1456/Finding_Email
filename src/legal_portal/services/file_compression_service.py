"""File compression service for handling large PDFs and images.

This service provides automatic compression for files that exceed a
configurable threshold, enabling import of larger files while optimizing storage.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional, Tuple

from legal_portal.config.default import settings
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    Image = None
    PIL_AVAILABLE = False
    logger.warning("Pillow not available - image compression will be skipped")


@dataclass
class CompressionResult:
    """Result of a file compression operation."""

    compressed_data: bytes
    original_size: int
    compressed_size: int
    compression_ratio: float
    method_used: str
    was_compressed: bool


class FileCompressionService:
    """Service for compressing PDFs and images."""

    def __init__(
        self,
        compression_threshold_mb: float = 10.0,
        pdf_quality: str = "ebook",
        image_quality: int = 85,
    ):
        """Initialize compression service.

        Args:
        ----
            compression_threshold_mb: Size threshold in MB to trigger compression
            pdf_quality: Ghostscript quality preset (screen, ebook, printer, prepress)
            image_quality: JPEG quality (0-100)

        """
        self.compression_threshold_bytes = int(compression_threshold_mb * 1024 * 1024)
        self.pdf_quality = pdf_quality
        self.image_quality = image_quality
        self.has_ghostscript = self._check_ghostscript()

        if self.has_ghostscript:
            logger.info(f"Ghostscript detected - using for PDF compression (quality: {pdf_quality})")
        else:
            logger.warning("Ghostscript not available - PDF compression will be limited")

    def _check_ghostscript(self) -> bool:
        """Check if Ghostscript is available."""
        try:
            result = subprocess.run(
                ["gs", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def should_compress(self, file_size: int) -> bool:
        """Determine if a file should be compressed based on size.

        Args:
        ----
            file_size: File size in bytes

        Returns:
        -------
            True if file should be compressed

        """
        return file_size > self.compression_threshold_bytes

    def compress_file(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> CompressionResult:
        """Compress a file if applicable.

        Args:
        ----
            file_data: Original file bytes
            filename: Original filename
            content_type: MIME type of the file

        Returns:
        -------
            CompressionResult with compression details

        """
        original_size = len(file_data)
        file_size_mb = original_size / (1024 * 1024)

        # Check if compression is needed
        if not self.should_compress(original_size):
            logger.debug(f"File '{filename}' ({file_size_mb:.2f}MB) below compression threshold, skipping")
            return CompressionResult(
                compressed_data=file_data,
                original_size=original_size,
                compressed_size=original_size,
                compression_ratio=1.0,
                method_used="none",
                was_compressed=False,
            )

        logger.info(f"Compressing file '{filename}' ({file_size_mb:.2f}MB)")

        # Determine compression method based on content type
        content_type_lower = content_type.lower()

        try:
            if "pdf" in content_type_lower or filename.lower().endswith(".pdf"):
                compressed_data, method = self._compress_pdf(file_data)
            elif any(img_type in content_type_lower for img_type in ["image", "jpeg", "jpg", "png"]):
                compressed_data, method = self._compress_image(file_data, content_type_lower)
            else:
                # Unsupported type for compression
                logger.warning(f"Compression not supported for content type: {content_type}")
                return CompressionResult(
                    compressed_data=file_data,
                    original_size=original_size,
                    compressed_size=original_size,
                    compression_ratio=1.0,
                    method_used="unsupported",
                    was_compressed=False,
                )

            compressed_size = len(compressed_data)
            compression_ratio = compressed_size / original_size
            size_reduction_pct = (1 - compression_ratio) * 100

            logger.info(
                f"Compression complete: {original_size / (1024 * 1024):.2f}MB → "
                f"{compressed_size / (1024 * 1024):.2f}MB "
                f"({size_reduction_pct:.1f}% reduction, method: {method})"
            )

            return CompressionResult(
                compressed_data=compressed_data,
                original_size=original_size,
                compressed_size=compressed_size,
                compression_ratio=compression_ratio,
                method_used=method,
                was_compressed=True,
            )

        except Exception as e:
            logger.error(f"Compression failed for '{filename}': {e}", exc_info=True)
            # Return original file if compression fails
            return CompressionResult(
                compressed_data=file_data,
                original_size=original_size,
                compressed_size=original_size,
                compression_ratio=1.0,
                method_used=f"failed: {str(e)}",
                was_compressed=False,
            )

    def _compress_pdf(self, pdf_data: bytes, target_size_mb: float = 50.0) -> Tuple[bytes, str]:
        """Compress a PDF using Ghostscript (preferred) or PyPDF2 (fallback).
        
        If the file is still over target_size_mb after initial compression,
        attempts aggressive compression using PyMuPDF.

        Args:
        ----
            pdf_data: Original PDF bytes
            target_size_mb: Target size in MB (default 50MB for Supabase)

        Returns:
        -------
            Tuple of (compressed_data, method_name)

        """
        target_size_bytes = int(target_size_mb * 1024 * 1024)
        original_size = len(pdf_data)

        # First pass: standard compression
        if self.has_ghostscript:
            compressed_data, method = self._compress_pdf_ghostscript(pdf_data)
        else:
            compressed_data, method = self._compress_pdf_pypdf2(pdf_data)

        # Check if we need aggressive compression
        if len(compressed_data) > target_size_bytes:
            logger.warning(
                f"PDF still {len(compressed_data) / (1024*1024):.1f}MB after {method}, "
                f"attempting aggressive compression to get under {target_size_mb}MB"
            )
            aggressive_data, aggressive_method = self._compress_pdf_aggressive(compressed_data)

            if len(aggressive_data) < len(compressed_data):
                return aggressive_data, f"{method}+{aggressive_method}"
            else:
                logger.warning("Aggressive compression did not reduce size further")

        return compressed_data, method

    def _compress_pdf_ghostscript(self, pdf_data: bytes) -> Tuple[bytes, str]:
        """Compress PDF using Ghostscript.

        Args:
        ----
            pdf_data: Original PDF bytes

        Returns:
        -------
            Tuple of (compressed_data, method_name)

        """
        # Create temporary files for input and output
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as input_file:
            input_file.write(pdf_data)
            input_path = input_file.name

        output_path = input_path + ".compressed.pdf"

        try:
            # Ghostscript command for PDF compression
            # Quality presets: screen (72dpi), ebook (150dpi), printer (300dpi), prepress (300dpi, color preserved)
            gs_command = [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                f"-dPDFSETTINGS=/{self.pdf_quality}",
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                f"-sOutputFile={output_path}",
                input_path,
            ]

            subprocess.run(
                gs_command,
                capture_output=True,
                timeout=300,  # 5 minute timeout
                check=True,
            )

            # Read compressed PDF
            with open(output_path, "rb") as f:
                compressed_data = f.read()

            # Verify the compressed version is smaller, otherwise use original
            if len(compressed_data) >= len(pdf_data):
                logger.warning("Ghostscript compression resulted in larger file, using original")
                compressed_data = pdf_data

            return compressed_data, f"ghostscript-{self.pdf_quality}"

        except subprocess.TimeoutExpired:
            logger.error("Ghostscript compression timed out")
            return pdf_data, "ghostscript-timeout"
        except subprocess.CalledProcessError as e:
            logger.error(f"Ghostscript compression failed: {e.stderr.decode()}")
            return pdf_data, "ghostscript-failed"
        finally:
            # Clean up temporary files
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)

    def _compress_pdf_pypdf2(self, pdf_data: bytes) -> Tuple[bytes, str]:
        """Compress PDF using PyPDF2 (basic compression fallback).

        Args:
        ----
            pdf_data: Original PDF bytes

        Returns:
        -------
            Tuple of (compressed_data, method_name)

        """
        try:
            from pypdf import PdfReader, PdfWriter

            # Read PDF
            pdf_reader = PdfReader(io.BytesIO(pdf_data))
            pdf_writer = PdfWriter()

            # Copy pages and compress
            for page in pdf_reader.pages:
                page.compress_content_streams()
                pdf_writer.add_page(page)

            # Write to bytes
            output_stream = io.BytesIO()
            pdf_writer.write(output_stream)
            compressed_data = output_stream.getvalue()

            # Verify the compressed version is smaller
            if len(compressed_data) >= len(pdf_data):
                logger.warning("PyPDF2 compression resulted in larger file, using original")
                return pdf_data, "pypdf2-skipped"

            return compressed_data, "pypdf2"

        except Exception as e:
            logger.error(f"PyPDF2 compression failed: {e}")
            return pdf_data, "pypdf2-failed"

    def _compress_pdf_aggressive(self, pdf_data: bytes) -> Tuple[bytes, str]:
        """Aggressively compress PDF by converting to images and back.
        
        This is a last-resort method for very large PDFs that need to fit
        under a size limit (e.g., 50MB Supabase limit).
        
        Args:
        ----
            pdf_data: Original PDF bytes
            
        Returns:
        -------
            Tuple of (compressed_data, method_name)

        """
        if not PIL_AVAILABLE:
            logger.warning("Pillow not available for aggressive PDF compression")
            return pdf_data, "pillow-unavailable"

        try:
            import fitz  # PyMuPDF

            # Open PDF
            doc = fitz.open(stream=pdf_data, filetype="pdf")

            # Convert pages to images at reduced resolution
            images = []
            dpi = 100  # Lower DPI for aggressive compression

            for page_num in range(len(doc)):
                page = doc[page_num]
                # Render page to pixmap
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)

            doc.close()

            # Create new PDF from images
            if images:
                output = io.BytesIO()
                images[0].save(
                    output,
                    format="PDF",
                    save_all=True,
                    append_images=images[1:] if len(images) > 1 else [],
                    quality=70,
                    optimize=True
                )
                compressed_data = output.getvalue()

                if len(compressed_data) < len(pdf_data):
                    return compressed_data, "pymupdf-aggressive"

            return pdf_data, "pymupdf-skipped"

        except ImportError:
            logger.warning("PyMuPDF (fitz) not available for aggressive compression")
            return pdf_data, "pymupdf-unavailable"
        except Exception as e:
            logger.error(f"Aggressive PDF compression failed: {e}")
            return pdf_data, "pymupdf-failed"

    def _compress_image(self, image_data: bytes, content_type: str) -> Tuple[bytes, str]:
        """Compress an image using Pillow.

        Args:
        ----
            image_data: Original image bytes
            content_type: MIME type of the image

        Returns:
        -------
            Tuple of (compressed_data, method_name)

        """
        if not PIL_AVAILABLE:
            logger.warning("Pillow not available for image compression")
            return image_data, "pillow-unavailable"

        try:
            # Open image
            img = Image.open(io.BytesIO(image_data))

            # Determine output format
            if "png" in content_type.lower():
                output_format = "PNG"
                optimize_params = {"optimize": True}
            else:
                # Convert to JPEG for maximum compression
                output_format = "JPEG"
                optimize_params = {
                    "quality": self.image_quality,
                    "optimize": True,
                }

                # Convert RGBA to RGB for JPEG
                if img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                    img = background

            # Compress image
            output_stream = io.BytesIO()
            img.save(output_stream, format=output_format, **optimize_params)
            compressed_data = output_stream.getvalue()

            # Verify the compressed version is smaller
            if len(compressed_data) >= len(image_data):
                logger.warning("Image compression resulted in larger file, using original")
                return image_data, f"pillow-{output_format.lower()}-skipped"

            return compressed_data, f"pillow-{output_format.lower()}"

        except Exception as e:
            logger.error(f"Image compression failed: {e}")
            return image_data, "pillow-failed"


# Global instance with default settings from config
_compression_service: Optional[FileCompressionService] = None


def get_compression_service() -> FileCompressionService:
    """Get or create the global compression service instance.

    Returns
    -------
        FileCompressionService instance configured from settings

    """
    global _compression_service
    if _compression_service is None:
        # Get settings from config (with fallback defaults)
        threshold_mb = getattr(settings, "compression_threshold_mb", 10.0)
        pdf_quality = getattr(settings, "pdf_compression_quality", "ebook")
        image_quality = getattr(settings, "image_compression_quality", 85)

        _compression_service = FileCompressionService(
            compression_threshold_mb=threshold_mb,
            pdf_quality=pdf_quality,
            image_quality=image_quality,
        )

    return _compression_service
