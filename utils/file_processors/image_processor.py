from __future__ import annotations

import mimetypes
from io import BytesIO

import pytesseract
from PIL import Image

from utils.data_models import DocumentType, FileType, ProcessedDocument
from utils.logging_config import setup_logging


logger = setup_logging("image_processor")


async def process_image(
    file_path: str, document_type: DocumentType, original_filename: str
) -> ProcessedDocument:
    """
    Processes an image file by extracting text using OCR from a given path.
    """
    logger.debug(f"Processing Image: {original_filename}")

    text_content = ""

    try:
        with open(file_path, "rb") as f:
            image = Image.open(BytesIO(f.read()))
            # Convert image to grayscale for better OCR results
            image = image.convert("L")
            text_content = pytesseract.image_to_string(image)
            logger.info(f"Successfully extracted text from {original_filename}")
    except Exception as e:
        logger.error(f"Error processing image {original_filename}: {e}")
        text_content = f"Error extracting text from {original_filename}."

    content_type, _ = mimetypes.guess_type(file_path)

    return ProcessedDocument(
        file_name=original_filename,
        content=text_content,
        document_type=document_type,
        file_type=FileType.IMAGE,
        metadata={"content_type": content_type},
    )
