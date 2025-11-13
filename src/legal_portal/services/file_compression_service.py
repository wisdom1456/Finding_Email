"""File compression service for handling large PDF and image files."""

import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# Define a constant for the large file threshold (10 MB)
LARGE_FILE_THRESHOLD_BYTES = 10 * 1024 * 1024


class FileCompressionService:
    """A service to compress large PDF and image files before analysis."""

    def is_ghostscript_installed(self) -> bool:
        """Check if Ghostscript is available in the system's PATH."""
        return shutil.which("gs") is not None

    def compress_pdf(self, input_path: str, output_path: str, quality: str = "ebook") -> bool:
        """Compresses a PDF using Ghostscript.

        Args:
        ----
            input_path: The full path to the source PDF file.
            output_path: The full path where the compressed PDF will be saved.
            quality: The Ghostscript preset to use for compression.
                     Options: 'screen', 'ebook', 'printer', 'prepress', 'default'.

        Returns:
        -------
            True if compression was successful, False otherwise.

        """
        if not self.is_ghostscript_installed():
            logger.warning("Ghostscript is not installed. PDF compression will be skipped.")
            return False

        command = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS=/{quality}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            input_path,
        ]

        try:
            logger.info(f"Compressing PDF: {Path(input_path).name}")
            subprocess.run(command, check=True, capture_output=True, text=True)
            logger.info(f"Successfully compressed PDF to {Path(output_path).name}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Ghostscript failed to compress PDF '{Path(input_path).name}'. Error: {e.stderr}")
            return False
        except FileNotFoundError:
            logger.error(
                "Ghostscript command 'gs' not found. Please ensure it is installed and in your system's PATH."
            )
            return False

    def compress_image(
        self,
        input_path: str,
        output_path: str,
        max_dimensions: tuple = (2048, 2048),
        quality: int = 85,
    ) -> bool:
        """Resizes and compresses an image using Pillow, converting to JPEG.

        Args:
        ----
            input_path: Full path to the source image.
            output_path: Full path to save the compressed image.
            max_dimensions: A tuple (width, height) for the maximum size.
            quality: The JPEG quality setting (1-95).

        Returns:
        -------
            True if successful, False otherwise.

        """
        try:
            logger.info(f"Compressing image: {Path(input_path).name}")
            with Image.open(input_path) as img:
                # Resize the image if it's larger than the max dimensions
                if img.width > max_dimensions[0] or img.height > max_dimensions[1]:
                    img.thumbnail(max_dimensions, Image.Resampling.LANCZOS)

                # Convert to RGB if it has an alpha channel (like PNGs) to save as JPEG
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                img.save(
                    output_path,
                    "JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=True,
                )
            logger.info(f"Successfully compressed image to {Path(output_path).name}")
            return True
        except Exception as e:
            logger.error(f"Pillow failed to compress image '{Path(input_path).name}'. Error: {e}")
            return False

    def process_file(self, input_path: str) -> str:
        """Process a file, compress it in-place if large enough, and return the final path.

        If a file is compressed, the original is replaced by the compressed version.
        If compression fails or is not needed, the original file path is returned.

        Args:
        ----
            input_path: The full path to the file to process.

        Returns:
        -------
            The path to the processed (potentially compressed) file.

        """
        file_path = Path(input_path)
        if not file_path.exists():
            logger.warning(f"File not found for processing: {input_path}")
            return input_path

        file_size = file_path.stat().st_size
        if file_size < LARGE_FILE_THRESHOLD_BYTES:
            return input_path  # No compression needed

        file_extension = file_path.suffix.lower()
        temp_output_path = file_path.with_suffix(f".compressed{file_extension}")

        success = False
        if file_extension == ".pdf":
            success = self.compress_pdf(str(file_path), str(temp_output_path))
        elif file_extension in [".png", ".jpg", ".jpeg"]:
            # All compressed images become JPEGs for consistency and size benefits
            temp_output_path = file_path.with_suffix(".compressed.jpg")
            success = self.compress_image(str(file_path), str(temp_output_path))

        if success:
            # On successful compression, replace the original with the compressed file
            try:
                original_size_mb = round(file_size / (1024 * 1024), 2)
                compressed_size_mb = round(temp_output_path.stat().st_size / (1024 * 1024), 2)
                logger.info(
                    f"Compression successful for {file_path.name}. "
                    f"Original: {original_size_mb} MB -> Compressed: {compressed_size_mb} MB"
                )
                os.remove(input_path)
                os.rename(temp_output_path, input_path)

            except OSError as e:
                logger.error(f"Failed to replace original file with compressed version. Error: {e}")
                # If replacement fails, cleanup the compressed file and use the original
                if temp_output_path.exists():
                    os.remove(temp_output_path)
                return input_path

        # If compression was not attempted or failed, return the original path
        return input_path
