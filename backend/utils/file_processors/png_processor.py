from __future__ import annotations

import mimetypes
import os
from io import BytesIO

import pytesseract
from PIL import Image

from backend.utils.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from backend_logic.utils.logging_config import get_module_logger


logger = get_module_logger(__name__)


async def process_png(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """
    Processes a PNG file by extracting text using OCR with PNG-specific optimizations.
    
    PNG-specific features:
    - Handles transparency channels properly
    - Optimized for lossless compression artifacts
    - Enhanced preprocessing for crisp text
    """
    logger.debug(f"Processing PNG: {original_filename}")

    text_content = ""

    try:
        with open(file_path, "rb") as f:
            image = Image.open(BytesIO(f.read()))
            
            # PNG-specific preprocessing
            # Handle transparency by converting RGBA to RGB with white background
            if image.mode in ("RGBA", "LA"):
                # Create a white background image
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "RGBA":
                    background.paste(image, mask=image.split()[-1])  # Use alpha channel as mask
                else:  # LA mode
                    background.paste(image.convert("RGB"))
                image = background
            
            # Convert to grayscale for better OCR results on PNG
            image = image.convert("L")
            
            # PNG-specific enhancement: sharpen for crisp text
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.2)  # Slight sharpening
            
            # OCR configuration optimized for PNG images
            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?@#$%^&*()_+-=[]{}|;:"\<>/`~'
            text_content = pytesseract.image_to_string(image, config=custom_config)
            
        logger.info(f"Successfully extracted text from PNG {original_filename}")
    except Exception as e:
        logger.error(f"Error processing PNG {original_filename}: {e}")
        text_content = f"Error extracting text from PNG {original_filename}."

    content_type, _ = mimetypes.guess_type(file_path)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    logger.info(
        f"✅ Created FileMetadata for PNG {original_filename}, size: {file_size}"
    )

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.PNG,
        metadata=file_metadata,
    )
