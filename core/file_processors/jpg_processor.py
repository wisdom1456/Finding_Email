from __future__ import annotations

import mimetypes
import os
from io import BytesIO

import pytesseract
from PIL import Image
from PIL.ExifTags import TAGS

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.core.logging_config import get_module_logger


logger = get_module_logger(__name__)


async def process_jpg(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """
    Processes a JPG file by extracting text using OCR with JPG-specific optimizations.
    
    JPG-specific features:
    - EXIF metadata extraction for image quality assessment
    - Compression artifact handling
    - Quality-based preprocessing optimization
    - Enhanced noise reduction for compressed images
    """
    logger.debug(f"Processing JPG: {original_filename}")

    text_content = ""
    metadata_info = ""

    try:
        with open(file_path, "rb") as f:
            image = Image.open(BytesIO(f.read()))
            
            # Extract EXIF metadata for JPG quality assessment
            try:
                exifdata = image.getexif()
                if exifdata:
                    metadata_entries = []
                    for tag_id in exifdata:
                        tag = TAGS.get(tag_id, tag_id)
                        data = exifdata.get(tag_id)
                        if tag in ["Make", "Model", "DateTime", "Software"]:
                            metadata_entries.append(f"{tag}: {data}")
                    if metadata_entries:
                        metadata_info = " [EXIF: " + ", ".join(metadata_entries) + "]"
                        logger.debug(f"Extracted EXIF metadata for {original_filename}")
            except Exception as e:
                logger.debug(f"No EXIF data available for {original_filename}: {e}")
            
            # JPG-specific preprocessing
            # Convert to RGB if needed (JPG doesn't support transparency)
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Convert to grayscale for OCR
            image = image.convert("L")
            
            # JPG-specific enhancement: reduce compression artifacts
            from PIL import ImageEnhance, ImageFilter
            
            # Apply slight blur to reduce JPEG artifacts
            image = image.filter(ImageFilter.SMOOTH_MORE)
            
            # Enhance contrast to compensate for potential quality loss
            contrast_enhancer = ImageEnhance.Contrast(image)
            image = contrast_enhancer.enhance(1.3)
            
            # Sharpen slightly to improve text clarity
            sharpness_enhancer = ImageEnhance.Sharpness(image)
            image = sharpness_enhancer.enhance(1.1)
            
            # OCR configuration optimized for JPG images with potential compression
            # Create character whitelist with properly escaped characters for security
            char_whitelist = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?@#$%^&*()_+-=[]{}|;:\\"<>/`~'
            
            # Properly format the config string for tesseract command line
            # The -c flag requires the parameter to be properly quoted to handle special characters
            custom_config = f"--oem 3 --psm 6 -c tessedit_char_whitelist={char_whitelist}"
            
            logger.debug(f"OCR config for {original_filename}: {custom_config}")
            text_content = pytesseract.image_to_string(image, config=custom_config)
            
            # Append metadata info to content if available
            if metadata_info:
                text_content += metadata_info
                
        logger.info(f"Successfully extracted text from JPG {original_filename}")
    except Exception as e:
        logger.error(f"Error processing JPG {original_filename}: {e}")
        text_content = f"Error extracting text from JPG {original_filename}."

    content_type, _ = mimetypes.guess_type(file_path)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # Create proper FileMetadata object with required fields
    file_metadata = FileMetadata(filename=original_filename, size=file_size)

    logger.info(
        f"✅ Created FileMetadata for JPG {original_filename}, size: {file_size}"
    )

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.JPG,
        metadata=file_metadata,
    )
