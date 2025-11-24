"""Utility functions for file compression operations.

Provides helper functions for checking file sizes, estimating compression
ratios, and formatting compression-related information.
"""

from __future__ import annotations

from typing import Tuple


def get_file_size_mb(file_data: bytes) -> float:
    """Get file size in megabytes.

    Args:
    ----
        file_data: File bytes

    Returns:
    -------
        File size in MB

    """
    return len(file_data) / (1024 * 1024)


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
    ----
        size_bytes: Size in bytes

    Returns:
    -------
        Formatted string (e.g., "15.5MB", "2.3GB")

    """
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f}GB"


def estimate_compression_ratio(content_type: str, file_size_mb: float) -> float:
    """Estimate potential compression ratio for a file.

    Args:
    ----
        content_type: MIME type of the file
        file_size_mb: Current file size in MB

    Returns:
    -------
        Estimated compression ratio (0.0-1.0, where lower is better)

    Examples:
    --------
        >>> estimate_compression_ratio("application/pdf", 50)
        0.5  # Expect ~50% size reduction

    """
    content_type_lower = content_type.lower()

    # PDFs: Generally 30-60% size reduction depending on content
    if "pdf" in content_type_lower:
        # Larger PDFs often compress better
        if file_size_mb > 50:
            return 0.4  # ~60% reduction
        elif file_size_mb > 20:
            return 0.5  # ~50% reduction
        else:
            return 0.6  # ~40% reduction

    # Images: Highly variable based on format and content
    elif "image" in content_type_lower:
        if "png" in content_type_lower:
            return 0.6  # PNG compression is more conservative
        elif any(fmt in content_type_lower for fmt in ["jpeg", "jpg"]):
            return 0.7  # Already compressed, less gains
        else:
            return 0.5  # Other image formats

    # Already compressed formats (minimal gains expected)
    elif any(fmt in content_type_lower for fmt in ["zip", "gzip", "bzip2", "7z", "rar", "tar.gz"]):
        return 0.95  # ~5% reduction at best

    # Default: assume moderate compression
    else:
        return 0.7


def is_compressible_type(filename: str, content_type: str) -> bool:
    """Determine if a file type is suitable for compression.

    Args:
    ----
        filename: Original filename
        content_type: MIME type

    Returns:
    -------
        True if file can be compressed

    """
    content_type_lower = content_type.lower()
    filename_lower = filename.lower()

    # Compressible types
    compressible_types = [
        "pdf",
        "image",
        "jpeg",
        "jpg",
        "png",
        "tiff",
        "tif",
        "bmp",
    ]

    # Check content type
    if any(ctype in content_type_lower for ctype in compressible_types):
        return True

    # Check file extension
    compressible_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"]
    if any(filename_lower.endswith(ext) for ext in compressible_extensions):
        return True

    return False


def calculate_size_reduction(original_size: int, compressed_size: int) -> Tuple[float, float]:
    """Calculate size reduction metrics.

    Args:
    ----
        original_size: Original file size in bytes
        compressed_size: Compressed file size in bytes

    Returns:
    -------
        Tuple of (reduction_percentage, compression_ratio)

    Examples:
    --------
        >>> calculate_size_reduction(100, 60)
        (40.0, 0.6)  # 40% reduction, 0.6 ratio

    """
    if original_size == 0:
        return 0.0, 1.0

    compression_ratio = compressed_size / original_size
    reduction_percentage = (1 - compression_ratio) * 100

    return reduction_percentage, compression_ratio


def get_compression_method_description(method: str) -> str:
    """Get human-readable description of compression method.

    Args:
    ----
        method: Compression method identifier

    Returns:
    -------
        Human-readable description

    """
    method_descriptions = {
        "ghostscript-screen": "Ghostscript (72dpi, screen quality)",
        "ghostscript-ebook": "Ghostscript (150dpi, ebook quality)",
        "ghostscript-printer": "Ghostscript (300dpi, printer quality)",
        "ghostscript-prepress": "Ghostscript (300dpi, prepress quality)",
        "pypdf2": "PyPDF2 (basic compression)",
        "pillow-jpeg": "Pillow (JPEG optimization)",
        "pillow-png": "Pillow (PNG optimization)",
        "none": "No compression (below threshold)",
        "unsupported": "File type not supported for compression",
    }

    # Handle variations with "-skipped" or "-failed" suffix
    base_method = method.split("-")[0:2]
    base_method_key = "-".join(base_method)

    if method in method_descriptions:
        return method_descriptions[method]
    elif base_method_key in method_descriptions:
        return method_descriptions[base_method_key]
    elif "failed" in method:
        return f"Compression failed ({method})"
    elif "timeout" in method:
        return f"Compression timed out ({method})"
    elif "skipped" in method:
        return f"Compression skipped ({method})"
    else:
        return method


def should_compress_file(
    file_size_bytes: int,
    content_type: str,
    filename: str,
    threshold_bytes: int,
) -> Tuple[bool, str]:
    """Determine if a file should be compressed.

    Args:
    ----
        file_size_bytes: File size in bytes
        content_type: MIME type
        filename: Original filename
        threshold_bytes: Compression threshold in bytes

    Returns:
    -------
        Tuple of (should_compress, reason)

    """
    # Check if file is below threshold
    if file_size_bytes <= threshold_bytes:
        threshold_mb = threshold_bytes / (1024 * 1024)
        file_size_mb = file_size_bytes / (1024 * 1024)
        return False, f"File size ({file_size_mb:.1f}MB) below threshold ({threshold_mb:.0f}MB)"

    # Check if file type is compressible
    if not is_compressible_type(filename, content_type):
        return False, f"File type not suitable for compression ({content_type})"

    # File should be compressed
    file_size_mb = file_size_bytes / (1024 * 1024)
    return True, f"File size ({file_size_mb:.1f}MB) exceeds threshold, compression recommended"


def format_compression_summary(
    files_compressed: int,
    total_original_size: int,
    total_compressed_size: int,
) -> str:
    """Format a compression summary message.

    Args:
    ----
        files_compressed: Number of files compressed
        total_original_size: Total original size in bytes
        total_compressed_size: Total compressed size in bytes

    Returns:
    -------
        Formatted summary string

    """
    if files_compressed == 0:
        return "No files were compressed"

    reduction_pct, ratio = calculate_size_reduction(total_original_size, total_compressed_size)
    original_mb = total_original_size / (1024 * 1024)
    compressed_mb = total_compressed_size / (1024 * 1024)
    saved_mb = (total_original_size - total_compressed_size) / (1024 * 1024)

    plural = "s" if files_compressed > 1 else ""
    return (
        f"{files_compressed} file{plural} compressed: "
        f"{original_mb:.1f}MB → {compressed_mb:.1f}MB "
        f"({reduction_pct:.1f}% reduction, {saved_mb:.1f}MB saved)"
    )


# Export public interface
__all__ = [
    "calculate_size_reduction",
    "estimate_compression_ratio",
    "format_compression_summary",
    "format_file_size",
    "get_compression_method_description",
    "get_file_size_mb",
    "is_compressible_type",
    "should_compress_file",
]
