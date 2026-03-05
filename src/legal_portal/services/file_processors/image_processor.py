from __future__ import annotations

import mimetypes
import os
from io import BytesIO

from PIL import Image

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# Try to import pytesseract, but make it optional
# OCR won't work in serverless environments without the Tesseract binary
try:
    import pytesseract

    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    logger.info("pytesseract not available (optional — requires Tesseract binary). OCR disabled; GPT-4o Vision fallback used.")


async def process_image(
    file_path: str,
    document_type: DocumentType,
    original_filename: str,
    progress_callback=None,
) -> ProcessedDocument:
    """Process an image file by extracting text using OCR from a given path."""
    logger.debug(f"Processing Image: {original_filename}")

    text_content = ""

    try:
        if HAS_OCR:
            with open(file_path, "rb") as f:
                image = Image.open(BytesIO(f.read()))
                # Convert image to grayscale for better OCR results
                image = image.convert("L")
                text_content = pytesseract.image_to_string(image)
            logger.info(f"Successfully extracted text from {original_filename}")
        else:
            logger.warning(f"OCR not available - skipping text extraction for {original_filename}")
            text_content = "[Image - OCR not available in this environment]"
    except Exception as e:
        logger.error(f"Error processing image {original_filename}: {e}")
        text_content = f"Error extracting text from {original_filename}."

    content_type, _ = mimetypes.guess_type(file_path)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    logger.info(f"✅ Fixed: Created FileMetadata for {original_filename}, size: {file_size}")

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.IMAGE,
        metadata=file_metadata,
    )
